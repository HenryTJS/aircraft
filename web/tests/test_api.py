# -*- coding: utf-8 -*-
"""API tests for the L1-06 vertical slice.

These tests re-execute the raw metric, so they need E:/l1 mounted. The first
request is the slow one; the app and validator both cache thereafter.
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
