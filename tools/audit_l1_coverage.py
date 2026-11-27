#!/usr/bin/env python
"""Audit the L1 registry against dashboard packages and local caches.

This is a coverage audit, not a raw recomputation.  It answers three
different questions separately:

* registered: can `/api/ask` resolve this gid and is at least metric enabled?
* displayable: does the dashboard have a precomputed package for it?
* validated: has this gid been exercised through claim/validator/API?

The last column is deliberately small.  A registered gid is not a signed
claim until its raw tool has been rerun and its graph has passed the
validator.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHM = Path("D:/shm/l1")
L1_JSON = ROOT / "cases" / "l1.json"
OUT = ROOT / "docs" / "l1_coverage.md"

# Gids that have been exercised end-to-end through claim graph, validator
# and API at least once.  Keep this explicit; do not infer it from a cache.
VALIDATED = {
    "L1-03",  # conflict + AE
    "L1-06",  # workflow + AE/PZT
    "L1-13",  # workflow
    "L1-23",  # C1 AE/DFOS/PZT; FBG is unsupported
    "L1-30",  # short-frame C4
    "L1-34",  # short-frame C4; no FBG
    "L1-36",  # short-frame C4
    "L1-49",  # C2 AE/DFOS
    "L1-04", "L1-05", "L1-09",
    "L1-50", "L1-51", "L1-52", "L1-54", "L1-55", "L1-56", "L1-59", "L1-60",
    "L1-14", "L1-24",
    "L1-25", "L1-27", "L1-29", "L1-31", "L1-35", "L1-41", "L1-44",
    "L1-22",
}

# All 29 L1 gids have had at least one raw metric run.  The two without a
# metric cache (L1-30 and L1-34) were run through earlier API checks but their
# short-frame results were not written to skills/cache.
RAW_METRIC_AUDITED = 29

FRAME_NOTES = {
    "L1-22": "20.7 GB AE, cold API ~365 s; raw parsing dominates",
    "L1-23": "FBG removed: fewer than 5 loading windows",
    "L1-30": "short trial: metric uses 60 s frames",
    "L1-34": "short trial: metric uses 30 s frames; no FBG",
    "L1-36": "short trial: metric uses 60 s frames; raw 84.84 vs dashboard 84.70",
}


def load_dashboard() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for campaign in ("c1", "c2", "c3", "c4"):
        path = ROOT / "dashboard" / "data" / f"index_{campaign}.js"
        text = path.read_text(encoding="utf-8")
        marker = f'window.SHM_DATASETS["{campaign}"]='
        start = text.index(marker) + len(marker)
        payload = text[start:].strip()
        if payload.endswith(";"):
            payload = payload[:-1]
        ds = json.loads(payload)
        for group in ds.get("groups", []):
            out[group["gid"]] = group
    return out


def csv_gids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return {row.get("gid", "").strip() for row in csv.DictReader(fh) if row.get("gid")}


def fbg_windows(gid: str) -> int:
    folder = Path("E:/l1") / gid / "FBG"
    if not folder.exists():
        return 0
    return len(list(folder.glob("*.txt")))


def main() -> None:
    registry = json.loads(L1_JSON.read_text(encoding="utf-8"))
    dashboard = load_dashboard()
    pzt = csv_gids(SHM / "results" / "pzt_crosslab_summary.csv")
    dfos = csv_gids(SHM / "results" / "l1_dfos_metrics.csv")

    rows = []
    counts = {"metric": 0, "fbg": 0, "dfos": 0, "pzt": 0, "workflow": 0, "conflict": 0}
    for gid, meta in registry.items():
        tools = meta.get("tools", [])
        for tool in counts:
            if tool in tools:
                counts[tool] += 1
        group = dashboard.get(gid, {})
        t85 = (group.get("meta") or {}).get("t85")
        convention = (group.get("meta") or {}).get("t85_convention", "")
        cache = ROOT / "skills" / "cache" / f"metric_{gid}.json"
        rows.append({
            "gid": gid,
            "campaign": meta.get("campaign", ""),
            "tools": ",".join(tools),
            "dashboard_t85": "—" if t85 is None else f"{float(t85):.2f}",
            "convention": convention,
            "cache": "yes" if cache.exists() else "—",
            "pzt": "yes" if gid in pzt else "—",
            "dfos": "yes" if gid in dfos else "—",
            "fbg": str(fbg_windows(gid)) if "fbg" in tools else "—",
            "validated": "yes" if gid in VALIDATED else "—",
            "note": FRAME_NOTES.get(gid, ""),
        })

    md = []
    md.append("# L1 覆盖审计")
    md.append("")
    md.append("生成命令：`python tools/audit_l1_coverage.py`。")
    md.append("")
    md.append("这份表只回答“注册/展示/验证”三种状态，不把注册当成验收。")
    md.append("")
    md.append("## 总览")
    md.append("")
    md.append(f"- 注册 gid：{len(rows)}")
    md.append(f"- 工具计数：metric {counts['metric']}、pzt {counts['pzt']}、dfos {counts['dfos']}、"
              f"fbg {counts['fbg']}、workflow {counts['workflow']}、conflict {counts['conflict']}")
    md.append(f"- dashboard 有预计算包：{sum(1 for r in rows if r['dashboard_t85'] != '—')}/{len(rows)}")
    md.append(f"- 有 metric 缓存：{sum(1 for r in rows if r['cache'] == 'yes')}/{len(rows)}")
    md.append(f"- 至少跑过一次 raw metric：{RAW_METRIC_AUDITED}/{len(rows)}（见 `docs/l1_metric_audit.md`）")
    md.append(f"- 端到端验证过：{sum(1 for r in rows if r['validated'] == 'yes')}/{len(rows)}")
    md.append("")
    md.append("## 逐组")
    md.append("")
    md.append("| gid | 批次 | tools | dashboard t85 | convention | cache | PZT 汇总 | DFOS 汇总 | FBG 窗 | 已端到端验证 | 备注 |")
    md.append("|---|---|---|---:|---|---|---|---|---:|---|---|")
    for r in rows:
        md.append(
            f"| {r['gid']} | {r['campaign']} | {r['tools']} | {r['dashboard_t85']} | "
            f"{r['convention']} | {r['cache']} | {r['pzt']} | {r['dfos']} | {r['fbg']} | "
            f"{r['validated']} | {r['note']} |"
        )
    md.append("")
    md.append("## 解释")
    md.append("")
    md.append("- `dashboard t85` 是预计算展示包，不是本次 raw 重算结果。")
    md.append("- `cache=yes` 只表示本地有 `skills/cache/metric_<gid>.json`，不代表该缓存仍对应当前代码。")
    md.append("- `PZT/DFOS 汇总` 只表示结果表里有该 gid，不代表该 gid 已接入 claim。")
    md.append("- `FBG 窗` 是原始 `.txt` 文件数；少于 5 个加载窗时 `fbg.profile` 会拒绝。")
    md.append("- `已端到端验证` 只覆盖 claim/validator/API 至少跑通过一次的 gid；其余仍需逐个跑 raw。")
    md.append("")
    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
