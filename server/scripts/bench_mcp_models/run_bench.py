#!/usr/bin/env python3
"""Benchmark Caila models on CottageMonitoring MCP tool selection / full agent loop.

Modes:
  (default) model-only — LLM latency + tool selection; MCP never contacted.
  --e2e — full agent loop via mcporter alias with X-Cottage-Dry-Run (resolve+DB,
           MQTT publish skipped). Safe for prod timing.

Example (on elion as openclaw):
  set -a; source ~/.openclaw/secrets/llms.env; set +a
  export PATH=$HOME/.npm-global/bin:$PATH
  cd ~/.openclaw/workspace/cottage-mcp-bench
  python3 run_bench.py --e2e --mcp-alias cottage-dry --out results/e2e.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

# OpenAI-style tool schemas mirroring cottage MCP (keep in sync with mcp/server.py).
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_house_status",
            "description": "Online status, last_seen, object counts for the authenticated house.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discover",
            "description": "Find objects by name/query and kind: light, temp, climate, sensor, energy, heating, appliance, all.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "kind": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_temperature",
            "description": "Room air / floor / outdoor temperatures.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sensors",
            "description": "Read sensors by kind or query.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "kind": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_lights",
            "description": "List lights with current on/off state.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_light",
            "description": "Turn a single light on or off by room/name query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "on": {"type": "boolean"},
                },
                "required": ["query", "on"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_lights",
            "description": (
                "Turn multiple lights on/off in one MQTT batch. Use for zones: "
                "«весь свет», «1 этаж», «уличное». Prefer over looping set_light."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "on": {"type": "boolean"},
                    "skip_unchanged": {"type": "boolean"},
                },
                "required": ["query", "on"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_climate",
            "description": "Underfloor heating status: setpoints, temps, relays, auto algorithm.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_climate",
            "description": (
                "Set underfloor heating setpoint (°C) for a room. Does not force relay. "
                "Use force_relay only for debug."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "setpoint_c": {"type": "number"},
                    "force_relay": {"type": ["boolean", "null"]},
                },
                "required": ["query", "setpoint_c"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_energy_status",
            "description": "Electricity: power, phases, consumption.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_heating_diagnostics",
            "description": "Warm floor diagnostics and auto algorithm state.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_kettle",
            "description": "BLE teapot status summary.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_kettle",
            "description": "Control BLE teapot on/off.",
            "parameters": {
                "type": "object",
                "properties": {"on": {"type": "boolean"}},
                "required": ["on"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_command_status",
            "description": "Poll command status by request_id after writes.",
            "parameters": {
                "type": "object",
                "properties": {"request_id": {"type": "string"}},
                "required": ["request_id"],
            },
        },
    },
]

READ_TOOLS = {
    "get_house_status",
    "discover",
    "get_temperature",
    "get_sensors",
    "list_lights",
    "get_climate",
    "get_energy_status",
    "get_heating_diagnostics",
    "get_kettle",
    "get_command_status",
}


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class Score:
    verdict: str  # pass | partial | fail | error
    score: float  # 0..1
    reasons: list[str] = field(default_factory=list)


@dataclass
class RunResult:
    model_id: str
    model_label: str
    scenario_id: str
    prompt: str
    llm_ms: float
    mcp_ms: float | None
    tool_calls: list[dict[str, Any]]
    assistant_text: str | None
    score: dict[str, Any]
    usage: dict[str, Any] | None
    error: str | None = None
    mcp_results: list[dict[str, Any]] = field(default_factory=list)
    wall_ms: float | None = None
    turns: int = 1
    # Wall ms until first write tool returns (would be MQTT publish moment).
    ms_to_command: float | None = None
    # Wall ms until final assistant text (no more tool calls).
    ms_to_final_text: float | None = None
    turn_timings: list[dict[str, Any]] = field(default_factory=list)


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--models", type=Path, default=HERE / "models.json")
    p.add_argument("--scenarios", type=Path, default=HERE / "scenarios.json")
    p.add_argument("--system-prompt", type=Path, default=HERE / "system_prompt.txt")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--model", action="append", default=[], help="Filter by label or id substring")
    p.add_argument("--scenario", action="append", default=[], help="Filter by scenario id")
    p.add_argument("--tier", action="append", default=[], help="Filter models by tier")
    p.add_argument(
        "--e2e",
        action="store_true",
        help="Full agent loop via MCP. Requires --mcp-alias with X-Cottage-Dry-Run (MQTT skipped).",
    )
    p.add_argument(
        "--execute-reads",
        action="store_true",
        help="Single-turn: execute only read tools via mcporter (no writes).",
    )
    p.add_argument("--mcp-alias", default="cottage-dry", help="mcporter server alias (use cottage-dry for e2e)")
    p.add_argument("--max-turns", type=int, default=3, help="Max agent turns in --e2e")
    p.add_argument("--max-tokens", type=int, default=512)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--sleep", type=float, default=0.4, help="Pause between model calls")
    p.add_argument("--dry-run-models", action="store_true", help="Print planned matrix and exit")
    return p.parse_args(argv)


def _uses_max_completion_tokens(model: str) -> bool:
    m = model.lower()
    return any(
        x in m
        for x in (
            "/gpt-5",
            "openai-proxy/gpt-5",
            "openrouter-proxy/openai/gpt-5",
            "/o1",
            "/o3",
            "/o4",
        )
    )


def _omit_temperature(model: str) -> bool:
    m = model.lower()
    # Several GPT-5 chat/mini endpoints only accept default temperature=1.
    return bool(re.search(r"gpt-5(?:\.|-)?(?:mini|nano|codex)?(?:$|/)", m)) or "/o1" in m or "/o3" in m


def caila_chat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> tuple[dict[str, Any], float]:
    url = base_url.rstrip("/") + "/chat/completions"
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
    }
    if not _omit_temperature(model):
        body["temperature"] = temperature
    if _uses_max_completion_tokens(model):
        body["max_completion_tokens"] = max_tokens
    else:
        body["max_tokens"] = max_tokens
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e
    elapsed_ms = (time.perf_counter() - t0) * 1000
    data = json.loads(raw.decode("utf-8"))
    return data, elapsed_ms


def extract_tool_calls(message: dict[str, Any]) -> list[ToolCall]:
    out: list[ToolCall] = []
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function") or {}
        name = fn.get("name") or ""
        args_raw = fn.get("arguments") or "{}"
        if isinstance(args_raw, dict):
            args = args_raw
        else:
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                args = {"_raw": args_raw}
        if not isinstance(args, dict):
            args = {"_value": args}
        out.append(ToolCall(name=name, arguments=args))
    return out


def _query_matches(query: Any, needles: list[str]) -> bool:
    q = "" if query is None else str(query).lower()
    if "" in needles:
        # empty needle means any non-empty query is ok, OR empty query ok for "all house"
        return True
    return any(n.lower() in q for n in needles if n)


def score_run(scenario: dict[str, Any], calls: list[ToolCall], assistant_text: str | None) -> Score:
    expect = scenario.get("expect") or {}
    primary = expect.get("primary_tool")
    forbidden = set(expect.get("forbidden_tools") or [])
    allow_prefix = set(expect.get("allow_prefix_tools") or [])
    allow_clarify = bool(expect.get("allow_clarify"))
    bonus = set(expect.get("bonus_tools") or [])
    args_expect = expect.get("args") or {}
    reasons: list[str] = []

    names = [c.name for c in calls]
    for name in names:
        if name in forbidden:
            return Score("fail", 0.0, [f"forbidden tool: {name}"])

    if not calls:
        text = (assistant_text or "").strip()
        if allow_clarify and text:
            return Score("partial", 0.55, ["no tool call; clarified in text"])
        return Score("fail", 0.0, ["no tool calls"])

    # Prefer first non-prefix tool as the action tool.
    action_idx = 0
    for i, c in enumerate(calls):
        if c.name not in allow_prefix:
            action_idx = i
            break
    action = calls[action_idx]

    if primary and action.name != primary:
        # Parallel tools: primary anywhere in first response is acceptable for reports.
        if primary in names and scenario.get("category") == "read_report":
            reasons.append(f"primary {primary} present among {[c.name for c in calls]}")
            action = next(c for c in calls if c.name == primary)
        elif allow_clarify and all(n in allow_prefix for n in names):
            return Score(
                "partial",
                0.6,
                [f"only clarifying/prefix tools {names}; no {primary} yet"],
            )
        else:
            return Score(
                "fail",
                0.15,
                [f"expected primary={primary}, got action={action.name} calls={names}"],
            )

    score = 1.0

    if "on" in args_expect:
        got = action.arguments.get("on")
        if got is not args_expect["on"]:
            return Score("fail", 0.1, [f"on expected {args_expect['on']}, got {got}"])

    if "setpoint_c" in args_expect:
        got = action.arguments.get("setpoint_c")
        try:
            ok = abs(float(got) - float(args_expect["setpoint_c"])) < 0.51
        except (TypeError, ValueError):
            ok = False
        if not ok:
            return Score("fail", 0.2, [f"setpoint_c expected ~{args_expect['setpoint_c']}, got {got}"])

    if args_expect.get("force_relay_not_true"):
        fr = action.arguments.get("force_relay")
        if fr is True:
            return Score("fail", 0.25, ["force_relay=true is not allowed"])

    if "query_any_of" in expect:
        if not _query_matches(action.arguments.get("query"), expect["query_any_of"]):
            score -= 0.25
            reasons.append(f"query weak: {action.arguments.get('query')!r}")

    if bonus:
        hit = bonus.intersection(names)
        if hit:
            reasons.append(f"bonus tools: {sorted(hit)}")
            score = min(1.0, score + 0.05 * len(hit))

    if action_idx > 0:
        reasons.append(f"prefix tools before action: {names[:action_idx]}")
        score = min(score, 0.9)

    verdict = "pass" if score >= 0.85 else "partial"
    if not reasons:
        reasons.append("ok")
    return Score(verdict, round(max(0.0, min(1.0, score)), 3), reasons)


def mcporter_call(alias: str, name: str, arguments: dict[str, Any], timeout: float) -> tuple[Any, float]:
    cmd = ["mcporter", "call", f"{alias}.{name}"]
    for k, v in arguments.items():
        if isinstance(v, bool):
            cmd.append(f"{k}={'true' if v else 'false'}")
        elif v is None:
            continue
        else:
            cmd.append(f"{k}={v}")
    env = os.environ.copy()
    t0 = time.perf_counter()
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        cwd=str(Path.home() / ".openclaw" / "workspace"),
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}")
    text = proc.stdout.strip()
    try:
        return json.loads(text), elapsed_ms
    except json.JSONDecodeError:
        return {"raw": text}, elapsed_ms


def filter_models(models: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    out = models
    if args.tier:
        tiers = {t.lower() for t in args.tier}
        out = [m for m in out if str(m.get("tier", "")).lower() in tiers]
    if args.model:
        needles = [n.lower() for n in args.model]
        out = [
            m
            for m in out
            if any(n in m["id"].lower() or n in m.get("label", "").lower() for n in needles)
        ]
    return out


def filter_scenarios(scenarios: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    if not args.scenario:
        return scenarios
    want = {s.lower() for s in args.scenario}
    return [s for s in scenarios if s["id"].lower() in want]


def summarize(results: list[RunResult]) -> dict[str, Any]:
    by_model: dict[str, list[RunResult]] = {}
    for r in results:
        by_model.setdefault(r.model_label, []).append(r)

    rows = []
    for label, items in by_model.items():
        scores = [i.score["score"] for i in items if i.error is None]
        llm = [i.llm_ms for i in items if i.error is None]
        mcp = [i.mcp_ms for i in items if i.mcp_ms is not None]
        wall = [i.wall_ms for i in items if i.wall_ms is not None and i.error is None]
        passes = sum(1 for i in items if i.score.get("verdict") == "pass")
        fails = sum(1 for i in items if i.score.get("verdict") == "fail" or i.error)
        rows.append(
            {
                "model": label,
                "n": len(items),
                "pass": passes,
                "fail": fails,
                "avg_score": round(sum(scores) / len(scores), 3) if scores else None,
                "avg_llm_ms": round(sum(llm) / len(llm)) if llm else None,
                "p50_llm_ms": round(sorted(llm)[len(llm) // 2]) if llm else None,
                "avg_mcp_ms": round(sum(mcp) / len(mcp)) if mcp else None,
                "avg_wall_ms": round(sum(wall) / len(wall)) if wall else None,
                "errors": sum(1 for i in items if i.error),
            }
        )
    rows.sort(key=lambda r: (-(r["avg_score"] or -1), r["avg_wall_ms"] or r["avg_llm_ms"] or 10**9))
    return {"by_model": rows}


def print_table(summary: dict[str, Any]) -> None:
    rows = summary["by_model"]
    if not rows:
        print("No results")
        return
    hdr = (
        f"{'model':28} {'score':>6} {'pass':>5} {'fail':>5} "
        f"{'wall_ms':>8} {'llm_ms':>8} {'mcp_ms':>8} {'err':>4}"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(
            f"{r['model'][:28]:28} "
            f"{(r['avg_score'] if r['avg_score'] is not None else float('nan')):6.3f} "
            f"{r['pass']:5d} {r['fail']:5d} "
            f"{(r['avg_wall_ms'] if r['avg_wall_ms'] is not None else -1):8d} "
            f"{(r['avg_llm_ms'] or 0):8d} "
            f"{(r['avg_mcp_ms'] if r['avg_mcp_ms'] is not None else -1):8d} "
            f"{r['errors']:4d}"
        )


def _message_tool_calls_openai(calls: list[ToolCall], raw_message: dict[str, Any]) -> dict[str, Any]:
    """Preserve provider tool_call ids when present; synthesize otherwise."""
    existing = raw_message.get("tool_calls") or []
    out_calls = []
    for i, call in enumerate(calls):
        src = existing[i] if i < len(existing) else {}
        tc_id = src.get("id") or f"call_{i}"
        args = call.arguments
        out_calls.append(
            {
                "id": tc_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(args, ensure_ascii=False),
                },
            }
        )
    msg: dict[str, Any] = {"role": "assistant", "tool_calls": out_calls}
    if raw_message.get("content"):
        msg["content"] = raw_message["content"]
    return msg


def run_e2e_case(
    *,
    base_url: str,
    api_key: str,
    model: dict[str, Any],
    scenario: dict[str, Any],
    system: str,
    args: argparse.Namespace,
) -> RunResult:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": scenario["prompt"]},
    ]
    all_calls: list[ToolCall] = []
    mcp_results: list[dict[str, Any]] = []
    turn_timings: list[dict[str, Any]] = []
    llm_ms_total = 0.0
    mcp_ms_total = 0.0
    usage_acc: dict[str, int] = {}
    last_text: str | None = None
    turns = 0
    ms_to_command: float | None = None
    ms_to_final_text: float | None = None
    wall0 = time.perf_counter()

    for turn in range(args.max_turns):
        turns = turn + 1
        data, llm_ms = caila_chat(
            base_url=base_url,
            api_key=api_key,
            model=model["id"],
            messages=messages,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            timeout=args.timeout,
        )
        llm_ms_total += llm_ms
        for k, v in (data.get("usage") or {}).items():
            if isinstance(v, int):
                usage_acc[k] = usage_acc.get(k, 0) + v

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        calls = extract_tool_calls(message)
        last_text = message.get("content")
        turn_timings.append(
            {
                "turn": turns,
                "llm_ms": round(llm_ms),
                "tools": [c.name for c in calls],
                "has_text": bool((last_text or "").strip()),
                "wall_ms": round((time.perf_counter() - wall0) * 1000),
            }
        )
        if not calls:
            ms_to_final_text = (time.perf_counter() - wall0) * 1000
            break

        all_calls.extend(calls)
        messages.append(_message_tool_calls_openai(calls, message))
        raw_tcs = message.get("tool_calls") or []
        for i, call in enumerate(calls):
            tc_id = (raw_tcs[i] or {}).get("id") if i < len(raw_tcs) else f"call_{i}"
            try:
                payload, mcp_ms = mcporter_call(
                    args.mcp_alias, call.name, call.arguments, timeout=args.timeout
                )
                mcp_ms_total += mcp_ms
                if call.name.startswith("set_") and isinstance(payload, dict):
                    if payload.get("status") == "sent":
                        raise RuntimeError(
                            f"Refusing live MQTT path: {call.name} status=sent "
                            f"payload={str(payload)[:200]}"
                        )
                    if ms_to_command is None:
                        # Moment command is ready (dry_run == would-have-published).
                        ms_to_command = (time.perf_counter() - wall0) * 1000
                preview = payload if isinstance(payload, dict) else {"raw": payload}
                content = json.dumps(payload, ensure_ascii=False, default=str)[:4000]
                mcp_results.append(
                    {
                        "tool": call.name,
                        "args": call.arguments,
                        "mcp_ms": round(mcp_ms),
                        "ok": True,
                        "result_preview": str(payload)[:240],
                        "status": preview.get("status") if isinstance(preview, dict) else None,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                content = json.dumps({"status": "error", "error": str(exc)[:400]}, ensure_ascii=False)
                mcp_results.append(
                    {
                        "tool": call.name,
                        "args": call.arguments,
                        "ok": False,
                        "error": str(exc)[:400],
                    }
                )
            messages.append({"role": "tool", "tool_call_id": tc_id, "content": content})

    wall_ms = (time.perf_counter() - wall0) * 1000
    if ms_to_final_text is None and last_text:
        ms_to_final_text = wall_ms
    scored = score_run(scenario, all_calls, last_text)
    return RunResult(
        model_id=model["id"],
        model_label=model["label"],
        scenario_id=scenario["id"],
        prompt=scenario["prompt"],
        llm_ms=round(llm_ms_total),
        mcp_ms=round(mcp_ms_total),
        tool_calls=[asdict(c) for c in all_calls],
        assistant_text=last_text,
        score=asdict(scored),
        usage=usage_acc or None,
        mcp_results=mcp_results,
        wall_ms=round(wall_ms),
        turns=turns,
        ms_to_command=round(ms_to_command) if ms_to_command is not None else None,
        ms_to_final_text=round(ms_to_final_text) if ms_to_final_text is not None else None,
        turn_timings=turn_timings,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    api_key = os.environ.get("CAILA_API_KEY", "").strip()
    if not api_key and not args.dry_run_models:
        print("CAILA_API_KEY is required (source ~/.openclaw/secrets/llms.env)", file=sys.stderr)
        return 2

    if args.e2e and args.mcp_alias in ("cottage", "cottage-dev"):
        print(
            "Refusing --e2e with live alias "
            f"{args.mcp_alias!r}. Use --mcp-alias cottage-dry (X-Cottage-Dry-Run).",
            file=sys.stderr,
        )
        return 2

    models_cfg = load_json(args.models)
    scenarios_cfg = load_json(args.scenarios)
    system = args.system_prompt.read_text(encoding="utf-8").strip()
    base_url = models_cfg.get("caila_base_url") or "https://caila.io/api/adapters/openai/v1"
    models = filter_models(models_cfg["models"], args)
    scenarios = filter_scenarios(scenarios_cfg["scenarios"], args)

    if not models or not scenarios:
        print("Nothing to run after filters", file=sys.stderr)
        return 2

    mode = "e2e-dry-run" if args.e2e else ("execute-reads" if args.execute_reads else "model-only")
    print(f"Mode: {mode}")
    print(f"Models ({len(models)}): " + ", ".join(m["label"] for m in models))
    print(f"Scenarios ({len(scenarios)}): " + ", ".join(s["id"] for s in scenarios))
    if args.dry_run_models:
        return 0

    results: list[RunResult] = []
    for model in models:
        for scenario in scenarios:
            print(f"→ {model['label']} :: {scenario['id']} …", flush=True)
            try:
                if args.e2e:
                    result = run_e2e_case(
                        base_url=base_url,
                        api_key=api_key,
                        model=model,
                        scenario=scenario,
                        system=system,
                        args=args,
                    )
                    results.append(result)
                    print(
                        f"  {result.score['verdict']} score={result.score['score']} "
                        f"wall={result.wall_ms}ms llm={result.llm_ms}ms mcp={result.mcp_ms}ms "
                        f"turns={result.turns} tools={[c['name'] for c in result.tool_calls]}"
                    )
                    if result.ms_to_command is not None:
                        print(f"  → ms_to_command (would MQTT): {result.ms_to_command} ms")
                    if result.ms_to_final_text is not None:
                        print(f"  → ms_to_final_text: {result.ms_to_final_text} ms")
                    for t in result.turn_timings:
                        print(
                            f"     turn{t['turn']}: llm={t['llm_ms']}ms "
                            f"tools={t['tools']} wall={t['wall_ms']}ms"
                        )
                else:
                    data, llm_ms = caila_chat(
                        base_url=base_url,
                        api_key=api_key,
                        model=model["id"],
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": scenario["prompt"]},
                        ],
                        max_tokens=args.max_tokens,
                        temperature=args.temperature,
                        timeout=args.timeout,
                    )
                    choice = (data.get("choices") or [{}])[0]
                    message = choice.get("message") or {}
                    calls = extract_tool_calls(message)
                    text = message.get("content")
                    scored = score_run(scenario, calls, text)

                    mcp_ms_total = 0.0
                    mcp_results: list[dict[str, Any]] = []
                    if args.execute_reads:
                        for call in calls:
                            if call.name not in READ_TOOLS:
                                continue
                            try:
                                payload, mcp_ms = mcporter_call(
                                    args.mcp_alias, call.name, call.arguments, timeout=args.timeout
                                )
                                mcp_ms_total += mcp_ms
                                mcp_results.append(
                                    {
                                        "tool": call.name,
                                        "args": call.arguments,
                                        "mcp_ms": round(mcp_ms),
                                        "ok": True,
                                        "result_preview": str(payload)[:240],
                                    }
                                )
                            except Exception as exc:  # noqa: BLE001
                                mcp_results.append(
                                    {
                                        "tool": call.name,
                                        "args": call.arguments,
                                        "ok": False,
                                        "error": str(exc)[:400],
                                    }
                                )

                    results.append(
                        RunResult(
                            model_id=model["id"],
                            model_label=model["label"],
                            scenario_id=scenario["id"],
                            prompt=scenario["prompt"],
                            llm_ms=round(llm_ms),
                            mcp_ms=round(mcp_ms_total) if args.execute_reads else None,
                            tool_calls=[asdict(c) for c in calls],
                            assistant_text=text,
                            score=asdict(scored),
                            usage=data.get("usage"),
                            mcp_results=mcp_results,
                            wall_ms=round(llm_ms),
                            turns=1,
                        )
                    )
                    print(
                        f"  {scored.verdict} score={scored.score} llm={llm_ms:.0f}ms "
                        f"tools={[c.name for c in calls]}"
                    )
            except Exception as exc:  # noqa: BLE001
                results.append(
                    RunResult(
                        model_id=model["id"],
                        model_label=model["label"],
                        scenario_id=scenario["id"],
                        prompt=scenario["prompt"],
                        llm_ms=0,
                        mcp_ms=None,
                        tool_calls=[],
                        assistant_text=None,
                        score={"verdict": "error", "score": 0.0, "reasons": [str(exc)[:300]]},
                        usage=None,
                        error=str(exc)[:500],
                    )
                )
                print(f"  ERROR {exc}")
            time.sleep(args.sleep)

    summary = summarize(results)
    payload = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "host": os.uname().nodename if hasattr(os, "uname") else "",
        "mode": mode,
        "mcp_alias": args.mcp_alias if args.e2e or args.execute_reads else None,
        "caila_base_url": base_url,
        "summary": summary,
        "results": [asdict(r) for r in results],
    }

    out = args.out
    if out is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = HERE / "results" / f"bench_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = out.parent / "latest.json"
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print_table(summary)
    if args.e2e:
        print("\nPer-command timing (e2e dry-run):")
        print(
            f"{'model':22} {'scenario':22} {'cmd_ms':>8} {'final_ms':>9} "
            f"{'wall':>8} {'turns':>5}  tools"
        )
        for r in results:
            tools = ",".join(c["name"] for c in r.tool_calls) or "-"
            print(
                f"{r.model_label[:22]:22} {r.scenario_id[:22]:22} "
                f"{(r.ms_to_command if r.ms_to_command is not None else -1):8d} "
                f"{(r.ms_to_final_text if r.ms_to_final_text is not None else -1):9d} "
                f"{(r.wall_ms or 0):8d} {r.turns:5d}  {tools}"
            )
    print(f"\nWrote {out}")
    print(f"Wrote {latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
