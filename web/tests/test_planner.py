# -*- coding: utf-8 -*-
"""Tests for the restricted semantic compiler. No network calls."""
from __future__ import annotations

import os
import unittest
from unittest import mock

from web import planner


class TestPlanner(unittest.TestCase):
    def setUp(self) -> None:
        self._keys = ("SHM_LLM_BASE_URL", "SHM_LLM_MODEL", "SHM_LLM_API_KEY")
        self._old = {k: os.environ.get(k) for k in self._keys}
        for key in self._keys:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_empty_question_defaults_both(self) -> None:
        result = planner.compile_question(None, "L1-06", ["L1-06"])
        self.assertEqual(result.source, "default")
        self.assertEqual(result.plan.metrics, ("t85", "t50"))
        self.assertEqual(result.plan.intent, "metric_query")

    def test_fallback_t85(self) -> None:
        result = planner.compile_question("L1-06 的 t85 是多少", "L1-06", ["L1-06"])
        self.assertEqual(result.source, "fallback")
        self.assertEqual(result.plan.metrics, ("t85",))

    def test_fallback_both(self) -> None:
        result = planner.compile_question("t50 和 t85 分别多少", "L1-06", ["L1-06"])
        self.assertEqual(result.plan.metrics, ("t85", "t50"))

    def test_fallback_unsupported_prediction(self) -> None:
        result = planner.compile_question("预测一下剩余寿命", "L1-06", ["L1-06"])
        self.assertEqual(result.plan.intent, "unsupported")
        self.assertEqual(result.plan.metrics, ())

    def test_llm_valid_plan(self) -> None:
        os.environ["SHM_LLM_BASE_URL"] = "http://127.0.0.1:9/v1"
        os.environ["SHM_LLM_MODEL"] = "test-model"
        raw = ('{"intent":"metric_query","gid":"L1-06",'
               '"metrics":["t50"],"reason":"asked t50"}')
        with mock.patch.object(planner, "_call_llm", return_value=raw):
            result = planner.compile_question("随便问", "L1-06", ["L1-06"])
        self.assertEqual(result.source, "llm")
        self.assertEqual(result.model, "test-model")
        self.assertEqual(result.plan.metrics, ("t50",))

    def test_llm_wrong_gid_falls_back(self) -> None:
        os.environ["SHM_LLM_BASE_URL"] = "http://127.0.0.1:9/v1"
        raw = '{"intent":"metric_query","gid":"L1-03","metrics":["t85"]}'
        with mock.patch.object(planner, "_call_llm", return_value=raw):
            result = planner.compile_question("t85 是多少", "L1-06", ["L1-06"])
        self.assertEqual(result.source, "fallback")
        self.assertIn("gid", result.error or "")
        self.assertEqual(result.plan.metrics, ("t85",))

    def test_llm_bad_json_falls_back(self) -> None:
        os.environ["SHM_LLM_BASE_URL"] = "http://127.0.0.1:9/v1"
        with mock.patch.object(planner, "_call_llm", return_value="not json"):
            result = planner.compile_question("t50 是多少", "L1-06", ["L1-06"])
        self.assertEqual(result.source, "fallback")
        self.assertEqual(result.plan.metrics, ("t50",))

    def test_llm_reason_not_exposed(self) -> None:
        os.environ["SHM_LLM_BASE_URL"] = "http://127.0.0.1:9/v1"
        raw = ('{"intent":"unsupported","gid":"L1-06","metrics":[],'
               '"reason":"剩余寿命约为 1000 循环"}')
        with mock.patch.object(planner, "_call_llm", return_value=raw):
            result = planner.compile_question("还能用多久", "L1-06", ["L1-06"])
        self.assertEqual(result.source, "llm")
        self.assertNotIn("1000", str(result.as_dict()))
        self.assertNotIn("reason", result.as_dict()["plan"])

    def test_unsupported_gid(self) -> None:
        result = planner.compile_question("t85", "L1-99", ["L1-06"])
        self.assertEqual(result.plan.intent, "unsupported")

    def test_empty_question_fbg_default(self) -> None:
        supported = {"L1-30": {"tools": ("fbg",)}}
        result = planner.compile_question(None, "L1-30", supported)
        self.assertEqual(result.source, "default")
        self.assertEqual(result.plan.intent, "fbg_profile")
        self.assertEqual(result.plan.tool, "fbg")

    def test_fallback_fbg_profile(self) -> None:
        supported = {"L1-30": {"tools": ("fbg",)}}
        result = planner.compile_question("FBG 应变剖面", "L1-30", supported)
        self.assertEqual(result.plan.intent, "fbg_profile")
        self.assertEqual(result.plan.tool, "fbg")

    def test_fallback_dfos_profile(self) -> None:
        supported = {"L1-03": {"tools": ("dfos",)}}
        result = planner.compile_question("DFOS 预警点", "L1-03", supported)
        self.assertEqual(result.plan.intent, "dfos_block")
        self.assertEqual(result.plan.base, "post")

    def test_fallback_pzt_t85(self) -> None:
        supported = {"L1-13": {"tools": ("pzt",)}}
        result = planner.compile_question("PZT 的 t85", "L1-13", supported)
        self.assertEqual(result.plan.intent, "pzt_index")
        self.assertEqual(result.plan.tool, "pzt")

    def test_fallback_explicit_tool_not_allowed(self) -> None:
        supported = {"L1-06": {"tools": ("metric", "pzt")}}
        result = planner.compile_question("FBG 剖面", "L1-06", supported)
        self.assertEqual(result.plan.intent, "unsupported")

    def test_llm_valid_pzt_plan(self) -> None:
        os.environ["SHM_LLM_BASE_URL"] = "http://127.0.0.1:9/v1"
        os.environ["SHM_LLM_MODEL"] = "test-model"
        supported = {"L1-13": {"tools": ("pzt",)}}
        raw = ('{"intent":"pzt_index","tool":"pzt","gid":"L1-13",'
               '"metrics":[],"base":"post","stride":1,"reason":"asked pzt"}')
        with mock.patch.object(planner, "_call_llm", return_value=raw):
            result = planner.compile_question("导波 t85", "L1-13", supported)
        self.assertEqual(result.source, "llm")
        self.assertEqual(result.plan.tool, "pzt")

    def test_llm_tool_not_allowed_falls_back(self) -> None:
        os.environ["SHM_LLM_BASE_URL"] = "http://127.0.0.1:9/v1"
        supported = {"L1-06": {"tools": ("metric", "pzt")}}
        raw = ('{"intent":"fbg_profile","tool":"fbg","gid":"L1-06",'
               '"metrics":[],"base":"post","stride":1}')
        with mock.patch.object(planner, "_call_llm", return_value=raw):
            result = planner.compile_question("t85 是多少", "L1-06", supported)
        self.assertEqual(result.source, "fallback")
        self.assertEqual(result.plan.tool, "metric")
        self.assertIn("not allowed", result.error or "")

    def test_llm_unsupported_recovers_explicit_tool(self) -> None:
        os.environ["SHM_LLM_BASE_URL"] = "http://127.0.0.1:9/v1"
        supported = {"L1-13": {"tools": ("pzt",)}}
        raw = ('{"intent":"unsupported","gid":"L1-13",'
               '"metrics":[],"base":"post","stride":1}')
        with mock.patch.object(planner, "_call_llm", return_value=raw):
            result = planner.compile_question("PZT 的 t85", "L1-13", supported)
        self.assertEqual(result.source, "fallback")
        self.assertEqual(result.plan.intent, "pzt_index")
        self.assertEqual(result.plan.tool, "pzt")
        self.assertIn("explicit whitelisted tool", result.error or "")

    def test_llm_unsupported_keeps_blocked_prediction(self) -> None:
        os.environ["SHM_LLM_BASE_URL"] = "http://127.0.0.1:9/v1"
        supported = {"L1-13": {"tools": ("pzt",)}}
        raw = ('{"intent":"unsupported","gid":"L1-13",'
               '"metrics":[],"base":"post","stride":1}')
        with mock.patch.object(planner, "_call_llm", return_value=raw):
            result = planner.compile_question("预测剩余寿命", "L1-13", supported)
        self.assertEqual(result.source, "llm")
        self.assertEqual(result.plan.intent, "unsupported")

    def test_cross_gid_is_unsupported(self) -> None:
        supported = {
            "L1-06": {"tools": ("metric", "pzt")},
            "L1-13": {"tools": ("pzt",)},
        }
        result = planner.compile_question(
            "把 L1-06 的 t85 和 L1-13 的 PZT 比一下", "L1-06", supported
        )
        self.assertEqual(result.plan.intent, "unsupported")
        self.assertIn("跨试件", result.plan.reason)

    def test_temporal_question_routes_to_metric(self) -> None:
        supported = {"L1-06": {"tools": ("metric", "pzt")}}
        result = planner.compile_question(
            "L1-06 在 62% 时能看到 93.76% 的结论吗", "L1-06", supported
        )
        self.assertEqual(result.source, "fallback")
        self.assertEqual(result.plan.intent, "metric_query")
        self.assertEqual(result.plan.metrics, ("t85",))

    def test_report_audit_is_unsupported(self) -> None:
        supported = {"L1-03": {"tools": ("metric", "dfos", "pzt", "conflict")}}
        result = planner.compile_question(
            "报告里写 L1-03 AE t85=76.29，这个数能用吗", "L1-03", supported
        )
        self.assertEqual(result.plan.intent, "unsupported")
        self.assertIn("报告审计", result.plan.reason)

    def test_conflict_case_fallback(self) -> None:
        supported = {"L1-03": {"tools": ("metric", "dfos", "pzt", "conflict")}}
        result = planner.compile_question(
            "AE、DFOS、PZT、FBG 能不能给出四个可比的 t85？", "L1-03", supported
        )
        self.assertEqual(result.source, "fallback")
        self.assertEqual(result.plan.intent, "conflict_case")
        self.assertEqual(result.plan.tool, "conflict")

    def test_workflow_fallback(self) -> None:
        supported = {"L1-13": {"tools": ("metric", "pzt", "workflow")}}
        result = planner.compile_question(
            "先查 L1-13 的 AE t85，再查 PZT t85，最后判断是否一致",
            "L1-13", supported,
        )
        self.assertEqual(result.source, "fallback")
        self.assertEqual(result.plan.intent, "workflow_case")
        self.assertEqual(result.plan.tool, "workflow")
        self.assertEqual([s["tool"] for s in result.plan.steps],
                         ["metric", "pzt"])

    def test_fmoc_fallback(self) -> None:
        supported = {"spec2": {"tools": ("fmoc",)}}
        result = planner.compile_question(
            "F-MOC spec2 的 AE t85 是多少", "spec2", supported
        )
        self.assertEqual(result.source, "fallback")
        self.assertEqual(result.plan.intent, "fmoc_profile")
        self.assertEqual(result.plan.tool, "fmoc")

    def test_fmoc_default_when_only_tool(self) -> None:
        supported = {"spec2": {"tools": ("fmoc",)}}
        result = planner.compile_question("t85 是多少", "spec2", supported)
        self.assertEqual(result.plan.intent, "fmoc_profile")
        self.assertEqual(result.plan.tool, "fmoc")

    def test_llm_tool_mismatch_falls_back(self) -> None:
        os.environ["SHM_LLM_BASE_URL"] = "http://127.0.0.1:9/v1"
        supported = {"L1-06": {"tools": ("metric", "pzt")}}
        raw = ('{"intent":"metric_query","tool":"metric","gid":"L1-06",'
               '"metrics":["t85"],"base":"post","stride":1}')
        with mock.patch.object(planner, "_call_llm", return_value=raw):
            result = planner.compile_question("PZT t85", "L1-06", supported)
        self.assertEqual(result.source, "fallback")
        self.assertEqual(result.plan.tool, "pzt")
        self.assertIn("question names pzt", result.error or "")


if __name__ == "__main__":
    unittest.main()
