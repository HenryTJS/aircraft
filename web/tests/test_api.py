# -*- coding: utf-8 -*-
"""API tests for the L1 and F-MOC vertical slices.

These tests re-execute the raw tools, so they need E:/l1 and E:/fmoc mounted.
The first request is the slow one; the app and validator both cache thereafter.
"""
import os
import unittest

os.environ.setdefault("SHM_LLM_DISABLE", "1")

from fastapi.testclient import TestClient

from web.app import app

L1_DATA = "E:/l1"


@unittest.skipUnless(os.path.isdir(L1_DATA), "E:/l1 not mounted")
class TestAssistantAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertIn("L1-06", r.json()["supported"])

    def test_t062_refused(self):
        r = self.client.post("/api/ask", json={"gid": "L1-06", "t": 0.62})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "refused")
        self.assertEqual(body["gate"], "temporal")
        self.assertIn("temporal_leakage", body["failed_checks"])
        self.assertNotIn("graph", body)
        self.assertNotIn("t85_pct", str(body))

    def test_t095_passes(self):
        r = self.client.post("/api/ask", json={"gid": "L1-06", "t": 0.95})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["verification"]["status"], "pass")
        claims = {c["predicate"]: c for c in body["graph"]["claims"]}
        self.assertAlmostEqual(claims["t85_pct"]["value"], 93.76, places=2)
        self.assertAlmostEqual(claims["t50_pct"]["value"], 68.02, places=2)
        self.assertEqual(claims["t85_pct"]["allowed_lifetime_max"], 0.95)

    def test_t093_refused(self):
        r = self.client.post("/api/ask", json={"gid": "L1-06", "t": 0.93})
        self.assertEqual(r.json()["status"], "refused")

    def test_question_t85_only(self):
        r = self.client.post(
            "/api/ask", json={"gid": "L1-06", "t": 0.95, "question": "t85 是多少"}
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        claims = {c["predicate"]: c for c in body["graph"]["claims"]}
        self.assertEqual(set(claims), {"t85_pct"})
        self.assertEqual(body["planner"]["source"], "fallback")

    def test_question_t50_only(self):
        r = self.client.post(
            "/api/ask", json={"gid": "L1-06", "t": 0.95, "question": "t50 是多少"}
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        claims = {c["predicate"]: c for c in body["graph"]["claims"]}
        self.assertEqual(set(claims), {"t50_pct"})
        self.assertEqual(body["planner"]["source"], "fallback")

    def test_question_unsupported(self):
        r = self.client.post(
            "/api/ask", json={"gid": "L1-06", "t": 0.95, "question": "预测剩余寿命"}
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "unsupported")
        self.assertNotIn("graph", body)
        self.assertNotIn("t85_pct", str(body))

    def test_fbg_profile(self):
        r = self.client.post(
            "/api/ask", json={"gid": "L1-30", "t": 0.95,
                              "question": "FBG 应变剖面"}
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["gate"], "not_applicable")
        self.assertEqual(body["planner"]["plan"]["tool"], "fbg")
        claims = {c["predicate"]: c for c in body["graph"]["claims"]}
        self.assertEqual(set(claims), {"shape_rob25_last"})
        self.assertEqual(claims["shape_rob25_last"]["status"], "supported")
        self.assertIsNone(claims["shape_rob25_last"]["boundary"]["cycle_anchor"])
        self.assertEqual(body["verification"]["status"], "pass")

    def test_dfos_partial(self):
        r = self.client.post(
            "/api/ask", json={"gid": "L1-03", "t": 0.95,
                              "question": "DFOS 预警点"}
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "partial")
        self.assertEqual(body["gate"], "boundary")
        claims = {c["predicate"]: c for c in body["graph"]["claims"]}
        self.assertEqual(claims["hi_end"]["status"], "supported")
        self.assertEqual(claims["warn50_pct"]["status"], "insufficient")
        self.assertFalse(claims["warn50_pct"]["boundary"]["threshold_resolved"])
        self.assertIn("未签发", body["answer"])
        self.assertEqual(body["verification"]["status"], "pass")

    def test_pzt_censored_insufficient(self):
        r = self.client.post(
            "/api/ask", json={"gid": "L1-06", "t": 0.95,
                              "question": "PZT 导波 t85"}
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "insufficient")
        self.assertEqual(body["gate"], "boundary")
        claim = body["graph"]["claims"][0]
        self.assertEqual(claim["predicate"], "t85_pct")
        self.assertEqual(claim["status"], "insufficient")
        self.assertTrue(claim["boundary"]["censored"])
        self.assertIn("不签发", body["answer"])
        self.assertEqual(body["verification"]["status"], "pass")

    def test_pzt_supported(self):
        r = self.client.post(
            "/api/ask", json={"gid": "L1-13", "t": 0.95,
                              "question": "PZT 的 t85"}
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        claim = body["graph"]["claims"][0]
        self.assertEqual(claim["status"], "supported")
        self.assertAlmostEqual(claim["value"], 87.7366, places=3)
        self.assertEqual(claim["allowed_lifetime_max"], 0.95)
        self.assertEqual(body["verification"]["status"], "pass")

    def test_pzt_temporal_refused(self):
        r = self.client.post(
            "/api/ask", json={"gid": "L1-13", "t": 0.80,
                              "question": "PZT 的 t85"}
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "refused")
        self.assertEqual(body["gate"], "temporal")
        self.assertIn("temporal_leakage", body["failed_checks"])
        self.assertNotIn("graph", body)

    def test_conflict_partial(self):
        r = self.client.post(
            "/api/ask", json={"gid": "L1-03", "t": 0.95,
                              "question": "AE、DFOS、PZT、FBG 能不能给出四个可比的 t85？"}
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "partial")
        self.assertEqual(body["gate"], "boundary")
        self.assertEqual(body["planner"]["plan"]["tool"], "conflict")
        self.assertEqual(len(body["graph"]["claims"]), 5)
        self.assertIn("不能给出四个可比的 t85", body["answer"])
        fbg = next(c for c in body["graph"]["claims"]
                   if c["predicate"] == "fbg_profile")
        self.assertEqual(fbg["status"], "insufficient")
        self.assertIn("2", fbg["missing_evidence"])
        self.assertEqual(body["verification"]["status"], "pass")

    def test_conflict_temporal_refused(self):
        r = self.client.post(
            "/api/ask", json={"gid": "L1-03", "t": 0.80,
                              "question": "四模态 t85 是否可比？"}
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "refused")
        self.assertEqual(body["gate"], "temporal")
        self.assertIn("temporal_leakage", body["failed_checks"])
        self.assertNotIn("graph", body)

    @unittest.skipUnless(os.path.isdir("E:/fmoc"), "E:/fmoc not mounted")
    def test_fmoc_partial(self):
        r = self.client.post(
            "/api/ask",
            json={"gid": "spec2", "t": 0.95,
                  "question": "F-MOC spec2 的 t85 是多少"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "partial")
        claims = {c["predicate"]: c for c in body["graph"]["claims"]}
        self.assertAlmostEqual(claims["t85_hit_pct"]["value"], 74.55, places=2)
        self.assertEqual(claims["t85_hit_pct"]["status"], "supported")
        self.assertEqual(claims["t85_dic_pct"]["status"], "insufficient")
        self.assertTrue(claims["t85_dic_pct"]["boundary"]["test_end_uncertain"])

    @unittest.skipUnless(os.path.isdir("E:/fmoc"), "E:/fmoc not mounted")
    def test_fmoc_temporal_refused(self):
        r = self.client.post(
            "/api/ask",
            json={"gid": "spec2", "t": 0.70,
                  "question": "F-MOC spec2 的 t85 是多少"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "refused")
        self.assertEqual(body["gate"], "temporal")

    def test_workflow_ok_with_gap(self):
        r = self.client.post(
            "/api/ask",
            json={"gid": "L1-13", "t": 0.95,
                  "question": "先查 L1-13 的 AE t85，再查 PZT t85，最后判断是否一致"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["gate"], "pass")
        self.assertEqual(body["planner"]["plan"]["tool"], "workflow")
        steps = body["planner"]["plan"]["steps"]
        self.assertEqual([s["tool"] for s in steps], ["metric", "pzt"])
        claims = {c["predicate"]: c for c in body["graph"]["claims"]}
        self.assertAlmostEqual(claims["t85_gap_pp"]["value"], 5.312145, places=5)
        self.assertEqual(claims["t85_gap_pp"]["status"], "supported")
        self.assertIn("数值差=5.31 pp", body["answer"])
        self.assertEqual(body["verification"]["status"], "pass")

    def test_workflow_temporal_refused(self):
        r = self.client.post(
            "/api/ask",
            json={"gid": "L1-13", "t": 0.80,
                  "question": "先查 L1-13 的 AE t85，再查 PZT t85，最后判断是否一致"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "refused")
        self.assertEqual(body["gate"], "temporal")
        self.assertIn("temporal_leakage", body["failed_checks"])
        self.assertNotIn("graph", body)

    def test_unknown_gid(self):
        r = self.client.post("/api/ask", json={"gid": "L1-99", "t": 0.95})
        self.assertEqual(r.status_code, 404)

    def test_index_injects_assistant(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("/static/assistant.js", r.text)
        self.assertIn("/static/assistant.css", r.text)

    def test_legacy_index_does_not_404(self):
        r = self.client.get("/data/index.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("SHM_INDEX", r.text)


if __name__ == "__main__":
    unittest.main()
