# Pura Vida Moves — Social Media Manager (MVP)

JK Automations' first v2 build: ONE social media agent for Julie (Pura Vida Moves,
Guanacaste, Costa Rica) that grows both of her Instagram accounts —
@puravidamoves (personal) and @puravidamoves.studio (studio).
Forked from [langchain-ai/deep-agents-ui](https://github.com/langchain-ai/deep-agents-ui) (MIT).

## Shape (deliberately small)

- **Julie talks to ONE agent.** No roster. Jobs that sound like agents are
  tools (schedule, snapshot), skills/brand files (voice, playbook), or
  scheduled runs of the same agent.
- **Dashboard = 3 things:** Chat · Approvals (in-chat approval cards,
  LangGraph interrupts that wait indefinitely) · This Week (the agent's plan
  + drafts & files panel).
- **Proactive, approvals-only:** the agent drafts, plans and queues;
  nothing publishes or sends without Julie's tap.

## Run it (Studio)

Backend (Deep Agent on LangGraph, port 2024):

```bash
cd agent
cp .env.example .env   # fill OPENAI_API_KEY (+ LANGSMITH_API_KEY to enable tracing)
uv sync --group dev
uv run langgraph dev --host 0.0.0.0 --port 2024
```

Frontend (Next.js, port 3000):

```bash
yarn install
yarn dev
```

Open http://100.108.226.67:3000 (tailnet) — config is prefilled for the
Studio deployment (`social_agent` graph at http://100.108.226.67:2024).

## Agent contents

- `agent/agent.py` — one Deep Agent: account_snapshot + lens_quick_audit
  (facts), propose_post (approval-gated queue), content_queue.
- `agent/brand/` — Julie's voice profile, verified studio facts (with an
  explicit "never invent" list), and the 13-method growth playbook.
- `agent/data/accounts.json` — live-pulled snapshot of both accounts
  (2026-11-04). Refresh during the weekly audit.

## Status / next

- MVP: chat + approvals + queue working against the local LangGraph server.
- LangSmith: set `LANGSMITH_API_KEY` in `agent/.env` and
  `LANGSMITH_TRACING=true` to enable traces + evals (JK account exists;
  key not yet on this machine).
- Next: real Instagram read refresh (Meta token for Julie's accounts),
  approval-gated publishing, scheduled proactive runs (morning sweep,
  Monday plan, Friday report), LangSmith eval dataset v1.

## v2 polish — 2026-11-04
- **Voice profile v2** (agent/brand/julie-voice.md): built from 129 real posts + comment threads — two registers (profe cómica / corazón), birthday ritual ("barreaños"), caption stats (~170 chars, hashtags rare).
- **Skills** (agent/skills/): lens-audit, julie-voice, growth-playbook, weekly-rhythm — loaded via Deep Agents SkillsMiddleware.
- **Agent definition** (agent/AGENT.md): mission, approvals-only rules, hard never-list, success measures — loaded as agent memory.
- **Config fix**: dashboard defaults load synchronously (src/lib/config.ts) — no setup screen, opens straight into the agent.
- **Logo**: sun-over-waves mark in public/logo.svg, header + favicon (src/app/icon.svg).
- Seeded audit findings in agent/data/accounts.json now carry the verified corpus evidence; unverifiable items are marked SIN VERIFICAR.
- Known limit: the local Qwen2.5:32b follows skill structure but does not reliably complete multi-step scoring procedures; a frontier model (OpenAI top-up) sharpens skill execution without code changes.
