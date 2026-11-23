# -*- coding: utf-8 -*-
"""FBG profile tool: raw 10-channel FBG loading windows -> strain-profile drift.

This is deliberately independent of the claim graph and of the AE metric.  It
reads the raw ``E:/l1/<gid>/FBG/*.txt`` windows and returns shape metrics with
an explicit window-axis caveat.  It does not read ``l1/results``.

Usage:
    python skills/fbg/run.py --gid L1-06 --json
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CODE_ROOT = HERE.parents[1]                 # D:/aircraft
DATA_ROOT = Path(os.environ.get("SHM_DATA_ROOT", "D:/shm"))
L1_ROOT = Path(os.environ.get("SHM_L1_ROOT", "E:/l1"))
for _p in (CODE_ROOT, DATA_ROOT, DATA_ROOT / "l1"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from skills.common import emit, envelope, evidence  # noqa: E402


def n_f_of(gid: str) -> int:
    try:
        import datasets
        value = datasets.n_f_table().get(gid)
        return int(value) if value else 0
    except Exception:
        return 0


def _med(values) -> float | None:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0 or not np.isfinite(arr).any():
        return None
    return float(np.nanmedian(arr))


def compute(gid: str) -> dict:
    import fbg_tools

    raw = L1_ROOT / gid / "FBG"
    if not raw.is_dir():
        raise ValueError(f"no raw FBG directory: {raw}")
    d = fbg_tools.group_profile(gid, root=str(L1_ROOT))
    if d is None:
        raise ValueError("fewer than 5 loading windows; FBG profile is not defined")
    prof = np.asarray(d["prof"], dtype=float)
    shape = np.asarray(d["shape_rob25"], dtype=float)
    centroid = np.asarray(d["centroid"], dtype=float)
    n = int(len(shape))
    if n < 5:
        raise ValueError(f"only {n} loading windows; need at least 5")
    k = max(1, int(round(n * 0.30)))
    n_f = n_f_of(gid)

    data = {
        "gid": gid,
        "dataset": "L1",
        "modality": "FBG",
        "source_format": "raw-fbg-profile",
        "axis": "window",
        "n_f": n_f,
        "n_windows": n,
        "n_channels": int(prof.shape[1]) if prof.ndim == 2 else 0,
        "p2p_med": _med(d["p2p_med"]),
        "shape_rob25_first": _med(shape[:k]),
        "shape_rob25_last": _med(shape[-k:]),
        "shape_rob25_median": _med(shape),
        "shape_rob25_max": float(np.nanmax(shape)) if np.isfinite(shape).any() else None,
        "centroid_drift": (float(np.nanmedian(centroid[-k:]) - np.nanmedian(centroid[:k]))
                           if np.isfinite(centroid).any() else None),
        "argmax_mode": (int(np.bincount(np.asarray(d["argmax"], dtype=int)).argmax())
                        if len(d["argmax"]) else None),
        "raw_fbg": str(raw),
        "coverage": None,
    }

    warnings: list[str] = [
        "FBG 轴是加载窗，不是寿命分数；不能把窗口序号直接当 cycle 或 RUL。",
    ]
    if n_f == 0:
        warnings.append("没有 n_f，无法把窗口轴映射到寿命分数。")
    if data["shape_rob25_max"] is not None and data["shape_rob25_max"] > 0:
        warnings.append("shape_rob25 是相对前 25% 窗口中位剖面的 L1 距离，越大表示漂移越强。")

    scope = {
        "gid": gid,
        "campaign": "L1",
        "modality": "FBG",
        "cycle_min": 0,
        "cycle_max": n_f,
        "lifetime_min": 0,
        "lifetime_max": 1,
    }
    ev = evidence(
        "E-FBG-PROFILE",
        str(raw),
        f"{gid} raw FBG loading-window profile",
        {
            "gid": gid,
            "n_windows": n,
            "n_channels": data["n_channels"],
            "shape_rob25_last": data["shape_rob25_last"],
            "centroid_drift": data["centroid_drift"],
            "axis": "window",
            "coverage": None,
        },
        scope,
        evidence_type="tool_result",
        coverage=None,
    )
    formula = ("per-window 10-channel P2P normalized profile; "
               "L1 distance to median of first 25% loading windows")
    report = (
        f"# fbg: {gid}\n\n"
        f"- windows: {n} · channels: {data['n_channels']}\n"
        f"- P2P median: {data['p2p_med']}\n"
        f"- shape_rob25 first/last: {data['shape_rob25_first']} / {data['shape_rob25_last']}\n"
        f"- centroid drift: {data['centroid_drift']}\n"
        f"- axis: window（不是寿命分数）· coverage: n/a\n"
    )
    return envelope("fbg", "ok", data, warnings=warnings, evidence=[ev],
                    computation={"kind": "computed", "formula": formula,
                                 "inputs": [str(raw)]},
                    report=report)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gid", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        obj = compute(args.gid)
    except Exception as exc:  # noqa: BLE001
        obj = envelope(
            "fbg", "unsupported",
            {"gid": args.gid, "reason": str(exc)},
            computation={"kind": "computed", "formula": None,
                         "inputs": [f"raw {args.gid} FBG"]},
            report=f"# fbg\n无法从 raw FBG 计算：{exc}\n",
        )
        emit(obj, args.json)
        return 1
    emit(obj, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
