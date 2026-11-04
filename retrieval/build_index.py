#!/usr/bin/env python3
"""Build the Business Brain retrieval index for one agent.

Chunks agent/brain/**/*.md by markdown headings, keeping each file's
YAML frontmatter as metadata (type, status, source). Always writes
index/chunks.jsonl (the portable artifact). When BRAIN_DATABASE_URL is
set, also (re)loads a Postgres table `brain_chunks` with a tsvector
column for the BM25 lane and a pgvector column left ready for the
embedding lane (embedding provider is a hosting-phase decision).

The index is a rebuildable cache. The brain files stay the only
source of truth; nothing here writes back to them.

Usage:
    python3 build_index.py --agent-dir /path/to/agent --client puravida
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
HEADING = re.compile(r"^(#{1,4})\s+(.*)$", re.M)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    m = FRONTMATTER.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, text[m.end():]


def chunk_file(path: Path, brain_root: Path, client: str, git_rev: str) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    rel = str(path.relative_to(brain_root))
    status = meta.get("status", "unknown")
    # Split on headings, tracking the heading path for context.
    parts = []
    current_path: list[str] = []
    current_lines: list[str] = []
    for line in body.splitlines():
        hm = HEADING.match(line)
        if hm:
            if current_lines:
                parts.append((list(current_path), "\n".join(current_lines).strip()))
            level = len(hm.group(1))
            current_path = current_path[: level - 1] + [hm.group(2).strip()]
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines:
        parts.append((list(current_path), "\n".join(current_lines).strip()))

    chunks = []
    for i, (hpath, content) in enumerate(parts):
        if not content:
            continue
        header = " | ".join(
            [f"client: {client}", f"file: {rel}", f"status: {status}"]
            + ([f"section: {' > '.join(hpath)}"] if hpath else [])
        )
        full = f"[{header}]\n{content}"
        chunks.append(
            {
                "id": hashlib.sha256(full.encode()).hexdigest()[:16],
                "client": client,
                "path": rel,
                "section": " > ".join(hpath),
                "type": meta.get("type", ""),
                "status": status,
                "source": meta.get("source", ""),
                "git_rev": git_rev,
                "content": full,
            }
        )
    return chunks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-dir", required=True)
    ap.add_argument("--client", required=True)
    args = ap.parse_args()

    agent_dir = Path(args.agent_dir)
    brain = agent_dir / "brain"
    try:
        git_rev = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=agent_dir.parent, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except Exception:
        git_rev = ""

    chunks: list[dict] = []
    for md in sorted(brain.rglob("*.md")):
        chunks.extend(chunk_file(md, brain, args.client, git_rev))

    out_dir = agent_dir / "index"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "chunks.jsonl"
    with open(out_file, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"chunks: {len(chunks)} -> {out_file}")

    url = os.environ.get("BRAIN_DATABASE_URL")
    if not url:
        print("BRAIN_DATABASE_URL not set; jsonl only (Postgres load skipped)")
        return
    try:
        import psycopg
    except ImportError:
        print("psycopg not installed; jsonl only (Postgres load skipped)")
        return
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS brain_chunks (
                    id TEXT PRIMARY KEY,
                    client TEXT NOT NULL,
                    path TEXT NOT NULL,
                    section TEXT,
                    type TEXT,
                    status TEXT,
                    source TEXT,
                    git_rev TEXT,
                    content TEXT NOT NULL,
                    tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
                    embedding VECTOR(1536)
                )
                """
            )
            cur.execute("DELETE FROM brain_chunks WHERE client = %s", (args.client,))
            cur.executemany(
                "INSERT INTO brain_chunks (id, client, path, section, type, status, source, git_rev, content)"
                " VALUES (%(id)s, %(client)s, %(path)s, %(section)s, %(type)s, %(status)s, %(source)s, %(git_rev)s, %(content)s)",
                chunks,
            )
        conn.commit()
    print(f"postgres: loaded {len(chunks)} chunks for client {args.client}")


if __name__ == "__main__":
    main()
