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


if __name__ == "__main__":
    unittest.main()
