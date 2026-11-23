# -*- coding: utf-8 -*-
"""Restricted semantic compiler for the SHM assistant.

The LLM is allowed to do one thing: translate a natural-language question into
a small, validated plan. It never sees or produces the numeric result. If no
LLM endpoint is configured, or the LLM returns anything outside the whitelist,
the deterministic fallback handles the question instead.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Iterable

import httpx

INTENTS = ("metric_query", "unsupported")
METRICS = ("t85", "t50")
_ALIASES = {
    "t85": "t85",
    "t85_pct": "t85",
    "t50": "t50",
    "t50_pct": "t50",
}

_SYSTEM = (
    "You are a semantic compiler for a structural health monitoring evidence "
    "system. Translate the user question into a JSON plan. Do not answer the "
    "question. Do not invent numbers, gids, tools, or metrics. Return JSON only."
)

_PROMPT = """Supported scope:
- gid: {gid}
- metrics: t85, t50
- intent: metric_query or unsupported

Return exactly one JSON object:
{{"intent":"metric_query","gid":"{gid}","metrics":["t85"],"reason":"short"}}
or
{{"intent":"unsupported","gid":"{gid}","metrics":[],"reason":"short"}}

Rules:
- If the question asks for t85, use metrics ["t85"].
- If it asks for t50, use ["t50"].
- If it asks for both or for the general lifetime threshold, use ["t85","t50"].
- If it asks for prediction, RUL, damage type, crack length, maintenance action,
  or anything outside gid {gid}, use intent "unsupported".
- Never put numeric t85/t50 values in the plan.

Question:
{question}
"""


@dataclass(frozen=True)
class Plan:
    intent: str
    gid: str
    metrics: tuple[str, ...] = ()
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "intent": self.intent,
            "gid": self.gid,
            "metrics": list(self.metrics),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PlannerResult:
    plan: Plan
    source: str  # llm | fallback | default
    model: str | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        plan = self.plan.as_dict()
        # The reason is free text from the planner. For the LLM path it is
        # untrusted and may contain a numeric claim, so do not expose it.
        if self.source == "llm":
            plan.pop("reason", None)
        out = {"source": self.source, "plan": plan}
        if self.model:
            out["model"] = self.model
        if self.error:
            out["error"] = self.error
        return out


def _llm_config() -> tuple[str, str, str]:
    base = os.environ.get("SHM_LLM_BASE_URL", "").strip()
    model = os.environ.get("SHM_LLM_MODEL", "qwen2.5:3b").strip()
    key = os.environ.get("SHM_LLM_API_KEY", "").strip()
    return base, model, key


def _endpoint(base: str) -> str:
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def _call_llm(question: str, gid: str) -> str:
    base, model, key = _llm_config()
    if not base:
        raise RuntimeError("SHM_LLM_BASE_URL is not configured")
    timeout = float(os.environ.get("SHM_LLM_TIMEOUT", "20"))
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 220,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _PROMPT.format(gid=gid, question=question)},
        ],
    }
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.post(_endpoint(base), json=payload, headers=headers)
        response.raise_for_status()
        obj = response.json()
    content = obj["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
    if not isinstance(content, str):
        raise RuntimeError("LLM content is not text")
    return content


def _strip_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_plan(raw: str | dict, gid: str, supported: Iterable[str]) -> Plan:
    obj = raw if isinstance(raw, dict) else json.loads(_strip_fence(str(raw)))
    if not isinstance(obj, dict):
        raise ValueError("plan is not an object")
    intent = str(obj.get("intent", "")).strip()
    if intent not in INTENTS:
        raise ValueError(f"unknown intent: {intent!r}")

    plan_gid = str(obj.get("gid", gid) or gid).strip()
    if plan_gid not in set(supported):
        raise ValueError(f"gid outside whitelist: {plan_gid!r}")
    if plan_gid != gid:
        raise ValueError(f"gid mismatch: {plan_gid!r} != {gid!r}")

    raw_metrics = obj.get("metrics", [])
    if not isinstance(raw_metrics, list):
        raise ValueError("metrics must be a list")
    metrics: list[str] = []
    for item in raw_metrics:
        key = str(item).strip().lower()
        if key not in _ALIASES:
            raise ValueError(f"metric outside whitelist: {item!r}")
        metric = _ALIASES[key]
        if metric not in metrics:
            metrics.append(metric)

    if intent == "metric_query" and not metrics:
        raise ValueError("metric_query requires at least one metric")
    if intent == "unsupported":
        metrics = []

    reason = str(obj.get("reason", "") or "").strip()
    if len(reason) > 300:
        reason = reason[:300]
    return Plan(intent=intent, gid=gid, metrics=tuple(metrics), reason=reason)


def _unsupported(gid: str, reason: str) -> Plan:
    return Plan(intent="unsupported", gid=gid, metrics=(), reason=reason)


def _fallback(question: str, gid: str) -> Plan:
    text = question.strip().lower().replace("ｔ", "t").replace("Ｔ", "T")
    blocked = ("预测", "rul", "剩余寿命", "还能用多久", "损伤类型",
               "裂纹长度", "裂纹类型", "检修", "换件", "适航")
    if any(word in text for word in blocked):
        return _unsupported(
            gid, "规则回退：预测、RUL、损伤类型或维修建议不在当前可签发范围内"
        )

    has85 = bool(re.search(r"(?:t\s*[-_]?\s*85(?!\d)|85\s*%|百分之八十五)", text))
    has50 = bool(re.search(r"(?:t\s*[-_]?\s*50(?!\d)|50\s*%|百分之五十)", text))

    if has85 and has50:
        return Plan("metric_query", gid, ("t85", "t50"), "规则回退：识别到 t85 与 t50")
    if has85:
        return Plan("metric_query", gid, ("t85",), "规则回退：识别到 t85")
    if has50:
        return Plan("metric_query", gid, ("t50",), "规则回退：识别到 t50")
    if "寿命" in text or "阈值" in text or "指标" in text:
        return Plan("metric_query", gid, ("t85", "t50"), "规则回退：泛化为 t85 与 t50")

    return _unsupported(
        gid, "没有识别到可执行的 t85/t50 查询；当前只支持 L1-06 的数值指标"
    )


def compile_question(question: str | None, gid: str,
                     supported: Iterable[str]) -> PlannerResult:
    """Compile a question into a validated plan; never returns a numeric answer."""
    supported = tuple(supported)
    if gid not in supported:
        return PlannerResult(
            plan=_unsupported(gid, f"gid {gid} 不在支持列表"),
            source="fallback",
            error="unsupported gid",
        )

    text = (question or "").strip()
    if not text:
        return PlannerResult(
            plan=Plan("metric_query", gid, ("t85", "t50"), "未提供问题，默认查询两个指标"),
            source="default",
        )

    base, model, _ = _llm_config()
    error: str | None = None
    if base:
        try:
            raw = _call_llm(text, gid)
            plan = _parse_plan(raw, gid, supported)
            return PlannerResult(plan=plan, source="llm", model=model)
        except Exception as exc:  # network, JSON, whitelist, provider error
            error = f"{type(exc).__name__}: {exc}"[:300]

    plan = _fallback(text, gid)
    return PlannerResult(plan=plan, source="fallback", error=error)
