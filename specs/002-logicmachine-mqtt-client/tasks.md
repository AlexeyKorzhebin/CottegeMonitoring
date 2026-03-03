# Tasks: Logic Machine MQTT Client App

**Input**: Design documents from `/specs/002-logicmachine-mqtt-client/`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Ручное тестирование (spec); автоматические тесты не предусмотрены.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1, US2, US3, US4 — user story from spec.md
- Include exact file paths in descriptions

## Path Conventions

- **cm-client/**: Logic Machine App source (deploy via lftp to `/data/apps/store/data/cottage-monitoring`)
- **deploy/**: Deployment scripts

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and directory structure

- [x] T001 Create cm-client/ directory structure per plan.md: cm-client/config.lp, cm-client/index.lp, cm-client/daemon/daemon.lua, cm-client/libs/, cm-client/icon.svg
- [x] T002 Create deploy/ directory and deploy/deploy-lftp.sh stub (placeholder script; full implementation in T033)
- [x] T003 [P] Create cm-client/README.md with installation instructions from quickstart.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Basic app shell — config form, daemon skeleton, icon. Required before user stories.

- [x] T004 Implement config.lp form skeleton: form id `cottage-monitoring-config`, events config-load, config-check, config-save (per contracts/config-schema.md)
- [x] T005 Implement config-save: on success call apps/request.lp?action=restart&name=cottage-monitoring (per research.md R-001)
- [x] T006 [P] Create cm-client/icon.svg — минимальная иконка приложения (SVG, ~100×100px; см. kb.logicmachine.net/misc/apps/)
- [x] T007 Create cm-client/daemon/daemon.lua skeleton: require('apps'), require('json'), require('config'); load config via config.get('cottage-monitoring', key, default); main loop with os.sleep(1) and storage.set('mqtt_connected', false); dlog/dalert helpers when config.debug (per research.md R-006)

**Checkpoint**: Config form saves, daemon starts and loops. Export buttons not functional yet.

---

## Phase 3: User Story 1 — Настройка приложения (P1) 🎯 MVP

**Goal**: Form settings, export to file, export to MQTT button. Daemon restart on save.

**Independent Test**: Open config form, enter values, Save — verify config.get returns values and daemon restarts. Click «Выгрузить в файл» — JSON download. Click «Выгрузить в MQTT» — after US2, meta+snapshot publish.

- [x] T008 [US1] Add all config form fields to cm-client/config.lp per contracts/config-schema.md: house_id, device_id, env_mode, mqtt_host, mqtt_port, mqtt_username, mqtt_password, mqtt_use_tls (disabled), client_id, debug, snapshot_interval, throttle, buffer_size
- [x] T009 [US1] Implement config-check validation in cm-client/config.lp: house_id/device_id 1–64 chars [a-zA-Z0-9_-], env_mode in [dev,prod], mqtt_port 1–65535, mqtt_username/mqtt_password non-empty, snapshot_interval/throttle/buffer_size ≥ 0; on invalid show alert and do not trigger config-save
- [x] T010 [US1] Create cm-client/index.lp: Back button, «Выгрузить все объекты в файл», «Выгрузить все объекты в MQTT» buttons
- [x] T011 [US1] Implement «Выгрузить в файл» in cm-client/index.lp: LP script that calls grp.all(), formats as JSON {ts, schema_hash, count, objects: [...]} with values from grp.getvalue; schema_hash = encdec.sha256(json.encode(sorted_addresses)) if encdec available, else ""; triggers file download (Content-Disposition)
- [x] T012 [US1] Implement «Выгрузить в MQTT» button logic in cm-client/index.lp: read storage.get('mqtt_connected'); if false show «MQTT недоступен»; if true set storage.set('force_export', 1), show success; daemon (US2) handles the actual publish

**Checkpoint**: US1 complete — config works, export to file works, export to MQTT button ready (will work when US2 daemon is connected).

---

## Phase 4: User Story 2 — Публикация телеметрии (P2)

**Goal**: Daemon connects to MQTT, publishes events, state, meta, snapshot; localbus listener; RAM buffer when offline; LWT status/offline.

**Independent Test**: Simulate groupwrite on controller, verify MQTT topics events and state/ga/<ga>. Restart daemon — verify meta+snapshot. Disconnect broker — verify buffer; reconnect — verify FIFO publish.

- [x] T013 [US2] Implement MQTT connect in cm-client/daemon/daemon.lua: mosquitto client, login_set, version_set PROTOCOL_V311, tls_insecure_set(true), connect(host, port 8883, keepalive 60), will_set for status/offline (per research.md R-002)
- [x] T014 [US2] Implement topic prefix in cm-client/daemon/daemon.lua: base_topic = (env_mode=='dev' and 'dev/' or '') .. 'cm/'..house_id..'/'..device_id..'/v1/'
- [x] T015 [US2] Implement initial sync on connect in cm-client/daemon/daemon.lua: publish status/online retained; subscribe cmd and rpc/req; publish meta/objects (or chunks if >100 objects: CHUNK_SIZE=100, chunk_total=ceil(count/100)); publish snapshot (grp.readvalue for each object, state/ga/<ga> retained) — per «Поведение при старте»
- [x] T016 [US2] Implement localbus groupwrite handler in cm-client/daemon/daemon.lua: lb:sethandler('groupwrite', fn); decode event via knxdatatype, grp.find; publish event to events topic; publish state to state/ga/<ga> retained (per research.md R-003, contracts/mqtt-protocol.md)
- [x] T017 [US2] Implement main loop in cm-client/daemon/daemon.lua: lb:step(), mqtt:loop(100), process buffer flush on reconnect, os.sleep(0.05); integrate localbus + MQTT (per research.md R-003)
- [x] T018 [US2] Implement RAM buffer in cm-client/daemon/daemon.lua: buf_add({topic, payload, qos, retain}) when MQTT disconnected and buffer_size>0; buf_flush on ON_CONNECT; FIFO drop on overflow (per research.md R-007, FR-006a)
- [x] T019 [US2] Implement storage.mqtt_connected and storage.force_export in cm-client/daemon/daemon.lua: set mqtt_connected true on connect, false on disconnect; on force_export set, run meta+snapshot publish, clear flag
- [x] T020 [US2] Implement meta chunking in cm-client/daemon/daemon.lua: if #objects>100, CHUNK_SIZE=100, publish meta/objects/chunk/N with chunk_no, chunk_total (per research.md R-008, FR-003)
- [x] T021 [US2] Implement schema_hash in cm-client/daemon/daemon.lua: encdec.sha256(json.encode(sorted objects)) for meta payload (per research.md R-005)

**Checkpoint**: Daemon publishes telemetry; «Выгрузить в MQTT» from US1 works when daemon connected.

---

## Phase 5: User Story 3 — Получение и выполнение команд (P3)

**Goal**: Subscribe to cmd, execute grp.write(ga, value), publish cmd/ack.

**Independent Test**: Send command via API POST /api/v1/houses/{house_id}/commands; verify MQTT cmd publish, cmd/ack received, value applied on bus.

- [x] T022 [US3] Implement ON_MESSAGE handler for cmd topic in cm-client/daemon/daemon.lua: parse JSON payload (request_id, ga+value or items)
- [x] T023 [US3] Implement single command execution in cm-client/daemon/daemon.lua: grp.write(ga, value), publish cmd/ack/<request_id> with status ok/error, results [{ga, applied, error}] (per FR-008)
- [x] T024 [US3] Implement batch command execution in cm-client/daemon/daemon.lua: for each item grp.write(ga, value), collect results; publish single cmd/ack with all results
- [x] T025 [US3] Implement error handling for cmd in cm-client/daemon/daemon.lua: unknown GA or invalid value → ack status=error, results with error message; invalid JSON → ack status=error (per Edge Cases spec)

**Checkpoint**: Commands from cloud execute on controller, ack published.

---

## Phase 6: User Story 4 — Обработка RPC (meta, snapshot) (P4)

**Goal**: Subscribe to rpc/req/<client_id>, respond to method=meta and method=snapshot with rpc/resp.

**Independent Test**: Send RPC meta via API; verify rpc/req publish, rpc/resp received with meta/objects. Same for snapshot.

- [x] T026 [US4] Implement ON_MESSAGE handler for rpc/req topic in cm-client/daemon/daemon.lua: parse JSON (request_id, method, params)
- [x] T027 [US4] Implement method=meta handler in cm-client/daemon/daemon.lua: build meta/objects payload (grp.all, schema_hash), publish to rpc/resp/<client_id>/<request_id>
- [x] T028 [US4] Implement method=snapshot handler in cm-client/daemon/daemon.lua: grp.readvalue for all objects, build state array [{ga, value, datatype}], publish to rpc/resp

**Checkpoint**: RPC meta and snapshot work; server can refresh schema/state on demand.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Optional settings, reconnect, documentation, deploy script

- [x] T029 Implement reconnect on disconnect in cm-client/daemon/daemon.lua: ON_DISCONNECT callback, reconnect() with backoff or immediate retry (per FR-006)
- [x] T030 [P] Implement optional snapshot_interval in cm-client/daemon/daemon.lua: if >0, periodic snapshot publish every N seconds (per FR-012)
- [x] T031 [P] Implement optional throttle in cm-client/daemon/daemon.lua: limit events/sec when >0 (per FR-012)
- [x] T032 [P] Update cm-client/README.md with config fields, quickstart steps, lftp deploy example
- [x] T033 Implement deploy/deploy-lftp.sh (build on T002 stub): args host [user] [password]; lcd to project root/cm-client, mirror -R to /data/apps/store/data/cottage-monitoring; default ftp://apps@192.168.100.130 per quickstart
- [x] T034 Manual test checklist: deploy via lftp → config form (config-load, config-save, restart) → «Выгрузить в файл» → daemon connect → «Выгрузить в MQTT» → groupwrite → events/state in MQTT → cmd from API → ack (per quickstart.md + acceptance scenarios)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all user stories
- **Phase 3 (US1)**: Depends on Phase 2
- **Phase 4 (US2)**: Depends on Phase 2; US1 export-to-MQTT button works when US2 complete
- **Phase 5 (US3)**: Depends on Phase 4 (daemon must be connected, subscribed)
- **Phase 6 (US4)**: Depends on Phase 4
- **Phase 7 (Polish)**: Depends on Phases 3–6

### User Story Dependencies

- **US1**: No dependency on US2–US4; export-to-MQTT shows «недоступно» until US2
- **US2**: Blocks US3, US4 (cmd and rpc require connected daemon)
- **US3, US4**: Can run in parallel after US2

### Parallel Opportunities

- T003, T006 can run in parallel (README, icon)
- T030, T031, T032 can run in parallel in Phase 7
- T026–T028 (US4) can be implemented sequentially in same file

---

## Implementation Strategy

### MVP First (US1 + minimal US2)

1. Phase 1: Setup
2. Phase 2: Foundational
3. Phase 3: US1 (config, export to file, export to MQTT button stub)
4. Phase 4: US2 (daemon MQTT, telemetry, buffer, LWT) — at least connect + meta + snapshot + localbus
5. **STOP and VALIDATE**: Config works, export to file works, telemetry flows to server
6. Deploy to controller, test manually

### Incremental Delivery

1. Setup + Foundational → app shell
2. US1 → config + export to file (MVP config)
3. US2 → telemetry (core value)
4. US3 → commands (full control)
5. US4 → RPC (server refresh)
6. Polish → reconnect, throttle, deploy script

---

## Notes

- App name: `cottage-monitoring` (config.get, apps/request.lp)
- Daemon path on controller: `/data/apps/store/data/cottage-monitoring/daemon/daemon.lua` (after deploy)
- MQTT protocol: specs/001-server-mqtt-ingestor/contracts/mqtt-topics.md
- Lua libs: mosquitto, localbus, grp, json, config, encdec (require before use)
