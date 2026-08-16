#!/usr/bin/env python3
"""Generate CottageMonitoring Grafana dashboards (JSON) for file provisioning."""

from __future__ import annotations

import json
from pathlib import Path

DS = {"type": "postgres", "uid": "cottage-monitoring-pg"}
OUT = Path(__file__).resolve().parent / "dashboards"

NUM = "(e.value #>> '{}')::double precision"
BOOL01 = "CASE WHEN lower(e.value #>> '{}') IN ('true','t','1') THEN 1 ELSE 0 END"
CS_NUM = "(cs.value #>> '{}')::double precision"
CS_BOOL = "CASE WHEN lower(cs.value #>> '{}') IN ('true','t','1') THEN 1 ELSE 0 END"
CS_JOIN = "replace(cs.ga, '-', '/')"

# Instant lights: status 1/2/* (wall switches), not stale control 1/1/* (R-017).
LIGHTS_NOW_DESC = (
    "Жёлтая лампа = горит, тёмная = выключен. "
    "Источник: status 1/2/* (факт с выключателя), не control 1/1/*."
)
LIGHTS_HISTORY_DESC = (
    "Строб: жёлтый = ВКЛ, тёмный = выкл. Ширина полосы = сколько горел. "
    "Наведите курсор — длительность интервала. Сырые events, без группировки по интервалу."
)
LIGHT_ICON_ON = (
    "https://elion.black-castle.ru/grafana/public/img/cottage/light-on-128.png"
)
LIGHT_ICON_OFF = (
    "https://elion.black-castle.ru/grafana/public/img/cottage/light-off-128.png"
)
# Same GAs as history charts. Canvas cannot spawn elements from query rows.
LIGHTS_1F = [
    ("Гостиная", "1/2/6"),
    ("Кухня", "1/2/7"),
    ("Спальня", "1/2/4"),
    ("Холл", "1/2/3"),
    ("Тамбур", "1/2/2"),
    ("Серверная", "1/2/9"),
    ("Ванная", "1/2/8"),
    ("Торшер", "1/2/18"),
    ("Подсветка кухня", "1/2/19"),
]
LIGHTS_2F = [
    ("Настя", "1/2/12"),
    ("Тим", "1/2/13"),
    ("Кабинет", "1/2/14"),
    ("Холл 2эт", "1/2/15"),
    ("Гостевая", "1/2/11"),
    ("Ванна 2эт", "1/2/16"),
    ("Чердак", "1/2/17"),
    ("Тайфайтер", "1/2/20"),
]
LIGHTS_OUT = [
    ("Крыльцо", "1/2/1"),
    ("Терраса", "1/2/5"),
    ("Балкон", "1/2/10"),
]

# Cross-links between cottage dashboards (root_url includes /grafana/).
DASH_LINKS = [
    {
        "title": "Overview",
        "type": "link",
        "url": "/grafana/d/cottage-overview/",
        "icon": "home",
        "keepTime": True,
        "targetBlank": False,
    },
    {
        "title": "Electricity",
        "type": "link",
        "url": "/grafana/d/cottage-energy/",
        "icon": "bolt",
        "keepTime": True,
        "targetBlank": False,
    },
    {
        "title": "Climate",
        "type": "link",
        "url": "/grafana/d/cottage-climate/",
        "icon": "cloud",
        "keepTime": True,
        "targetBlank": False,
    },
    {
        "title": "Lights",
        "type": "link",
        "url": "/grafana/d/cottage-lights/",
        "icon": "circle",
        "keepTime": True,
        "targetBlank": False,
    },
    {
        "title": "Batteries",
        "type": "link",
        "url": "/grafana/d/cottage-batteries/",
        "icon": "battery",
        "keepTime": True,
        "targetBlank": False,
    },
    {
        "title": "LM Load",
        "type": "link",
        "url": "/grafana/d/cottage-lm-load/",
        "icon": "heart-rate",
        "keepTime": True,
        "targetBlank": False,
    },
    {
        "title": "Все Cottage",
        "type": "dashboards",
        "tags": ["cottage"],
        "asDropdown": True,
        "includeVars": False,
        "keepTime": True,
        "targetBlank": False,
    },
]

NAV_MD = (
    "**Cottage:** "
    "[Overview](/grafana/d/cottage-overview/) · "
    "[Electricity](/grafana/d/cottage-energy/) · "
    "[Climate](/grafana/d/cottage-climate/) · "
    "[Lights](/grafana/d/cottage-lights/) · "
    "[Batteries](/grafana/d/cottage-batteries/) · "
    "[LM Load](/grafana/d/cottage-lm-load/)"
)

# Utility meter: consumption Total — kWh with 2 decimals (no SI→MWh scaling).
METER_TOTAL_GA = "32/1/59"
METER_SQL = f"""
SELECT cs.ts AS time,
  round({CS_NUM}::numeric, 2) AS value
FROM current_state cs
WHERE cs.house_id = 'house' AND {CS_JOIN} = '{METER_TOTAL_GA}'
""".strip()
METER_DESC = (
    "GA 32/1/59 energy_meter — consumption Total. "
    "Показания счётчика для ЖКХ, кВт·ч с точностью до 0.01."
)

_PANEL_ID = 0


def _next_id() -> int:
    global _PANEL_ID
    _PANEL_ID += 1
    return _PANEL_ID


def panel_common(title: str, ptype: str, x: int, y: int, w: int, h: int, **extra):
    p = {
        "id": _next_id(),
        "type": ptype,
        "title": title,
        "datasource": DS,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "targets": [],
    }
    p.update(extra)
    return p


def sql_target(ref: str, raw_sql: str, fmt: str = "time_series"):
    return {"refId": ref, "rawQuery": True, "format": fmt, "rawSql": raw_sql}


def nav_panel(y: int):
    p = panel_common("", "text", 0, y, 24, 2)
    p.pop("datasource", None)
    p["targets"] = []
    p["options"] = {
        "mode": "markdown",
        "content": NAV_MD,
    }
    p["transparent"] = True
    return p


def timeseries(title, x, y, w, h, sql, unit=None, fill_opacity=10, description=None):
    p = panel_common(title, "timeseries", x, y, w, h)
    p["targets"] = [sql_target("A", sql)]
    # Do NOT use $__timeGroupAlias(..., NULL) over long ranges — it can allocate
    # huge null arrays and crash the browser (RangeError: Invalid array length).
    # insertNulls = gap threshold in ms: break the line if points are farther apart.
    field_cfg = {
        "defaults": {
            "custom": {
                "fillOpacity": fill_opacity,
                "spanNulls": False,
                # Break line if gap between points > 2 days (shows multi-day outages
                # on long ranges without exploding arrays via SQL NULL gapfill).
                "insertNulls": 172800000,
                "lineInterpolation": "linear",
            }
        }
    }
    if unit:
        field_cfg["defaults"]["unit"] = unit
    p["fieldConfig"] = field_cfg
    p["options"] = {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
        "tooltip": {"mode": "multi", "sort": "none"},
    }
    if description:
        p["description"] = description
    return p


def stat(
    title,
    x,
    y,
    w,
    h,
    sql,
    unit=None,
    decimals=1,
    description=None,
    mappings=None,
    graph_mode="area",
    text_mode="auto",
    color_mode="value",
):
    p = panel_common(title, "stat", x, y, w, h)
    p["targets"] = [sql_target("A", sql, fmt="table")]
    defaults: dict = {
        "decimals": decimals,
        "color": {"mode": "thresholds"},
    }
    if unit:
        defaults["unit"] = unit
    if mappings:
        defaults["mappings"] = mappings
    p["fieldConfig"] = {"defaults": defaults}
    p["options"] = {
        "reduceOptions": {"calcs": ["lastNotNull"]},
        "colorMode": color_mode,
        "graphMode": graph_mode,
        "textMode": text_mode,
    }
    if description:
        p["description"] = description
    return p


def on_off_stat(title, x, y, w, h, sql, description=None):
    """Boolean 0/1 → ON/OFF with colors."""
    return stat(
        title,
        x,
        y,
        w,
        h,
        sql,
        decimals=0,
        description=description,
        graph_mode="none",
        text_mode="value",
        color_mode="background",
        mappings=[
            {
                "type": "value",
                "options": {
                    "0": {"text": "OFF", "color": "semi-dark-red", "index": 0},
                    "1": {"text": "ON", "color": "semi-dark-green", "index": 1},
                },
            }
        ],
    )


def _light_icon_sql(rooms: list[tuple[str, str]]) -> str:
    """One row, one URL column per room. Canvas Field mode needs named columns."""
    cols = []
    for name, ga in rooms:
        cols.append(
            f"""  MAX(CASE WHEN {CS_JOIN} = '{ga}' THEN
    CASE WHEN {CS_BOOL} = 1 THEN '{LIGHT_ICON_ON}' ELSE '{LIGHT_ICON_OFF}' END
  END) AS "{name}\""""
        )
    gas = ", ".join(f"'{ga}'" for _name, ga in rooms)
    return (
        "SELECT\n"
        + ",\n".join(cols)
        + f"\nFROM current_state cs\nWHERE cs.house_id = 'house'\n  AND {CS_JOIN} IN ({gas})"
    )


def _canvas_rect(*, name, left, top, width, height, image_field=None, text=None, text_size=12):
    el = {
        "name": name,
        "type": "rectangle",
        "constraint": {"horizontal": "left", "vertical": "top"},
        "placement": {
            "left": left,
            "top": top,
            "width": width,
            "height": height,
            "rotation": 0,
        },
        "background": {"color": {"fixed": "transparent"}},
        "border": {"width": 0},
        "connections": [],
        "config": {
            "align": "center",
            "valign": "middle",
            "color": {"fixed": "#C8C8C8"},
        },
    }
    if image_field:
        el["background"]["image"] = {"mode": "field", "field": image_field}
        el["background"]["size"] = "contain"
    if text is not None:
        el["config"]["text"] = {"mode": "fixed", "fixed": text}
        el["config"]["size"] = text_size
    return el


def light_tiles(title, x, y, w, h, rooms: list[tuple[str, str]], cols: int, description=None):
    """Canvas grid: PNG lamp tile + room caption. Stat cannot embed images."""
    icon = 88
    label_h = 22
    gap_x = 16
    gap_y = 10
    pad = 8
    elements = []
    for i, (name, _ga) in enumerate(rooms):
        col = i % cols
        row = i // cols
        left = pad + col * (icon + gap_x)
        top = pad + row * (icon + label_h + gap_y)
        elements.append(
            _canvas_rect(
                name=f"{name} icon",
                left=left,
                top=top,
                width=icon,
                height=icon,
                image_field=name,
            )
        )
        elements.append(
            _canvas_rect(
                name=f"{name} label",
                left=left,
                top=top + icon,
                width=icon,
                height=label_h,
                text=name,
                text_size=11,
            )
        )
    p = panel_common(title, "canvas", x, y, w, h)
    p["targets"] = [sql_target("A", _light_icon_sql(rooms), fmt="table")]
    p["options"] = {
        "inlineEditing": False,
        "showAdvancedTypes": True,
        "panZoom": False,
        "zoomToContent": True,
        "tooltip": {"mode": "none"},
        "root": {"name": "Element", "type": "frame", "elements": elements},
    }
    p["description"] = description or LIGHTS_NOW_DESC
    return p


def _light_history_sql(rooms: list[tuple[str, str]]) -> str:
    """Raw on/off events plus last state at range start (so the first strobe has duration)."""
    cases = " ".join(f"WHEN '{ga}' THEN '{name}'" for name, ga in rooms)
    gas = ", ".join(f"'{ga}'" for _name, ga in rooms)
    return f"""
WITH last_before AS (
  SELECT DISTINCT ON (e.ga)
    $__timeFrom()::timestamptz AS ts,
    e.ga,
    e.value
  FROM events e
  WHERE e.house_id = 'house'
    AND e.ga IN ({gas})
    AND e.ts < $__timeFrom()::timestamptz
  ORDER BY e.ga, e.ts DESC
),
in_range AS (
  SELECT e.ts, e.ga, e.value
  FROM events e
  WHERE e.house_id = 'house'
    AND e.ga IN ({gas})
    AND $__timeFilter(e.ts)
)
SELECT
  s.ts AS time,
  CASE WHEN lower(s.value #>> '{{}}') IN ('true','t','1') THEN 1 ELSE 0 END AS value,
  CASE s.ga {cases} END AS metric
FROM (
  SELECT ts, ga, value FROM last_before
  UNION ALL
  SELECT ts, ga, value FROM in_range
) s
ORDER BY time, metric
""".strip()


def light_history(title, x, y, w, h, rooms: list[tuple[str, str]]):
    """State timeline (strobe): yellow = on, dark = off, bar width = duration."""
    p = panel_common(title, "state-timeline", x, y, w, h)
    p["targets"] = [sql_target("A", _light_history_sql(rooms), fmt="time_series")]
    p["fieldConfig"] = {
        "defaults": {
            "decimals": 0,
            "custom": {
                "fillOpacity": 100,
                "lineWidth": 0,
                "spanNulls": True,
            },
            "color": {"mode": "thresholds"},
            "thresholds": {
                "mode": "absolute",
                "steps": [
                    {"color": "#3A3A3A", "value": None},
                    {"color": "#3A3A3A", "value": 0},
                    {"color": "#F5C400", "value": 1},
                ],
            },
            "mappings": [
                {
                    "type": "value",
                    "options": {
                        "0": {"text": "выкл", "color": "#3A3A3A", "index": 0},
                        "1": {"text": "ВКЛ", "color": "#F5C400", "index": 1},
                    },
                }
            ],
        }
    }
    p["options"] = {
        "mergeValues": True,
        "showValue": "never",
        "alignValue": "center",
        "rowHeight": 0.85,
        "legend": {
            "displayMode": "list",
            "placement": "bottom",
            "showLegend": True,
        },
        "tooltip": {"mode": "single", "sort": "none"},
        "perPage": 20,
    }
    p["description"] = LIGHTS_HISTORY_DESC
    return p


def heat_tiles(title, x, y, w, h, description=None):
    """Glanceable floor-relay grid: orange = heating, dark = off. Status 1/5/*."""
    sql = f"""
SELECT
  now() AS time,
  CASE WHEN {CS_BOOL} = 1 THEN 1 ELSE 0 END AS value,
  replace(replace(o.name, 'ТП - ', ''), ' :status', '') AS metric
FROM objects o
JOIN current_state cs ON cs.house_id = o.house_id AND {CS_JOIN} = o.ga
WHERE o.house_id = 'house'
  AND o.tags LIKE '%heat%'
  AND o.tags LIKE '%status%'
  AND o.tags NOT LIKE '%control%'
ORDER BY time, metric
""".strip()
    p = panel_common(title, "stat", x, y, w, h)
    p["targets"] = [sql_target("A", sql, fmt="time_series")]
    p["fieldConfig"] = {
        "defaults": {
            "decimals": 0,
            "color": {"mode": "thresholds"},
            "thresholds": {
                "mode": "absolute",
                "steps": [
                    {"color": "#3A3A3A", "value": None},
                    {"color": "#3A3A3A", "value": 0},
                    {"color": "#E85D04", "value": 1},
                ],
            },
            "mappings": [
                {
                    "type": "value",
                    "options": {
                        "0": {"text": "○", "index": 0},
                        "1": {"text": "греет", "index": 1},
                    },
                }
            ],
        }
    }
    p["options"] = {
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        "orientation": "auto",
        "textMode": "value_and_name",
        "colorMode": "background",
        "graphMode": "none",
        "justifyMode": "center",
        "wideLayout": True,
        "showPercentChange": False,
    }
    p["description"] = description or "Оранжевая плитка = реле зоны греет. Статусы 1/5/*."
    return p


def table(title, x, y, w, h, sql, description=None, field_config=None):
    p = panel_common(title, "table", x, y, w, h)
    p["targets"] = [sql_target("A", sql, fmt="table")]
    if description:
        p["description"] = description
    if field_config:
        p["fieldConfig"] = field_config
    return p


def meter_stat(title, x, y, w, h):
    """Counter for utilities: e.g. 67126.65 kWh (never auto-scale to MWh)."""
    return stat(
        title,
        x,
        y,
        w,
        h,
        METER_SQL,
        unit="suffix:kWh",
        decimals=2,
        graph_mode="none",
        text_mode="value",
        description=METER_DESC,
    )


def row(title, y):
    return {
        "id": _next_id(),
        "type": "row",
        "title": title,
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": y},
        "collapsed": False,
    }


def dashboard(title: str, uid: str, panels: list, tags: list[str], refresh="30s"):
    # Default auto-refresh 30s (instant tiles + most graphs). Batteries / LM Load use 1m.
    for i, p in enumerate(panels, start=1):
        p["id"] = i
    return {
        "id": None,
        "uid": uid,
        "title": title,
        "tags": tags,
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 1,
        "editable": True,
        "graphTooltip": 1,
        "refresh": refresh,
        "time": {"from": "now-24h", "to": "now"},
        "annotations": {"list": []},
        "links": DASH_LINKS,
        "panels": panels,
    }


def overview():
    global _PANEL_ID
    _PANEL_ID = 0
    panels = []
    y = 0
    panels.append(nav_panel(y))
    y += 2
    panels.append(row("Сейчас", y))
    y += 1

    panels.append(
        on_off_stat(
            "Дом online",
            0,
            y,
            3,
            4,
            """
SELECT now() AS time,
  CASE WHEN online_status = 'online' THEN 1 ELSE 0 END AS value
FROM houses WHERE house_id = 'house'
""".strip(),
            description="Контроллер LogicMachine на связи с сервером.",
        )
    )
    panels.append(
        on_off_stat(
            "Автоотопление",
            3,
            y,
            3,
            4,
            f"""
SELECT cs.ts AS time, {CS_BOOL} AS value
FROM current_state cs
WHERE cs.house_id = 'house' AND {CS_JOIN} = '1/7/1'
""".strip(),
            description="GA 1/7/1 — автобалансировка тёплых полов. ON = алгоритм сам включает реле.",
        )
    )
    panels.append(
        stat(
            "Мощность сейчас",
            6,
            y,
            3,
            4,
            f"""
SELECT cs.ts AS time, {CS_NUM} AS value
FROM current_state cs
WHERE cs.house_id = 'house' AND {CS_JOIN} = '32/1/35'
""".strip(),
            unit="watt",
            decimals=0,
            description="Total P — активная мощность (сколько реально потребляем прямо сейчас), Вт.",
        )
    )
    panels.append(
        meter_stat("Показания счётчика", 9, y, 5, 4)
    )
    panels.append(
        stat(
            "За сутки",
            14,
            y,
            3,
            4,
            f"""
SELECT cs.ts AS time, {CS_NUM} AS value
FROM current_state cs
WHERE cs.house_id = 'house' AND {CS_JOIN} = '32/1/58'
""".strip(),
            unit="suffix:kWh",
            decimals=2,
            description="Потребление за текущие сутки, кВт·ч.",
        )
    )
    panels.append(
        stat(
            "Улица",
            17,
            y,
            2,
            4,
            f"""
SELECT cs.ts AS time, {CS_NUM} AS value
FROM current_state cs
WHERE cs.house_id = 'house' AND {CS_JOIN} = '32/5/1'
""".strip(),
            unit="celsius",
            decimals=1,
            description="Температура снаружи.",
        )
    )
    panels.append(
        stat(
            "PF (коэф. мощности)",
            19,
            y,
            5,
            4,
            f"""
SELECT cs.ts AS time, {CS_NUM} AS value
FROM current_state cs
WHERE cs.house_id = 'house' AND {CS_JOIN} = '32/1/38'
""".strip(),
            decimals=2,
            description=(
                "PF = Power Factor (коэффициент мощности). "
                "Показывает, насколько эффективно используется ток: 1.0 — идеально, "
                "ниже ~0.9 — много реактивной нагрузки (насосы, блоки питания). "
                "Не путать с потреблением кВт·ч."
            ),
        )
    )
    y += 4

    panels.append(
        timeseries(
            "Мощность (Total P)",
            0,
            y,
            24,
            7,
            f"""
SELECT
  $__timeGroupAlias(e.ts, $__interval),
  avg({NUM}) AS "Total P"
FROM events e
WHERE e.house_id = 'house'
  AND e.ga = '32/1/35'
  AND $__timeFilter(e.ts)
GROUP BY 1
ORDER BY 1
""".strip(),
            unit="watt",
            description="Активная мощность дома во времени.",
        )
    )
    y += 7

    panels.append(row("Свет", y))
    y += 1
    panels.append(light_tiles("1 этаж", 0, y, 10, 10, LIGHTS_1F, cols=3))
    panels.append(light_tiles("2 этаж", 10, y, 10, 10, LIGHTS_2F, cols=3))
    panels.append(light_tiles("Улица", 20, y, 4, 10, LIGHTS_OUT, cols=1))
    y += 10

    panels.append(row("Тёплые полы", y))
    y += 1
    panels.append(heat_tiles("Реле зон", 0, y, 24, 5))
    y += 5

    panels.append(row("Температура и влажность в помещениях (воздух 33/1/*)", y))
    y += 1
    panels.append(
        table(
            "Воздух °C",
            0,
            y,
            12,
            8,
            f"""
SELECT
  CASE o.ga
    WHEN '33/1/7' THEN 'Гостиная'
    WHEN '33/1/13' THEN 'Кухня'
    WHEN '33/1/4' THEN 'Спальня 1эт'
    WHEN '33/1/28' THEN 'Холл 1эт'
    WHEN '33/1/10' THEN 'Ванная 1эт'
    WHEN '33/1/1' THEN 'Серверная'
    WHEN '33/1/34' THEN 'Спальня 2эт'
    WHEN '33/1/22' THEN 'Настя'
    WHEN '33/1/19' THEN 'Тим'
    WHEN '33/1/16' THEN 'Кабинет'
    WHEN '33/1/25' THEN 'Холл 2эт'
    WHEN '33/1/31' THEN 'Ванная 2эт'
    ELSE o.name
  END AS room,
  round({CS_NUM}::numeric, 2) AS temp_c,
  cs.ts AS updated
FROM objects o
JOIN current_state cs ON cs.house_id = o.house_id AND {CS_JOIN} = o.ga
WHERE o.house_id = 'house'
  AND o.tags LIKE '%temperature%'
  AND o.ga LIKE '33/1/%'
ORDER BY room
""".strip(),
            description="Температура воздуха в помещении (Zigbee 33/1/*), не пол.",
        )
    )
    panels.append(
        table(
            "Влажность %",
            12,
            y,
            12,
            8,
            f"""
SELECT
  CASE o.ga
    WHEN '33/1/8' THEN 'Гостиная'
    WHEN '33/1/14' THEN 'Кухня'
    WHEN '33/1/5' THEN 'Спальня 1эт'
    WHEN '33/1/29' THEN 'Холл 1эт'
    WHEN '33/1/11' THEN 'Ванная 1эт'
    WHEN '33/1/2' THEN 'Серверная'
    WHEN '33/1/35' THEN 'Спальня 2эт'
    WHEN '33/1/23' THEN 'Настя'
    WHEN '33/1/20' THEN 'Тим'
    WHEN '33/1/17' THEN 'Кабинет'
    WHEN '33/1/26' THEN 'Холл 2эт'
    WHEN '33/1/32' THEN 'Ванная 2эт'
    ELSE o.name
  END AS room,
  round({CS_NUM}::numeric, 0) AS humidity_pct,
  cs.ts AS updated
FROM objects o
JOIN current_state cs ON cs.house_id = o.house_id AND {CS_JOIN} = o.ga
WHERE o.house_id = 'house'
  AND o.tags LIKE '%humidity%'
  AND o.ga LIKE '33/1/%'
ORDER BY room
""".strip(),
            description="Влажность воздуха в помещениях (Zigbee 33/1/*).",
        )
    )

    return dashboard(
        "Cottage — Overview",
        "cottage-overview",
        panels,
        ["cottage", "overview"],
    )


def energy():
    global _PANEL_ID
    _PANEL_ID = 0
    panels = []
    y = 0
    panels.append(nav_panel(y))
    y += 2
    panels.append(row("Мгновенные / счётчик", y))
    y += 1

    # Prominent meter reading for utilities (32/1/59)
    panels.append(meter_stat("Показания счётчика (для ЖКХ)", 0, y, 8, 5))

    specs = [
        (
            "Total P",
            "32/1/35",
            "watt",
            0,
            "Активная мощность — реальное потребление сейчас, Вт (то, за что платим по сути).",
        ),
        (
            "Total Q",
            "32/1/36",
            None,
            0,
            "Реактивная мощность, вар. Не учитывается в кВт·ч, но нагружает сеть (двигатели, ИБП).",
        ),
        (
            "Total S",
            "32/1/37",
            "voltamp",
            0,
            "Полная мощность S = √(P²+Q²), ВА. Сколько «тянет» сеть с учётом реактивной части.",
        ),
        (
            "PF",
            "32/1/38",
            None,
            2,
            "Power Factor — коэффициент мощности (P/S). 1.0 = идеально; ниже 0.9 — много реактивной нагрузки.",
        ),
        (
            "Частота",
            "32/1/7",
            "hertz",
            1,
            "Частота сети, Гц. Норма ~50 Гц.",
        ),
        (
            "Час",
            "32/1/57",
            "suffix:kWh",
            3,
            "Энергия за текущий час, кВт·ч.",
        ),
        (
            "Сутки",
            "32/1/58",
            "suffix:kWh",
            2,
            "Энергия за текущие сутки, кВт·ч.",
        ),
        (
            "AP energy 32/1/39",
            "32/1/39",
            "suffix:kWh",
            2,
            "Другой регистр счётчика (Total AP energy). Для ЖКХ используем 32/1/59 сверху.",
        ),
    ]
    # 8 specs in 2 rows under the big meter? Put them to the right of meter in 2x4
    for i, (title, ga, unit, dec, desc) in enumerate(specs):
        col = 8 + (i % 4) * 4
        row_y = y + (i // 4) * 5
        panels.append(
            stat(
                title,
                col,
                row_y,
                4,
                5,
                f"""
SELECT cs.ts AS time, {CS_NUM} AS value
FROM current_state cs
WHERE cs.house_id = 'house' AND {CS_JOIN} = '{ga}'
""".strip(),
                unit=unit,
                decimals=dec,
                description=desc,
            )
        )
    y += 10

    panels.append(row("Мощность", y))
    y += 1
    panels.append(
        timeseries(
            "Total P",
            0,
            y,
            24,
            8,
            f"""
SELECT
  $__timeGroupAlias(e.ts, $__interval),
  avg({NUM}) AS "Total P"
FROM events e
WHERE e.house_id = 'house' AND e.ga = '32/1/35' AND $__timeFilter(e.ts)
GROUP BY 1 ORDER BY 1
""".strip(),
            unit="watt",
            description="Активная мощность дома, Вт.",
        )
    )
    y += 8
    panels.append(
        timeseries(
            "Мощность по фазам (P L1/L2/L3)",
            0,
            y,
            24,
            8,
            f"""
SELECT
  $__timeGroupAlias(e.ts, $__interval),
  avg({NUM}) FILTER (WHERE e.ga = '32/1/13') AS "L1",
  avg({NUM}) FILTER (WHERE e.ga = '32/1/21') AS "L2",
  avg({NUM}) FILTER (WHERE e.ga = '32/1/29') AS "L3"
FROM events e
WHERE e.house_id = 'house'
  AND e.ga IN ('32/1/13','32/1/21','32/1/29')
  AND $__timeFilter(e.ts)
GROUP BY 1 ORDER BY 1
""".strip(),
            unit="watt",
            description="Активная мощность по фазам L1/L2/L3.",
        )
    )
    y += 8

    panels.append(row("Напряжение и ток", y))
    y += 1
    panels.append(
        timeseries(
            "Urms L1/L2/L3",
            0,
            y,
            12,
            7,
            f"""
SELECT
  $__timeGroupAlias(e.ts, $__interval),
  avg({NUM}) FILTER (WHERE e.ga = '32/1/1') AS "L1",
  avg({NUM}) FILTER (WHERE e.ga = '32/1/3') AS "L2",
  avg({NUM}) FILTER (WHERE e.ga = '32/1/5') AS "L3"
FROM events e
WHERE e.house_id = 'house'
  AND e.ga IN ('32/1/1','32/1/3','32/1/5')
  AND $__timeFilter(e.ts)
GROUP BY 1 ORDER BY 1
""".strip(),
            unit="volt",
            description="Действующее напряжение по фазам, В. Норма ~230 В.",
        )
    )
    panels.append(
        timeseries(
            "Irms L1/L2/L3",
            12,
            y,
            12,
            7,
            f"""
SELECT
  $__timeGroupAlias(e.ts, $__interval),
  avg({NUM}) FILTER (WHERE e.ga = '32/1/11') AS "L1",
  avg({NUM}) FILTER (WHERE e.ga = '32/1/19') AS "L2",
  avg({NUM}) FILTER (WHERE e.ga = '32/1/27') AS "L3"
FROM events e
WHERE e.house_id = 'house'
  AND e.ga IN ('32/1/11','32/1/19','32/1/27')
  AND $__timeFilter(e.ts)
GROUP BY 1 ORDER BY 1
""".strip(),
            unit="amp",
            description="Действующий ток по фазам, А.",
        )
    )
    y += 7

    panels.append(row("Потребление", y))
    y += 1
    panels.append(
        timeseries(
            "Потребление за час (kWh)",
            0,
            y,
            24,
            7,
            f"""
SELECT
  $__timeGroupAlias(e.ts, $__interval),
  avg({NUM}) AS "Hour kWh"
FROM events e
WHERE e.house_id = 'house' AND e.ga = '32/1/57' AND $__timeFilter(e.ts)
GROUP BY 1 ORDER BY 1
""".strip(),
            unit="suffix:kWh",
            description="Энергия за час, кВт·ч.",
        )
    )

    return dashboard(
        "Cottage — Electricity",
        "cottage-energy",
        panels,
        ["cottage", "energy", "electricity"],
    )


def climate():
    global _PANEL_ID
    _PANEL_ID = 0
    panels = []
    y = 0
    panels.append(nav_panel(y))
    y += 2
    panels.append(row("Температура воздуха в помещениях (33/1/*)", y))
    y += 1
    panels.append(
        timeseries(
            "Воздух в комнатах + улица",
            0,
            y,
            24,
            9,
            f"""
SELECT
  $__timeGroupAlias(e.ts, $__interval),
  avg({NUM}) FILTER (WHERE e.ga = '32/5/1') AS "Улица",
  avg({NUM}) FILTER (WHERE e.ga = '33/1/7') AS "Гостиная",
  avg({NUM}) FILTER (WHERE e.ga = '33/1/13') AS "Кухня",
  avg({NUM}) FILTER (WHERE e.ga = '33/1/4') AS "Спальня 1эт",
  avg({NUM}) FILTER (WHERE e.ga = '33/1/22') AS "Настя",
  avg({NUM}) FILTER (WHERE e.ga = '33/1/19') AS "Тим",
  avg({NUM}) FILTER (WHERE e.ga = '33/1/16') AS "Кабинет",
  avg({NUM}) FILTER (WHERE e.ga = '33/1/34') AS "Спальня 2эт"
FROM events e
WHERE e.house_id = 'house'
  AND e.ga IN (
    '32/5/1','33/1/7','33/1/13','33/1/4','33/1/22','33/1/19','33/1/16','33/1/34'
  )
  AND $__timeFilter(e.ts)
GROUP BY 1 ORDER BY 1
""".strip(),
            unit="celsius",
        )
    )
    y += 9

    panels.append(row("Влажность в помещениях (33/1/*)", y))
    y += 1
    panels.append(
        timeseries(
            "Влажность воздуха",
            0,
            y,
            16,
            7,
            f"""
SELECT
  $__timeGroupAlias(e.ts, $__interval),
  avg({NUM}) FILTER (WHERE e.ga = '33/1/8') AS "Гостиная",
  avg({NUM}) FILTER (WHERE e.ga = '33/1/14') AS "Кухня",
  avg({NUM}) FILTER (WHERE e.ga = '33/1/11') AS "Ванная 1эт",
  avg({NUM}) FILTER (WHERE e.ga = '33/1/32') AS "Ванная 2эт",
  avg({NUM}) FILTER (WHERE e.ga = '32/5/3') AS "Улица"
FROM events e
WHERE e.house_id = 'house'
  AND e.ga IN ('33/1/8','33/1/14','33/1/11','33/1/32','32/5/3')
  AND $__timeFilter(e.ts)
GROUP BY 1 ORDER BY 1
""".strip(),
            unit="humidity",
        )
    )
    panels.append(
        table(
            "Погода сейчас",
            16,
            y,
            8,
            7,
            f"""
SELECT
  CASE o.ga
    WHEN '32/5/1' THEN 'Температура'
    WHEN '32/5/2' THEN 'Ощущается'
    WHEN '32/5/3' THEN 'Влажность'
    WHEN '32/5/4' THEN 'Давление'
    WHEN '32/5/6' THEN 'Ветер м/с'
    WHEN '32/5/7' THEN 'Порывы м/с'
    WHEN '32/5/8' THEN 'Описание'
    ELSE o.name
  END AS metric,
  cs.value #>> '{{}}' AS value,
  cs.ts AS updated
FROM objects o
JOIN current_state cs ON cs.house_id = o.house_id AND {CS_JOIN} = o.ga
WHERE o.house_id = 'house'
  AND o.ga IN ('32/5/1','32/5/2','32/5/3','32/5/4','32/5/6','32/5/7','32/5/8')
ORDER BY o.ga
""".strip(),
        )
    )
    y += 7

    panels.append(row("Тёплые полы: температура В ПОЛУ (1/3/*) vs уставка", y))
    y += 1
    panels.append(
        table(
            "Зоны ТП (пол, не воздух)",
            0,
            y,
            14,
            10,
            f"""
WITH floor_t AS (
  SELECT o.ga, replace(o.name, 'Темп - ', '') AS zone, {CS_NUM} AS floor_c
  FROM objects o
  JOIN current_state cs ON cs.house_id = o.house_id AND {CS_JOIN} = o.ga
  WHERE o.house_id = 'house'
    AND o.tags LIKE '%heat%' AND o.tags LIKE '%temp%'
    AND o.tags NOT LIKE '%setpoint%'
    AND o.ga LIKE '1/3/%'
),
sp AS (
  SELECT o.ga, replace(o.name, 'Уставка ТП - ', '') AS zone, {CS_NUM} AS setpoint_c
  FROM objects o
  JOIN current_state cs ON cs.house_id = o.house_id AND {CS_JOIN} = o.ga
  WHERE o.house_id = 'house' AND o.tags LIKE '%setpoint%'
),
rel AS (
  SELECT replace(replace(o.name, 'ТП - ', ''), ' :status', '') AS zone,
         {CS_BOOL} AS relay_on
  FROM objects o
  JOIN current_state cs ON cs.house_id = o.house_id AND {CS_JOIN} = o.ga
  WHERE o.house_id = 'house'
    AND o.tags LIKE '%heat%' AND o.tags LIKE '%status%'
)
SELECT
  CASE WHEN coalesce(r.relay_on, 0) = 1 THEN '🔥' ELSE '❄' END AS icon,
  f.zone,
  round(f.floor_c::numeric, 2) AS floor_c,
  round(s.setpoint_c::numeric, 1) AS setpoint_c,
  CASE WHEN coalesce(r.relay_on, 0) = 1 THEN 'ON' ELSE 'OFF' END AS relay
FROM floor_t f
LEFT JOIN sp s ON trim(both FROM s.zone) = trim(both FROM f.zone)
LEFT JOIN rel r ON r.zone = f.zone
  OR r.zone = replace(f.zone, '1 этаж', '1 этажа')
  OR replace(r.zone, '1 этажа', '1 этаж') = f.zone
ORDER BY f.zone
""".strip(),
            description=(
                "🔥 греет / ❄ выкл. "
                "floor_c — температура В ПЛЁНКЕ ПОЛА (1/3/*), не воздух в комнате. "
                "setpoint — уставка комфорта (1/6/*)."
            ),
        )
    )
    panels.append(
        timeseries(
            "Температура В ПОЛУ (1/3/*)",
            14,
            y,
            10,
            10,
            f"""
SELECT
  $__timeGroupAlias(e.ts, $__interval),
  avg({NUM}) FILTER (WHERE e.ga = '1/3/7') AS "Кухня",
  avg({NUM}) FILTER (WHERE e.ga = '1/3/5') AS "Гостиная 1",
  avg({NUM}) FILTER (WHERE e.ga = '1/3/6') AS "Гостиная 2",
  avg({NUM}) FILTER (WHERE e.ga = '1/3/4') AS "Спальня",
  avg({NUM}) FILTER (WHERE e.ga = '1/3/12') AS "Настя",
  avg({NUM}) FILTER (WHERE e.ga = '1/3/13') AS "Тим"
FROM events e
WHERE e.house_id = 'house'
  AND e.ga IN ('1/3/7','1/3/5','1/3/6','1/3/4','1/3/12','1/3/13')
  AND $__timeFilter(e.ts)
GROUP BY 1 ORDER BY 1
""".strip(),
            unit="celsius",
        )
    )
    y += 10

    panels.append(row("Реле отопления (история)", y))
    y += 1
    panels.append(
        timeseries(
            "Реле ТП (0/1)",
            0,
            y,
            24,
            7,
            f"""
SELECT
  $__timeGroupAlias(e.ts, $__interval),
  max({BOOL01}) FILTER (WHERE e.ga = '1/5/7') AS "Кухня",
  max({BOOL01}) FILTER (WHERE e.ga = '1/5/5') AS "Гостиная1",
  max({BOOL01}) FILTER (WHERE e.ga = '1/5/6') AS "Гостиная2",
  max({BOOL01}) FILTER (WHERE e.ga = '1/5/4') AS "Спальня",
  max({BOOL01}) FILTER (WHERE e.ga = '1/5/12') AS "Настя",
  max({BOOL01}) FILTER (WHERE e.ga = '1/5/13') AS "Тим"
FROM events e
WHERE e.house_id = 'house'
  AND e.ga IN ('1/5/7','1/5/5','1/5/6','1/5/4','1/5/12','1/5/13')
  AND $__timeFilter(e.ts)
GROUP BY 1 ORDER BY 1
""".strip(),
        )
    )

    return dashboard(
        "Cottage — Climate",
        "cottage-climate",
        panels,
        ["cottage", "climate", "temperature"],
    )


def lights():
    global _PANEL_ID
    _PANEL_ID = 0
    panels = []
    y = 0
    panels.append(nav_panel(y))
    y += 2
    panels.append(row("Сейчас", y))
    y += 1
    panels.append(light_tiles("1 этаж", 0, y, 24, 10, LIGHTS_1F, cols=5))
    y += 10
    panels.append(light_tiles("2 этаж", 0, y, 16, 10, LIGHTS_2F, cols=4))
    panels.append(light_tiles("Улица", 16, y, 8, 10, LIGHTS_OUT, cols=3))
    y += 10
    panels.append(row("История", y))
    y += 1
    panels.append(light_history("1 этаж", 0, y, 24, 9, LIGHTS_1F))
    y += 9
    panels.append(light_history("2 этаж", 0, y, 16, 9, LIGHTS_2F))
    panels.append(light_history("Улица", 16, y, 8, 9, LIGHTS_OUT))
    return dashboard(
        "Cottage — Lights",
        "cottage-lights",
        panels,
        ["cottage", "lights"],
    )


def batteries():
    global _PANEL_ID
    _PANEL_ID = 0
    panels = []
    y = 0
    panels.append(nav_panel(y))
    y += 2
    panels.append(row("Заряд батареек Zigbee", y))
    y += 1

    bat_thresholds = {
        "mode": "absolute",
        "steps": [
            {"color": "dark-red", "value": None},
            {"color": "dark-red", "value": 0},
            {"color": "dark-yellow", "value": 20},
            {"color": "dark-green", "value": 50},
        ],
    }

    # One colored table
    panels.append(
        table(
            "Батарейки",
            0,
            y,
            14,
            14,
            f"""
SELECT
  CASE
    WHEN {CS_NUM} < 20 THEN '🔴'
    WHEN {CS_NUM} < 50 THEN '🟡'
    ELSE '🟢'
  END AS lvl,
  CASE
    WHEN o.ga = '33/1/3' THEN 'Серверная'
    WHEN o.ga = '33/1/6' THEN 'Спальня 1эт'
    WHEN o.ga = '33/1/9' THEN 'Гостиная'
    WHEN o.ga = '33/1/12' THEN 'Ванная 1эт'
    WHEN o.ga = '33/1/15' THEN 'Кухня'
    WHEN o.ga = '33/1/18' THEN 'Кабинет'
    WHEN o.ga = '33/1/21' THEN 'Тим'
    WHEN o.ga = '33/1/24' THEN 'Настя'
    WHEN o.ga = '33/1/27' THEN 'Холл 2эт'
    WHEN o.ga = '33/1/30' THEN 'Холл 1эт'
    WHEN o.ga = '33/1/33' THEN 'Ванная 2эт'
    WHEN o.ga = '33/1/36' THEN 'Спальня 2эт'
    WHEN o.ga = '32/7/15' THEN 'PIR sensor 1'
    ELSE replace(replace(o.name, 'zb_sensor_', ''), '_battery', '')
  END AS sensor,
  round({CS_NUM}::numeric, 0) AS battery_pct,
  cs.ts AS updated,
  o.ga
FROM objects o
JOIN current_state cs ON cs.house_id = o.house_id AND {CS_JOIN} = o.ga
WHERE o.house_id = 'house'
  AND o.tags LIKE '%battery%'
ORDER BY battery_pct ASC, sensor
""".strip(),
            description=(
                "🟢 ≥50% · 🟡 20–49% · 🔴 <20%. "
                "Zigbee датчики температуры/влажности + PIR."
            ),
            field_config={
                "defaults": {},
                "overrides": [
                    {
                        "matcher": {"id": "byName", "options": "battery_pct"},
                        "properties": [
                            {"id": "unit", "value": "percent"},
                            {"id": "decimals", "value": 0},
                            {"id": "thresholds", "value": bat_thresholds},
                            {
                                "id": "custom.cellOptions",
                                "value": {"type": "color-background", "mode": "basic"},
                            },
                        ],
                    }
                ],
            },
        )
    )

    # Gauges for worst / all — compact stats on the right sorted by SQL still show as individual
    # Show critical (<50) as stats
    panels.append(
        table(
            "Нужна замена / контроль (<50%)",
            14,
            y,
            10,
            7,
            f"""
SELECT
  CASE
    WHEN {CS_NUM} < 20 THEN '🔴'
    ELSE '🟡'
  END AS lvl,
  CASE
    WHEN o.ga = '33/1/3' THEN 'Серверная'
    WHEN o.ga = '33/1/6' THEN 'Спальня 1эт'
    WHEN o.ga = '33/1/9' THEN 'Гостиная'
    WHEN o.ga = '33/1/12' THEN 'Ванная 1эт'
    WHEN o.ga = '33/1/15' THEN 'Кухня'
    WHEN o.ga = '33/1/18' THEN 'Кабинет'
    WHEN o.ga = '33/1/21' THEN 'Тим'
    WHEN o.ga = '33/1/24' THEN 'Настя'
    WHEN o.ga = '33/1/27' THEN 'Холл 2эт'
    WHEN o.ga = '33/1/30' THEN 'Холл 1эт'
    WHEN o.ga = '33/1/33' THEN 'Ванная 2эт'
    WHEN o.ga = '33/1/36' THEN 'Спальня 2эт'
    WHEN o.ga = '32/7/15' THEN 'PIR sensor 1'
    ELSE o.name
  END AS sensor,
  round({CS_NUM}::numeric, 0) AS battery_pct
FROM objects o
JOIN current_state cs ON cs.house_id = o.house_id AND {CS_JOIN} = o.ga
WHERE o.house_id = 'house'
  AND o.tags LIKE '%battery%'
  AND {CS_NUM} < 50
ORDER BY battery_pct ASC
""".strip(),
            description="Сенсоры с зарядом ниже 50%.",
            field_config={
                "defaults": {},
                "overrides": [
                    {
                        "matcher": {"id": "byName", "options": "battery_pct"},
                        "properties": [
                            {"id": "unit", "value": "percent"},
                            {"id": "thresholds", "value": bat_thresholds},
                            {
                                "id": "custom.cellOptions",
                                "value": {"type": "color-background", "mode": "basic"},
                            },
                        ],
                    }
                ],
            },
        )
    )
    panels.append(
        timeseries(
            "Заряд во времени (основные)",
            14,
            y + 7,
            10,
            7,
            f"""
SELECT
  $__timeGroupAlias(e.ts, $__interval),
  avg({NUM}) FILTER (WHERE e.ga = '33/1/9') AS "Гостиная",
  avg({NUM}) FILTER (WHERE e.ga = '33/1/15') AS "Кухня",
  avg({NUM}) FILTER (WHERE e.ga = '33/1/24') AS "Настя",
  avg({NUM}) FILTER (WHERE e.ga = '33/1/21') AS "Тим",
  avg({NUM}) FILTER (WHERE e.ga = '33/1/12') AS "Ванная 1эт"
FROM events e
WHERE e.house_id = 'house'
  AND e.ga IN ('33/1/9','33/1/15','33/1/24','33/1/21','33/1/12')
  AND $__timeFilter(e.ts)
GROUP BY 1 ORDER BY 1
""".strip(),
            unit="percent",
            description="История заряда (часто обновляется редко).",
        )
    )

    return dashboard(
        "Cottage — Batteries",
        "cottage-batteries",
        panels,
        ["cottage", "batteries"],
        refresh="1m",
    )


LOAD_THRESHOLDS = {
    "mode": "absolute",
    "steps": [
        {"color": "semi-dark-green", "value": None},
        {"color": "semi-dark-yellow", "value": 1.0},
        {"color": "orange", "value": 1.5},
        {"color": "semi-dark-red", "value": 2.0},
    ],
}


def _load_latest_sql(ga: str) -> str:
    return f"""
SELECT e.ts AS time, {NUM} AS value
FROM events e
WHERE e.house_id = 'house' AND e.ga = '{ga}'
ORDER BY e.ts DESC
LIMIT 1
""".strip()


def _load_num_overrides(colnames: list[str]) -> list[dict]:
    """Color numeric table cells by the same loadavg thresholds."""
    return [
        {
            "matcher": {"id": "byName", "options": name},
            "properties": [
                {"id": "decimals", "value": 3},
                {"id": "thresholds", "value": LOAD_THRESHOLDS},
                {
                    "id": "custom.cellOptions",
                    "value": {"type": "color-background", "mode": "basic"},
                },
                {"id": "color", "value": {"mode": "thresholds"}},
            ],
        }
        for name in colnames
    ]


def lm_load():
    """LogicMachine CPU loadavg from GA 34/1/6..8."""
    global _PANEL_ID
    _PANEL_ID = 0
    panels = []
    y = 0
    panels.append(nav_panel(y))
    y += 2
    panels.append(row("Сейчас (loadavg LM)", y))
    y += 1

    for i, (title, ga, desc) in enumerate(
        [
            ("load1", "34/1/6", "Средняя загрузка за 1 мин (GA 34/1/6)."),
            ("load5", "34/1/7", "Средняя загрузка за 5 мин (GA 34/1/7)."),
            ("load15", "34/1/8", "Средняя загрузка за 15 мин (GA 34/1/8). Алерт при >2.0."),
        ]
    ):
        p = stat(
            title,
            i * 4,
            y,
            4,
            4,
            _load_latest_sql(ga),
            decimals=2,
            description=desc,
            color_mode="background",
            graph_mode="none",
            text_mode="value",
        )
        p["fieldConfig"]["defaults"]["thresholds"] = LOAD_THRESHOLDS
        p["fieldConfig"]["defaults"]["color"] = {"mode": "thresholds"}
        panels.append(p)

    panels.append(
        table(
            "Порог алерта",
            12,
            y,
            12,
            4,
            """
SELECT
  'load15 > 2.0 for 10m' AS rule,
  'warning' AS severity,
  'Telegram · team=cottage' AS notify
""".strip(),
            description="Grafana alert: cottage-lm-load15-high → cottage-telegram.",
        )
    )
    y += 4

    panels.append(row("История", y))
    y += 1
    ts = timeseries(
        "Loadavg LM (1 / 5 / 15 мин)",
        0,
        y,
        24,
        10,
        f"""
SELECT
  $__timeGroupAlias(e.ts, $__interval),
  avg({NUM}) FILTER (WHERE e.ga = '34/1/6') AS "load1",
  avg({NUM}) FILTER (WHERE e.ga = '34/1/7') AS "load5",
  avg({NUM}) FILTER (WHERE e.ga = '34/1/8') AS "load15"
FROM events e
WHERE e.house_id = 'house'
  AND e.ga IN ('34/1/6','34/1/7','34/1/8')
  AND $__timeFilter(e.ts)
GROUP BY 1 ORDER BY 1
""".strip(),
        description=(
            "Зелёный <1.0 · жёлтый 1.0–1.5 · оранжевый 1.5–2.0 · красный >2.0. "
            "Линия 2.0 — порог алерта load15. Цифры сверху — цвет фона по тем же порогам."
        ),
    )
    ts["fieldConfig"]["defaults"]["thresholds"] = LOAD_THRESHOLDS
    ts["fieldConfig"]["defaults"]["color"] = {"mode": "palette-classic"}
    ts["fieldConfig"]["defaults"]["custom"]["thresholdsStyle"] = {"mode": "line+area"}
    panels.append(ts)
    y += 10

    panels.append(row("По дням (MSK)", y))
    y += 1
    panels.append(
        table(
            "Суточные avg / p50 / p95 / max",
            0,
            y,
            24,
            10,
            f"""
WITH e AS (
  SELECT
    e.ga,
    (e.ts AT TIME ZONE 'Europe/Moscow')::date AS day,
    {NUM} AS v
  FROM events e
  WHERE e.house_id = 'house'
    AND e.ga IN ('34/1/6','34/1/7','34/1/8')
    AND e.ts > now() - interval '14 days'
)
SELECT
  day,
  CASE ga
    WHEN '34/1/6' THEN 'load1'
    WHEN '34/1/7' THEN 'load5'
    WHEN '34/1/8' THEN 'load15'
  END AS metric,
  count(*) AS n,
  round(avg(v)::numeric, 3) AS avg,
  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY v)::numeric, 3) AS p50,
  round(percentile_cont(0.95) WITHIN GROUP (ORDER BY v)::numeric, 3) AS p95,
  round(max(v)::numeric, 3) AS max
FROM e
WHERE v IS NOT NULL
GROUP BY day, ga
ORDER BY day DESC, metric
""".strip(),
            description="Ячейки avg/p50/p95/max окрашены: зелёный <1 · жёлтый ≥1 · оранжевый ≥1.5 · красный ≥2.",
            field_config={
                "defaults": {},
                "overrides": _load_num_overrides(["avg", "p50", "p95", "max"]),
            },
        )
    )

    return dashboard(
        "Cottage — LM Load",
        "cottage-lm-load",
        panels,
        ["cottage", "load", "logicmachine"],
        refresh="1m",
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in [
        ("cottage_overview.json", overview),
        ("cottage_energy.json", energy),
        ("cottage_climate.json", climate),
        ("cottage_lights.json", lights),
        ("cottage_batteries.json", batteries),
        ("cottage_lm_load.json", lm_load),
    ]:
        path = OUT / name
        path.write_text(json.dumps(fn(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()