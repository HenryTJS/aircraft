# -*- coding: utf-8 -*-
"""Run the 30-case P3 planner benchmark.

This is deliberately a *planner* benchmark first: it measures whether the
question is compiled into the right whitelisted plan, without paying the cost
of re-running every raw tool.  ``--api`` adds the end-to-end status check for
the cases that declare an expected API status (default: temporal cases only).

Usage:
    conda run --no-capture-output -n xjtushm python -m bench.run_bench
    conda run --no-capture-output -n xjtushm python -m bench.run_bench --mode both
    conda run --no-capture-output -n xjtushm python -m bench.run_bench --mode fallback --api --api-ids T01,T02
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web import app as webapp  # noqa: E402  (loads .env, exposes SUPPORTED)
from web import planner  # noqa: E402

CASES = ROOT / "bench" / "cases.json"
CATEGORIES = (
    "single_hop",
    "paraphrase",
    "multi_tool",
    "unknown",
    "temporal",
    "ambiguous",
    "wrong_premise",
    "unknown_data",
    "cross_case",
    "invalid_fusion",
    "multi_step",
    "modality_boundary",
    "report_audit",
    "wrong_tool",
)


def load_cases(path: Path | None = None) -> list[dict]:
    path = path or CASES
    with path.open(encoding="utf-8") as fh:
        cases = json.load(fh)
    if not cases:
        raise SystemExit(f"no cases in {path}")
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate case id")
    return cases


def _with_llm(enabled: bool):
    """Temporarily force the planner onto the fallback path."""
    saved = os.environ.get("SHM_LLM_BASE_URL")
    if not enabled:
        os.environ["SHM_LLM_BASE_URL"] = ""
    return saved


def _restore_llm(saved: str | None) -> None:
    if saved is None:
        os.environ.pop("SHM_LLM_BASE_URL", None)
    else:
        os.environ["SHM_LLM_BASE_URL"] = saved


def plan_one(case: dict, use_llm: bool) -> planner.PlannerResult:
    saved = _with_llm(use_llm)
    try:
        return planner.compile_question(
            case["question"], case["gid"], webapp.SUPPORTED
        )
    finally:
        _restore_llm(saved)


def score_plan(case: dict, result: planner.PlannerResult) -> dict:
    expected = case["expect"]
    plan = result.plan
    got_metrics = sorted(plan.metrics)
    want_metrics = sorted(expected.get("metrics", []))
    return {
        "id": case["id"],
        "category": case["category"],
        "gid": case["gid"],
        "question": case["question"],
        "source": result.source,
        "intent": plan.intent,
        "tool": plan.tool,
        "metrics": list(plan.metrics),
        "expected_intent": expected["intent"],
        "expected_tool": expected["tool"],
        "expected_metrics": expected.get("metrics", []),
        "intent_ok": plan.intent == expected["intent"],
        "tool_ok": plan.tool == expected["tool"],
        "metrics_ok": got_metrics == want_metrics,
        "planner_error": result.error,
    }


def api_one(client, case: dict) -> dict:
    try:
        response = client.get(
            "/api/ask",
            params={"gid": case["gid"], "t": case["t"], "q": case["question"]},
        )
    except Exception as exc:  # pragma: no cover - defensive for benchmark runs
        return {"status": "exception", "error": f"{type(exc).__name__}: {exc}"}
    if response.status_code == 404:
        return {"status": "http_404", "http_status": 404}
    try:
        body = response.json()
    except Exception:
        return {"status": "bad_json", "http_status": response.status_code}
    return {
        "status": body.get("status", "unknown"),
        "gate": body.get("gate"),
        "planner": body.get("planner"),
        "http_status": response.status_code,
        "checks": ((body.get("verification") or {}).get("checks")),
        "failed_checks": (body.get("verification") or {}).get("failed_checks"),
    }


def summarize(rows: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["category"]].append(row)
    out = []
    for category in CATEGORIES:
        items = grouped.get(category, [])
        if not items:
            continue
        status_items = [r for r in items if r.get("status_ok") is not None]
        out.append({
            "category": category,
            "n": len(items),
            "intent_ok": sum(bool(r["intent_ok"]) for r in items),
            "tool_ok": sum(bool(r["tool_ok"]) for r in items),
            "metrics_ok": sum(bool(r["metrics_ok"]) for r in items),
            "status_n": len(status_items),
            "status_ok": sum(bool(r["status_ok"]) for r in status_items),
        })
    status_items = [r for r in rows if r.get("status_ok") is not None]
    out.append({
        "category": "ALL",
        "n": len(rows),
        "intent_ok": sum(bool(r["intent_ok"]) for r in rows),
        "tool_ok": sum(bool(r["tool_ok"]) for r in rows),
        "metrics_ok": sum(bool(r["metrics_ok"]) for r in rows),
        "status_n": len(status_items),
        "status_ok": sum(bool(r["status_ok"]) for r in status_items),
    })
    return out


def pct(ok: int, n: int) -> str:
    return "-" if not n else f"{ok}/{n} ({ok / n:.0%})"


def print_table(mode: str, rows: list[dict]) -> None:
    print(f"\n## {mode}")
    print("| category | n | intent | tool | metrics | status |")
    print("|---|---:|---:|---:|---:|---:|")
    for item in summarize(rows):
        print(
            f"| {item['category']} | {item['n']} | "
            f"{pct(item['intent_ok'], item['n'])} | "
            f"{pct(item['tool_ok'], item['n'])} | "
            f"{pct(item['metrics_ok'], item['n'])} | "
            f"{pct(item['status_ok'], item['status_n'])} |"
        )
    failed = [r for r in rows if not (r["intent_ok"] and r["tool_ok"] and r["metrics_ok"])]
    if failed:
        print("\n规划失败：")
        for r in failed:
            print(
                f"- {r['id']} expected {r['expected_intent']}/{r['expected_tool']}/"
                f"{r['expected_metrics']} got {r['intent']}/{r['tool']}/{r['metrics']} "
                f"source={r['source']} :: {r['question']}"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("fallback", "llm", "both"), default="fallback")
    parser.add_argument("--api", action="store_true", help="run end-to-end status checks")
    parser.add_argument("--cases", default=str(CASES), help="case JSON path")
    parser.add_argument(
        "--api-ids",
        default="",
        help="comma-separated case ids for end-to-end checks; default temporal cases",
    )
    parser.add_argument("--out", default="", help="write JSON results to this path")
    args = parser.parse_args()

    cases = load_cases(Path(args.cases))
    if not args.api_ids:
        args.api_ids = ",".join(c["id"] for c in cases if c["category"] == "temporal")
    modes = ["fallback", "llm"] if args.mode == "both" else [args.mode]
    all_results = {}

    for mode in modes:
        use_llm = mode == "llm"
        rows = []
        for case in cases:
            result = plan_one(case, use_llm=use_llm)
            row = score_plan(case, result)
            row["status_ok"] = None
            rows.append(row)

        if args.api:
            wanted = {x.strip() for x in args.api_ids.split(",") if x.strip()}
            from fastapi.testclient import TestClient
            client = TestClient(webapp.app)
            for row in rows:
                if row["id"] not in wanted:
                    continue
                case = next(c for c in cases if c["id"] == row["id"])
                api = api_one(client, case)
                row["actual_status"] = api.get("status")
                row["expected_status"] = case["expect"].get("status")
                row["status_ok"] = api.get("status") == case["expect"].get("status")
                row["api"] = api

        print_table(mode, rows)
        all_results[mode] = {"rows": rows, "summary": summarize(rows)}

    if args.out:
        out = Path(args.out)
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
