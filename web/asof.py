# -*- coding: utf-8 -*-
"""As-of prefix lookup for L1-13 and main-016.

The prefix file is a frame table.  This module deliberately returns only
values at or before the requested cycle/time.  It has no ``t85`` field and
does not expose the test's final hit total or total energy, so a successful
call cannot leak the end of the experiment through the response.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PREFIX = ROOT / "prefix"

# Public aliases.  The main dashboard calls the specimen "016"; the canonical
# online id is "main-016".
_ALIASES = {
    "L1-13": "L1-13",
    "016": "main-016",
    "main-016": "main-016",
}
SUPPORTED = frozenset(_ALIASES.values())

_cache: dict[str, dict[str, np.ndarray]] = {}


def _canonical(gid: str) -> str:
    canonical = _ALIASES.get(str(gid))
    if canonical is None:
        raise KeyError(gid)
    return canonical


def _load(gid: str) -> dict[str, np.ndarray]:
    canonical = _canonical(gid)
    if canonical not in _cache:
        path = PREFIX / f"{canonical}.npz"
        if not path.exists():
            raise FileNotFoundError(path)
        z = np.load(path, allow_pickle=True)
        _cache[canonical] = {k: np.asarray(z[k]) for k in z.files}
    return _cache[canonical]


def state_from_prefix(prefix: dict, cycle: float | None = None,
                      at_s: float | None = None) -> dict:
    """Select one prefix row and the latest PZT state at or before it."""
    cycles = np.asarray(prefix["cycle"], dtype=float)
    ts = np.asarray(prefix["t_s"], dtype=float)
    if cycle is None and at_s is None:
        raise ValueError("need cycle or at_s")
    if cycle is None:
        idx = int(np.searchsorted(ts, float(at_s), side="right") - 1)
    else:
        idx = int(np.searchsorted(cycles, float(cycle), side="right") - 1)
    if idx < 0:
        raise ValueError("requested time is before the first frame")
    idx = min(idx, len(cycles) - 1)
    cur_cycle = float(cycles[idx])

    pzt_cycle = np.asarray(prefix.get("pzt_cycle", []), dtype=float)
    pzt = None
    if len(pzt_cycle):
        j = int(np.searchsorted(pzt_cycle, cur_cycle, side="right") - 1)
        if j >= 0:
            pzt = {
                "cycle": float(pzt_cycle[j]),
                "age_cycles": max(0.0, cur_cycle - float(pzt_cycle[j])),
                "D": float(np.asarray(prefix["pzt_d"])[j]),
                "tof_drift_us": float(np.asarray(prefix["pzt_tof_drift"])[j]),
            }

    if "frame_hits" in prefix:
        state = {
            "frame_index": idx,
            "cycle": cur_cycle,
            "cum_hits": int(np.asarray(prefix["cum_hits"])[idx]),
            "frame_hits": int(np.asarray(prefix["frame_hits"])[idx]),
            "hit_rate_h": float(np.asarray(prefix["hit_rate_h"])[idx]),
        }
        reason = "prefix only; t85 requires the completed test and is not an online value"
    elif "frame_energy" in prefix:
        state = {
            "frame_index": idx,
            "cycle": cur_cycle,
            "frame_energy": float(np.asarray(prefix["frame_energy"])[idx]),
            "cum_energy": float(np.asarray(prefix["cum_energy"])[idx]),
            "ce_log": float(np.asarray(prefix["ce_log"])[idx]),
        }
        reason = "prefix only; cumulative AE energy is a progress clock, not damage or RUL"
    else:
        raise ValueError("prefix has no supported state columns")

    return {
        "status": "ok",
        "gid": str(prefix.get("gid", "")),
        "dataset": str(prefix.get("dataset", "")),
        "asof": {
            "elapsed_s": float(ts[idx]),
            "elapsed_h": float(ts[idx] / 3600.0),
            "cycle": cur_cycle,
        },
        "state": state,
        "pzt": pzt,
        "boundary": {
            "axis": "cycle",
            "t85_available": False,
            "contains_future": False,
            "reason": reason,
        },
    }


def state(gid: str, cycle: float | None = None, at_s: float | None = None) -> dict:
    return state_from_prefix(_load(gid), cycle=cycle, at_s=at_s)
