# -*- coding: utf-8 -*-
"""Raw `.pridb` metric for L1 C1/C2 and L2 (binned read; no FBG mask).

Why binned
----------
Reading millions of `Time` rows into Python was the bottleneck (L2-04 >10 min).
SQLite aggregates in-place: `GROUP BY Time/1e7` returns ~tens of thousands of
1 s bins, and t85 on 1 s bins differs from per-hit t85 by <0.01 pp here.  The
anchor (`evaluate_l1_hi_ae._cycle_of`) is applied to bin centres and weighted
by bin counts.

Axis choices
------------
- L1 C1/C2: cycle anchor (DFOS/FBG) on single-session records; time fallback
  for multi-session or missing anchor, with `warning`.
- L2: session→cycle table, mapped from bin time to cycle.

Every output carries `axis`, `load_mask`, `coverage`.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import numpy as np

SETTYPE_HIT = 2
TIME_BASE = 1e7  # 100 ns
BIN_S = 1.0

L1_ROOT = Path(os.environ.get("SHM_L1_ROOT", "E:/l1"))
L2_ROOT = Path(os.environ.get("SHM_L2_ROOT", "E:/l2"))
CACHE_DIR = Path(__file__).resolve().parents[1] / "cache"

L2_NF = {"L2-04": 1_046_000, "L2-05": 1_140_000, "L2-07": 540_000}

# (relative path, cycle_start, cycle_end); copied from l2/scripts/l2_ae_scan.py
L2_SPECS = {
    "L2-04": [
        (r"BI/BI_0k/L204.pridb", 0, 2076),
        (r"BI/BI_2k/L204-BI-2k.pridb", 2076, 42076),
        (r"AI/AI_42k/L204_42K.pridb", 42076, 162000),
        (r"AI/AI_162k/L204_162K.pridb", 162000, 352000),
        (r"AI/AI_352k/L204_352K.pridb", 352000, 365000),
        (r"AI/AI_365k/L204_365K.pridb", 365000, 415000),
        (r"AI/AI_415k/L204_415K.pridb", 415000, 416000),
        (r"AI/AI_416k/L204_416K.pridb", 416000, 506000),
        (r"AI/AI_506k/L204_506K.pridb", 506000, 826000),
        (r"AI/AI_826k/L204_826K.pridb", 826000, 1046000),
    ],
    "L2-05": [
        (r"Fatigue/BI/L205_BI.pridb", 0, 5000),
        (r"Fatigue/AI/AI_5K/L205_AI_5000.pridb", 5000, 10000),
        (r"Fatigue/AI/AI_10K/L205_AI_10K.pridb", 10000, 680000),
        (r"Fatigue/AI/AI_680K/L205_AI_680.pridb", 680000, 800000),
        (r"Fatigue/AI/AI_800K/L205_AI_800.pridb", 800000, 850000),
        (r"Fatigue/AI/AI_850K/L205_AI_850.pridb", 850000, 910000),
        (r"Fatigue/AI/AI_910K/L205_AI_910.pridb", 910000, 1140000),
    ],
    "L2-07": [
        (r"Fatigue/AI/0K/L2_07.pridb", 0, 160000),
        (r"Fatigue/AI/160K/L207_160K.pridb", 160000, 540000),
    ],
}


def _read_bins(path: Path, bin_s: float = BIN_S) -> tuple[np.ndarray, np.ndarray, int]:
    """Return (bin_start_seconds, hits_per_bin, total_hits), cached by file mtime."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    st = path.stat()
    cp = CACHE_DIR / f"pridb_{path.stem}_{st.st_size}_{int(st.st_mtime)}_{int(bin_s * 1000)}.npz"
    if cp.exists():
        try:
            with np.load(cp) as z:
                return z["t"], z["c"], int(z["n"])
        except Exception:
            pass

    con = sqlite3.connect(str(path))
    cur = con.cursor()
    divisor = int(TIME_BASE * bin_s)
    n = cur.execute("SELECT COUNT(*) FROM ae_data WHERE SetType=?",
                    (SETTYPE_HIT,)).fetchone()[0]
    if not n:
        con.close()
        return np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64), 0
    if n <= 20_000_000:
        # SQL aggregation is faster for small/medium tables.
        rows = cur.execute(
            "SELECT CAST(Time / ? AS INTEGER) AS b, COUNT(*) "
            "FROM ae_data WHERE SetType=? GROUP BY b ORDER BY b",
            (divisor, SETTYPE_HIT),
        ).fetchall()
        con.close()
        b = np.fromiter((r[0] for r in rows), dtype=np.int64, count=len(rows))
        c = np.fromiter((r[1] for r in rows), dtype=np.float64, count=len(rows))
        t = b.astype(np.float64) * bin_s
    else:
        # Huge tables: streaming + np.bincount beats SQL GROUP BY.
        times = np.fromiter((r[0] for r in cur.execute(
            "SELECT Time FROM ae_data WHERE SetType=?", (SETTYPE_HIT,))),
            dtype=np.int64, count=n)
        con.close()
        bins = times // divisor
        c = np.bincount(bins).astype(np.float64)
        t = np.arange(len(c), dtype=np.float64) * bin_s
    n = int(c.sum())
    try:
        np.savez_compressed(cp, t=t, c=c, n=n)
    except Exception:
        pass
    return t, c, n


def _t_at(axis: np.ndarray, weights: np.ndarray, level: float) -> float:
    """Linear interpolation of axis at cumulative-weight level (0..1)."""
    cum = np.cumsum(weights)
    target = level * cum[-1]
    j = int(np.searchsorted(cum, target))
    if j <= 0:
        return float(axis[0])
    if j >= len(axis):
        return float(axis[-1])
    c0, c1 = float(cum[j - 1]), float(cum[j])
    f = 0.0 if c1 == c0 else (target - c0) / (c1 - c0)
    return float(axis[j - 1]) + f * (float(axis[j]) - float(axis[j - 1]))


def compute_l1_pridb(gid: str) -> dict:
    """L1 C1/C2: bin hits, apply the cycle anchor when single-session."""
    ae = L1_ROOT / gid / "AE"
    files = sorted(ae.glob("*.pridb")) if ae.exists() else []
    if not files:
        raise ValueError(f"no .pridb under {ae}")

    t_all, c_all = [], []
    off = 0.0
    for f in files:
        t, c, _n = _read_bins(f)
        if not len(t):
            continue
        t_all.append(t + off)
        c_all.append(c)
        off = float(t_all[-1][-1]) + BIN_S
    if not t_all:
        raise ValueError(f"no hits in {ae}")
    t = np.concatenate(t_all)
    c = np.concatenate(c_all)
    n = int(c.sum())
    span = float(t[-1] - t[0])
    if span <= 0:
        raise ValueError(f"non-positive span for {gid}")

    from datasets import N_F
    n_f = N_F.get(gid)

    # Single-session C1/C2: use the project's DFOS/FBG cycle anchor.
    if n_f and len(files) == 1:
        try:
            import evaluate_l1_hi_ae as e
            cyc = np.asarray(e._cycle_of(gid, t + BIN_S / 2.0, n_f), dtype=float)
            ok = np.isfinite(cyc) & (cyc >= 0) & (cyc <= n_f)
            cyc, cnt = cyc[ok], c[ok]
            if len(cyc) >= 2 and cnt.sum() > 0:
                order = np.argsort(cyc)
                cyc, cnt = cyc[order], cnt[order]
                t50 = _t_at(cyc, cnt, 0.50)
                t85 = _t_at(cyc, cnt, 0.85)
                return {
                    "gid": gid, "dataset": "L1", "source_format": "pridb",
                    "n_f": int(n_f), "n_frames": int(np.ceil(span / 600.0)),
                    "hits": int(cnt.sum()), "n_files": len(files),
                    "f_hz": float(n_f) / span,
                    "t50_pct": t50 / n_f * 100.0,
                    "t85_pct": t85 / n_f * 100.0,
                    "frame_s": 600.0,
                    "axis": "cycle", "load_mask": "dfos/fbg anchor",
                    "coverage": float(cyc[-1] / n_f),
                    "bin_s": BIN_S,
                    "raw_ae": str(ae),
                }
        except Exception:
            pass

    # Fallback: observed time fraction (documented, not the cycle standard).
    t50 = _t_at(t + BIN_S / 2.0, c, 0.50)
    t85 = _t_at(t + BIN_S / 2.0, c, 0.85)
    return {
        "gid": gid, "dataset": "L1", "source_format": "pridb",
        "n_f": int(n_f) if n_f else None,
        "n_frames": int(np.ceil(span / 600.0)),
        "hits": n, "n_files": len(files),
        "f_hz": (float(n_f) / span) if n_f else None,
        "t50_pct": (t50 - t[0]) / span * 100.0,
        "t85_pct": (t85 - t[0]) / span * 100.0,
        "frame_s": 600.0,
        "axis": "time", "load_mask": "none", "coverage": 1.0,
        "warning": "cycle anchor unavailable; time-axis fallback",
        "bin_s": BIN_S,
        "raw_ae": str(ae),
    }


def compute_l2_pridb(gid: str) -> dict:
    """L2: bin hits per session, map bin time to cycle, pool and compute t_x."""
    if gid not in L2_SPECS:
        raise ValueError(f"no L2 cycle map for {gid}")
    cyc_all, cnt_all = [], []
    for rel, c0, c1 in L2_SPECS[gid]:
        p = L2_ROOT / gid / "AE" / rel
        if not p.exists():
            continue
        t, c, _n = _read_bins(p)
        if not len(t):
            continue
        span = float(t[-1] - t[0])
        if span <= 0:
            cyc = np.full(len(t), float(c0))
        else:
            cyc = c0 + (t - t[0]) / span * (c1 - c0)
        cyc_all.append(cyc)
        cnt_all.append(c)
    if not cyc_all:
        raise ValueError(f"no hits under {L2_ROOT / gid / 'AE'}")
    cyc = np.concatenate(cyc_all)
    cnt = np.concatenate(cnt_all)
    order = np.argsort(cyc)
    cyc, cnt = cyc[order], cnt[order]
    n_f = L2_NF.get(gid)
    if not n_f:
        raise ValueError(f"no n_f for {gid}")
    t50 = _t_at(cyc, cnt, 0.50)
    t85 = _t_at(cyc, cnt, 0.85)
    return {
        "gid": gid, "dataset": "L2", "source_format": "pridb",
        "n_f": int(n_f), "n_frames": int(len(np.unique(cyc // 1000.0))),
        "hits": int(cnt.sum()), "n_files": len(cyc_all),
        "f_hz": None,
        "t50_pct": t50 / n_f * 100.0,
        "t85_pct": t85 / n_f * 100.0,
        "frame_s": None,
        "axis": "cycle", "load_mask": "none",
        "coverage": float(cyc[-1] / n_f),
        "bin_s": BIN_S,
        "raw_ae": str(L2_ROOT / gid / "AE"),
    }
