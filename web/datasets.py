# -*- coding: utf-8 -*-
"""Dataset registry for the web shell.

The registry is data, not code. `cases/l1.json` declares all 29 L1
specimens and which raw-backed tools each one may use. F-MOC specimens come
from `cases/fmoc.json`. Adding a specimen means adding a real reader/tool and
a registry row, not editing a hard-coded list in `app.py`.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
L1_PATH = ROOT / "cases" / "l1.json"
FMOC_PATH = ROOT / "cases" / "fmoc.json"

_ALLOWED_TOOLS = {
    "metric", "fbg", "dfos", "pzt", "fmoc",
    "conflict", "workflow",
}


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_supported() -> dict:
    """Return {gid: {dataset, campaign, label, tools: tuple}}.

    Tools are validated here so a typo in the registry fails at startup rather
    than becoming a silent 500 later.
    """
    raw = _load_json(L1_PATH)
    supported: dict[str, dict] = {}
    for gid, meta in raw.items():
        if not isinstance(meta, dict):
            raise ValueError(f"{L1_PATH}: {gid} entry is not an object")
        tools = tuple(str(t) for t in meta.get("tools", []))
        unknown = set(tools) - _ALLOWED_TOOLS
        if unknown:
            raise ValueError(f"{L1_PATH}: {gid} has unknown tools {sorted(unknown)}")
        if "metric" not in tools:
            raise ValueError(f"{L1_PATH}: {gid} must keep metric as the AE mainline")
        supported[gid] = {
            "dataset": str(meta.get("dataset", "L1")),
            "campaign": str(meta.get("campaign", "")),
            "label": str(meta.get("label", gid)),
            "tools": tools,
        }

    fmoc = _load_json(FMOC_PATH)
    for spec in fmoc.get("specimens", []):
        gid = str(spec)
        supported[gid] = {
            "dataset": "F-MOC",
            "campaign": "F-MOC",
            "label": f"F-MOC {gid}",
            "tools": ("fmoc",),
        }
    return supported
