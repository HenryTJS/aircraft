# -*- coding: utf-8 -*-
"""metric: compute t50/t85 from raw AE hits/frames and raw FBG load windows.

Scope:
- L1 C3/C4: raw `.DTA` frames + FBG load mask → cycle-fraction t85;
- L1 C1/C2: raw `.pridb` hits → time-fraction t85 (`axis="time"`);
- L2: raw `.pridb` + session→cycle map → cycle-fraction t85.

No results access; every output carries `axis`, `load_mask`, `coverage`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE_ROOT = HERE.parents[1]  # D:/aircraft
DATA_ROOT = Path(os.environ.get("SHM_DATA_ROOT", "D:/shm"))
sys.path.insert(0, str(CODE_ROOT))
sys.path.insert(0, str(DATA_ROOT))
sys.path.insert(0, str(DATA_ROOT / "l1"))
sys.path.insert(0, str(HERE))

import numpy as np

from adapters import RawL1Adapter
from skills.common import emit, envelope, evidence
from pridb import compute_l1_pridb, compute_l2_pridb

FRAME_S = 600.0
CACHE = HERE.parent / "cache"


def _t_at(hi: np.ndarray, cycle: np.ndarray, level: float, n_f: float) -> float:
    target = level * hi[-1]
    j = int(np.searchsorted(hi, target))
    if j <= 0:
        cyc = cycle[0]
    elif j >= len(cycle):
        cyc = cycle[-1]
    else:
        h0, h1 = hi[j - 1], hi[j]
        f = 0.0 if h1 == h0 else (target - h0) / (h1 - h0)
        cyc = cycle[j - 1] + f * (cycle[j] - cycle[j - 1])
    return float(cyc / n_f * 100.0) if n_f else float("nan")


def compute_l1(gid: str) -> dict:
    import ae_cycle
    import ae_frames
    from datasets import N_F_FALLBACK

    root = str(RawL1Adapter().root)
    fr = ae_frames.group_frames(gid, root=root, frame_s=FRAME_S, verbose=False)
    if fr is None or "n" not in fr:
        raise ValueError("no raw DTA frames")
    t_sec = np.asarray(fr["t_day"], dtype=float) * 86400.0
    n = np.asarray(fr["n"], dtype=float)
    pts = ae_cycle.group_load(gid, root=root)
    if not pts:
        raise ValueError("no raw FBG load windows")
    tf = np.asarray([p[0] for p in pts], dtype=float)
    lf = np.asarray([1.0 if p[1] > ae_cycle.P2P_LOAD else 0.0 for p in pts], dtype=float)
    g = ae_cycle._ratio_on_grid(t_sec, tf, lf, FRAME_S,
                                fill=ae_cycle.FILL, n_hits=n,
                                pause_win=ae_cycle._pause_win(FRAME_S))
    n_f = N_F_FALLBACK.get(gid)
    if not n_f:
        raise ValueError("no raw n_f for this gid")
    load_s = float(np.sum(g)) * FRAME_S
    f_hz = n_f / load_s if load_s > 0 else float("nan")
    cycle = np.cumsum(g * FRAME_S * f_hz)
    hi = np.cumsum(n) / np.sum(n)
    t50 = _t_at(hi, cycle, 0.50, n_f)
    t85 = _t_at(hi, cycle, 0.85, n_f)
    return {"gid": gid, "dataset": "L1", "source_format": "dta",
            "n_f": int(n_f), "n_frames": int(len(n)),
            "hits": int(np.sum(n)), "f_hz": float(f_hz),
            "t50_pct": t50, "t85_pct": t85,
            "frame_s": FRAME_S,
            "axis": "cycle", "load_mask": "fbg", "coverage": 1.0,
            "raw_ae": f"{root}/{gid}/AE",
            "raw_fbg": f"{root}/{gid}/FBG"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="L1", choices=["L1", "L2", "PHM2019"])
    ap.add_argument("--gid", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        if args.dataset == "L1":
            ae = Path(os.environ.get("SHM_L1_ROOT", "E:/l1")) / args.gid / "AE"
            if list(ae.glob("*.DTA")):
                data = compute_l1(args.gid)
            elif list(ae.glob("*.pridb")):
                data = compute_l1_pridb(args.gid)
            else:
                raise ValueError(f"no .DTA or .pridb under {ae}")
        elif args.dataset == "L2":
            data = compute_l2_pridb(args.gid)
        else:
            raise ValueError("PHM2019 has no t85; use the crack labels, not metric")
    except Exception as exc:
        obj = envelope("metric", "unsupported",
                       {"dataset": args.dataset, "gid": args.gid, "reason": str(exc)},
                       computation={"kind": "computed", "formula": "raw HI -> t85",
                                    "inputs": [f"raw {args.gid}"]},
                       report=f"# metric\n无法从 raw 计算：{exc}")
        emit(obj, args.json)
        return 1

    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / f"metric_{args.gid}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    ev = [evidence("E-METRIC-RAW", data["raw_ae"], f"{args.gid} raw AE",
                   {"gid": args.gid, "n_f": data.get("n_f"), "hits": data["hits"],
                    "t50_pct": data["t50_pct"], "t85_pct": data["t85_pct"],
                    "axis": data.get("axis"), "load_mask": data.get("load_mask"),
                    "coverage": data.get("coverage"),
                    "source_format": data.get("source_format")},
                   {"gid": args.gid, "campaign": None, "modality": "AE",
                    "cycle_min": 0, "cycle_max": data.get("n_f") or 0,
                    "lifetime_min": 0, "lifetime_max": 1})]
    fh = data.get("f_hz")
    fhs = f"{fh:.3f}" if isinstance(fh, (int, float)) else "—"
    report = (f"# metric: {args.gid}\n\n"
              f"- format: {data.get('source_format')}\n"
              f"- axis: {data.get('axis')} · load_mask: {data.get('load_mask')}\n"
              f"- hits: {data['hits']} · frames: {data['n_frames']}\n"
              f"- f: {fhs} Hz · coverage: {data.get('coverage')}\n"
              f"- t50: {data['t50_pct']:.2f}%\n"
              f"- t85: {data['t85_pct']:.2f}%\n")
    obj = envelope("metric", "ok", data, evidence=ev,
                   computation={"kind": "computed",
                                "formula": f"cumsum(raw hits)/total -> t85 on raw {data.get('axis')} axis",
                                "inputs": [data["raw_ae"]]},
                   report=report)
    emit(obj, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
