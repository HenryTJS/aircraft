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

INTENTS = ("metric_query", "fbg_profile", "dfos_block", "pzt_index",
           "fmoc_profile", "conflict_case", "workflow_case", "unsupported")
METRICS = ("t85", "t50")
TOOLS = ("metric", "fbg", "dfos", "pzt", "fmoc", "conflict", "workflow")
INTENT_TOOL = {
    "metric_query": "metric",
    "fbg_profile": "fbg",
    "dfos_block": "dfos",
    "pzt_index": "pzt",
    "fmoc_profile": "fmoc",
    "conflict_case": "conflict",
    "workflow_case": "workflow",
}
TOOL_INTENT = {value: key for key, value in INTENT_TOOL.items()}
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
- tools: {tools}
- metrics: t85, t50 (only for tool=metric)
- base: post or bi (only for tool=dfos)
- stride: integer 1..10 (only for tool=pzt)

Return exactly one JSON object:
{{"intent":"metric_query","tool":"metric","gid":"{gid}","metrics":["t85"],"base":"post","stride":1,"reason":"short"}}
or one of:
{{"intent":"fbg_profile","tool":"fbg","gid":"{gid}","metrics":[],"base":"post","stride":1,"reason":"short"}}
{{"intent":"dfos_block","tool":"dfos","gid":"{gid}","metrics":[],"base":"post","stride":1,"reason":"short"}}
{{"intent":"pzt_index","tool":"pzt","gid":"{gid}","metrics":[],"base":"post","stride":1,"reason":"short"}}
{{"intent":"fmoc_profile","tool":"fmoc","gid":"{gid}","metrics":[],"base":"post","stride":1,"reason":"short"}}
{conflict}{workflow}{{"intent":"unsupported","tool":"","gid":"{gid}","metrics":[],"base":"post","stride":1,"reason":"short"}}

Rules:
- Use only a tool listed in tools.
- metric_query: the question asks for AE t85/t50. Use ["t85"], ["t50"], or both.
- fbg_profile: FBG / 光纤光栅 / 应变剖面 / 加载窗 / shape_rob25.
- dfos_block: DFOS / 分布式应变 / 块级 HI / 预警点 / warn50 / hi_end.
- pzt_index: PZT / 导波 / 退相关 / TOF / 飞行时间.
- fmoc_profile: F-MOC / spec1..spec7 / Vallen / pridb; only if fmoc is listed.
- conflict_case: the question asks whether AE/FBG/DFOS/PZT can be compared,
  why their numbers disagree, or whether all four modalities are available.
  Use this only when "conflict" is listed in tools.
- workflow_case: the question explicitly asks for a sequence, a joint check,
  or an agreement check between AE t85 and PZT t85. Use this only when
  "workflow" is listed in tools. The steps are always metric t85 then pzt.
- If the question asks for prediction, RUL, damage type, crack length,
  maintenance action, or anything outside gid {gid}, use "unsupported".
- Never put numeric t85/t50 values in the plan.

Question:
{question}
"""


@dataclass(frozen=True)
class Plan:
    intent: str
    gid: str
    tool: str = "metric"
    metrics: tuple[str, ...] = ()
    base: str = "post"
    stride: int = 1
    reason: str = ""
    steps: tuple[dict, ...] = ()

    def as_dict(self) -> dict:
        return {
            "intent": self.intent,
            "tool": self.tool,
            "gid": self.gid,
            "metrics": list(self.metrics),
            "base": self.base,
            "stride": self.stride,
            "steps": [dict(step) for step in self.steps],
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


def _allowed_tools(gid: str, supported) -> tuple[str, ...]:
    """Return the tools a gid is allowed to use.

    `supported` can be the API's metadata dict or a plain iterable of gids.
    The plain form is kept for the original metric-only planner tests.
    """
    if isinstance(supported, dict):
        meta = supported.get(gid) or {}
        raw = meta.get("tools") or ("metric",)
    else:
        raw = ("metric",)
    tools = tuple(t for t in raw if t in TOOL_INTENT)
    return tools


def _supported_gids(supported) -> tuple[str, ...]:
    return tuple(supported.keys()) if isinstance(supported, dict) else tuple(supported)


def _call_llm(question: str, gid: str, allowed_tools: Iterable[str]) -> str:
    base, model, key = _llm_config()
    if not base:
        raise RuntimeError("SHM_LLM_BASE_URL is not configured")
    timeout = float(os.environ.get("SHM_LLM_TIMEOUT", "20"))
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    conflict = ""
    if "conflict" in allowed_tools:
        conflict = (
            '{"intent":"conflict_case","tool":"conflict","gid":"%s",'
            '"metrics":[],"base":"post","stride":1,"reason":"short"}\n' % gid
        )
    workflow = ""
    if "workflow" in allowed_tools:
        workflow = (
            '{"intent":"workflow_case","tool":"workflow","gid":"%s",'
            '"metrics":[],"steps":[{"tool":"metric","metrics":["t85"]},'
            '{"tool":"pzt","metrics":[]}],"base":"post","stride":1,'
            '"reason":"short"}\\n' % gid
        )
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 260,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _PROMPT.format(
                gid=gid, tools=", ".join(allowed_tools),
                conflict=conflict, workflow=workflow, question=question)},
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


def _parse_plan(raw: str | dict, gid: str, supported) -> Plan:
    obj = raw if isinstance(raw, dict) else json.loads(_strip_fence(str(raw)))
    if not isinstance(obj, dict):
        raise ValueError("plan is not an object")
    intent = str(obj.get("intent", "")).strip()
    if intent not in INTENTS:
        raise ValueError(f"unknown intent: {intent!r}")

    plan_gid = str(obj.get("gid", gid) or gid).strip()
    if plan_gid not in _supported_gids(supported):
        raise ValueError(f"gid outside whitelist: {plan_gid!r}")
    if plan_gid != gid:
        raise ValueError(f"gid mismatch: {plan_gid!r} != {gid!r}")

    if intent == "unsupported":
        return _unsupported(gid, str(obj.get("reason", "") or ""))

    allowed = _allowed_tools(gid, supported)
    expected_tool = INTENT_TOOL[intent]
    tool = str(obj.get("tool", expected_tool) or expected_tool).strip()
    if tool not in TOOLS:
        raise ValueError(f"tool outside whitelist: {tool!r}")
    if tool not in allowed:
        raise ValueError(f"tool {tool!r} not allowed for {gid}")
    if tool != expected_tool:
        raise ValueError(f"intent {intent!r} does not match tool {tool!r}")

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

    if tool == "metric":
        if not metrics:
            raise ValueError("metric_query requires at least one metric")
    else:
        metrics = []

    steps: list[dict] = []
    if intent == "workflow_case":
        raw_steps = obj.get("steps")
        if not isinstance(raw_steps, list) or len(raw_steps) != 2:
            raise ValueError("workflow_case requires exactly two steps")
        for index, item in enumerate(raw_steps):
            if not isinstance(item, dict):
                raise ValueError("workflow step is not an object")
            step_tool = str(item.get("tool", "") or "").strip()
            expected = "metric" if index == 0 else "pzt"
            if step_tool != expected:
                raise ValueError(
                    f"workflow step {index + 1} must be {expected}"
                )
            if step_tool not in allowed:
                raise ValueError(f"workflow tool {step_tool!r} not allowed")
            step_metrics = []
            if step_tool == "metric":
                for raw in item.get("metrics") or []:
                    key = str(raw).strip().lower()
                    if key not in _ALIASES:
                        raise ValueError(f"metric outside whitelist: {raw!r}")
                    step_metrics.append(_ALIASES[key])
                if not step_metrics:
                    step_metrics = ["t85"]
                if step_metrics != ["t85"]:
                    raise ValueError("workflow AE step must query t85")
            steps.append({"tool": step_tool, "metrics": step_metrics})

    base = str(obj.get("base", "post") or "post").strip().lower()
    if base not in ("post", "bi"):
        raise ValueError(f"base outside whitelist: {base!r}")
    try:
        stride = int(obj.get("stride", 1) or 1)
    except (TypeError, ValueError) as exc:
        raise ValueError("stride is not an integer") from exc
    if not 1 <= stride <= 10:
        raise ValueError("stride outside 1..10")

    reason = str(obj.get("reason", "") or "").strip()
    if len(reason) > 300:
        reason = reason[:300]
    return Plan(intent=intent, gid=gid, tool=tool, metrics=tuple(metrics),
                base=base, stride=stride, reason=reason, steps=tuple(steps))


def _unsupported(gid: str, reason: str) -> Plan:
    return Plan(intent="unsupported", gid=gid, tool="", reason=reason)


def _metric_plan(question: str, gid: str) -> Plan:
    text = question.strip().lower().replace("ｔ", "t").replace("Ｔ", "T")
    has85 = bool(re.search(r"(?:t\s*[-_]?\s*85(?!\d)|85\s*%|百分之八十五)", text))
    has50 = bool(re.search(
        r"(?:t\s*[-_]?\s*50(?!\d)|50\s*%|百分之五十|半寿命|一半寿命|中位寿命)",
        text,
    ))
    if has85 and has50:
        return Plan("metric_query", gid, "metric", ("t85", "t50"),
                    reason="规则回退：识别到 t85 与 t50")
    if has85:
        return Plan("metric_query", gid, "metric", ("t85",),
                    reason="规则回退：识别到 t85")
    if has50:
        return Plan("metric_query", gid, "metric", ("t50",),
                    reason="规则回退：识别到 t50")
    return Plan("metric_query", gid, "metric", ("t85", "t50"),
                reason="规则回退：泛化为 t85 与 t50")


def _explicit_tools(text: str) -> list[str]:
    """Tools explicitly named by the question, in deterministic order."""
    text = text.lower()
    requested: list[str] = []
    if any(word in text for word in ("fmoc", "f-moc", "f m o c", "vallen", "pridb")):
        requested.append("fmoc")
    if any(word in text for word in ("ae", "声发射")):
        requested.append("metric")
    if any(word in text for word in ("pzt", "导波", "退相关", "tof", "飞行时间")):
        requested.append("pzt")
    if any(word in text for word in ("dfos", "分布式应变", "块级", "预警点", "warn50", "hi_end")):
        requested.append("dfos")
    if any(word in text for word in ("fbg", "光纤光栅", "应变剖面", "加载窗", "shape_rob25")):
        requested.append("fbg")
    requested = list(dict.fromkeys(requested))
    # F-MOC is an AE dataset, but its tool is not the L1 metric.  If the
    # question names F-MOC, do not also route it to metric just because it
    # says "AE".
    if "fmoc" in requested:
        return ["fmoc"]
    return requested


def _fallback(question: str, gid: str, supported) -> Plan:
    text = question.strip().lower().replace("ｔ", "t").replace("Ｔ", "T")
    blocked = ("预测", "rul", "剩余寿命", "还能用多久", "损伤类型",
               "裂纹", "检修", "换件", "适航")
    if any(word in text for word in blocked):
        return _unsupported(
            gid, "规则回退：预测、RUL、损伤类型或维修建议不在当前可签发范围内"
        )

    mentioned = {
        re.sub(r"\s+", "", item) for item in re.findall(r"l\s*\d+\s*-\s*\d+", text)
    }
    if len(mentioned) > 1 or (mentioned and gid.lower() not in mentioned):
        return _unsupported(
            gid,
            "问题涉及多个试件或多个 gid；当前 API 一次只处理一个 gid，"
            "跨试件比较多步编排尚未实现",
        )

    audit_words = ("报告", "报告里", "文中", "旧表", "审计", "核对")
    audit_ask = ("能用吗", "对吗", "是否可用", "可信吗", "能不能用", "审计", "核对")
    audit_value = re.search(r"(?:t\s*[-_]?\s*(?:50|85)|\d{1,3}(?:\.\d+)?\s*%)", text)
    if audit_value and any(w in text for w in audit_words) and any(w in text for w in audit_ask):
        return _unsupported(
            gid,
            "外部报告中的数值不能直接作为证据；当前系统只重算 raw 数据，"
            "没有报告审计工具，不能替报告里的结论背书",
        )

    allowed = _allowed_tools(gid, supported)
    if not allowed:
        return _unsupported(gid, f"gid {gid} 没有可调用的工具")

    temporal = re.search(r"(?:在|当)\s*(\d{1,3})\s*%\s*(?:时|的时候)", text)
    if temporal and ("结论" in text or "看到" in text or "能不能" in text):
        if "metric" in allowed:
            return Plan(
                "metric_query", gid, "metric", ("t85",),
                reason="规则回退：识别到寿命时点查询，交给时间门判断",
            )

    def has(*words: str) -> bool:
        return any(word in text for word in words)

    if ("conflict" in allowed and gid == "L1-03"
            and has("冲突", "多模态", "四模态", "四个模态", "可比",
                    "不一致", "差异", "对不上", "一致", "谁先", "领先",
                    "滞后", "相差", "为什么不同", "availability", "齐全")):
        return Plan("conflict_case", gid, "conflict", (),
                    reason="规则回退：识别到跨模态可比性/可用性查询")

    if ("workflow" in allowed and "metric" in allowed and "pzt" in allowed
            and has("先", "再", "然后", "最后", "多步", "联合", "综合",
                    "一致", "交叉", "对照", "一起", "同时", "都查", "分别")
            and has("pzt", "导波")
            and has("ae", "声发射", "t85", "t50", "两个", "两者")):
        steps = (
            {"tool": "metric", "metrics": ["t85"]},
            {"tool": "pzt", "metrics": []},
        )
        return Plan("workflow_case", gid, "workflow", steps=steps,
                    reason="规则回退：识别到 AE 与 PZT 的顺序/一致性检查")

    requested = _explicit_tools(text)

    if len(requested) > 1:
        return _unsupported(gid, "一次只支持一个工具；问题同时指向多个模态")
    if requested and requested[0] not in allowed:
        return _unsupported(
            gid, f"问题指向 {requested[0]}，但 {gid} 的白名单是 {', '.join(allowed)}"
        )

    tool = requested[0] if requested else ""
    if not tool:
        has85 = bool(re.search(r"(?:t\s*[-_]?\s*85(?!\d)|85\s*%|百分之八十五)", text))
        has50 = bool(re.search(
            r"(?:t\s*[-_]?\s*50(?!\d)|50\s*%|百分之五十|半寿命|一半寿命|中位寿命)",
            text,
        ))
        wants_metric = (has85 or has50 or "寿命" in text
                        or "阈值" in text or "指标" in text)
        if wants_metric:
            if "metric" in allowed:
                return _metric_plan(question, gid)
            if "pzt" in allowed:
                tool = "pzt"
            elif "fmoc" in allowed:
                tool = "fmoc"
            else:
                return _unsupported(
                    gid, f"{gid} 没有 AE t85/t50 工具；可用工具为 {', '.join(allowed)}"
                )
        elif len(allowed) == 1:
            tool = allowed[0]
        else:
            return _unsupported(gid, "没有识别到可执行的工具查询")

    if tool == "metric":
        return _metric_plan(question, gid)

    base = "post"
    if has("冲击前", "bi", "bi 基准"):
        base = "bi"
    stride = 1
    match = re.search(r"stride\s*[=:：]?\s*(\d+)", text)
    if match:
        stride = max(1, min(10, int(match.group(1))))
    return Plan(TOOL_INTENT[tool], gid, tool, (), base, stride,
                reason=f"规则回退：识别到 {tool} 查询")


def _default_plan(gid: str, supported) -> Plan:
    allowed = _allowed_tools(gid, supported)
    if not allowed:
        return _unsupported(gid, f"gid {gid} 没有可调用的工具")
    if "metric" in allowed:
        return Plan("metric_query", gid, "metric", ("t85", "t50"),
                    reason="未提供问题，默认查询两个指标")
    tool = allowed[0]
    return Plan(TOOL_INTENT[tool], gid, tool, (),
                reason=f"未提供问题，默认调用 {tool}")


def compile_question(question: str | None, gid: str, supported) -> PlannerResult:
    """Compile a question into a validated plan; never returns a numeric answer."""
    if gid not in _supported_gids(supported):
        return PlannerResult(
            plan=_unsupported(gid, f"gid {gid} 不在支持列表"),
            source="fallback",
            error="unsupported gid",
        )

    text = (question or "").strip()
    if not text:
        return PlannerResult(plan=_default_plan(gid, supported), source="default")

    # A cross-modal question names several tools by construction. Resolve it
    # deterministically before the LLM path so "multiple tools" is not an
    # error; the conflict graph itself decides which claims are signable.
    fallback_plan = _fallback(text, gid, supported)
    if fallback_plan.tool in ("conflict", "workflow"):
        return PlannerResult(plan=fallback_plan, source="fallback")
    # These two are scope boundaries, not semantic ambiguities: a model must
    # not turn a cross-gid question into a single-gid answer, or audit an
    # external report without the raw data.
    if fallback_plan.intent == "unsupported" and (
        "跨试件" in fallback_plan.reason or "报告审计" in fallback_plan.reason
    ):
        return PlannerResult(plan=fallback_plan, source="fallback")
    if "时间门" in fallback_plan.reason:
        return PlannerResult(plan=fallback_plan, source="fallback")

    base, model, _ = _llm_config()
    error: str | None = None
    if base:
        try:
            raw = _call_llm(text, gid, _allowed_tools(gid, supported))
            plan = _parse_plan(raw, gid, supported)
            explicit = _explicit_tools(text)
            if plan.tool == "workflow":
                if set(explicit) - {"metric", "pzt"}:
                    raise ValueError("workflow plan names an extra tool")
            else:
                if len(explicit) > 1:
                    raise ValueError("question names multiple tools")
                if (len(explicit) == 1 and plan.intent != "unsupported"
                        and plan.tool != explicit[0]):
                    raise ValueError(
                        f"question names {explicit[0]} but plan uses {plan.tool}"
                    )
            if plan.intent == "unsupported":
                # A model may over-refuse an explicit in-scope tool query
                # ("PZT t85"). The deterministic parser is allowed to
                # recover only when it identifies an explicit non-metric
                # tool, never for prediction/RUL/damage-type questions.
                fallback = _fallback(text, gid, supported)
                if fallback.intent != "unsupported" and fallback.tool != "metric":
                    return PlannerResult(
                        plan=fallback,
                        source="fallback",
                        error="LLM returned unsupported; deterministic parser found an explicit whitelisted tool",
                    )
            return PlannerResult(plan=plan, source="llm", model=model)
        except Exception as exc:  # network, JSON, whitelist, provider error
            error = f"{type(exc).__name__}: {exc}"[:300]

    plan = _fallback(text, gid, supported)
    return PlannerResult(plan=plan, source="fallback", error=error)
