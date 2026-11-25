# -*- coding: utf-8 -*-
"""Compare a bare chat model with the evidence-constrained system.

The bare model gets the question only.  The system gets the same question
through ``/api/ask``, with its normal planner, tools and verifier.  This is a
small qualitative comparison, not a leaderboard: it records whether the bare
answer contains a numeric claim, whether it explicitly refuses, and what the
system actually returned.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web import app as webapp  # noqa: E402
from web import planner  # noqa: E402

CASES = ROOT / "bench" / "hard_cases.json"
RESULTS = ROOT / "bench" / "results"

_PERCENT = re.compile(r"\d+(?:\.\d+)?\s*%")
_METRIC = re.compile(r"\b(?:t50|t85)\b\s*(?:[=:：]|是|为)?\s*\d+(?:\.\d+)?", re.I)
_REFUSE = ("不能", "无法", "没有数据", "没有足够", "不确定", "无法确认", "不能确认", "缺少")


def load_cases(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        cases = json.load(fh)
    if not cases:
        raise SystemExit(f"no cases in {path}")
    return cases


def bare_answer(question: str, timeout: float = 60.0) -> dict:
    base, model, key = planner._llm_config()
    if not base:
        return {"ok": False, "error": "SHM_LLM_BASE_URL is not configured", "answer": ""}
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 320,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是飞行器结构健康监测助手。只根据用户给出的信息回答。"
                    "不能计算、没有数据或问题缺少指代对象时，明确说不能，不要编造数值。"
                ),
            },
            {"role": "user", "content": question},
        ],
    }
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.post(planner._endpoint(base), headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
        content = body["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "answer": ""}
    return {"ok": True, "model": model, "answer": content}


def system_answer(client: TestClient, case: dict) -> dict:
    try:
        response = client.get(
            "/api/ask",
            params={"gid": case["gid"], "t": case["t"], "q": case["question"]},
        )
    except Exception as exc:
        return {"status": "exception", "error": f"{type(exc).__name__}: {exc}"}
    if response.status_code == 404:
        return {"status": "http_404", "http_status": 404}
    try:
        body = response.json()
    except Exception:
        return {"status": "bad_json", "http_status": response.status_code}
    graph = body.get("graph") or {}
    claims = graph.get("claims") or []
    return {
        "status": body.get("status", "unknown"),
        "gate": body.get("gate"),
        "answer": body.get("answer", ""),
        "message": body.get("message", ""),
        "planner": body.get("planner"),
        "n_claims": len(claims),
        "claim_statuses": [c.get("status") for c in claims],
        "claim_values": [
            {"id": c.get("id"), "predicate": c.get("predicate"), "value": c.get("value"), "status": c.get("status")}
            for c in claims
        ],
        "failed_checks": (body.get("verification") or {}).get("failed_checks") or [],
        "http_status": response.status_code,
    }


def flags(answer: str) -> dict:
    text = answer or ""
    return {
        "has_percent": bool(_PERCENT.search(text)),
        "has_metric_value": bool(_METRIC.search(text)),
        "refused": any(word in text for word in _REFUSE),
    }


def truncate(text: str, limit: int = 140) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(CASES))
    parser.add_argument("--out", default=str(RESULTS / "api_vs_system.json"))
    parser.add_argument("--md", default=str(RESULTS / "api_vs_system.md"))
    parser.add_argument("--no-bare", action="store_true", help="skip bare model calls")
    args = parser.parse_args()

    cases = load_cases(Path(args.cases))
    client = TestClient(webapp.app)
    rows = []
    for case in cases:
        print(f"[{case['id']}] {case['question']}", flush=True)
        bare = {"ok": False, "answer": "", "error": "skipped"} if args.no_bare else bare_answer(case["question"])
        system = system_answer(client, case)
        bf = flags(bare.get("answer", ""))
        rows.append({
            "id": case["id"],
            "category": case["category"],
            "gid": case["gid"],
            "t": case["t"],
            "question": case["question"],
            "expect": case["expect"],
            "why": case["why"],
            "bare": {**bare, **bf},
            "system": system,
        })

    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"model": planner._llm_config()[1], "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    md = Path(args.md)
    if not md.is_absolute():
        md = ROOT / md
    lines = [
        "# Bare API vs evidence-constrained system",
        "",
        f"Model: `{planner._llm_config()[1]}`. `has_percent` / `has_metric_value` are lexical flags, not correctness scores.",
        "",
        "| id | category | bare numeric | bare refused | system status | system claims | system answer |",
        "|---|---|---:|---:|---|---:|---|",
    ]
    for row in rows:
        bare = row["bare"]
        system = row["system"]
        numeric = "yes" if (bare.get("has_percent") or bare.get("has_metric_value")) else "no"
        refused = "yes" if bare.get("refused") else "no"
        claims = system.get("n_claims", 0)
        lines.append(
            f"| {row['id']} | {row['category']} | {numeric} | {refused} | "
            f"{system.get('status')} | {claims} | {truncate(system.get('answer') or system.get('message') or '')} |"
        )
    lines += ["", "## Bare answers", ""]
    for row in rows:
        bare = row["bare"]
        lines.append(f"### {row['id']} {row['question']}")
        lines.append("")
        lines.append(f"- bare: {truncate(bare.get('answer') or bare.get('error') or '', 500)}")
        lines.append(f"- system: `{row['system'].get('status')}` {truncate(row['system'].get('answer') or row['system'].get('message') or '', 500)}")
        lines.append("")
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text("\n".join(lines), encoding="utf-8")

    print(f"\nwrote {out}")
    print(f"wrote {md}")
    print("\n| id | bare numeric | bare refused | system | claims |")
    print("|---|---:|---:|---|---:|")
    for row in rows:
        bare = row["bare"]
        system = row["system"]
        numeric = "yes" if (bare.get("has_percent") or bare.get("has_metric_value")) else "no"
        refused = "yes" if bare.get("refused") else "no"
        print(f"| {row['id']} | {numeric} | {refused} | {system.get('status')} | {system.get('n_claims', 0)} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
