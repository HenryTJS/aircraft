# -*- coding: utf-8 -*-
"""Build a small, as-of prefix index for one L1 specimen.

The index is intentionally only a frame table.  It contains no ``t85`` and no
``n_f``.  The API slices it at the requested cycle and returns only the rows
at or before that cycle, so a query cannot see the end of the test.

The current L1-13 source is the raw-derived cycle table and frame table in
``D:/shm/l1/results``.  Those caches are regenerated from raw ``.DTA`` and FBG
by ``l1/ae_frames.py`` and ``l1/ae_cycle.py``; this builder does not read a
dashboard package and does not call ``skills/metric``.

Usage:
    python tools/build_prefix.py --gid L1-13
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SHM = Path(os.environ.get("SHM_DATA_ROOT", "D:/shm"))
RESULTS = SHM / "l1" / "results"
OUT = ROOT / "prefix"


def _pzt_rows(gid: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    path = RESULTS / "pzt_crosslab.csv"
    cycles: list[float] = []
    dvals: list[float] = []
    tofs: list[float] = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("gid") != gid:
                continue
            try:
                cycle = float(row["cycle"])
            except (KeyError, TypeError, ValueError):
                continue
            d = row.get("D", "").strip()
            tof = row.get("tof_us", "").strip()
            if not d or not tof:
                continue
            try:
                dval = float(d)
                tofval = float(tof)
            except ValueError:
                continue
            cycles.append(cycle)
            dvals.append(dval)
            tofs.append(tofval)
    order = np.argsort(np.asarray(cycles, dtype=float))
    return (np.asarray(cycles, dtype=float)[order],
            np.asarray(dvals, dtype=float)[order],
            np.asarray(tofs, dtype=float)[order])


def build(gid: str = "L1-13") -> Path:
    cyc_path = RESULTS / f"_l1cyc_{gid}.npz"
    fr_path = RESULTS / f"_l1ae_frames_{gid}.npz"
    if not cyc_path.exists() or not fr_path.exists():
        raise SystemExit(
            f"missing raw-derived cache for {gid}: {cyc_path.name} / {fr_path.name}"
        )
    cyc = np.load(cyc_path, allow_pickle=True)
    fr = np.load(fr_path, allow_pickle=True)
    if "t_epoch" not in cyc or "cycle" not in cyc or "n" not in fr:
        raise SystemExit(f"unexpected cache layout for {gid}")

    t_epoch = np.asarray(cyc["t_epoch"], dtype=float)
    cycle = np.asarray(cyc["cycle"], dtype=float)
    n = np.asarray(fr["n"], dtype=float)
    m = min(len(t_epoch), len(cycle), len(n))
    if m < 2:
        raise SystemExit(f"not enough frames for {gid}: {m}")
    t_epoch = t_epoch[:m]
    cycle = cycle[:m]
    n = n[:m]
    frame_s = float(np.asarray(fr["frame_s"]).reshape(-1)[0]) if "frame_s" in fr else 600.0
    t_s = t_epoch - t_epoch[0]
    cum_hits = np.cumsum(n)
    hit_rate_h = n / (frame_s / 3600.0)

    pzt_cycle, pzt_d, pzt_tof = _pzt_rows(gid)
    if len(pzt_cycle):
        drift = pzt_tof - pzt_tof[0]
        # Keep the first state as a reference; the API never interpolates.
        pzt_tof_drift = drift
    else:
        pzt_cycle = np.asarray([], dtype=float)
        pzt_d = np.asarray([], dtype=float)
        pzt_tof_drift = np.asarray([], dtype=float)

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{gid}.npz"
    np.savez_compressed(
        out,
        gid=np.asarray(gid),
        t_s=t_s,
        cycle=cycle,
        frame_hits=n,
        cum_hits=cum_hits,
        hit_rate_h=hit_rate_h,
        frame_s=np.asarray(frame_s),
        pzt_cycle=pzt_cycle,
        pzt_d=pzt_d,
        pzt_tof_drift=pzt_tof_drift,
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gid", default="L1-13")
    args = ap.parse_args()
    path = build(args.gid)
    z = np.load(path, allow_pickle=True)
    print(f"wrote {path}")
    print(f"  frames={len(z['cycle'])} first_cycle={z['cycle'][0]:.1f} "
          f"last_cycle={z['cycle'][-1]:.1f} pzt_states={len(z['pzt_cycle'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
