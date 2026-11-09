# -*- coding: utf-8 -*-
"""Fill the corpus with small PDFs first; hard timeouts, no hanging."""
from __future__ import annotations

import concurrent.futures as cf
import csv
import json
import os
import re
import subprocess
import sys
import time

import pdfplumber

HERE = os.path.dirname(os.path.abspath(__file__))
PDFS = os.path.join(HERE, "pdfs")
CURL = r"D:\anaconda3\Library\bin\curl.exe"
TARGET = 52
MAX_SIZE = 1_600_000


def valid(path: str) -> bool:
    try:
        with pdfplumber.open(path) as pdf:
            return len(pdf.pages) > 0
    except Exception:
        return False


def path_for(aid: str) -> str:
    return os.path.join(PDFS, re.sub(r"[^A-Za-z0-9._-]", "_", aid) + ".pdf")


def head_size(url: str) -> int | None:
    try:
        r = subprocess.run(
            [CURL, "-L", "-sI", "--max-time", "12", "--connect-timeout", "6", url],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=18,
        )
        if r.returncode != 0:
            return None
        sizes = re.findall(r"(?im)^content-length:\s*(\d+)", r.stdout)
        return int(sizes[-1]) if sizes else None
    except Exception:
        return None


def download(p: dict) -> dict | None:
    path = path_for(p["arxiv_id"])
    if os.path.exists(path) and valid(path):
        p["pdf_path"] = os.path.relpath(path, HERE)
        p["pdf_bytes"] = os.path.getsize(path)
        return p
    cmd = [CURL, "-L", "--connect-timeout", "8", "--max-time", "55",
           "-sS", "-o", path, p["pdf_url"]]
    try:
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=65)
    except subprocess.TimeoutExpired:
        return None
    if os.path.exists(path) and valid(path) and os.path.getsize(path) > 10000:
        p["pdf_path"] = os.path.relpath(path, HERE)
        p["pdf_bytes"] = os.path.getsize(path)
        return p
    return None


def main() -> int:
    rows = [json.loads(x) for x in open(os.path.join(HERE, "candidates.jsonl"),
                                        encoding="utf-8") if x.strip()]
    good = []
    for p in rows:
        path = path_for(p["arxiv_id"])
        if os.path.exists(path) and valid(path):
            p["pdf_path"] = os.path.relpath(path, HERE)
            p["pdf_bytes"] = os.path.getsize(path)
            good.append(p)
    have = {p["arxiv_id"] for p in good}
    print(f"valid={len(good)} target={TARGET}", flush=True)

    # HEAD sizes in parallel; choose small PDFs first.
    todo = [p for p in rows if p["arxiv_id"] not in have]
    print(f"probing {len(todo)} candidates", flush=True)
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        sizes = list(ex.map(lambda p: (p, head_size(p["pdf_url"])), todo))
    small = [(p, s) for p, s in sizes if s and s <= MAX_SIZE]
    small.sort(key=lambda x: x[1])
    print(f"small candidates={len(small)}", flush=True)

    for p, s in small:
        if len(good) >= TARGET:
            break
        p = dict(p)
        got = download(p)
        if got:
            good.append(got)
            print(f"OK {len(good)} {p['arxiv_id']} {s} bytes", flush=True)
        else:
            print(f"FAIL {p['arxiv_id']} {s} bytes", flush=True)
        time.sleep(0.2)

    good.sort(key=lambda p: (p["query_label"], p["year"], p["title"]))
    with open(os.path.join(HERE, "papers.jsonl"), "w", encoding="utf-8") as fh:
        for p in good:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    cols = ["arxiv_id", "year", "title", "authors", "query_label", "keywords",
            "pdf_path", "pdf_bytes", "abs_url", "pdf_url", "abstract"]
    with open(os.path.join(HERE, "papers.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for p in good:
            w.writerow({k: ("; ".join(p[k]) if k in ("authors", "keywords")
                            else p.get(k, "")) for k in cols})
    print(f"FINAL valid={len(good)}", flush=True)
    return 0 if len(good) >= 50 else 1


if __name__ == "__main__":
    raise SystemExit(main())
