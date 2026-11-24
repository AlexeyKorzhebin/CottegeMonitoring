# Zigbee Ceiling Light Params Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`. Steps use checkbox (`- [ ]`) syntax for tracking. Do not offer inline execution. Do not use `inherit` for subagent models; pick from `.cursor/rules/subagent-models.mdc` (map to available session slugs).

**Goal:** Виртуальные GA `34/1|2/*` на LM для brightness / CCT / RGB потолочных Zigbee; read через `mqtt_listen`, write через `zigbee_send`; sync при ON реле с LWW по `updatetime`.

**Architecture:** Каталог JSON → one-shot `grp.create` → `mqtt_listen` statusmap + converters → `zigbee_send` таблица (Тима = группа `Ceiling_lamps_tima`) → event-скрипт `zb_light_sync` на теге реле. Алиса/Nord/HA — out of scope.

**Tech Stack:** Lua 5.1 on Logic Machine (`grp`, `mosquitto`, `json`, `event`, `storage`); FTP deploy scripts; pytest only if добавляется Python helper.

**Spec:** `docs/superpowers/specs/2026-11-24-zigbee-ceiling-light-params-design.md`

---

## Global Constraints

- Реле KNX `1/1/13` (Тима), `1/1/15` (холл), `1/1/14` (кабинет) **не менять логику on/off** — только добавить тег `zb_light_sync`.
- Тима write: **только** `zigbee2mqtt/Ceiling_lamps_tima/set` (группа id 1: tima1+tima2). Не два отдельных publish.
- Status Тима: `zigbee2mqtt/Ceiling_lamp_tima1` (и опционально state группы); `tima2` не пишет status.
- Холл: `Ceiling_lamp_hall_2_floor`. Кабинет: `Ceiling_lamp_office`.
- Диапазон GA только `34/1/1–9` control, `34/2/1–9` status (см. каталог ниже).
- `mqtt_listen` **id 4** only. Не трогать id 48.
- `zigbee_send` живёт на LM с MQTT-паролем — **не коммитить пароль**. В git: шаблон/фрагмент маппинга без секретов + инструкция в quickstart.
- Guard `storage.zb_light_from_sync_align` (или аналог) при выравнивании control←status.
- Не расширять Nord Ops / HA / Alice в этой волне.
- Спеки: обновить `specs/002-logicmachine-mqtt-client/quickstart.md` (+ research R-XXX при operational caveat).
- Коммиты: английский, why-first; спеки вместе с кодом (правило update-specs-on-commit).

---

## Catalog (lock)

| Zone | Relay | z2m set target | Param | Control | Status | DPT |
|------|-------|----------------|-------|---------|--------|-----|
| Тима | `1/1/13` | `Ceiling_lamps_tima` | brightness | `34/1/1` | `34/2/1` | 5 (0–100%) |
| Тима | | | color_temp | `34/1/2` | `34/2/2` | 9 (mired) |
| Тима | | | rgb | `34/1/3` | `34/2/3` | 12 (uint32 0xRRGGBB) |
| Холл | `1/1/15` | `Ceiling_lamp_hall_2_floor` | brightness | `34/1/4` | `34/2/4` | 5 |
| Холл | | | color_temp | `34/1/5` | `34/2/5` | 9 |
| Холл | | | rgb | `34/1/6` | `34/2/6` | 12 |
| Кабинет | `1/1/14` | `Ceiling_lamp_office` | brightness | `34/1/7` | `34/2/7` | 5 |
| Кабинет | | | color_temp | `34/1/8` | `34/2/8` | 9 |
| Кабинет | | | rgb | `34/1/9` | `34/2/9` | 12 |

Names: `Свет Zigbee - <Зона> - яркость|CCT|RGB` и `:status`.  
Tags control: `2floor, light, zigbee, zigbee_send`. Status: `2floor, light, zigbee, status`.

Converters: brightness LM% ↔ z2m 0–254 (`round(pct*2.54)`, `round(bri/2.54)`); CCT as-is mired; RGB uint32 ↔ `{r,g,b}`.

---

## File map

| Path | Role |
|------|------|
| `cm-client/scripts/zb_ceiling_light_catalog.json` | 18 objects + zone/relay/z2m map |
| `cm-client/scripts/create-zb-ceiling-light-objects.lua` | one-shot `grp.create` + tag relays |
| `cm-client/scripts/mqtt_listen.lua` | statusmap + converters for ceiling params |
| `cm-client/scripts/zb_light_sync.lua` | event script source (tag `zb_light_sync`) |
| `cm-client/scripts/zigbee_send_ceiling_fragment.lua` | mapping fragment **without password** for merge into live zigbee_send |
| `specs/002-logicmachine-mqtt-client/quickstart.md` | deploy + GA table |
| `specs/002-logicmachine-mqtt-client/research.md` | R-XXX notes |
| Design already at `docs/superpowers/specs/2026-11-24-…` | keep in sync if GA change |

---

### Task 1: Catalog + create-objects Lua

**Files:**
- Create: `cm-client/scripts/zb_ceiling_light_catalog.json`
- Create: `cm-client/scripts/create-zb-ceiling-light-objects.lua`

- [ ] **Step 1: Write catalog JSON** with all 18 GAs, names, tags, datatype, zone, relay_ga, z2m_topic, param (`brightness`|`color_temp`|`rgb`), role (`control`|`status`).

- [ ] **Step 2: Write create Lua** mirroring `create-ai-srv-objects.lua`: skip existing addresses; `grp.create`; after objects, ensure relays `1/1/13`,`1/1/14`,`1/1/15` have tag `zb_light_sync` (via `grp.addtags` / equivalent available on this LM — if only recreate tags via UI note in quickstart).

- [ ] **Step 3: Commit** `Add Zigbee ceiling light GA catalog and create script.`

---

### Task 2: mqtt_listen read-path

**Files:**
- Modify: `cm-client/scripts/mqtt_listen.lua`

- [ ] **Step 1: Add converters** `Bri254toPct`, `Pct unchanged for status write`, unpack RGB from z2m `color.r/g/b` → uint32; CCT number.

- [ ] **Step 2: Extend statusmap**

```lua
['zigbee2mqtt/Ceiling_lamp_tima1'] = {
  brightness = { addr = '34/2/1', convert_func = Bri254toPct },
  color_temp = '34/2/2',
  -- color handled in custom branch OR map if framework supports nested
},
['zigbee2mqtt/Ceiling_lamp_hall_2_floor'] = { ... 34/2/4-6 ... },
['zigbee2mqtt/Ceiling_lamp_office'] = { ... 34/2/7-9 ... },
```

If current mqtt_listen only maps flat keys: add a small JSON handler for these three topics that reads `brightness`, `color_temp`, `color` and `grp.update`s status GAs (same pattern as `ai_srv_json`). Prefer that over breaking existing flat maps.

- [ ] **Step 3: Commit** `Map Zigbee ceiling lamp params into mqtt_listen status GAs.`

---

### Task 3: zigbee_send write-path (fragment + live merge notes)

**Files:**
- Create: `cm-client/scripts/zigbee_send_ceiling_fragment.lua`
- Modify: `specs/002-logicmachine-mqtt-client/quickstart.md` (how to merge into live script)

- [ ] **Step 1: Fragment** — table control GA → `{ topic = 'zigbee2mqtt/<name>/set', build_payload(value) }`; Тима → `Ceiling_lamps_tima`; guard if `storage.zb_light_from_sync_align` then return.

- [ ] **Step 2: Document** live merge: open zigbee_send on LM, paste fragment into existing mqtt publish path (password stays local).

- [ ] **Step 3: Commit** `Add zigbee_send fragment for ceiling light param writes.`

---

### Task 4: Event sync script `zb_light_sync`

**Files:**
- Create: `cm-client/scripts/zb_light_sync.lua`

- [ ] **Step 1: Implement** event script:
  1. `event.dst` → zone via catalog relay map.
  2. If value false → return.
  3. For each param: compare `grp.find(control).updatetime` vs status; control newer → publish set (call same build as send or `grp.write` trigger); status newer → set storage guard, `grp.update(control, status_value)`, clear guard.
  4. Equal → no-op.

- [ ] **Step 2: Document** install as **event** script with tag filter `zb_light_sync` (LM UI / scripting DB).

- [ ] **Step 3: Commit** `Add zb_light_sync event script for relay ON last-write-wins.`

---

### Task 5: Specs + deploy checklist

**Files:**
- Modify: `specs/002-logicmachine-mqtt-client/quickstart.md`
- Modify: `specs/002-logicmachine-mqtt-client/research.md` (short R-XXX: group `Ceiling_lamps_tima`, GA table, sync LWW)

- [ ] **Step 1: Quickstart** — GA table, z2m names, deploy order: create objects → mqtt_listen FTP+respawn id4 → merge zigbee_send → install event script → tag relays → manual test §9 of design.

- [ ] **Step 2: Commit** `Document Zigbee ceiling light params ops in LM quickstart.`

---

### Task 6: Live deploy + manual verification (operator/agent with LAN)

- [ ] **Step 1:** Run create script on LM (FTP + user script / dofile pattern as AI-SRV).
- [ ] **Step 2:** Deploy mqtt_listen; respawn resident 4.
- [ ] **Step 3:** Merge zigbee_send fragment on LM (keep password).
- [ ] **Step 4:** Install `zb_light_sync` event; confirm tags on relays.
- [ ] **Step 5: Manual tests** (design §9): Тима brightness via group; холл CCT/RGB; кабинет; OFF→ON LWW; z2m UI change then relay cycle no rollback; regress торшер/тайфайтер.

---

## Done when

- 18 GA exist on LM; mqtt_listen updates status from z2m; writing control publishes set (Тима via group); relay ON runs LWW sync; quickstart documents ops; no secrets in git.
