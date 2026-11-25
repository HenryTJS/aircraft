# -*- coding: utf-8 -*-
"""Boundary-aware claim tests for the FBG / DFOS / PZT skills.

The examples are generated from raw L1 data.  These tests check that a
modality tool cannot sign a point when its own boundary fields say the
number is unresolved, censored, or not on a lifetime axis.
"""
import copy
import json
import os
import unittest

from validate import validate_graph

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCHEMA = os.path.join(ROOT, "schema", "claim_evidence.schema.json")
L1_DATA = "E:/l1"
EXAMPLES = {
    "fbg": os.path.join(ROOT, "examples", "L1-30_fbg.json"),
    "dfos": os.path.join(ROOT, "examples", "L1-03_dfos.json"),
    "pzt": os.path.join(ROOT, "examples", "L1-06_pzt.json"),
    "pzt_supported": os.path.join(ROOT, "examples", "L1-13_pzt.json"),
    "fmoc": os.path.join(ROOT, "examples", "spec2_fmoc.json"),
}


def load(kind):
    with open(SCHEMA, encoding="utf-8") as fh:
        schema = json.load(fh)
    with open(EXAMPLES[kind], encoding="utf-8") as fh:
        graph = json.load(fh)
    return schema, graph


@unittest.skipUnless(os.path.isdir(L1_DATA), "E:/l1 not mounted")
class TestSkillClaims(unittest.TestCase):
    def test_fbg_example_passes(self):
        schema, graph = load("fbg")
        rep = validate_graph(graph, schema)
        self.assertEqual(rep.failed, [], rep.failed)

    def test_dfos_example_passes(self):
        schema, graph = load("dfos")
        rep = validate_graph(graph, schema)
        self.assertEqual(rep.failed, [], rep.failed)

    def test_pzt_example_passes(self):
        schema, graph = load("pzt")
        rep = validate_graph(graph, schema)
        self.assertEqual(rep.failed, [], rep.failed)

    def test_pzt_supported_example_passes(self):
        schema, graph = load("pzt_supported")
        rep = validate_graph(graph, schema)
        self.assertEqual(rep.failed, [], rep.failed)

    @unittest.skipUnless(os.path.isdir("E:/fmoc"), "E:/fmoc not mounted")
    def test_fmoc_example_passes(self):
        schema, graph = load("fmoc")
        rep = validate_graph(graph, schema)
        self.assertEqual(rep.failed, [], rep.failed)

    @unittest.skipUnless(os.path.isdir("E:/fmoc"), "E:/fmoc not mounted")
    def test_fmoc_time_axis_must_be_true(self):
        schema, graph = load("fmoc")
        g = copy.deepcopy(graph)
        claim = next(c for c in g["claims"] if c["predicate"] == "t85_hit_pct")
        claim["boundary"]["time_axis"] = False
        rep = validate_graph(g, schema)
        self.assertTrue(
            any(c["name"] == "boundary_consistency" for c in rep.failed),
            rep.failed,
        )

    def test_fbg_window_claim_rejects_cycle_anchor(self):
        schema, graph = load("fbg")
        g = copy.deepcopy(graph)
        g["claims"][0]["boundary"]["cycle_anchor"] = 0.5
        rep = validate_graph(g, schema)
        self.assertTrue(
            any(c["name"] == "boundary_consistency" for c in rep.failed),
            rep.failed,
        )

    def test_dfos_unresolved_threshold_cannot_be_supported(self):
        schema, graph = load("dfos")
        g = copy.deepcopy(graph)
        claim = next(c for c in g["claims"] if c["predicate"] == "warn50_pct")
        claim["status"] = "supported"
        claim["allowed_lifetime_max"] = 0.95
        claim["missing_evidence"] = None
        claim["boundary"]["threshold_resolved"] = False
        rep = validate_graph(g, schema)
        self.assertTrue(
            any(c["name"] == "boundary_consistency" for c in rep.failed),
            rep.failed,
        )

    def test_pzt_censored_claim_cannot_be_supported(self):
        schema, graph = load("pzt")
        g = copy.deepcopy(graph)
        claim = g["claims"][0]
        claim["status"] = "supported"
        claim["allowed_lifetime_max"] = 0.95
        claim["missing_evidence"] = None
        claim["boundary"]["censored"] = True
        rep = validate_graph(g, schema)
        self.assertTrue(
            any(c["name"] == "boundary_consistency" for c in rep.failed),
            rep.failed,
        )


if __name__ == "__main__":
    unittest.main()
