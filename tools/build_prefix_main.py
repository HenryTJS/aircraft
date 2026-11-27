# -*- coding: utf-8 -*-
"""Build an as-of prefix table for one main-sample specimen.

The main sample is the internal 5 Hz compression-compression fatigue set.  A
source row is one AE feature window; the dashboard package records
``window_s=0.1594`` for specimen 016.  The table below deliberately stores only
prefix quantities (elapsed time, cycle, window energy, cumulative energy and
cumulative log energy).  It contains no final life, no total energy and no
``t85``.
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RAW = Path(os.environ.get("MAIN_RAW_ROOT", "E:/main"))
OUT = ROOT / "prefix"
WINDOW_S = 0.1594
LOAD_HZ = 5.0  # main README: 5 Hz sine, compression-compression


def _read_energy(path: Path) -> np.ndarray:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise SystemExit(f"empty CSV: {path}")
        energy_col = next(
            (c for c in reader.fieldnames if c.strip().lower() == "spectralenergy"),
            None,
        )
        if energy_col is None:
            raise SystemExit(f"missing SpectralEnergy column in {path}")
        values: list[float] = []
        for row in reader:
            raw = (row.get(energy_col) or "").strip()
            try:
                v = float(raw)
            except ValueError:
                v = 0.0
            values.append(max(0.0, v))
    return np.asarray(values, dtype=float)


def build(gid: str = "016") -> Path:
    if gid != "016":
        raise SystemExit("only main 016 is indexed for the online line")
    raw_dir = RAW / gid
    src = raw_dir / f"{gid}声发射.csv"
    if not src.exists():
        raise SystemExit(f"missing raw AE CSV: {src}")
    energy = _read_energy(src)
    if len(energy) < 2:
        raise SystemExit(f"not enough windows in {src}")
    n = len(energy)
    t_s = np.arange(n, dtype=float) * WINDOW_S
    cycle = t_s * LOAD_HZ
    cum_energy = np.cumsum(energy)
    ce_log = np.cumsum(np.log1p(energy))

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "main-016.npz"
    np.savez_compressed(
        out,
        gid=np.asarray("main-016"),
        dataset=np.asarray("main"),
        t_s=t_s,
        cycle=cycle,
        frame_energy=energy,
        cum_energy=cum_energy,
        ce_log=ce_log,
        n_windows=np.asarray(n),
        window_s=np.asarray(WINDOW_S),
        load_hz=np.asarray(LOAD_HZ),
        source=np.asarray(str(src)),
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gid", default="016")
    args = ap.parse_args()
    path = build(args.gid)
    z = np.load(path, allow_pickle=True)
    print(f"wrote {path}")
    print(
        f"  windows={len(z['cycle'])} first_cycle={z['cycle'][0]:.1f} "
        f"last_cycle={z['cycle'][-1]:.1f} last_s={z['t_s'][-1]:.1f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
