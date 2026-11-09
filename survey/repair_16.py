# -*- coding: utf-8 -*-
"""Repair the 16 truncated PDFs with resumable curl and strict validation."""
from __future__ import annotations

import concurrent.futures as cf
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
PROXY = "http://127.0.0.1:7897"
IDS = [
    "2412.09819", "2503.16477", "2506.03828", "2509.16204",
    "2511.03179", "2511.10394", "2601.01321", "2602.01253",
    "2603.07572", "2604.08987", "2605.12916", "2606.17094",
    "2607.10994", "2608.18017", "2608.19218", "2608.19299",
]


def meta() -> dict:
    out = {}
    for name in ("papers.jsonl", "candidates.jsonl"):
        path = os.path.join(HERE, name)
        if os.path.exists(path):
            for line in open(path, encoding="utf-8"):
                if line.strip():
                    p = json.loads(line)
                    out.setdefault(p["arxiv_id"], p)
    return out


def check(path: str) -> tuple[bool, str]:
    if not os.path.exists(path) or os.path.getsize(path) < 10000:
        return False, "missing/small"
    with open(path, "rb") as f:
        f.seek(max(0, os.path.getsize(path) - 200))
        tail = f.read()
    if b"%%EOF" not in tail:
        return False, "no EOF"
    try:
        with pdfplumber.open(path) as pdf:
            if len(pdf.pages) == 0:
                return False, "0 pages"
    except Exception as exc:
        return False, type(exc).__name__
    return True, "ok"


def run_curl(url: str, path: str, resume: bool, max_time: int) -> int:
    cmd = [CURL, "-x", PROXY, "-L", "--connect-timeout", "10", "--max-time", str(max_time),
           "--retry", "1", "-sS", "-o", path]
    if resume:
        cmd += ["-C", "-"]
    cmd.append(url)
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=max_time + 20).returncode
    except subprocess.TimeoutExpired:
        return 28


def repair(aid: str, metas: dict) -> tuple[str, str]:
    path = os.path.join(PDFS, aid + ".pdf")
    p = metas.get(aid)
    if not p:
        return aid, "no meta"
    ok, why = check(path)
    if ok:
        return aid, "already ok"
    # 1) resume partial file
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        run_curl(p["pdf_url"], path, True, 180)
        ok, why = check(path)
        if ok:
            return aid, "resumed"
    # 2) full download, longer timeout
    if os.path.exists(path):
        os.remove(path)
    run_curl(p["pdf_url"], path, False, 300)
    ok, why = check(path)
    return aid, "full" if ok else f"failed:{why}"


def main() -> int:
    metas = meta()
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(repair, aid, metas): aid for aid in IDS}
        for fut in cf.as_completed(futs):
            aid, status = fut.result()
            print(f"{aid}\t{status}", flush=True)
    good = []
    for aid in IDS:
        ok, why = check(os.path.join(PDFS, aid + ".pdf"))
        if ok:
            good.append(aid)
    print(f"repaired_valid={len(good)}/16", flush=True)
    return 0 if len(good) == len(IDS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
