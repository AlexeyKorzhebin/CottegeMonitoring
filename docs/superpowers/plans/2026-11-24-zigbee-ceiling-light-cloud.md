# Zigbee ceiling light params — cloud / HA / MCP

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax.

**Goal:** Semantic facade (ops/MCP/HA) over LM GA SoT for ceiling brightness/CCT/RGB.

**Architecture:** See design §4 + §12 in `docs/superpowers/specs/2026-11-24-zigbee-ceiling-light-params-design.md`. Cloud mirrors `current_state`; writes only control GAs on LM.

**Tech Stack:** Python FastAPI ops/MCP, HA custom component, catalog JSON from cm-client.

---

### Task 1: Server roles + catalog map + list/set_lights

- [ ] ObjectRole `LIGHT_PARAM_CONTROL` / `LIGHT_PARAM_STATUS` for GA `36/1/*` and `36/2/*` in `object_resolver.py`
- [ ] `ceiling_light_params.py` loads `cm-client/scripts/zb_ceiling_light_catalog.json` → relay_ga → params
- [ ] `list_lights` enriches from **status** GA; `set_lights`/`set_light` write **control** GA (+ relay); params schema + catalog descriptions
- [ ] Unit tests + update `test_ops_drift.py` schema assert
- [ ] Do **not** git commit unless user asked

### Task 2: Home Assistant facade

- [ ] `LightItem` + ColorModes; commands → set_lights with params; tests
- [ ] No commit unless asked

### Task 3: Specs

- [ ] 001/002 quickstart + skill note; force_export for `36/*`

### Task 4: Deploy + verify

- [ ] Server deploy; LM force_export; verify list/set against live GAs
