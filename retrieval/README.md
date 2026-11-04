# Business Brain retrieval layer

Status (2026-11-04): built and tested, **not wired into the agents' runtime** — on purpose. Measured brain sizes tonight: Pura Vida ≈ 3.0k tokens, JK ≈ 2.6k tokens. At this size the whole brain fits in context cheaply (Lane 1, pinned core: AGENT.md + brain/index.md + voice/facts loaded by the agent definition), and files beat an index. The step-up triggers from the Phase 2 research stand:

- Build/wire the index when a client brain passes ~200k tokens, or measured retrieval failures appear on the golden set.
- Add a reranker when top-20 failure exceeds ~5% on the golden set.
- Pilot Graphiti only if >15–20% of queries become multi-hop or point-in-time.

What exists here so the step-up is a config change, not a project:

- `build_index.py` — chunks `agent/brain/**/*.md` by headings with frontmatter metadata (client, type, status, source, git_rev) and a contextual header per chunk. Writes `agent/index/chunks.jsonl` always; with `BRAIN_DATABASE_URL` set it also loads Postgres (`brain_chunks`, pgvector extension enabled, `tsvector` generated column for the BM25 lane, `embedding VECTOR(1536)` column reserved — the embedding provider choice rides the hosting phase; DeepSeek has no embeddings).
- `search.py` — Lane 2 deterministic lookup (exact-term over verified chunks; abstains when nothing verified matches — this is the prices/hours lane) and Lane 3 lexical hybrid with the hard pre-filters enforced in code: `client = X AND status = verified`. The model never sets the filters.

Safety invariants: the index is a rebuildable cache; brain files are the only source of truth; nothing writes back except through the corrections-inbox → owner-approval path that already exists.
