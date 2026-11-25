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


SKILL_TOOLS = {
    "fbg": ("fbg.profile", "FBG"),
    "dfos": ("dfos.block", "DFOS"),
    "pzt": ("pzt.index", "PZT"),
    "fmoc": ("fmoc.profile", "AE"),
}


def run_skill(tool: str, gid: str, base: str = "post",
              stride: int = 1) -> tuple[dict, float]:
    """Run one modality tool and return (data, elapsed_ms).

    The tools are independent processes so the graph builder cannot import a
    helper that silently reuses a cached result from the API process.
    """
    if tool not in SKILL_TOOLS:
        raise SystemExit(f"unsupported tool: {tool!r}")
    cmd = [sys.executable, str(ROOT / "skills" / tool / "run.py"),
           "--gid", gid, "--json"]
    if tool == "dfos":
        cmd += ["--base", base]
    if tool == "pzt":
        cmd += ["--stride", str(stride)]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", timeout=1800)
    elapsed = (time.time() - t0) * 1000.0
    try:
        obj = json.loads(p.stdout)
    except Exception as exc:
        raise SystemExit(f"{tool} output is not JSON:\n{p.stdout[:500]}\n{p.stderr[:500]}") from exc
    if obj.get("status") != "ok":
        raise SystemExit(f"{tool} status={obj.get('status')}: "
                         f"{obj.get('data', {}).get('reason', '')}")
    return obj["data"], elapsed


def _skill_claim_specs(tool: str, data: dict, t_max: float) -> list[dict]:
    """Return the claims that a modality tool is allowed to sign.

    A claim is only `supported` when the tool's boundary fields say the number
    is a point, not a censored or unresolved boundary.  The claims are still
    emitted as `insufficient` so the consumer can see why no point is signed.
    """
    if tool == "fbg":
        return [{
            "predicate": "shape_rob25_last",
            "value": data["shape_rob25_last"],
            "unit": "L1",
            "text": (f"{data['gid']} 的 FBG 末窗应变剖面相对首窗中位剖面的 "
                     f"shape_rob25 为 {data['shape_rob25_last']:.6f}；"
                     "轴为加载窗，不是寿命分数。"),
            "boundary": {"cycle_anchor": None},
            "status": "supported",
            "allowed": None,
            "missing": None,
            "coverage_basis": "not_applicable",
        }]

    if tool == "dfos":
        resolved = bool(data.get("threshold_resolved"))
        warn50 = data.get("warn50_pct")
        specs = [{
            "predicate": "hi_end",
            "value": data["hi_end"],
            "unit": "normalized",
            "text": (f"{data['gid']} 的 DFOS 块级 HI 末端为 {data['hi_end']:.3f}；"
                     "这是归一化块级包络，不是空间损伤图。"),
            "boundary": {
                "threshold_resolved": resolved,
                "hi_ceiling": data.get("hi_ceiling"),
            },
            "status": "supported",
            "allowed": None,
            "missing": None,
            "coverage_basis": "block",
        }]
        if warn50 is not None:
            specs.append({
                "predicate": "warn50_pct",
                "value": warn50,
                "unit": "%",
                "text": (f"{data['gid']} 的 DFOS 块级 50% 预警点为 {warn50:.3f}%"
                         + ("；25/50/70 阈值可分。" if resolved
                            else "；25/50/70 落在同一 block，不能当三个独立预警点。")),
                "boundary": {
                    "threshold_resolved": resolved,
                    "hi_ceiling": data.get("hi_ceiling"),
                },
                "status": "supported" if resolved else "insufficient",
                "allowed": t_max if resolved else None,
                "missing": (None if resolved else
                            "DFOS 块级分辨率不足，25/50/70 阈值落在同一 block"),
                "coverage_basis": "block",
            })
        return specs

    if tool == "fmoc":
        uncertain = bool(data.get("test_end_uncertain"))
        boundary = {
            "time_axis": True,
            "test_end_uncertain": uncertain,
            "dic_last_h": data.get("dic_last_h"),
        }
        specs = [{
            "predicate": "t85_hit_pct",
            "value": data["t85_hit_pct"],
            "unit": "%",
            "text": (f"{data['gid']} 的 F-MOC AE hits 在观测时间窗口内 "
                     f"t85={data['t85_hit_pct']:.2f}%；轴是时间，不是 cycle，"
                     "不能与 L1 的寿命分数直接比较。"),
            "boundary": boundary,
            "status": "supported",
            "allowed": t_max,
            "missing": None,
            "coverage_basis": "lifetime",
        }]
        if data.get("t85_dic_pct") is not None:
            specs.append({
                "predicate": "t85_dic_pct",
                "value": data["t85_dic_pct"],
                "unit": "%",
                "text": (f"{data['gid']} 的 F-MOC AE t85 按 DIC 末帧归一化为 "
                         f"{data['t85_dic_pct']:.2f}%；DIC 末帧只是 test_end 下界"
                         + ("，且 AE 超出 DIC 2% 以上，该值只能当敏感性。"
                            if uncertain else "。")),
                "boundary": boundary,
                "status": "insufficient" if uncertain else "supported",
                "allowed": None if uncertain else t_max,
                "missing": ("AE 记录超过 DIC 末帧 2% 以上，test_end 不确定"
                            if uncertain else None),
                "coverage_basis": "lifetime",
            })
        return specs

    if tool == "pzt":
        censored = bool(data.get("censored"))
        coverage = data.get("coverage")
        supported = (not censored) and coverage is not None and float(coverage) >= 0.95
        interval = data.get("crossing_interval_pct")
        interval_text = (f"，交叉区间 [{interval[0]:.2f}, {interval[1]:.2f}]%"
                         if interval else "")
        return [{
            "predicate": "t85_pct",
            "value": data["t85_pct"],
            "unit": "%",
            "text": (f"{data['gid']} 的 PZT 累积退相关 t85 为 {data['t85_pct']:.2f}%"
                     f"{interval_text}；"
                     + ("这是删失边界，不是精确失效点。" if censored
                        else "该值可作为 PZT 口径的数值 claim。")),
            "boundary": {
                "threshold_reached": bool(data.get("threshold_reached")),
                "crossing_interval_pct": interval,
                "censored": censored,
            },
            "status": "supported" if supported else "insufficient",
            "allowed": t_max if supported else None,
            "missing": (None if supported else
                        ("PZT t85 在寿命末端删失" if censored
                         else f"PZT 寿命覆盖 {coverage} < 0.95")),
            "coverage_basis": "partial",
        }]

    raise SystemExit(f"unsupported tool: {tool!r}")


def build_conflict_graph(gid: str = "L1-03", t_max: float = 1.0,
                         mode: str = "retrospective",
                         question: str | None = None) -> dict:
    """Build the L1-03 availability/conflict case.

    This is deliberately not a "four comparable t85" graph.  The three raw
    tools return three different kinds of evidence, and the FBG tool cannot
    form a profile because the raw directory has too few loading windows.
    """
    if gid != "L1-03":
        raise SystemExit("conflict case currently supports only L1-03")
    if not (0.0 <= t_max <= 1.0):
        raise SystemExit("--t-max must be in [0, 1]")
    if mode not in ("streaming", "retrospective"):
        raise SystemExit("--mode must be streaming or retrospective")

    ae, ae_ms = run_metric(gid)
    dfos, dfos_ms = run_skill("dfos", gid)
    pzt, pzt_ms = run_skill("pzt", gid)

    n_f = int(ae.get("n_f") or 0)
    now = _now()

    def scope_for(modality: str, lifetime: bool = True) -> dict:
        return {
            "gid": gid,
            "campaign": "L1",
            "modality": modality,
            "cycle_min": 0,
            "cycle_max": n_f or None,
            "lifetime_min": 0 if lifetime else None,
            "lifetime_max": 1 if lifetime else None,
        }

    def tool_call(tcid: str, tool: str, args: dict, result: dict, ms: float) -> dict:
        return {
            "tool_call_id": tcid,
            "tool_name": tool,
            "arguments": args,
            "result": result,
            "created_at": now,
            "elapsed_ms": round(ms, 1),
        }

    def evidence_item(eid: str, tcid: str, tool: str, title: str,
                      modality: str, metric: str, value: float,
                      coverage: float, basis: str, boundary: dict,
                      raw: str) -> dict:
        return {
            "evidence_id": eid,
            "evidence_type": "tool_result",
            "source": {
                "kind": "tool",
                "title": title,
                "tool_name": tool,
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
                "value": float(value),
                "gid": gid,
                "coverage": coverage,
                "coverage_basis": basis,
                "boundary": boundary,
            },
            "quote": None,
            "locator": {
                "file": raw,
                "page": None,
                "section": None,
                "table": None,
                "figure": None,
                "row": None,
                "clause": None,
                "char_start": None,
                "char_end": None,
            },
            "scope": scope_for(modality),
            "observed_lifetime_fraction": coverage,
            "tool_call_id": tcid,
            "coverage": coverage,
            "coverage_basis": basis,
            "retrieved_at": now,
            "content_hash": None,
            "reliability": "primary",
        }

    ae_scope = scope_for("AE")
    dfos_scope = scope_for("DFOS")
    pzt_scope = scope_for("PZT")
    fbg_scope = scope_for("FBG", lifetime=False)

    claims = [
        {
            "claim_id": "C001",
            "text": (f"{gid} 的 AE 全寿命 t85 为 {ae['t85_pct']:.2f}%；"
                     "这是 AE 事件累积口径，不是其他模态的 t85。"),
            "claim_type": "numeric",
            "subject": gid,
            "predicate": "t85_pct",
            "value": float(ae["t85_pct"]),
            "unit": "%",
            "comparator": "eq",
            "tolerance": 1e-6,
            "status": "supported",
            "evidence_ids": ["E001"],
            "tool_call_ids": ["T001"],
            "scope": ae_scope,
            "allowed_lifetime_max": t_max,
            "missing_evidence": None,
            "confidence": 0.99,
            "created_by": "Analyst",
        },
        {
            "claim_id": "C002",
            "text": (f"{gid} 的 DFOS 块级 HI 末端为 {dfos['hi_end']:.3f}；"
                     "这是归一化块级包络，不是 t85，也不是空间损伤图。"),
            "claim_type": "numeric",
            "subject": gid,
            "predicate": "hi_end",
            "value": float(dfos["hi_end"]),
            "unit": "normalized",
            "comparator": "eq",
            "tolerance": 1e-6,
            "status": "supported",
            "evidence_ids": ["E002"],
            "tool_call_ids": ["T002"],
            "scope": dfos_scope,
            "boundary": {
                "threshold_resolved": bool(dfos.get("threshold_resolved")),
                "hi_ceiling": dfos.get("hi_ceiling"),
            },
            "allowed_lifetime_max": None,
            "missing_evidence": None,
            "confidence": 0.99,
            "created_by": "Analyst",
        },
        {
            "claim_id": "C003",
            "text": (f"{gid} 的 DFOS 块级 50% 预警点为 {dfos.get('warn50_pct'):.2f}%；"
                     "25/50/70 落在同一 block，不能当三个独立预警点。"),
            "claim_type": "numeric",
            "subject": gid,
            "predicate": "warn50_pct",
            "value": float(dfos["warn50_pct"]),
            "unit": "%",
            "comparator": "eq",
            "tolerance": 1e-6,
            "status": "insufficient",
            "evidence_ids": ["E003"],
            "tool_call_ids": ["T002"],
            "scope": dfos_scope,
            "boundary": {
                "threshold_resolved": bool(dfos.get("threshold_resolved")),
                "hi_ceiling": dfos.get("hi_ceiling"),
            },
            "allowed_lifetime_max": None,
            "missing_evidence": "DFOS 块级分辨率不足，25/50/70 阈值落在同一 block",
            "confidence": None,
            "created_by": "Analyst",
        },
        {
            "claim_id": "C004",
            "text": (f"{gid} 的 PZT t85 为 {pzt['t85_pct']:.2f}%；"
                     "该值在寿命末端删失，只能给出交叉区间。"),
            "claim_type": "numeric",
            "subject": gid,
            "predicate": "t85_pct",
            "value": float(pzt["t85_pct"]),
            "unit": "%",
            "comparator": "eq",
            "tolerance": 1e-6,
            "status": "insufficient",
            "evidence_ids": ["E004"],
            "tool_call_ids": ["T003"],
            "scope": pzt_scope,
            "boundary": {
                "threshold_reached": bool(pzt.get("threshold_reached")),
                "crossing_interval_pct": pzt.get("crossing_interval_pct"),
                "censored": bool(pzt.get("censored")),
            },
            "allowed_lifetime_max": None,
            "missing_evidence": "PZT t85 在寿命末端删失，不能作为精确失效点",
            "confidence": None,
            "created_by": "Analyst",
        },
        {
            "claim_id": "C005",
            "text": (f"{gid} 的 FBG 原始目录只有 2 个加载窗，"
                     "fbg.profile 要求至少 5 个，无法形成可比剖面。"),
            "claim_type": "limitation",
            "subject": gid,
            "predicate": "fbg_profile",
            "value": None,
            "unit": None,
            "comparator": None,
            "tolerance": None,
            "status": "insufficient",
            "evidence_ids": [],
            "tool_call_ids": [],
            "scope": fbg_scope,
            "boundary": {"cycle_anchor": None},
            "allowed_lifetime_max": None,
            "missing_evidence": "raw FBG has only 2 loading windows; at least 5 required",
            "confidence": None,
            "created_by": "Analyst",
        },
    ]

    evidence = [
        evidence_item("E001", "T001", "metric.l1_t85",
                      f"{gid} raw AE (metric.l1_t85)", "AE", "t85_pct",
                      ae["t85_pct"], float(ae.get("coverage") or 0.0),
                      "lifetime", {}, "E:\\l1\\L1-03\\AE"),
        evidence_item("E002", "T002", "dfos.block",
                      f"{gid} raw DFOS (dfos.block)", "DFOS", "hi_end",
                      dfos["hi_end"], 1.0, "block",
                      {"threshold_resolved": bool(dfos.get("threshold_resolved")),
                       "hi_ceiling": dfos.get("hi_ceiling")},
                      str(dfos.get("raw_dfos") or "")),
        evidence_item("E003", "T002", "dfos.block",
                      f"{gid} raw DFOS (dfos.block)", "DFOS", "warn50_pct",
                      dfos["warn50_pct"], 1.0, "block",
                      {"threshold_resolved": bool(dfos.get("threshold_resolved")),
                       "hi_ceiling": dfos.get("hi_ceiling")},
                      str(dfos.get("raw_dfos") or "")),
        evidence_item("E004", "T003", "pzt.index",
                      f"{gid} raw PZT (pzt.index)", "PZT", "t85_pct",
                      pzt["t85_pct"], float(pzt.get("coverage") or 0.0),
                      "partial",
                      {"threshold_reached": bool(pzt.get("threshold_reached")),
                       "crossing_interval_pct": pzt.get("crossing_interval_pct"),
                       "censored": bool(pzt.get("censored"))},
                      str(pzt.get("raw_pzt") or "")),
    ]

    tool_calls = [
        tool_call("T001", "metric.l1_t85",
                  {"dataset": "L1", "gid": gid}, ae, ae_ms),
        tool_call("T002", "dfos.block",
                  {"gid": gid, "base": "post"}, dfos, dfos_ms),
        tool_call("T003", "pzt.index",
                  {"gid": gid, "stride": 1}, pzt, pzt_ms),
    ]

    graph_question = (question.strip() if isinstance(question, str) and question.strip()
                      else f"{gid} 的 AE、DFOS、PZT、FBG 能不能给出四个可比的 t85？")
    return {
        "schema_version": "1.0",
        "graph_id": "G001",
        "question": graph_question,
        "created_at": now,
        "policy": {
            "require_evidence": True,
            "allow_unsupported_claims": False,
            "max_evidence_per_claim": 8,
            "temporal_leakage_check": True,
            "temporal_mode": mode,
            "require_numeric_tool_evidence": True,
        },
        "claims": claims,
        "evidence": evidence,
        "edges": [
            {"claim_id": "C001", "evidence_id": "E001", "relation": "supports"},
            {"claim_id": "C002", "evidence_id": "E002", "relation": "supports"},
            {"claim_id": "C003", "evidence_id": "E003", "relation": "supports"},
            {"claim_id": "C004", "evidence_id": "E004", "relation": "supports"},
        ],
        "tool_calls": tool_calls,
        "verification": {"status": "needs_review",
                         "summary": "populated by validate.py", "checks": []},
    }


def build_skill_graph(tool: str, gid: str, t_max: float = 1.0,
                      base: str = "post", stride: int = 1,
                      mode: str = "retrospective",
                      data: dict | None = None, elapsed_ms: float = 0.0,
                      question: str | None = None) -> dict:
    """Build a claim graph for FBG/DFOS/PZT/F-MOC with boundary metadata."""
    if tool not in SKILL_TOOLS:
        raise SystemExit(f"unsupported tool: {tool!r}")
    if not (0.0 <= t_max <= 1.0):
        raise SystemExit("--t-max must be in [0, 1]")
    if mode not in ("streaming", "retrospective"):
        raise SystemExit("--mode must be streaming or retrospective")
    if data is None:
        data, elapsed_ms = run_skill(tool, gid, base=base, stride=stride)

    tool_name, modality = SKILL_TOOLS[tool]
    n_f = int(data.get("n_f") or 0)
    if tool == "fbg":
        scope = {
            "gid": gid, "campaign": "L1", "modality": modality,
            "cycle_min": None, "cycle_max": n_f or None,
            "lifetime_min": None, "lifetime_max": None,
        }
    elif tool == "fmoc":
        scope = {
            "gid": gid, "campaign": "F-MOC", "modality": modality,
            "cycle_min": None, "cycle_max": None,
            "lifetime_min": 0, "lifetime_max": 1,
        }
    else:
        scope = {
            "gid": gid, "campaign": "L1", "modality": modality,
            "cycle_min": 0, "cycle_max": n_f or None,
            "lifetime_min": 0, "lifetime_max": 1,
        }

    specs = _skill_claim_specs(tool, data, t_max)
    tool_call = {
        "tool_call_id": "T001",
        "tool_name": tool_name,
        "arguments": {"gid": gid, **({"base": base} if tool == "dfos" else {}),
                      **({"stride": stride} if tool == "pzt" else {})},
        "result": data,
        "created_at": _now(),
        "elapsed_ms": round(elapsed_ms, 1),
    }
    claims: list[dict] = []
    evidence: list[dict] = []
    edges: list[dict] = []

    for i, spec in enumerate(specs, start=1):
        cid = f"C{i:03d}"
        eid = f"E{i:03d}"
        value = spec["value"]
        coverage = data.get("coverage")
        if tool == "dfos" and coverage is None and data.get("n_blocks"):
            # The DFOS tool scans the whole test; the limitation is block
            # resolution, not a partial lifetime.  State that explicitly
            # instead of leaving coverage null.
            coverage = 1.0
        tolerance = 0.01 if abs(float(value)) > 1e6 else 1e-6
        claim = {
            "claim_id": cid,
            "text": spec["text"],
            "claim_type": "numeric",
            "subject": gid,
            "predicate": spec["predicate"],
            "value": float(value),
            "unit": spec["unit"],
            "comparator": "eq",
            "tolerance": tolerance,
            "status": spec["status"],
            "evidence_ids": [eid],
            "tool_call_ids": ["T001"],
            "scope": scope,
            "boundary": spec["boundary"],
            "allowed_lifetime_max": spec["allowed"],
            "missing_evidence": spec["missing"],
            "confidence": 0.99 if spec["status"] == "supported" else None,
            "created_by": "Analyst",
        }
        claims.append(claim)

        content = {
            "metric": spec["predicate"],
            "value": float(value),
            "gid": gid,
            "coverage": coverage,
            "coverage_basis": spec["coverage_basis"],
            "boundary": spec["boundary"],
        }
        if tool == "dfos":
            content.update({"n_blocks": data.get("n_blocks"),
                            "base_mode": data.get("base_mode"),
                            "threshold_resolved": data.get("threshold_resolved"),
                            "hi_ceiling": data.get("hi_ceiling")})
        elif tool == "pzt":
            content.update({"threshold_reached": data.get("threshold_reached"),
                            "crossing_interval_pct": data.get("crossing_interval_pct"),
                            "censored": data.get("censored"),
                            "n_states": data.get("n_states")})
        elif tool == "fbg":
            content.update({"axis": "window", "cycle_anchor": None,
                            "n_windows": data.get("n_windows")})
        elif tool == "fmoc":
            content.update({
                "axis": "time",
                "indicator": "hits",
                "n_hits": data.get("n_hits"),
                "t85_dic_pct": data.get("t85_dic_pct"),
                "dic_last_h": data.get("dic_last_h"),
                "test_end_uncertain": data.get("test_end_uncertain"),
            })

        evidence.append({
            "evidence_id": eid,
            "evidence_type": "tool_result",
            "source": {
                "kind": "tool",
                "title": f"{gid} raw {modality} ({tool_name})",
                "tool_name": tool_name,
                "version": "0.1.0",
                "authors": [],
                "year": None,
                "venue": None,
                "doi": None,
                "url": None,
                "clause": None,
            },
            "content": content,
            "quote": None,
            "locator": {
                "file": (data.get("raw_fbg") or data.get("raw_dfos")
                         or data.get("raw_pzt") or data.get("raw_fmoc")),
                "page": None, "section": None, "table": None, "figure": None,
                "row": None, "clause": None, "char_start": None, "char_end": None,
            },
            "scope": scope,
            "observed_lifetime_fraction": coverage,
            "tool_call_id": "T001",
            "coverage": coverage,
            "coverage_basis": spec["coverage_basis"],
            "retrieved_at": _now(),
            "content_hash": None,
            "reliability": "primary",
        })
        edges.append({"claim_id": cid, "evidence_id": eid, "relation": "supports"})

    graph_question = (question.strip() if isinstance(question, str) and question.strip()
                      else f"{gid} 的 {modality} 工具输出是什么？边界是什么？")
    return {
        "schema_version": "1.0",
        "graph_id": "G001",
        "question": graph_question,
        "created_at": _now(),
        "policy": {
            "require_evidence": True,
            "allow_unsupported_claims": False,
            "max_evidence_per_claim": 8,
            "temporal_leakage_check": True,
            "temporal_mode": mode,
            "require_numeric_tool_evidence": True,
        },
        "claims": claims,
        "evidence": evidence,
        "edges": edges,
        "tool_calls": [tool_call],
        "verification": {"status": "needs_review",
                         "summary": "populated by validate.py", "checks": []},
    }


def build_workflow_graph(gid: str = "L1-13", t_max: float = 1.0,
                         mode: str = "retrospective",
                         question: str | None = None) -> dict:
    """Run AE t85 then PZT t85 and add one derived agreement claim.

    The two tool calls are independent. The derived claim is not another
    sensor reading: it is the signed difference between the two signed t85
    values, and the validator recomputes it from the two evidence items.
    """
    if not (0.0 <= t_max <= 1.0):
        raise SystemExit("--t-max must be in [0, 1]")
    if mode not in ("streaming", "retrospective"):
        raise SystemExit("--mode must be streaming or retrospective")

    ae, ae_ms = run_metric(gid)
    pzt, pzt_ms = run_skill("pzt", gid)

    ae_graph = build(gid, t_max, data=ae, elapsed_ms=ae_ms, mode=mode,
                     metrics=("t85",), question=question)
    pzt_graph = build_skill_graph("pzt", gid, t_max=t_max, mode=mode,
                                  data=pzt, elapsed_ms=pzt_ms,
                                  question=question)
    ae_claim = ae_graph["claims"][0]
    pzt_claim = pzt_graph["claims"][0]

    pzt_claim["claim_id"] = "C002"
    pzt_claim["evidence_ids"] = ["E002"]
    pzt_claim["tool_call_ids"] = ["T002"]
    pzt_graph["evidence"][0]["evidence_id"] = "E002"
    pzt_graph["evidence"][0]["tool_call_id"] = "T002"
    pzt_graph["tool_calls"][0]["tool_call_id"] = "T002"

    ae_ok = ae_claim.get("status") == "supported"
    pzt_ok = pzt_claim.get("status") == "supported"
    gap = None
    if ae_ok and pzt_ok:
        # Use the raw metric values, not the two-decimal claim display values.
        gap = round(float(ae["t85_pct"]) - float(pzt["t85_pct"]), 6)

    subject = gid
    n_f = int(ae.get("n_f") or 0)
    multi_scope = {
        "gid": gid,
        "campaign": "L1",
        "modality": "MULTI",
        "cycle_min": 0,
        "cycle_max": n_f or None,
        "lifetime_min": 0,
        "lifetime_max": 1,
    }
    if gap is not None:
        gap_claim = {
            "claim_id": "C003",
            "text": (f"{gid} 的 AE t85 与 PZT t85 数值差为 {gap:.2f} pp；"
                     "两者采样与插值口径不同，这个差值只做一致性检查，"
                     "不是同一物理量的偏差，也不是 RUL 差。"),
            "claim_type": "comparative",
            "subject": subject,
            "predicate": "t85_gap_pp",
            "value": gap,
            "unit": "pp",
            "comparator": "approx",
            "tolerance": 0.01,
            "status": "supported",
            "evidence_ids": ["E001", "E002"],
            "tool_call_ids": ["T001", "T002"],
            "scope": multi_scope,
            "allowed_lifetime_max": None,
            "missing_evidence": None,
            "confidence": 0.99,
            "created_by": "Analyst",
        }
    else:
        gap_claim = {
            "claim_id": "C003",
            "text": (f"{gid} 的 PZT t85 未签发，不能完成 AE-PZT 一致性检查。"),
            "claim_type": "comparative",
            "subject": subject,
            "predicate": "t85_gap_pp",
            "value": None,
            "unit": "pp",
            "comparator": None,
            "tolerance": None,
            "status": "insufficient",
            "evidence_ids": ["E001", "E002"],
            "tool_call_ids": ["T001", "T002"],
            "scope": multi_scope,
            "allowed_lifetime_max": None,
            "missing_evidence": pzt_claim.get("missing_evidence")
                               or "PZT t85 未达到可签发条件",
            "confidence": None,
            "created_by": "Analyst",
        }

    graph_question = (question.strip() if isinstance(question, str) and question.strip()
                      else f"{gid} 先查 AE t85，再查 PZT t85，两者是否一致？")
    return {
        "schema_version": "1.0",
        "graph_id": "G001",
        "question": graph_question,
        "created_at": _now(),
        "policy": ae_graph["policy"],
        "claims": [ae_claim, pzt_claim, gap_claim],
        "evidence": ae_graph["evidence"] + pzt_graph["evidence"],
        "edges": [
            {"claim_id": "C001", "evidence_id": "E001", "relation": "supports"},
            {"claim_id": "C002", "evidence_id": "E002", "relation": "supports"},
            {"claim_id": "C003", "evidence_id": "E001", "relation": "supports"},
            {"claim_id": "C003", "evidence_id": "E002", "relation": "supports"},
        ],
        "tool_calls": ae_graph["tool_calls"] + pzt_graph["tool_calls"],
        "verification": {"status": "needs_review",
                         "summary": "populated by validate.py", "checks": []},
    }


def build(gid: str, t_max: float, dataset: str = "L1", data: dict | None = None,
          elapsed_ms: float = 0.0, mode: str = "streaming",
          metrics: tuple[str, ...] = ("t85", "t50"),
          question: str | None = None) -> dict:
    """Build a graph for an allowed lifetime.

    mode="streaming" keeps the strict online gate: evidence observed after
    t_max is temporal leakage. mode="retrospective" is for a completed test:
    the full-life t85/t50 is quoted, but only if the value itself lies within
    the allowed lifetime. The latter is explicit in policy.temporal_mode so a
    retrospective claim cannot masquerade as an online one.

    metrics is the planner-selected subset; the tool still returns both values,
    but only selected claims/evidence are placed in the graph.
    """
    if data is None:
        data, elapsed_ms = run_metric(gid, dataset)
    elapsed = elapsed_ms
    if not (0.0 <= t_max <= 1.0):
        raise SystemExit("--t-max must be in [0, 1]")
    if mode not in ("streaming", "retrospective"):
        raise SystemExit("--mode must be streaming or retrospective")

    aliases = {"t85": "t85", "t85_pct": "t85", "t50": "t50", "t50_pct": "t50"}
    selected: list[str] = []
    for item in metrics:
        key = str(item).strip().lower()
        if key not in aliases:
            raise SystemExit(f"unsupported metric: {item!r}")
        metric = aliases[key]
        if metric not in selected:
            selected.append(metric)
    if not selected:
        raise SystemExit("at least one metric is required")
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
        suffix = ("（全寿命回顾，允许寿命上限 "
                  f"{t_max:.0%}）" if mode == "retrospective" else "")
        return {
            "claim_id": cid,
            "text": f"{gid} 的 AE 累积 hit 曲线 {label} 为 {value:.2f}%。{suffix}",
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

    claim_defs = [
        ("C001", "t85_pct", data["t85_pct"], "t85", "E001"),
        ("C002", "t50_pct", data["t50_pct"], "t50", "E002"),
    ]
    selected_defs = [d for d in claim_defs if d[3] in selected]
    graph_question = (question.strip() if isinstance(question, str) and question.strip()
                      else f"{gid} 的 t50 / t85 是多少？"
                      + (f"在只看到寿命前 {t_max:.0%} 数据时，这个结论是否成立？"
                         if mode == "streaming" else
                         f"在允许寿命上限 {t_max:.0%} 的回顾范围内，这个数值结论是否成立？"))

    return {
        "schema_version": "1.0",
        "graph_id": "G001",
        "question": graph_question,
        "created_at": _now(),
        "policy": {
            "require_evidence": True,
            "allow_unsupported_claims": False,
            "max_evidence_per_claim": 8,
            "temporal_leakage_check": True,
            "temporal_mode": mode,
            "require_numeric_tool_evidence": True,
        },
        "claims": [
            claim(cid, metric, value, label)
            for cid, metric, value, label, _ in selected_defs
        ],
        "evidence": [
            evidence(eid, metric, value)
            for _, metric, value, _, eid in selected_defs
        ],
        "edges": [
            {"claim_id": cid, "evidence_id": eid, "relation": "supports"}
            for cid, _, _, _, eid in selected_defs
        ],
        "tool_calls": [tool],
        "verification": {"status": "needs_review",
                         "summary": "populated by validate.py", "checks": []},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gid", required=True)
    ap.add_argument("--tool", default="metric",
                    choices=["metric", "fbg", "dfos", "pzt", "fmoc",
                             "conflict", "workflow"])
    ap.add_argument("--dataset", default="L1")
    ap.add_argument("--base", default="post", choices=["post", "bi"],
                    help="DFOS baseline mode (ignored by other tools)")
    ap.add_argument("--stride", type=int, default=1,
                    help="PZT state stride (ignored by other tools)")
    ap.add_argument("--t-max", type=float, default=1.0)
    ap.add_argument("--mode", default="streaming",
                    choices=["streaming", "retrospective"])
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    if args.tool == "metric":
        graph = build(args.gid, args.t_max, args.dataset, mode=args.mode)
    elif args.tool == "conflict":
        graph = build_conflict_graph(
            args.gid, t_max=args.t_max, mode=args.mode,
        )
    elif args.tool == "workflow":
        graph = build_workflow_graph(
            args.gid, t_max=args.t_max, mode=args.mode,
        )
    else:
        graph = build_skill_graph(
            args.tool, args.gid, t_max=args.t_max,
            base=args.base, stride=args.stride, mode=args.mode,
        )
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"wrote {out}")
    if args.t_max < 1.0:
        print(f"note: allowed_lifetime_max={args.t_max}; "
              f"mode={args.mode}; validator applies the corresponding gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
