# -*- coding: utf-8 -*-
"""DFOS block tool: raw distributed-strain blocks -> block HI / warning cycles.

Reads the raw ``<gid>分布式应变.csv`` plus the FBG/DFOS block anchors, then
recomputes the block-level local-peak deviation HI.  It deliberately does not
read ``l1/results``.  The output is a block-level envelope, not a spatial
damage map: DFOS localization has already been falsified in this project.

Usage:
    python skills/dfos/run.py --gid L1-03 --json
    python skills/dfos/run.py --gid L1-49 --base post --json
"""
from __future__ import annotations

import argparse
import contextlib
import io
import math
import os
import sys
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


def _pct(value, n_f: int) -> float | None:
    v = _num(value)
    return round(v / n_f * 100.0, 3) if v is not None and n_f else None


def compute(gid: str, base_mode: str = "post") -> dict:
    import evaluate_l1_dfos as dfos
    from datasets import campaign_members

    allowed = set(campaign_members("C1")) | set(campaign_members("C2"))
    if gid not in allowed:
        raise ValueError("DFOS tool only supports L1 C1/C2 groups")
    if base_mode not in ("post", "bi"):
        raise ValueError("base must be 'post' or 'bi'")
    raw = L1_ROOT / gid / f"{gid}分布式应变.csv"
    if not raw.is_file():
        raise ValueError(f"no raw DFOS file: {raw}")

    # analyze() prints a human-readable block summary; capture it so --json
    # stays machine-readable.
    with contextlib.redirect_stdout(io.StringIO()):
        row = dfos.analyze(gid, base_mode=base_mode)
    n_f = int(row.get("n_f") or 0)
    n_blk = int(row.get("n_blk") or 0)
    hi_end = _num(row.get("HI_end"))
    warn25 = _num(row.get("warn25"))
    warn50 = _num(row.get("warn50"))
    warn70 = _num(row.get("warn70"))
    warn25_pct = _pct(warn25, n_f)
    warn50_pct = _pct(warn50, n_f)
    warn70_pct = _pct(warn70, n_f)
    tail_mono = _num(row.get("tail_mono"))
    saturation = (hi_end is not None and hi_end >= 0.999
                  and warn25_pct is not None
                  and warn25_pct == warn50_pct == warn70_pct)

    data = {
        "gid": gid,
        "dataset": "L1",
        "modality": "DFOS",
        "source_format": "raw-dfos-block",
        "axis": "cycle",
        "n_f": n_f,
        "n_blocks": n_blk,
        "base_mode": base_mode,
        "hi_end": hi_end,
        "warn25_cycle": warn25,
        "warn25_pct": warn25_pct,
        "warn50_cycle": warn50,
        "warn50_pct": warn50_pct,
        "warn70_cycle": warn70,
        "warn70_pct": warn70_pct,
        "tail_mono_pct": tail_mono,
        "rmse_end": _num(row.get("rmse_end")),
        "spike_fix": _num(row.get("spike_fix")),
        "saturation": bool(saturation),
        "raw_dfos": str(raw),
        "coverage": None,
    }

    warnings: list[str] = [
        "DFOS 是块级包络，不是空间损伤图；空间定位在本项目已证伪。",
    ]
    if n_blk < 5:
        warnings.append(f"只有 {n_blk} 个 block，块级 HI 不稳定。")
    if saturation:
        warnings.append("HI 到 1.0 且 0.25/0.50/0.70 同刻，指标饱和，不能用作分级。")
    if base_mode == "post":
        warnings.append("健康基准是冲击后前 10 段；不是冲击前真健康态，解释时要标 base=post。")

    scope = {
        "gid": gid,
        "campaign": "L1",
        "modality": "DFOS",
        "cycle_min": 0,
        "cycle_max": n_f,
        "lifetime_min": 0,
        "lifetime_max": 1,
    }
    ev = evidence(
        "E-DFOS-BLOCK",
        str(raw),
        f"{gid} raw DFOS block profile",
        {
            "gid": gid,
            "n_blocks": n_blk,
            "hi_end": hi_end,
            "warn50_pct": warn50_pct,
            "saturation": bool(saturation),
            "axis": "cycle",
            "coverage": None,
        },
        scope,
        evidence_type="tool_result",
        coverage=None,
    )
    formula = ("block median spatial profile vs baseline; local peak deviation; "
               "p90 normalization; monotone envelope; thresholds at 0.25/0.50/0.70")
    report = (
        f"# dfos: {gid}\n\n"
        f"- blocks: {n_blk} · base: {base_mode}\n"
        f"- HI end: {hi_end} · tail monotonic: {tail_mono}%\n"
        f"- warn 25/50/70 %: {warn25_pct} / {warn50_pct} / {warn70_pct}\n"
        f"- saturated: {saturation} · spike fixes: {data['spike_fix']}\n"
    )
    return envelope("dfos", "ok", data, warnings=warnings, evidence=[ev],
                    computation={"kind": "computed", "formula": formula,
                                 "inputs": [str(raw)]},
                    report=report)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gid", required=True)
    ap.add_argument("--base", default="post", choices=["post", "bi"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        obj = compute(args.gid, args.base)
    except Exception as exc:  # noqa: BLE001
        obj = envelope(
            "dfos", "unsupported",
            {"gid": args.gid, "base_mode": args.base, "reason": str(exc)},
            computation={"kind": "computed", "formula": None,
                         "inputs": [f"raw {args.gid} DFOS"]},
            report=f"# dfos\n无法从 raw DFOS 计算：{exc}\n",
        )
        emit(obj, args.json)
        return 1
    emit(obj, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
