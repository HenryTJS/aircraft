# -*- coding: utf-8 -*-
"""Profile Vallen `.pridb` AE files on a time axis (F-MOC initial analysis).

This is deliberately generic: it only assumes the AMSY-6 schema used by
F-MOC (`ae_data` with `SetType=2` hits, `Time` in 100 ns, `Eny` energy).

It does NOT build a cycle axis and does NOT remove pauses: F-MOC has no
cycle log in the file, and the markers only record a few suspend/resume
events.  The t_x values below are therefore "time fraction of the observed
AE window", not the cycle-fraction standard used for L1 (see
`docs/metric_standard.md`).

Usage:
    python tools/profile_fmoc.py --root E:/fmoc/ACOUSTIC --out docs/fmoc_initial.csv
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

import numpy as np

TIME_BASE = 1e7  # .pridb Time unit: 100 ns
SETTYPE_HIT = 2


def _t_at(times: np.ndarray, weights: np.ndarray, frac: float) -> float:
    """Time (s) at which cumulative `weights` reaches `frac` of its total."""
    cum = np.cumsum(weights)
    target = frac * cum[-1]
    j = int(np.searchsorted(cum, target))
    if j <= 0:
        return float(times[0])
    if j >= len(times):
        return float(times[-1])
    c0, c1 = float(cum[j - 1]), float(cum[j])
    f = 0.0 if c1 == c0 else (target - c0) / (c1 - c0)
    return float(times[j - 1]) + f * (float(times[j]) - float(times[j - 1]))


def profile(path: Path, with_energy: bool = True) -> dict:
    con = sqlite3.connect(str(path))
    cur = con.cursor()
    n, mi, ma = cur.execute(
        "SELECT COUNT(*), MIN(Time), MAX(Time) FROM ae_data WHERE SetType=?",
        (SETTYPE_HIT,),
    ).fetchone()
    if not n:
        con.close()
        return {"specimen": path.stem, "n_hits": 0}
    times = np.fromiter(
        (r[0] for r in cur.execute(
            "SELECT Time FROM ae_data WHERE SetType=?", (SETTYPE_HIT,))),
        dtype=np.int64, count=n,
    )
    energy = None
    if with_energy:
        energy = np.fromiter(
            ((r[0] or 0) for r in cur.execute(
                "SELECT Eny FROM ae_data WHERE SetType=?", (SETTYPE_HIT,))),
            dtype=np.float64, count=n,
        )
    con.close()

    order = np.argsort(times, kind="mergesort")
    times = times[order].astype(np.float64) / TIME_BASE
    if energy is not None:
        energy = energy[order]

    t_min, t_max = float(mi) / TIME_BASE, float(ma) / TIME_BASE
    dur = t_max - t_min
    if dur <= 0:
        dur = float("nan")

    def pct(t: float) -> float:
        return (t - t_min) / dur * 100.0 if dur and np.isfinite(dur) else float("nan")

    ones = np.ones(n, dtype=np.float64)
    t50_hit = pct(_t_at(times, ones, 0.50))
    t85_hit = pct(_t_at(times, ones, 0.85))
    t99_hit = pct(_t_at(times, ones, 0.99))
    last10 = float((times > t_max - 0.1 * dur).sum()) / n * 100.0
    out = {
        "specimen": path.stem,
        "n_hits": int(n),
        "t_min_s": round(t_min, 2),
        "t_max_s": round(t_max, 2),
        "duration_h": round(dur / 3600.0, 2),
        "rate_hz": round(n / dur, 2) if dur else float("nan"),
        "t50_hit_pct": round(t50_hit, 2),
        "t85_hit_pct": round(t85_hit, 2),
        "t99_hit_pct": round(t99_hit, 2),
        "last10_share_pct": round(last10, 2),
        "t85_active_pct": round(t85_hit / t99_hit * 100.0, 2) if (t99_hit > 0 and t85_hit <= t99_hit) else None,
        "coverage_ok": bool(t99_hit >= 95.0),
        "t50_energy_pct": None,
        "t85_energy_pct": None,
        "energy_total": None,
    }
    if energy is not None and energy.sum() > 0:
        out["t50_energy_pct"] = round(pct(_t_at(times, energy, 0.50)), 2)
        out["t85_energy_pct"] = round(pct(_t_at(times, energy, 0.85)), 2)
        out["energy_total"] = float(f"{energy.sum():.3e}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="E:/fmoc/ACOUSTIC")
    ap.add_argument("--out", default="docs/fmoc_initial.csv")
    ap.add_argument("--no-energy", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.root)
    files = sorted(root.glob("*.pridb"))
    if not files:
        print(f"no .pridb under {root}", file=sys.stderr)
        return 1

    rows = []
    for p in files:
        print(f"[profile] {p.name}", file=sys.stderr)
        rows.append(profile(p, with_energy=not args.no_energy))

    fields = list(rows[0].keys())
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print("| specimen | n_hits | duration_h | rate_hz | t50_hit | t85_hit | t99_hit | last10_share | t85_active | t85_energy |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        print(f"| {r['specimen']} | {r['n_hits']} | {r['duration_h']} | {r['rate_hz']} | "
              f"{r['t50_hit_pct']} | {r['t85_hit_pct']} | {r['t99_hit_pct']} | "
              f"{r['last10_share_pct']} | {r['t85_active_pct']} | {r['t85_energy_pct']} |")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
