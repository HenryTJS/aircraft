# -*- coding: utf-8 -*-
"""As-of prefix tests.

The point of these tests is the negative claim: a query at cycle X must not
change when the prefix file still contains later rows.  The response must also
not expose ``t85`` or ``n_f``.
"""
import unittest

import numpy as np
from fastapi.testclient import TestClient

from web.app import app
from web.asof import PREFIX, state_from_prefix


def _load_prefix(gid="L1-13"):
    return {k: np.asarray(v) for k, v in np.load(PREFIX / f"{gid}.npz", allow_pickle=True).items()}


class TestAsOf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_returns_prefix_only(self):
        r = self.client.get("/api/asof", params={"gid": "L1-13", "cycle": 50000})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertLessEqual(body["state"]["cycle"], 50000)
        self.assertFalse(body["boundary"]["contains_future"])
        self.assertFalse(body["boundary"]["t85_available"])
        self.assertNotIn("t85_pct", body)
        self.assertNotIn("n_f", body)

    def test_monotonic_prefix(self):
        vals = []
        for cycle in (50000, 100000, 200000):
            r = self.client.get("/api/asof", params={"gid": "L1-13", "cycle": cycle})
            self.assertEqual(r.status_code, 200)
            vals.append(r.json()["state"])
        self.assertLessEqual(vals[0]["cum_hits"], vals[1]["cum_hits"])
        self.assertLessEqual(vals[1]["cum_hits"], vals[2]["cum_hits"])
        self.assertLessEqual(vals[0]["cycle"], vals[1]["cycle"])
        self.assertLessEqual(vals[1]["cycle"], vals[2]["cycle"])

    def test_future_invariance(self):
        full = _load_prefix()
        cut_cycle = 100000.0
        cut = {
            k: v[: int(np.searchsorted(full["cycle"], cut_cycle, side="right"))]
            for k, v in full.items()
            if isinstance(v, np.ndarray) and v.ndim == 1 and len(v) == len(full["cycle"])
        }
        # PZT arrays have their own length; keep only states at or before the cut.
        for key in ("pzt_cycle", "pzt_d", "pzt_tof_drift"):
            arr = full[key]
            cut[key] = arr[: int(np.searchsorted(arr, cut_cycle, side="right"))]
        cut["gid"] = full["gid"]
        cut["frame_s"] = full["frame_s"]
        a = state_from_prefix(full, cycle=cut_cycle)
        b = state_from_prefix(cut, cycle=cut_cycle)
        self.assertEqual(a["state"], b["state"])
        self.assertEqual(a["pzt"], b["pzt"])
        self.assertEqual(a["asof"], b["asof"])

    def test_main_prefix_only(self):
        r = self.client.get("/api/asof", params={"gid": "016", "cycle": 10000})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["gid"], "main-016")
        self.assertEqual(body["dataset"], "main")
        self.assertLessEqual(body["state"]["cycle"], 10000)
        self.assertIn("cum_energy", body["state"])
        self.assertIn("ce_log", body["state"])
        self.assertFalse(body["boundary"]["contains_future"])
        self.assertFalse(body["boundary"]["t85_available"])
        self.assertNotIn("t85_pct", body)
        self.assertNotIn("n_f", body)
        self.assertIsNone(body["pzt"])

    def test_main_future_invariance(self):
        full = _load_prefix("main-016")
        cut_cycle = 12000.0
        cut = {
            k: v[: int(np.searchsorted(full["cycle"], cut_cycle, side="right"))]
            for k, v in full.items()
            if isinstance(v, np.ndarray) and v.ndim == 1 and len(v) == len(full["cycle"])
        }
        for key in ("gid", "dataset", "n_windows", "window_s", "load_hz", "source"):
            cut[key] = full[key]
        a = state_from_prefix(full, cycle=cut_cycle)
        b = state_from_prefix(cut, cycle=cut_cycle)
        self.assertEqual(a["state"], b["state"])
        self.assertEqual(a["asof"], b["asof"])
        self.assertEqual(a["gid"], "main-016")

    def test_unknown_gid(self):
        r = self.client.get("/api/asof", params={"gid": "L1-99", "cycle": 1})
        self.assertEqual(r.status_code, 404)

    def test_before_first_frame(self):
        r = self.client.get("/api/asof", params={"gid": "L1-13", "cycle": 0})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
