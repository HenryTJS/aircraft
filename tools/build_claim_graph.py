# -*- coding: utf-8 -*-
"""Build a claim–evidence graph from the raw metric (no hand-written numbers).

The graph binds each `tool_result` evidence to a `tool_call`; `validate.py`
re-executes that tool and rejects the graph if the value does not reproduce.

Usage:
    python tools/build_claim_graph.py --gid L1-06 --out examples/L1-06_t85.json
    python tools/build_claim_graph.py --gid L1-06 --t-max 0.62 \\
        --out examples/L1-06_t85_at062.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def run_metric(gid: str, dataset: str = "L1") -> tuple[dict, float]:
    cmd = [sys.executable, str(ROOT / "skills" / "metric" / "run.py"),
           "--dataset", dataset, "--gid", gid, "--json"]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", timeout=600)
    elapsed = (time.time() - t0) * 1000.0
    try:
        obj = json.loads(p.stdout)
    except Exception as exc:
        raise SystemExit(f"metric output is not JSON:\n{p.stdout[:500]}\n{p.stderr[:500]}") from exc
    if obj.get("status") != "ok":
        raise SystemExit(f"metric status={obj.get('status')}: "
                         f"{obj.get('data', {}).get('reason', '')}")
    return obj["data"], elapsed


def build(gid: str, t_max: float, dataset: str = "L1") -> dict:
    data, elapsed = run_metric(gid, dataset)
    if not (0.0 <= t_max <= 1.0):
        raise SystemExit("--t-max must be in [0, 1]")
    n_f = int(data["n_f"])
    coverage = 1.0
    convention = "linear,600s,load-mask"
    scope = {
        "gid": gid,
        "campaign": None,
        "modality": "AE",
        "cycle_min": 0,
        "cycle_max": n_f,
        "lifetime_min": 0,
        "lifetime_max": 1,
    }

    tool = {
        "tool_call_id": "T001",
        "tool_name": "metric.l1_t85",
        "arguments": {"dataset": dataset, "gid": gid, "frame_s": 600, "convention": convention},
        "result": {
            "t50_pct": data["t50_pct"],
            "t85_pct": data["t85_pct"],
            "n_f": n_f,
            "hits": int(data["hits"]),
            "n_frames": int(data["n_frames"]),
            "coverage": coverage,
        },
        "created_at": _now(),
        "elapsed_ms": round(elapsed, 1),
    }

    def evidence(eid: str, metric: str, value: float) -> dict:
        return {
            "evidence_id": eid,
            "evidence_type": "tool_result",
            "source": {
                "kind": "tool",
                "title": f"{gid} raw AE+FBG ({convention})",
                "tool_name": "metric.l1_t85",
                "version": "0.1.0",
                "authors": [],
                "year": None,
                "venue": None,
                "doi": None,
                "url": None,
                "clause": None,
            },
            "content": {
                "metric": metric,
                "value": value,
                "gid": gid,
                "n_f": n_f,
                "convention": convention,
                "coverage": coverage,
            },
            "quote": None,
            "locator": {
                "file": data["raw_ae"],
                "page": None,
                "section": None,
                "table": None,
                "figure": None,
                "row": None,
                "clause": None,
                "char_start": None,
                "char_end": None,
            },
            "scope": scope,
            "observed_lifetime_fraction": 1.0,
            "tool_call_id": "T001",
            "coverage": coverage,
            "retrieved_at": _now(),
            "content_hash": None,
            "reliability": "primary",
        }

    def claim(cid: str, metric: str, value: float, label: str) -> dict:
        return {
            "claim_id": cid,
            "text": f"{gid} 的 AE 累积 hit 曲线 {label} 为 {value:.2f}%。",
            "claim_type": "numeric",
            "subject": gid,
            "predicate": metric,
            "value": round(float(value), 2),
            "unit": "%",
            "comparator": "eq",
            "tolerance": 0.01,
            "status": "supported",
            "evidence_ids": ["E001" if metric == "t85_pct" else "E002"],
            "tool_call_ids": ["T001"],
            "scope": scope,
            "allowed_lifetime_max": t_max,
            "missing_evidence": None,
            "confidence": 0.99,
            "created_by": "Analyst",
        }

    return {
        "schema_version": "1.0",
        "graph_id": "G001",
        "question": (f"{gid} 的 t50 / t85 是多少？"
                     f"在只看到寿命前 {t_max:.0%} 数据时，这个结论是否成立？"),
        "created_at": _now(),
        "policy": {
            "require_evidence": True,
            "allow_unsupported_claims": False,
            "max_evidence_per_claim": 8,
            "temporal_leakage_check": True,
            "require_numeric_tool_evidence": True,
        },
        "claims": [
            claim("C001", "t85_pct", data["t85_pct"], "t85"),
            claim("C002", "t50_pct", data["t50_pct"], "t50"),
        ],
        "evidence": [
            evidence("E001", "t85_pct", data["t85_pct"]),
            evidence("E002", "t50_pct", data["t50_pct"]),
        ],
        "edges": [
            {"claim_id": "C001", "evidence_id": "E001", "relation": "supports"},
            {"claim_id": "C002", "evidence_id": "E002", "relation": "supports"},
        ],
        "tool_calls": [tool],
        "verification": {"status": "needs_review",
                         "summary": "populated by validate.py", "checks": []},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gid", required=True)
    ap.add_argument("--dataset", default="L1")
    ap.add_argument("--t-max", type=float, default=1.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    graph = build(args.gid, args.t_max, args.dataset)
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"wrote {out}")
    if args.t_max < 1.0:
        print(f"note: allowed_lifetime_max={args.t_max}; validator should reject this graph")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
