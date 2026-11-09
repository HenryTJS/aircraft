# -*- coding: utf-8 -*-
"""Repair truncated PDFs with curl resume, then validate with pdfplumber."""
from __future__ import annotations

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
META = os.path.join(HERE, "papers.jsonl")
CAND = os.path.join(HERE, "candidates.jsonl")


def valid(path: str) -> bool:
    try:
        with pdfplumber.open(path) as pdf:
            return len(pdf.pages) > 0
    except Exception:
        return False


def load_map():
    rows = []
    for name in ("papers.jsonl", "candidates.jsonl"):
        path = os.path.join(HERE, name)
        if os.path.exists(path):
            rows += [json.loads(x) for x in open(path, encoding="utf-8") if x.strip()]
    out = {}
    for p in rows:
        out.setdefault(p["arxiv_id"], p)
    return out


def curl_download(url: str, path: str, resume: bool, timeout: int) -> bool:
    cmd = [CURL, "-L", "--connect-timeout", "10", "--max-time", str(timeout),
           "-sS", "-o", path]
    if resume:
        cmd += ["-C", "-"]
    cmd.append(url)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout + 15)
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def main() -> int:
    meta = load_map()
    paths = [os.path.join(PDFS, x) for x in os.listdir(PDFS) if x.endswith(".pdf")]
    bad = [p for p in paths if not valid(p)]
    print(f"initial valid={len(paths)-len(bad)} bad={len(bad)}", flush=True)
    for path in bad:
        aid = os.path.splitext(os.path.basename(path))[0]
        p = meta.get(aid)
        if not p:
            print("NO META", aid, flush=True)
            continue
        size = os.path.getsize(path)
        print(f"repair {aid} size={size}", flush=True)
        # Try resume first, then full download.
        if size > 1000:
            curl_download(p["pdf_url"], path, True, 180)
        if not valid(path):
            if os.path.exists(path):
                os.remove(path)
            curl_download(p["pdf_url"], path, False, 300)
        if valid(path):
            print(f"  OK {aid} {os.path.getsize(path)}", flush=True)
        else:
            print(f"  STILL BAD {aid}", flush=True)
        time.sleep(0.5)

    paths = [os.path.join(PDFS, x) for x in os.listdir(PDFS) if x.endswith(".pdf")]
    good = [p for p in paths if valid(p)]
    print(f"FINAL valid={len(good)} total={len(paths)}", flush=True)
    return 0 if len(good) >= 50 else 1


if __name__ == "__main__":
    raise SystemExit(main())
