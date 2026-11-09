# -*- coding: utf-8 -*-
"""Collect 50+ arXiv papers on LLM applications in professional domains.

Outputs:
  survey/pdfs/*.pdf
  survey/papers.jsonl
  survey/papers.csv
  survey/collection_report.json

The collector is deliberately transparent: every query and every selected
paper is recorded, so the survey corpus can be audited.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
PDFS = os.path.join(HERE, "pdfs")
os.makedirs(PDFS, exist_ok=True)

NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
API = "https://export.arxiv.org/api/query"

QUERIES = [
    ('all:"large language model" AND all:aerospace', "aerospace"),
    ('all:"large language model" AND all:aviation', "aviation"),
    ('all:"large language model" AND all:aircraft', "aircraft"),
    ('all:"large language model" AND all:"structural health monitoring"', "SHM"),
    ('all:"large language model" AND all:prognostics', "PHM"),
    ('all:"large language model" AND all:"fault diagnosis"', "fault diagnosis"),
    ('all:"large language model" AND all:manufacturing', "manufacturing"),
    ('all:"large language model" AND all:"digital twin"', "digital twin"),
    ('all:"large language model" AND all:maintenance', "maintenance"),
    ('all:"large language model" AND all:"engineering design"', "engineering design"),
    ('all:"large language model" AND all:requirements', "requirements"),
    ('all:"large language model" AND all:certification', "certification"),
    ('all:"multimodal large language model" AND all:"time series"', "multimodal time series"),
    ('all:"large language model" AND all:agent AND all:industrial', "industrial agent"),
    ('all:"retrieval augmented generation" AND all:engineering', "RAG engineering"),
    ('all:"large language model" AND all:reliability', "reliability"),
    ('all:"large language model" AND all:robot AND all:industrial', "industrial robotics"),
]

KEY = [
    "aerospace", "aviation", "aircraft", "spacecraft", "satellite", "flight",
    "manufacturing", "industrial", "maintenance", "prognostic", "structural health",
    "fault diagnosis", "digital twin", "engineering design", "requirement",
    "certification", "reliability", "sensor", "time series", "phm", "inspection",
    "nondestructive", "NDT", "asset", "turbine", "engine", "composite",
]


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def query(q: str, n: int = 20) -> list[dict]:
    params = {"search_query": q, "start": 0, "max_results": n,
              "sortBy": "relevance", "sortOrder": "descending"}
    r = requests.get(API, params=params, timeout=60,
                     headers={"User-Agent": "shm-llm-survey/1.0"})
    r.raise_for_status()
    root = ET.fromstring(r.text)
    out = []
    for e in root.findall("a:entry", NS):
        aid = e.find("a:id", NS).text.split("/abs/")[-1]
        base = re.sub(r"v\d+$", "", aid)
        title = clean(e.find("a:title", NS).text)
        summary = clean(e.find("a:summary", NS).text)
        published = e.find("a:published", NS).text[:4]
        authors = [a.find("a:name", NS).text for a in e.findall("a:author", NS)]
        pdf = None
        for link in e.findall("a:link", NS):
            if link.attrib.get("title") == "pdf":
                pdf = link.attrib.get("href")
        if not pdf:
            pdf = f"https://arxiv.org/pdf/{aid}"
        out.append({
            "arxiv_id": base, "version_id": aid, "title": title,
            "abstract": summary, "year": published, "authors": authors,
            "abs_url": f"https://arxiv.org/abs/{base}",
            "pdf_url": pdf, "query": q,
        })
    return out


def main() -> int:
    all_papers = {}
    query_report = []
    for q, label in QUERIES:
        try:
            items = query(q, 20)
        except Exception as exc:
            print(f"[query fail] {label}: {exc}", file=sys.stderr)
            items = []
        query_report.append({"label": label, "query": q, "n": len(items)})
        for p in items:
            p["query_label"] = label
            key = p["arxiv_id"]
            if key not in all_papers:
                all_papers[key] = p
        print(f"{label:24s} {len(items):3d} hits, total {len(all_papers)}")
        time.sleep(3)

    # relevance score
    for p in all_papers.values():
        text = (p["title"] + " " + p["abstract"]).lower()
        hits = [k for k in KEY if k.lower() in text]
        p["keywords"] = hits
        p["score"] = len(hits)

    ranked = sorted(all_papers.values(), key=lambda p: (-p["score"], p["year"]), reverse=False)
    # prefer relevant, but keep 60 for PDF download success margin
    selected = [p for p in ranked if p["score"] >= 2][:70]
    if len(selected) < 55:
        selected = ranked[:70]

    # de-duplicate by normalized title
    seen, unique = set(), []
    for p in selected:
        t = re.sub(r"[^a-z0-9]+", " ", p["title"].lower()).strip()
        if t in seen:
            continue
        seen.add(t)
        unique.append(p)
    selected = unique[:65]

    downloaded = []
    for i, p in enumerate(selected, 1):
        path = os.path.join(PDFS, p["arxiv_id"].replace("/", "_") + ".pdf")
        if not os.path.exists(path) or os.path.getsize(path) < 10000:
            try:
                r = requests.get(p["pdf_url"], timeout=90,
                                 headers={"User-Agent": "shm-llm-survey/1.0"})
                if r.status_code == 200 and r.content[:4] == b"%PDF":
                    with open(path, "wb") as fh:
                        fh.write(r.content)
                else:
                    print(f"[pdf fail] {p['arxiv_id']} status={r.status_code}", file=sys.stderr)
            except Exception as exc:
                print(f"[pdf fail] {p['arxiv_id']}: {exc}", file=sys.stderr)
            time.sleep(1)
        if os.path.exists(path) and os.path.getsize(path) > 10000:
            p["pdf_path"] = os.path.relpath(path, HERE)
            p["pdf_bytes"] = os.path.getsize(path)
            downloaded.append(p)
        if i % 10 == 0:
            print(f"downloaded {len(downloaded)} / attempted {i}")

    # if fewer than 50, relax and continue with remaining candidates
    if len(downloaded) < 50:
        for p in ranked:
            if len(downloaded) >= 50:
                break
            if any(x["arxiv_id"] == p["arxiv_id"] for x in downloaded):
                continue
            path = os.path.join(PDFS, p["arxiv_id"].replace("/", "_") + ".pdf")
            try:
                r = requests.get(p["pdf_url"], timeout=90,
                                 headers={"User-Agent": "shm-llm-survey/1.0"})
                if r.status_code == 200 and r.content[:4] == b"%PDF":
                    with open(path, "wb") as fh:
                        fh.write(r.content)
                    p["pdf_path"] = os.path.relpath(path, HERE)
                    p["pdf_bytes"] = os.path.getsize(path)
                    downloaded.append(p)
            except Exception as exc:
                print(f"[pdf fail2] {p['arxiv_id']}: {exc}", file=sys.stderr)
            time.sleep(1)

    downloaded.sort(key=lambda p: (p["query_label"], p["year"], p["title"]))
    with open(os.path.join(HERE, "papers.jsonl"), "w", encoding="utf-8") as fh:
        for p in downloaded:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    with open(os.path.join(HERE, "papers.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        cols = ["arxiv_id", "year", "title", "authors", "query_label", "keywords",
                "pdf_path", "pdf_bytes", "abs_url", "pdf_url", "abstract"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for p in downloaded:
            w.writerow({k: ("; ".join(p[k]) if k == "authors" else
                            "; ".join(p[k]) if k == "keywords" else p.get(k, ""))
                        for k in cols})
    report = {
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "n_queries": len(QUERIES),
        "n_candidates": len(all_papers),
        "n_downloaded": len(downloaded),
        "queries": query_report,
        "selection_rule": "score>=2; dedupe normalized title; max 65; download until >=50",
    }
    with open(os.path.join(HERE, "collection_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if len(downloaded) >= 50 else 1


if __name__ == "__main__":
    raise SystemExit(main())
