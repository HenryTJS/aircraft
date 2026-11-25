# -*- coding: utf-8 -*-
"""PZT guided-wave tool: raw .mat states -> adjacent-state decorrelation / t50 / t85.

The damage index is the median decorrelation of the 56 guided-wave paths
between adjacent PZT states, cumulatively summed on the lifetime axis.  This is
the same construction as the AE cumulative-hit t85, deliberately.

The tool reads raw ``E:/l1/<gid>/PZT*/State_*`` data.  It overrides the original
``nf_of``/``life_map`` helpers so it does not read ``l1/results`` for n_f or the
time axis.  It can be slow: one group reads 8 .mat files per state.

Usage:
    python skills/pzt/run.py --gid L1-06 --json
    python skills/pzt/run.py --gid L1-25 --stride 2 --json
"""
from __future__ import annotations

import argparse
import contextlib
import math
import os
import sys

import numpy as np
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE_ROOT = HERE.parents[1]                 # D:/aircraft
DATA_ROOT = Path(os.environ.get("SHM_DATA_ROOT", "D:/shm"))
L1_ROOT = Path(os.environ.get("SHM_L1_ROOT", "E:/l1"))
for _p in (CODE_ROOT, DATA_ROOT, DATA_ROOT / "l1"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from skills.common import emit, envelope, evidence  # noqa: E402


def _num(value) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def compute(gid: str, stride: int = 1) -> dict:
    import datasets
    import pzt_crosslab as pzt

    if gid not in pzt.BATCH:
        raise ValueError("PZT tool only supports the L1 groups in pzt_crosslab.BATCH")
    raw = L1_ROOT / gid
    if not raw.is_dir():
        raise ValueError(f"no raw PZT directory: {raw}")
    if stride < 1:
        raise ValueError("stride must be >= 1")

    table = datasets.n_f_table()
    nf = table.get(gid)
    if not nf:
        raise ValueError(f"no n_f for {gid} in datasets.n_f_table()")

    pzt.STRIDE = int(stride)
    pzt.nf_of = lambda _gid, _lab: float(nf)
    pzt.life_map = lambda *_args, **_kwargs: None

    rows, err = pzt.run_group(gid)
    if rows is None:
        raise ValueError(err or "PZT run_group returned no rows")
    summary = pzt.metrics(gid, rows)
    n_f = int(nf)
    life_min = _num(summary.get("life_min"))
    life_max = _num(summary.get("life_max"))
    coverage = None
    if life_min is not None and life_max is not None:
        coverage = round(max(0.0, min(1.0, (life_max - life_min) / 100.0)), 4)
    t85 = _num(summary.get("t85"))
    t50 = _num(summary.get("t50"))
    # The cumulative D curve always reaches its own 85% at the last state at
    # the latest. Keep the crossing interval so a t85=100 can be read as
    # "crossed somewhere inside the last interval", not as an exact point.
    crossing_interval = None
    threshold_reached = False
    if rows:
        d = np.array([r.get("D", np.nan) for r in rows], dtype=float)
        x = np.array([r.get("life_pct", np.nan) for r in rows], dtype=float)
        ok = np.isfinite(d) & np.isfinite(x) & (x >= 0) & (x <= 100)
        x, d = x[ok], d[ok]
        if len(x):
            order = np.argsort(x)
            x, d = x[order], d[order]
            cum = np.cumsum(d)
            total = float(cum[-1])
            if total > 0:
                threshold_reached = True
                j = min(int(np.searchsorted(cum, 0.85 * total)), len(x) - 1)
                left = float(x[j - 1]) if j > 0 else float(x[j])
                crossing_interval = [round(left, 3), round(float(x[j]), 3)]
    censored = bool(threshold_reached and t85 is not None and t85 >= 99.9)
    lo = _num(summary.get("tof_slope_ts_lo"))

    data = {
        "gid": gid,
        "dataset": "L1",
        "modality": "PZT",
        "source_format": "raw-pzt-mat",
        "axis": "cycle",
        "n_f": n_f,
        "n_states": int(summary.get("n_states") or 0),
        "life_min_pct": life_min,
        "life_max_pct": life_max,
        "D_sum": _num(summary.get("D_sum")),
        "t50_pct": t50,
        "t85_pct": t85,
        "tof_drift_us": _num(summary.get("tof_drift_us")),
        "tof_slope_ts": _num(summary.get("tof_slope_ts")),
        "tof_slope_ts_lo": lo,
        "tof_slope_ts_hi": _num(summary.get("tof_slope_ts_hi")),
        "kendall_tau": _num(summary.get("kendall_tau")),
        "kendall_p": _num(summary.get("kendall_p")),
        "coverage": coverage,
        "stride": int(stride),
        "threshold_reached": bool(threshold_reached),
        "crossing_interval_pct": crossing_interval,
        "censored": censored,
        "raw_pzt": str(raw),
    }

    warnings: list[str] = [
        "PZT 的 D 是相邻状态退相关中位，不是裂纹长度；t85=100 落在寿命末端，属边界/删失，不是精确失效点。",
    ]
    if data["n_states"] < 12:
        warnings.append(f"只有 {data['n_states']} 个状态，累积曲线不稳定。")
    if life_min is not None and life_min > 5.0:
        warnings.append(f"PZT 起点在寿命 {life_min:.1f}%，不是 0。")
    if censored:
        warnings.append("t85 落在寿命末端，无法区分 100% 前刚越阈还是 100% 处才越阈，不能当精确失效点。")
    if lo is not None and lo <= 0:
        warnings.append("TOF 漂移 Theil-Sen 95% 下界不高于 0，趋势不显著。")
    if stride > 1:
        warnings.append(f"stride={stride}，D 用抽样相邻状态计算；寿命轴仍按完整序号。")

    scope = {
        "gid": gid,
        "campaign": "L1",
        "modality": "PZT",
        "cycle_min": 0,
        "cycle_max": n_f,
        "lifetime_min": 0,
        "lifetime_max": 1,
    }
    ev = evidence(
        "E-PZT-INDEX",
        str(raw),
        f"{gid} raw PZT guided-wave states",
        {
            "gid": gid,
            "n_states": data["n_states"],
            "t50_pct": t50,
            "t85_pct": t85,
            "threshold_reached": bool(threshold_reached),
            "crossing_interval_pct": crossing_interval,
            "tof_slope_ts": data["tof_slope_ts"],
            "coverage": coverage,
            "axis": "cycle",
        },
        scope,
        evidence_type="tool_result",
        coverage=coverage,
    )
    formula = ("median decorrelation D over 56 paths between adjacent PZT states; "
               "cumsum(D); t50/t85 on life_pct = state_interval_index / n_f")
    report = (
        f"# pzt: {gid}\n\n"
        f"- states: {data['n_states']} · life: {life_min}–{life_max}% · coverage: {coverage}\n"
        f"- t50/t85: {t50} / {t85}% · censored: {censored}\n"
        f"- dTOF: {data['tof_drift_us']} µs · TS slope: {data['tof_slope_ts']} "
        f"[{data['tof_slope_ts_lo']}, {data['tof_slope_ts_hi']}]\n"
    )
    return envelope("pzt", "ok", data, warnings=warnings, evidence=[ev],
                    computation={"kind": "computed", "formula": formula,
                                 "inputs": [str(raw)]},
                    report=report)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gid", required=True)
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        # datasets/pzt_crosslab emit PDF-parser notices on stdout during import.
        # Keep stdout for the JSON envelope only; diagnostics go to stderr.
        with contextlib.redirect_stdout(sys.stderr):
            obj = compute(args.gid, args.stride)
    except Exception as exc:  # noqa: BLE001
        obj = envelope(
            "pzt", "unsupported",
            {"gid": args.gid, "stride": args.stride, "reason": str(exc)},
            computation={"kind": "computed", "formula": None,
                         "inputs": [f"raw {args.gid} PZT"]},
            report=f"# pzt\n无法从 raw PZT 计算：{exc}\n",
        )
        emit(obj, args.json)
        return 1
    emit(obj, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
