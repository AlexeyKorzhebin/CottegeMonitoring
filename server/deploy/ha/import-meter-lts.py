#!/usr/bin/env python3
"""Backfill HA recorder long-term statistics for sensor.schetchik from Timescale.

Energy dashboard reads hourly `statistics.sum` deltas, not live entity state.
New sensors have no August history; this script inserts one hour row per Moscow
hour from the first August reading, with sum = reading - baseline.

Must run on elion with HA stopped. Does not copy Nord code.
"""
from __future__ import annotations

import sqlite3
import subprocess
import time
from pathlib import Path

DB = Path("/var/lib/homeassistant/home-assistant_v2.db")
STATISTIC_ID = "sensor.schetchik"
PSQL = [
    "sudo",
    "-u",
    "postgres",
    "psql",
    "-d",
    "cottage_monitoring",
    "-t",
    "-A",
    "-F",
    "\t",
    "-c",
]
SQL = r"""
SELECT extract(epoch FROM hour_start)::bigint,
       reading
FROM (
  SELECT DISTINCT ON (date_trunc('hour', ts AT TIME ZONE 'Europe/Moscow'))
    date_trunc('hour', ts AT TIME ZONE 'Europe/Moscow') AT TIME ZONE 'Europe/Moscow' AS hour_start,
    (value #>> '{}')::double precision AS reading
  FROM events
  WHERE house_id = 'house'
    AND ga = '32/1/59'
    AND ts >= TIMESTAMPTZ '2026-08-01 00:00:00 Europe/Moscow'
    AND ts < now()
  ORDER BY date_trunc('hour', ts AT TIME ZONE 'Europe/Moscow'), ts DESC
) x
ORDER BY hour_start;
"""


def hours() -> list[tuple[float, float]]:
    out = subprocess.check_output([*PSQL, SQL], text=True)
    rows: list[tuple[float, float]] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        ts_s, val_s = line.split("\t")
        rows.append((float(ts_s), float(val_s)))
    if len(rows) < 24:
        raise SystemExit(f"too few hourly rows: {len(rows)}")
    return rows


def main() -> None:
    if not DB.is_file():
        raise SystemExit(f"missing {DB}")
    rows = hours()
    baseline = rows[0][1]
    now = time.time()
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    meta = cur.execute(
        "SELECT id FROM statistics_meta WHERE statistic_id = ?", (STATISTIC_ID,)
    ).fetchone()
    if meta is None:
        raise SystemExit(f"no statistics_meta for {STATISTIC_ID}")
    metadata_id = int(meta[0])
    max_id = cur.execute("SELECT COALESCE(MAX(id), 0) FROM statistics").fetchone()[0]
    cur.execute("DELETE FROM statistics_short_term WHERE metadata_id = ?", (metadata_id,))
    cur.execute("DELETE FROM statistics WHERE metadata_id = ?", (metadata_id,))
    payload = []
    for i, (start_ts, reading) in enumerate(rows, start=1):
        payload.append(
            (
                int(max_id) + i,
                now,
                metadata_id,
                float(start_ts),
                reading,
                reading - baseline,
            )
        )
    cur.executemany(
        """
        INSERT INTO statistics (
          id, created, created_ts, metadata_id, start, start_ts,
          mean, mean_weight, min, max, last_reset, last_reset_ts, state, sum
        ) VALUES (?, '', ?, ?, '', ?, NULL, NULL, NULL, NULL, '', NULL, ?, ?)
        """,
        payload,
    )
    # Seed 5-minute table with the last hourly sum so the next compile continues
    # from ~500 kWh instead of resetting the zero point to the live meter reading.
    last_start, last_state, last_sum = payload[-1][3], payload[-1][4], payload[-1][5]
    max_short = cur.execute(
        "SELECT COALESCE(MAX(id), 0) FROM statistics_short_term"
    ).fetchone()[0]
    cur.execute(
        """
        INSERT INTO statistics_short_term (
          id, created, created_ts, metadata_id, start, start_ts,
          mean, mean_weight, min, max, last_reset, last_reset_ts, state, sum
        ) VALUES (?, '', ?, ?, '', ?, NULL, NULL, NULL, NULL, '', NULL, ?, ?)
        """,
        (int(max_short) + 1, now, metadata_id, last_start, last_state, last_sum),
    )
    conn.commit()
    conn.close()
    print(
        f"inserted {len(payload)} hourly rows for {STATISTIC_ID}; "
        f"baseline={baseline:.4f} last_state={last_state:.4f} last_sum={last_sum:.4f}"
    )


if __name__ == "__main__":
    main()
