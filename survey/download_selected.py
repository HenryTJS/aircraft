# -*- coding: utf-8 -*-
"""Download selected candidate PDFs in parallel and write the corpus manifest."""
from __future__ import annotations

import concurrent.futures as cf
import csv
import json
import os
import re
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
PDFS = os.path.join(HERE, "pdfs")
os.makedirs(PDFS, exist_ok=True)
CAND = os.path.join(HERE, "candidates.jsonl")
TARGET = 55
MAX_TRY = 90


def load() -> list[dict]:
    with open(CAND, encoding="utf-8") as fh:
        rows = [json.loads(x) for x in fh if x.strip()]
    # Keep domain diversity: order by score then year, but cap each query label.
    rows.sort(key=lambda p: (-p["score"], p["year"]))
    out, per = [], {}
    for p in rows:
        lab = p["query_label"]
        if per.get(lab, 0) >= 7:
            continue
        per[lab] = per.get(lab, 0) + 1
        out.append(p)
    for p in rows:
        if p not in out:
            out.append(p)
    return out


def safe_name(p: dict) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", p["arxiv_id"]) + ".pdf"


def get_pdf(p: dict) -> dict | None:
    path = os.path.join(PDFS, safe_name(p))
    if os.path.exists(path) and os.path.getsize(path) > 10000:
        p["pdf_path"] = os.path.relpath(path, HERE)
        p["pdf_bytes"] = os.path.getsize(path)
        return p
    for url in (p["pdf_url"], p["pdf_url"].replace("/pdf/", "/pdf/")):
        try:
            r = requests.get(url, timeout=45,
                             headers={"User-Agent": "shm-llm-survey/1.0"})
            if r.status_code == 200 and r.content[:4] == b"%PDF" and len(r.content) > 10000:
                with open(path, "wb") as fh:
                    fh.write(r.content)
                p["pdf_path"] = os.path.relpath(path, HERE)
                p["pdf_bytes"] = len(r.content)
                return p
        except Exception as exc:
            print(f"[fail] {p['arxiv_id']}: {exc}", file=sys.stderr)
        time.sleep(0.5)
    return None


def main() -> int:
    cands = load()
    print(f"candidates={len(cands)} target={TARGET}", flush=True)
    got = []
    # Try the first MAX_TRY in parallel; stop once target is reached.
    with cf.ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(get_pdf, p): p for p in cands[:MAX_TRY]}
        for i, fut in enumerate(cf.as_completed(futs), 1):
            p = fut.result()
            if p:
                got.append(p)
            if i % 10 == 0:
                print(f"attempted={i} downloaded={len(got)}", flush=True)
            if len(got) >= TARGET:
                # do not cancel running futures abruptly; they are short
                pass
    # de-duplicate by arxiv id and keep score order
    seen, final = set(), []
    for p in got:
        if p["arxiv_id"] in seen:
            continue
        seen.add(p["arxiv_id"])
        final.append(p)
    final.sort(key=lambda p: (p["query_label"], p["year"], p["title"]))
    with open(os.path.join(HERE, "papers.jsonl"), "w", encoding="utf-8") as fh:
        for p in final:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    with open(os.path.join(HERE, "papers.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        cols = ["arxiv_id", "year", "title", "authors", "query_label", "keywords",
                "pdf_path", "pdf_bytes", "abs_url", "pdf_url", "abstract"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for p in final:
            w.writerow({k: ("; ".join(p[k]) if k in ("authors", "keywords")
                            else p.get(k, "")) for k in cols})
    report = {"n_candidates": len(cands), "n_downloaded": len(final),
              "target": TARGET, "queries": sorted({p["query_label"] for p in final})}
    with open(os.path.join(HERE, "download_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0 if len(final) >= 50 else 1


if __name__ == "__main__":
    raise SystemExit(main())
