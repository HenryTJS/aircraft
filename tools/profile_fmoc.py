# -*- coding: utf-8 -*-
"""Profile Vallen `.pridb` AE files on a time axis (F-MOC initial analysis).

Generic: it assumes the AMSY-6 schema (`ae_data` with `SetType=2` hits, `Time`
in 100 ns, `Eny` energy) and takes root/settype/time factor from a JSON config.

It does NOT build a cycle axis and does NOT remove pauses: F-MOC has no cycle
log in the file, and the markers only record a few suspend/resume events.

DIC timestamps are used only as a **lower bound** for test end:
`dic_last_s` is the last `specN_<seconds>.tif`; if AE ends after it, test end
is not identifiable from the supplied files, and `t85_dic` is a sensitivity,
not a correction.

Usage:
    python tools/profile_fmoc.py --config cases/fmoc.json --out docs/fmoc_initial.csv
    python tools/profile_fmoc.py --root E:/fmoc/ACOUSTIC --dic-dir E:/fmoc/DIC
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np

SETTYPE_HIT = 2
TIME_FACTOR = 1e-7  # 100 ns -> s


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


def _dic_last_s(dic_dir: Path | None, stem: str) -> float | None:
    if not dic_dir or not dic_dir.exists():
        return None
    vals = []
    for p in dic_dir.glob(f"{stem}_*.tif"):
        m = re.search(r"_(\d+)\.tif$", p.name)
        if m:
            vals.append(int(m.group(1)))
    return float(max(vals)) if vals else None


def profile(path: Path, dic_dir: Path | None = None,
            settype: int = SETTYPE_HIT, time_factor: float = TIME_FACTOR,
            with_energy: bool = True) -> dict:
    con = sqlite3.connect(str(path))
    cur = con.cursor()
    n, mi, ma = cur.execute(
        "SELECT COUNT(*), MIN(Time), MAX(Time) FROM ae_data WHERE SetType=?",
        (settype,),
    ).fetchone()
    if not n:
        con.close()
        return {"specimen": path.stem, "n_hits": 0}
    times = np.fromiter(
        (r[0] for r in cur.execute(
            "SELECT Time FROM ae_data WHERE SetType=?", (settype,))),
        dtype=np.int64, count=n,
    )
    energy = None
    if with_energy:
        energy = np.fromiter(
            ((r[0] or 0) for r in cur.execute(
                "SELECT Eny FROM ae_data WHERE SetType=?", (settype,))),
            dtype=np.float64, count=n,
        )
    con.close()

    order = np.argsort(times, kind="mergesort")
    times = times[order].astype(np.float64) * time_factor
    if energy is not None:
        energy = energy[order]

    t_min, t_max = float(mi) * time_factor, float(ma) * time_factor
    dur = t_max - t_min
    if dur <= 0:
        dur = float("nan")

    def pct(t: float) -> float:
        return (t - t_min) / dur * 100.0 if dur and np.isfinite(dur) else float("nan")

    ones = np.ones(n, dtype=np.float64)
    t50 = _t_at(times, ones, 0.50)
    t85 = _t_at(times, ones, 0.85)
    t99 = _t_at(times, ones, 0.99)
    last10 = float((times > t_max - 0.1 * dur).sum()) / n * 100.0
    dic_last = _dic_last_s(dic_dir, path.stem)

    out = {
        "specimen": path.stem,
        "n_hits": int(n),
        "t_min_s": round(t_min, 2),
        "t_max_s": round(t_max, 2),
        "duration_h": round(dur / 3600.0, 2),
        "rate_hz": round(n / dur, 2) if dur else float("nan"),
        "t50_s": round(t50, 2),
        "t85_s": round(t85, 2),
        "t99_s": round(t99, 2),
        "t50_hit_pct": round(pct(t50), 2),
        "t85_hit_pct": round(pct(t85), 2),
        "t99_hit_pct": round(pct(t99), 2),
        "last10_share_pct": round(last10, 2),
        "t85_active_pct": round(t85 / t99 * 100.0, 2) if t99 > 0 else None,
        "coverage_ok": bool(pct(t99) >= 95.0),
        "dic_last_s": round(dic_last, 1) if dic_last else None,
        "dic_last_h": round(dic_last / 3600.0, 2) if dic_last else None,
        "ae_over_dic": round(t_max / dic_last, 3) if dic_last else None,
        "t85_dic_pct": round(t85 / dic_last * 100.0, 2) if dic_last else None,
        "test_end_uncertain": (dic_last is None or t_max > dic_last * 1.02),
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
    ap.add_argument("--config", default=None)
    ap.add_argument("--root", default="E:/fmoc/ACOUSTIC")
    ap.add_argument("--dic-dir", default="E:/fmoc/DIC")
    ap.add_argument("--out", default="docs/fmoc_initial.csv")
    ap.add_argument("--no-energy", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.root)
    dic_dir = Path(args.dic_dir)
    settype, time_factor = SETTYPE_HIT, TIME_FACTOR
    if args.config:
        cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
        root = Path(cfg.get("root", root))
        dic_dir = Path(cfg.get("dic_dir", dic_dir))
        settype = int(cfg.get("settype", settype))
        time_factor = float(cfg.get("time_factor", time_factor))

    files = sorted(root.glob("*.pridb"))
    if not files:
        print(f"no .pridb under {root}", file=sys.stderr)
        return 1

    rows = []
    for p in files:
        print(f"[profile] {p.name}", file=sys.stderr)
        rows.append(profile(p, dic_dir, settype, time_factor,
                            with_energy=not args.no_energy))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print("| specimen | n_hits | duration_h | t85_full | t99 | t85_active | dic_last_h | t85_dic | ae/dic |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        print(f"| {r['specimen']} | {r['n_hits']} | {r['duration_h']} | "
              f"{r['t85_hit_pct']} | {r['t99_hit_pct']} | {r['t85_active_pct']} | "
              f"{r['dic_last_h']} | {r['t85_dic_pct']} | {r['ae_over_dic']} |")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
