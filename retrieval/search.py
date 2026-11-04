#!/usr/bin/env python3
"""Query the Business Brain index in the lanes the runtime will use.

Lane 2 (deterministic): exact-term lookup over verified fact chunks.
    No similarity search for prices, hours, rules — the whole matching
    section returns, or an explicit abstention when nothing verified
    matches. Use for anything the abstention contract covers.

Lane 3 (hybrid lexical): BM25-style ranking over chunks with the two
    hard pre-filters enforced HERE, in code, never by the model:
    client = <client> AND status = verified. Unverified and unknown
    material can never surface through this lane.

Reads index/chunks.jsonl built by build_index.py (the Postgres table
carries the same columns and filters when BRAIN_DATABASE_URL is used
at runtime; the jsonl path keeps this tool dependency-free).

Usage:
    python3 search.py --index /path/to/index/chunks.jsonl --client jk \
        --lane lookup --query "Stage 1 fee"
    python3 search.py --index ... --client jk --lane search --query "voice rules captions"
"""

import argparse
import json
import re
from pathlib import Path

STOP = set("the a an and or of to in for on with is are que la el en y de los las un una".split())


def tokens(s: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9áéíóúñü]+", s.lower()) if t not in STOP and len(t) > 2]


def load(index_path: str, client: str) -> list[dict]:
    rows = [json.loads(l) for l in Path(index_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    # Hard pre-filter, in code: this client only.
    return [r for r in rows if r["client"] == client]


def lane_lookup(rows: list[dict], query: str) -> list[dict]:
    q = query.lower()
    hits = [
        r for r in rows
        if r["status"] == "verified" and q in r["content"].lower()
    ]
    return hits


def lane_search(rows: list[dict], query: str, k: int = 5) -> list[tuple[float, dict]]:
    qt = set(tokens(query))
    scored = []
    for r in rows:
        if r["status"] != "verified":  # hard pre-filter: verified only
            continue
        ct = tokens(r["content"])
        if not ct:
            continue
        overlap = sum(1 for t in ct if t in qt)
        if overlap:
            scored.append((overlap / (len(ct) ** 0.5), r))
    scored.sort(key=lambda x: -x[0])
    return scored[:k]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--client", required=True)
    ap.add_argument("--lane", choices=["lookup", "search"], required=True)
    ap.add_argument("--query", required=True)
    args = ap.parse_args()

    rows = load(args.index, args.client)
    if args.lane == "lookup":
        hits = lane_lookup(rows, args.query)
        if not hits:
            print("ABSTAIN: no verified chunk matches. Treat as unknown; ask the owner.")
            return
        for h in hits:
            print(f"--- {h['path']} :: {h['section']} [{h['status']}]")
            print(h["content"][:800])
    else:
        for score, r in lane_search(rows, args.query):
            print(f"--- {score:.2f} {r['path']} :: {r['section']} [{r['status']}]")
            print(r["content"][:400])


if __name__ == "__main__":
    main()
