# -*- coding: utf-8 -*-
"""F-MOC profile tool: raw Vallen `.pridb` hits on an observed-time axis.

This is the unknown-dataset entry point.  It does not read the L1 metric, the
L1 result tables, or the F-MOC result CSV.  It opens the raw `.pridb` file,
uses the configuration in ``cases/fmoc.json`` and returns only quantities
that the file can support:

* ``t85_hit_pct`` is a fraction of the observed AE time window, not a cycle
  fraction and not a remaining-life estimate.
* ``t85_dic_pct`` uses the last DIC frame as a lower bound for test end.
  When ``test_end_uncertain`` is true, it is a sensitivity value.

Usage:
    python skills/fmoc/run.py --gid spec1 --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE_ROOT = HERE.parents[1]                 # D:/aircraft
for _p in (CODE_ROOT,):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from skills.common import emit, envelope, evidence  # noqa: E402


def _config() -> dict:
    path = CODE_ROOT / "cases" / "fmoc.json"
    return json.loads(path.read_text(encoding="utf-8"))


def compute(gid: str) -> dict:
    cfg = _config()
    specs = cfg.get("specimens") or []
    if gid not in specs:
        raise ValueError(f"unknown F-MOC specimen {gid!r}; expected one of {specs}")
    root = Path(cfg.get("root", "E:/fmoc/ACOUSTIC"))
    dic_dir = Path(cfg.get("dic_dir", "E:/fmoc/DIC"))
    pridb = root / f"{gid}.pridb"
    if not pridb.exists():
        raise FileNotFoundError(f"raw .pridb not found: {pridb}")

    from tools.profile_fmoc import profile

    r = profile(
        pridb,
        dic_dir=dic_dir,
        settype=int(cfg.get("settype", 2)),
        time_factor=float(cfg.get("time_factor", 1e-7)),
        with_energy=True,
    )
    if not r.get("n_hits"):
        raise ValueError(f"no SetType hits in {pridb}")

    data = {
        "gid": gid,
        "dataset": "F-MOC",
        "modality": "AE",
        "source_format": "vallen-pridb",
        "axis": "time",
        "indicator": "hits",
        "n_hits": int(r["n_hits"]),
        "duration_h": r.get("duration_h"),
        "t50_hit_pct": r.get("t50_hit_pct"),
        "t85_hit_pct": r.get("t85_hit_pct"),
        "t99_hit_pct": r.get("t99_hit_pct"),
        "t85_active_pct": r.get("t85_active_pct"),
        "t85_dic_pct": r.get("t85_dic_pct"),
        "dic_last_h": r.get("dic_last_h"),
        "ae_over_dic": r.get("ae_over_dic"),
        "test_end_uncertain": bool(r.get("test_end_uncertain")),
        "coverage_ok": bool(r.get("coverage_ok")),
        "t85_energy_pct": r.get("t85_energy_pct"),
        "t50_s": r.get("t50_s"),
        "t85_s": r.get("t85_s"),
        "t99_s": r.get("t99_s"),
        "raw_fmoc": str(pridb),
        "raw_dic": str(dic_dir),
        "coverage": 1.0,
        "coverage_basis": "lifetime",
    }

    warnings = [
        "F-MOC 的轴是观测时间，不是 cycle；不能与 L1 的 cycle-fraction 直接比。",
        "DIC 末帧只是 test_end 的下界；test_end_uncertain=true 时 t85_dic 只能当敏感性值。",
        "t85_full 受 AE 尾部稀疏影响；hits 与能量排序可能不一致，当前 indicator=hits。",
    ]
    if not data["coverage_ok"]:
        warnings.append("t99 时间覆盖 <95%，尾部仍有较多 hit，t85 的解释力受限。")
    if data["test_end_uncertain"]:
        warnings.append("AE 记录超过 DIC 末帧 2% 以上，真实 test_end 不可由现有文件确定。")

    ev = evidence(
        "E-FMOC-PROFILE",
        str(pridb),
        f"{gid} raw F-MOC AE time profile",
        {
            "gid": gid,
            "n_hits": data["n_hits"],
            "axis": "time",
            "indicator": "hits",
            "t85_hit_pct": data["t85_hit_pct"],
            "t85_dic_pct": data["t85_dic_pct"],
            "dic_last_h": data["dic_last_h"],
            "ae_over_dic": data["ae_over_dic"],
            "test_end_uncertain": data["test_end_uncertain"],
        },
        {
            "gid": gid,
            "campaign": "F-MOC",
            "modality": "AE",
            "cycle_min": None,
            "cycle_max": None,
            "lifetime_min": 0,
            "lifetime_max": 1,
        },
        evidence_type="tool_result",
        coverage=1.0,
    )

    report = (
        f"| {gid} | {data['n_hits']} | {data['duration_h']} h | "
        f"{data['t85_hit_pct']}% | {data['t85_dic_pct']}% | "
        f"{data['test_end_uncertain']} |"
    )
    return envelope(
        "fmoc",
        "ok",
        data,
        warnings=warnings,
        evidence=[ev],
        report=report,
        computation={
            "kind": "computed",
            "formula": (
                "sort hits by Time; cumulative hits; t_x = linear time at x% "
                "of cumulative hits; t85_dic = t85_s / dic_last_s"
            ),
            "inputs": [str(pridb), str(dic_dir)],
        },
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gid", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        obj = compute(args.gid)
    except Exception as exc:
        obj = envelope("fmoc", "unsupported", {"gid": args.gid, "reason": str(exc)})
    emit(obj, args.json)
    return 0 if obj.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
