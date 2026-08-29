#!/usr/bin/env python3
"""Fix HA recorder units for outdoor weather sensors mislabeled as °C.

First hours of the HA showcase stored wind/humidity/pressure LTS as
temperature. Values are real; only statistics_meta unit/unit_class is wrong.
That creates four Settings → Repairs issues (units_changed_sensor.pogoda_*).

Must run on elion with HA stopped. Does not copy Nord code.
"""
from __future__ import annotations

import json
from pathlib import Path

DB = Path("/var/lib/homeassistant/home-assistant_v2.db")
ISSUES = Path("/var/lib/homeassistant/.storage/repairs.issue_registry")

# unit_class must match homeassistant.components.sensor.recorder._get_unit_class
# for the live entity device_class + unit (humidity % → unitless).
FIXES = (
    ("sensor.pogoda_veter_skorost", "m/s", "speed"),
    ("sensor.pogoda_veter_poryvy", "m/s", "speed"),
    ("sensor.pogoda_vlazhnost", "%", "unitless"),
    ("sensor.pogoda_davlenie", "mmHg", "pressure"),
)
ISSUE_IDS = {f"units_changed_{sid}" for sid, _, _ in FIXES}


def main() -> None:
    if not DB.exists():
        raise SystemExit(f"missing {DB}")
    import sqlite3

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    for statistic_id, unit, unit_class in FIXES:
        row = con.execute(
            "SELECT id, unit_of_measurement, unit_class FROM statistics_meta WHERE statistic_id=?",
            (statistic_id,),
        ).fetchone()
        if row is None:
            print(f"skip missing {statistic_id}")
            continue
        print(
            f"{statistic_id}: {row['unit_of_measurement']}/{row['unit_class']} -> {unit}/{unit_class}"
        )
        con.execute(
            "UPDATE statistics_meta SET unit_of_measurement=?, unit_class=? WHERE id=?",
            (unit, unit_class, row["id"]),
        )
    con.commit()
    con.close()

    if ISSUES.exists():
        payload = json.loads(ISSUES.read_text(encoding="utf-8"))
        before = payload["data"]["issues"]
        after = [issue for issue in before if issue.get("issue_id") not in ISSUE_IDS]
        payload["data"]["issues"] = after
        ISSUES.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"repairs: {len(before)} -> {len(after)}")


if __name__ == "__main__":
    main()
