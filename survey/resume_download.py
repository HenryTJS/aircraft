# -*- coding: utf-8 -*-
"""Resume PDF downloads with curl and hard timeouts (Windows-safe)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PDFS = os.path.join(HERE, "pdfs")
CAND = os.path.join(HERE, "candidates.jsonl")
CURL = r"D:\anaconda3\Library\bin\curl.exe"
TARGET = 55


def path_for(p):
    return os.path.join(PDFS, re.sub(r"[^A-Za-z0-9._-]", "_", p["arxiv_id"]) + ".pdf")


def main() -> int:
    rows = [json.loads(x) for x in open(CAND, encoding="utf-8") if x.strip()]
    have = []
    for p in rows:
        path = path_for(p)
        if os.path.exists(path) and os.path.getsize(path) > 10000:
            p["pdf_path"] = os.path.relpath(path, HERE)
            p["pdf_bytes"] = os.path.getsize(path)
            have.append(p)
    seen = {p["arxiv_id"] for p in have}
    todo = [p for p in rows if p["arxiv_id"] not in seen]
    print(f"have={len(have)} todo={len(todo)} target={TARGET}", flush=True)
    for p in todo:
        if len(have) >= TARGET:
            break
        path = path_for(p)
        cmd = [CURL, "-L", "--max-time", "25", "--connect-timeout", "10",
               "-sS", "-o", path, p["pdf_url"]]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=35)
            ok = (r.returncode == 0 and os.path.exists(path)
                  and os.path.getsize(path) > 10000
                  and open(path, "rb").read(4) == b"%PDF")
            if ok:
                p["pdf_path"] = os.path.relpath(path, HERE)
                p["pdf_bytes"] = os.path.getsize(path)
                have.append(p)
                print(f"OK {len(have):2d} {p['arxiv_id']} {p['pdf_bytes']}", flush=True)
            else:
                print(f"FAIL {p['arxiv_id']} rc={r.returncode} "
                      f"{(r.stderr or '')[-120:]}", flush=True)
        except subprocess.TimeoutExpired:
            print(f"TIMEOUT {p['arxiv_id']}", flush=True)
        time.sleep(0.4)

    have.sort(key=lambda p: (p["query_label"], p["year"], p["title"]))
    with open(os.path.join(HERE, "papers.jsonl"), "w", encoding="utf-8") as fh:
        for p in have:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"FINAL {len(have)}", flush=True)
    return 0 if len(have) >= 50 else 1


if __name__ == "__main__":
    raise SystemExit(main())
