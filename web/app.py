# -*- coding: utf-8 -*-
"""FastAPI shell for the SHM claim-evidence assistant.

This is deliberately a thin vertical slice:

- the existing dashboard remains the visualization layer;
- the server exposes only L1-06 from the raw metric for now;
- the numeric answer is produced by `tools/build_claim_graph.py` and must
  pass `validate.py` before it is returned.

The `t` parameter is an *allowed lifetime* (0..1), not a wall-clock request
time. It is checked in retrospective mode because L1-06 is a completed test:
the claim is a full-life t85, and it is only admitted when t85 itself lies
inside the allowed lifetime. This is not an online prognosis.
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
from web import planner  # noqa: E402

DASHBOARD = ROOT / "dashboard"
WEB = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "schema" / "claim_evidence.schema.json"

# The slice is intentionally small and explicit. Adding a dataset requires
# a real raw-metric path and a validator runner, not just a UI entry.
SUPPORTED = {
    "L1-06": {"dataset": "L1", "label": "ReMAP C3 变幅 VA"},
}

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
    gid: str = Field(default="L1-06", min_length=1)
    t: float = Field(default=0.95, ge=0.0, le=1.0)
    question: str | None = Field(default=None, max_length=500)


app = FastAPI(
    title="SHM evidence assistant",
    version="0.1.0",
    description="Claim-evidence slice over the existing SHM dashboard.",
)


def _answer(graph: dict) -> str:
    """Deterministic wording, never an LLM-generated number."""
    by_pred = {c.get("predicate"): c for c in graph["claims"]}
    parts = []
    for key, label in (("t85_pct", "t85"), ("t50_pct", "t50")):
        c = by_pred.get(key)
        if c is not None:
            parts.append(f"{label}={float(c['value']):.2f}%")
    allowed = graph["claims"][0].get("allowed_lifetime_max")
    return (f"{graph['claims'][0]['subject']} 全寿命回顾："
            + "，".join(parts)
            + f"；允许寿命上限 {float(allowed):.0%}。数值均在允许范围内。")


def _evaluate(gid: str, t: float, question: str | None = None) -> dict:
    if gid not in SUPPORTED:
        raise HTTPException(status_code=404, detail=f"unsupported gid: {gid}")

    decision = planner.compile_question(question, gid, SUPPORTED)
    if decision.plan.intent == "unsupported":
        return {
            "status": "unsupported",
            "gid": gid,
            "t": t,
            "question": question or "",
            "message": "当前只支持 L1-06 的 t50/t85 数值查询；预测、RUL、损伤类型与维修建议不在可签发范围内。",
            "planner": decision.as_dict(),
        }

    dataset = SUPPORTED[gid]["dataset"]
    data, elapsed = _metric(gid, dataset)
    # Do not seed validator._TOOL_CACHE here. The verifier must run its own
    # raw metric pass; otherwise "verification" would only compare the graph
    # against the number the API just produced.
    graph = claim_graph.build(
        gid, t, dataset, data=data, elapsed_ms=elapsed,
        mode="retrospective", metrics=decision.plan.metrics,
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
        # Do not return the claim/evidence payload on a refused answer.
        return {
            "status": "refused",
            "gate": "temporal",
            "gid": gid,
            "t": t,
            "question": graph["question"],
            "message": "时间门未通过：该数值结论超出允许寿命上限，系统不签发 claim。",
            "failed_checks": names,
            "planner": decision.as_dict(),
            "verification": {
                "status": "fail",
                "summary": graph["verification"]["summary"],
            },
        }

    return {
        "status": "ok",
        "gate": "pass",
        "gid": gid,
        "t": t,
        "question": graph["question"],
        "answer": _answer(graph),
        "planner": decision.as_dict(),
        "graph": graph,
        "verification": graph["verification"],
    }


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "supported": sorted(SUPPORTED)}


@app.get("/api/supported")
def supported() -> dict:
    return {
        "items": [
            {"gid": gid, **meta, "modes": ["t85_pct", "t50_pct"]}
            for gid, meta in sorted(SUPPORTED.items())
        ]
    }


@app.get("/api/ask")
def ask_get(
    gid: str = Query(default="L1-06"),
    t: float = Query(default=0.95, ge=0.0, le=1.0),
    q: str | None = Query(default=None, max_length=500),
) -> dict:
    return _evaluate(gid, t, q)


@app.post("/api/ask")
def ask_post(body: AskBody) -> dict:
    return _evaluate(body.gid, body.t, body.question)


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
