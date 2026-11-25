"""Build the dashboard PZT overlay from the raw-derived PZT summary table.

The dashboard data packages are AE/FBG oriented; PZT is kept in a separate
small overlay so the core packages do not need to be regenerated.  Values are
raw-derived from D:/shm/l1/results/pzt_crosslab.csv and the summary table.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path("D:/shm/l1/results/pzt_crosslab.csv")
SUM = Path("D:/shm/l1/results/pzt_crosslab_summary.csv")
OUT = ROOT / "dashboard" / "data" / "pzt.js"


def fnum(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def main() -> None:
    summary = {}
    with SUM.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            summary[row["gid"]] = {
                "t50": fnum(row.get("t50")),
                "t85": fnum(row.get("t85")),
                "coverage": fnum(row.get("life_max")),
                "n_states": int(float(row.get("n_states") or 0)),
            }

    groups: dict[str, list[dict]] = {}
    with SRC.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            groups.setdefault(row["gid"], []).append(row)

    out = {}
    for gid, rows in sorted(groups.items()):
        rows.sort(key=lambda r: fnum(r.get("life_pct")) or 0.0)
        life, dvals, tofs = [], [], []
        first_tof = None
        for r in rows:
            life.append(round(fnum(r.get("life_pct")) or 0.0, 4))
            dvals.append(None if fnum(r.get("D")) is None else round(fnum(r["D"]), 6))
            tof = fnum(r.get("tof_us"))
            if tof is not None and first_tof is None:
                first_tof = tof
            tofs.append(None if (tof is None or first_tof is None) else round(tof - first_tof, 4))
        meta = summary.get(gid, {})
        out[gid] = {
            "life": life,
            "D": dvals,
            "tof_drift": tofs,
            "t50": meta.get("t50"),
            "t85": meta.get("t85"),
            "coverage": meta.get("coverage"),
            "n_states": meta.get("n_states"),
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = "window.SHM_PZT=window.SHM_PZT||{};\n" + "\n".join(
        f"window.SHM_PZT[{json.dumps(gid)}]={json.dumps(data, ensure_ascii=False, separators=(',', ':'))};"
        for gid, data in out.items()
    )
    OUT.write_text(payload + "\n", encoding="utf-8")
    print(f"wrote {OUT} groups={len(out)} bytes={OUT.stat().st_size}")


if __name__ == "__main__":
    main()
