# -*- coding: utf-8 -*-
"""FastAPI shell for the SHM claim-evidence assistant.

This is deliberately a thin vertical slice:

- the existing dashboard remains the visualization layer;
- the server exposes four L1 gid/tool pairs plus F-MOC `spec1`–`spec7`,
  each backed by a raw tool;
- the numeric answer is produced by `tools/build_claim_graph.py` and must
  pass `validate.py` before it is returned.

The `t` parameter is an *allowed lifetime* (0..1), not a wall-clock request
time. For AE/PZT/DFOS claims it is checked in retrospective mode because the
tests are completed: a full-life value is only admitted when it lies inside
the allowed lifetime. This is not an online prognosis. FBG has a loading-window
axis, so `t` is explicitly not applicable to its profile claim.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE lines without overriding a real environment.

    This keeps the API key out of the repository and out of shell history for
    the common local-demo case. Tests set SHM_LLM_DISABLE=1 so a developer's
    .env cannot turn mock tests into network calls.
    """
    if os.environ.get("SHM_LLM_DISABLE") == "1" or not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[7:].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(ROOT / ".env")

import tools.build_claim_graph as claim_graph  # noqa: E402
from validate import validate_graph  # noqa: E402
from web import asof, datasets, planner  # noqa: E402

DASHBOARD = ROOT / "dashboard"
WEB = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "schema" / "claim_evidence.schema.json"

# Data registry: all 29 L1 specimens plus F-MOC spec1–spec7. Each tool value
# is backed by a raw runner; the registry decides which tools a gid may use.
SUPPORTED = datasets.load_supported()

_metric_cache: dict[tuple[str, str], tuple[dict, float]] = {}
_metric_lock = threading.Lock()
_schema: dict | None = None


def _load_schema() -> dict:
    global _schema
    if _schema is None:
        with SCHEMA_PATH.open(encoding="utf-8") as fh:
            _schema = json.load(fh)
    return _schema


def _metric(gid: str, dataset: str) -> tuple[dict, float]:
    key = (dataset, gid)
    with _metric_lock:
        if key in _metric_cache:
            return _metric_cache[key]
    data, elapsed = claim_graph.run_metric(gid, dataset)
    with _metric_lock:
        _metric_cache[key] = (data, elapsed)
    return data, elapsed


class AskBody(BaseModel):
    gid: str | None = Field(default=None, min_length=1)
    t: float | None = Field(default=None, ge=0.0, le=1.0)
    question: str | None = Field(default=None, max_length=500)


app = FastAPI(
    title="SHM evidence assistant",
    version="0.1.0",
    description="Claim-evidence slice over the existing SHM dashboard.",
)


def _fmt(value: float, unit: str) -> str:
    if unit == "%":
        return f"{float(value):.2f}%"
    if unit == "normalized":
        return f"{float(value):.3f}"
    return f"{float(value):.6f}"


def _allowed_suffix(claim: dict) -> str:
    allowed = claim.get("allowed_lifetime_max")
    if allowed is None:
        return ""
    return f"；允许寿命上限 {float(allowed):.0%}"


def _answer(graph: dict, tool: str) -> str:
    """Deterministic wording, never an LLM-generated number."""
    claims = graph["claims"]
    subject = claims[0]["subject"] if claims else graph.get("question", "")

    if tool == "conflict":
        def pick(pred: str, modality: str | None = None) -> dict | None:
            for c in claims:
                if c.get("predicate") == pred and (
                        modality is None
                        or (c.get("scope") or {}).get("modality") == modality):
                    return c
            return None

        ae = pick("t85_pct", "AE")
        pzt = pick("t85_pct", "PZT")
        dfos_hi = pick("hi_end", "DFOS")
        dfos_warn = pick("warn50_pct", "DFOS")
        fbg = pick("fbg_profile", "FBG")
        parts = []
        if ae is not None and ae.get("status") == "supported":
            parts.append(f"AE t85={float(ae['value']):.2f}%")
        if pzt is not None:
            interval = (pzt.get("boundary") or {}).get("crossing_interval_pct")
            it = (f"[{interval[0]:.2f}, {interval[1]:.2f}]%"
                  if interval else "")
            parts.append(f"PZT t85={float(pzt['value']):.2f}%{it}，"
                         + ("删失，不签发点估计"
                            if pzt.get("status") != "supported" else "可签发"))
        if dfos_hi is not None and dfos_hi.get("status") == "supported":
            parts.append(f"DFOS 块级 HI={float(dfos_hi['value']):.3f}")
        if dfos_warn is not None:
            parts.append("DFOS 50% 预警点未签发"
                         if dfos_warn.get("status") != "supported"
                         else f"DFOS 50% 预警点={float(dfos_warn['value']):.2f}%")
        if fbg is not None:
            parts.append("FBG 无法形成剖面，因为原始只有 2 个加载窗")
        return (f"{subject} 不能给出四个可比的 t85。"
                + "；".join(parts)
                + "。这些值分别是事件累积、块级包络、导波退相关和覆盖不足，"
                  "不是同一物理量，不能当作四个寿命点排序。")

    if tool == "workflow":
        by_pred = {c.get("predicate"): c for c in claims}
        # There are two t85_pct claims; pick by modality, not by predicate.
        ae = next((c for c in claims
                   if c.get("predicate") == "t85_pct"
                   and (c.get("scope") or {}).get("modality") == "AE"), None)
        pzt = next((c for c in claims
                    if c.get("predicate") == "t85_pct"
                    and (c.get("scope") or {}).get("modality") == "PZT"), None)
        gap = by_pred.get("t85_gap_pp")
        parts = []
        if ae is not None:
            parts.append(f"AE t85={float(ae['value']):.2f}%")
        if pzt is not None:
            if pzt.get("status") == "supported":
                parts.append(f"PZT t85={float(pzt['value']):.2f}%")
            else:
                interval = (pzt.get("boundary") or {}).get("crossing_interval_pct")
                it = (f"，交叉区间 [{interval[0]:.2f}, {interval[1]:.2f}]%"
                      if interval else "")
                parts.append(f"PZT t85={float(pzt['value']):.2f}%{it}，未签发")
        if gap is not None and gap.get("status") == "supported":
            parts.append(f"数值差={float(gap['value']):.2f} pp")
            tail = ("。两个数都通过工具重跑与证据校验；差值只做一致性检查，"
                    "两种口径不同，不能当作 RUL 偏差。")
        else:
            tail = ("。PZT 边界不足，不能完成一致性判断；系统不签发差值 claim。")
        return f"{subject} " + "；".join(parts) + tail

    if tool == "fmoc":
        by_pred = {c.get("predicate"): c for c in claims}
        hit = by_pred.get("t85_hit_pct")
        dic = by_pred.get("t85_dic_pct")
        uncertain = bool((hit or {}).get("boundary", {}).get("test_end_uncertain"))
        parts = []
        if hit is not None:
            parts.append(f"F-MOC AE hits 观测时间 t85={float(hit['value']):.2f}%")
        if dic is not None:
            if dic.get("status") == "supported":
                parts.append(f"DIC 末帧归一化 t85={float(dic['value']):.2f}%")
            else:
                parts.append(f"DIC 末帧归一化边界={float(dic['value']):.2f}%，"
                             "test_end 不确定，不签发")
        return (f"{subject} " + "；".join(parts)
                + "。轴是观测时间，不是 cycle；不能与 L1 的寿命分数直接比较。"
                + (" AE 记录超过 DIC 末帧 2% 以上。" if uncertain else ""))

    if tool == "metric":
        by_pred = {c.get("predicate"): c for c in claims}
        parts = []
        for key, label in (("t85_pct", "t85"), ("t50_pct", "t50")):
            c = by_pred.get(key)
            if c is not None:
                parts.append(f"{label}={float(c['value']):.2f}%")
        return (f"{subject} 全寿命回顾："
                + "，".join(parts)
                + f"；允许寿命上限 {float(claims[0]['allowed_lifetime_max']):.0%}。"
                + "数值均在允许范围内。")

    if tool == "fbg":
        c = claims[0]
        return (f"{subject} FBG 末窗应变剖面 shape_rob25="
                f"{float(c['value']):.6f}；轴为加载窗，不映射寿命分数，"
                "t 不适用于该 claim。")

    if tool == "dfos":
        hi = next((c for c in claims if c["predicate"] == "hi_end"), None)
        warn = next((c for c in claims if c["predicate"] == "warn50_pct"), None)
        parts = []
        if hi is not None and hi.get("status") == "supported":
            parts.append(f"DFOS 块级 HI 末端={float(hi['value']):.3f}")
        if warn is not None:
            if warn.get("status") == "supported":
                parts.append(f"50% 预警点={float(warn['value']):.2f}%")
            else:
                parts.append("50% 预警点未签发，"
                             + (warn.get("missing_evidence") or "边界不足"))
        return f"{subject} " + "；".join(parts) + "。块级包络不是空间损伤图。"

    if tool == "pzt":
        c = claims[0]
        interval = (c.get("boundary") or {}).get("crossing_interval_pct")
        interval_text = ""
        if interval:
            interval_text = f"，交叉区间 [{interval[0]:.2f}, {interval[1]:.2f}]%"
        if c.get("status") == "supported":
            return (f"{subject} PZT 累积退相关 t85={float(c['value']):.2f}%"
                    f"{interval_text}{_allowed_suffix(c)}。")
        missing = c.get("missing_evidence") or "边界不足"
        return (f"{subject} PZT 累积退相关 t85 边界={float(c['value']):.2f}%"
                f"{interval_text}；{missing}，系统不签发点估计。")

    return f"{subject} 的工具输出已生成。"


def _evaluate(gid: str | None, t: float | None,
              question: str | None = None) -> dict:
    if gid is not None and gid not in SUPPORTED:
        # A question that explicitly names a supported gid overrides the
        # board fallback; an invalid board id alone is still a 404.
        question_gid, question_source = planner.resolve_gid(
            question, SUPPORTED, None,
        )
        if question_source != "question" or question_gid is None:
            raise HTTPException(status_code=404, detail=f"unsupported gid: {gid}")

    resolved_gid, resolved_t, resolution = planner.resolve_context(
        question, SUPPORTED, gid, t,
    )
    if resolved_gid is None:
        source = resolution["gid_source"]
        if source == "multiple":
            message = "问题里出现多个试件编号，系统不猜，请一次只问一个试件。"
        elif source == "unknown":
            message = "问题里的试件不在当前白名单，系统不猜，也不会回退到别的试件。"
        else:
            message = "问题里没有明确试件，也没有选中的看板试件；请写 L1-xx 或 specN。"
        return {
            "status": "unsupported",
            "gid": None,
            "t": resolved_t,
            "question": question or "",
            "message": message,
            "resolved": {"gid": None, "t": resolved_t, **resolution},
            "planner": {"intent": "unsupported", "tool": None, "gid": None},
        }

    gid = resolved_gid
    t = resolved_t
    meta = SUPPORTED[gid]
    decision = planner.compile_question(question, gid, SUPPORTED)
    if decision.plan.intent == "unsupported":
        labels = "、".join(meta["tools"])
        return {
            "status": "unsupported",
            "gid": gid,
            "t": t,
            "question": question or "",
            "message": f"当前 {gid} 只支持 {labels} 的白名单查询；"
                       "预测、RUL、损伤类型与维修建议不在可签发范围内。",
            "resolved": {"gid": gid, "t": t, **resolution},
            "planner": decision.as_dict(),
        }

    tool = decision.plan.tool
    if tool == "metric":
        data, elapsed = _metric(gid, meta["dataset"])
        graph = claim_graph.build(
            gid, t, meta["dataset"], data=data, elapsed_ms=elapsed,
            mode="retrospective", metrics=decision.plan.metrics,
            question=question,
        )
    elif tool == "conflict":
        graph = claim_graph.build_conflict_graph(
            gid, t_max=t, mode="retrospective", question=question,
        )
    elif tool == "workflow":
        graph = claim_graph.build_workflow_graph(
            gid, t_max=t, mode="retrospective", question=question,
        )
    else:
        # The skill runner and the verifier each execute the raw tool in
        # separate subprocesses. Do not seed any cache here.
        graph = claim_graph.build_skill_graph(
            tool, gid, t_max=t, base=decision.plan.base,
            stride=decision.plan.stride, mode="retrospective",
            question=question,
        )

    report = validate_graph(graph, _load_schema())
    graph["verification"] = {
        "status": "pass" if not report.failed else "fail",
        "summary": f"{len(report.failed)} failed / {len(report.checks)} checks",
        "checks": report.checks,
    }

    if report.failed:
        names = sorted({c["name"] for c in report.failed
                        if c["name"] != "verification_status"})
        temporal = "temporal_leakage" in names
        # Do not return the claim/evidence payload on a refused answer.
        return {
            "status": "refused",
            "gate": "temporal" if temporal else "verification",
            "gid": gid,
            "t": t,
            "question": graph["question"],
            "message": ("时间门未通过：该数值结论超出允许寿命上限，系统不签发 claim。"
                        if temporal else
                        "验证未通过：claim 的边界或工具重跑结果不一致，系统不签发 claim。"),
            "failed_checks": names,
            "resolved": {"gid": gid, "t": t, **resolution},
            "planner": decision.as_dict(),
            "verification": {
                "status": "fail",
                "summary": graph["verification"]["summary"],
            },
        }

    claims = graph["claims"]
    signed = [c for c in claims if c.get("status") == "supported"]
    insufficient = [c for c in claims if c.get("status") != "supported"]

    if not signed:
        status = "insufficient"
        gate = "boundary"
        message = "边界不足：工具输出不能签发数值 claim，只返回可核对的范围与原因。"
    elif insufficient:
        status = "partial"
        gate = "boundary"
        message = "部分签发：可支持的 claim 已返回，边界不足的 claim 只标原因。"
    else:
        status = "ok"
        gate = "not_applicable" if tool == "fbg" else "pass"
        message = ""

    out = {
        "status": status,
        "gate": gate,
        "gid": gid,
        "t": t,
        "question": graph["question"],
        "resolved": {"gid": gid, "t": t, **resolution},
        "answer": _answer(graph, tool),
        "planner": decision.as_dict(),
        "graph": graph,
        "verification": graph["verification"],
    }
    if message:
        out["message"] = message
    return out


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "supported": sorted(SUPPORTED)}


@app.get("/api/supported")
def supported() -> dict:
    return {
        "items": [
            {"gid": gid, **meta,
             "tools": list(meta["tools"]),
             "modes": (["t85_pct", "t50_pct"] if "metric" in meta["tools"] else [])}
            for gid, meta in sorted(SUPPORTED.items())
        ]
    }


@app.get("/api/ask")
def ask_get(
    gid: str | None = Query(default=None),
    t: float | None = Query(default=None, ge=0.0, le=1.0),
    q: str | None = Query(default=None, max_length=500),
) -> dict:
    return _evaluate(gid, t, q)


@app.post("/api/ask")
def ask_post(body: AskBody) -> dict:
    return _evaluate(body.gid, body.t, body.question)


@app.get("/api/asof")
def asof_get(
    gid: str = Query(default="L1-13"),
    cycle: float | None = Query(default=None, ge=0.0),
    at_s: float | None = Query(default=None, ge=0.0),
) -> dict:
    """Return only prefix state up to the requested cycle or elapsed second."""
    try:
        return asof.state(gid, cycle=cycle, at_s=at_s)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unsupported gid: {gid}")
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail=f"prefix not built for {gid}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/data/index.js")
def empty_legacy_index() -> Response:
    """The main-sample index was never generated; keep the console clean.

    C1-C4 indexes are loaded independently, so L1-06 still works.
    """
    return Response(
        "window.SHM_INDEX=window.SHM_INDEX||[];\n",
        media_type="application/javascript",
    )


@app.get("/", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html = (DASHBOARD / "index.html").read_text(encoding="utf-8")
    if "assistant.css" not in html:
        html = html.replace(
            "</head>",
            '<link rel="stylesheet" href="/static/assistant.css">\n</head>',
        )
    if "assistant.js" not in html:
        html = html.replace(
            "</body>",
            '<script src="/static/assistant.js"></script>\n</body>',
        )
    return HTMLResponse(html)


@app.get("/alignment.html")
def alignment() -> FileResponse:
    return FileResponse(DASHBOARD / "alignment.html")


app.mount("/assets", StaticFiles(directory=DASHBOARD / "assets"), name="assets")
app.mount("/data", StaticFiles(directory=DASHBOARD / "data"), name="data")
app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web.app:app", host="127.0.0.1", port=8000, reload=False)
