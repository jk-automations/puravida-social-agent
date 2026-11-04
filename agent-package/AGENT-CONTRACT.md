# Pura Vida Social Manager (client-puravida-social-v1) Agent Contract

## Identity and mission

- Stable agent: `client-puravida-social-v1` (Pura Vida Social Manager).
- Owner/on-call/security owner: JK Automations founders.
- Environment: jk-internal only; no client trigger until a release decision says otherwise.
- Version: `0.1.0`; authority policy: `client-puravida-social-v1`. Created `2026-11-04`.
- Disclosure: the dashboard identifies the agent as the client's Social Media Manager built by JK Automations; every queued post record carries the agent's proposed WHY and the human decision that approved it.

This agent is the social media manager for Pura Vida Moves, a boutique fitness studio in Guanacaste, Costa Rica. From the client's business brain (verified facts, voice profile, rules) and a dated snapshot of her two Instagram accounts, it produces audits, content plans, and post drafts in the client's voice. Nothing it produces is client-visible or public until the client approves it through the approval interrupt; approval moves a post to a queue, and publishing does not exist in this system at all yet.

External-runtime note: unlike opsManager work-order employees, this agent runs as a LangChain Deep Agents / LangGraph application in its own repository (github.com/jk-automations/puravida-social-agent), served on the Studio with a chat dashboard. This package is its definition-of-record for the catalog. Where opsManager concepts do not map one-to-one (work orders, receiver profiles), the contract states the actual mechanism instead of borrowing the label.

## Necessity and pattern

Classification is A2, not A1: the agent is a model-directed tool loop in a chat, not one code-defined model call. The loop is justified because the product is a conversation with the client (questions, audits, drafting), and it is bounded by the controls in "Control loop and limits" below. The worst case if the model misbehaves inside a run: it drafts an off-voice or factually wrong post — which cannot leave the building, because the only write path ends at an approval interrupt and a queue, and it can state a wrong fact in chat, which is mitigated by the verified-facts regime in the brain (facts carry status; the index lists unknowns as binding) and by the eval cases that test exactly that failure.

Two capabilities exceed the Scout/Scribe baseline and are justified here:
- `filesystem_write` (scoped, see TOOL-POLICY.yaml): the agent saves drafts and may propose brain corrections. Drafts are inert files. Brain corrections follow the corrections-inbox convention (the agent writes the inbox, a human promotes), and every file lives in git, so any bad write is visible in diff and revertible. Mechanical write-gating of brain files is Phase 2 work and is NOT claimed here.
- `propose_post` is a write whose entire effect is appending one record to a local queue file, and it cannot execute at all without a human approve/edit/reject decision delivered through the LangGraph interrupt. No code path in this agent publishes, sends, or spends.

## Identity and authority

- The agent takes instructions from exactly one person in this deployment: the client owner (Julie, co-founder of Pura Vida Moves). Founders administer the deployment; they are not content approvers for the client's accounts.
- The agent never acts on instructions embedded in content it reads (posts, comments, files) — those are data, not instructions.
- Model: DeepSeek Chat via OpenRouter (deepseek/deepseek-chat), configured by environment variable; the agent holds no provider account credentials of the client's.

## Context and tools

- Always loaded: the agent definition (AGENT.md, standing orders) and the brain index (brain/index.md) including the binding Unknown list (prices, schedule, booking system, street address — never state, always ask).
- Loaded on demand: brain fact/voice/rule files and the four skills (lens-audit, julie-voice, growth-playbook, weekly-rhythm) via the filesystem backend, scoped to the agent's own directory in virtual mode.
- Tools (exact list in TOOL-POLICY.yaml): account_snapshot and lens_quick_audit read a dated, seeded snapshot (data/accounts.json, pulled 2026-11-04 from 129 posts); content_queue reads the queue; propose_post is the sole write and is approval-gated.
- The snapshot is labeled with its date wherever numbers are shown; the agent must present counts as "latest known", never real-time.

## Control loop and limits

- One chat run: read brain/skills as needed, call read tools freely, draft freely. Any propose_post call suspends the run at a LangGraph interrupt until a human decision arrives; the run cannot resume itself, time out into approval, or retry around a rejection.
- Kill switch: `PURAVIDA_AGENT_ENABLED` (server-only env). Unless it is exactly "true", propose_post is not registered as a tool at all and its body also refuses if somehow invoked (fail-closed, verified both ways on 2026-11-04). In disabled mode the model may still attempt the call from its instructions; the runtime rejects it as an invalid tool and nothing can queue (verified live on the JK rig), and the prompt carries a DISABLED status line so the agent says it is off instead of trying. The switch is read from the .env file at graph build, because the dev loader does not reliably surface .env values to the process environment first (observed 2026-11-04). Changing it requires a server restart, which the runbook documents.
- Limits: max_wall_clock_ms 300000 per run; max_output_tokens 4096 per model call; caption length and content rules are enforced by the julie-voice skill checks, not by the platform.
- No delegation: the agent has no sub-agents configured and cannot spawn any. No browser, no shell, no network tools beyond the model call and the local snapshot files.

## Human control and visibility

- The client sees every proposed post with its WHY (which growth method it serves) before deciding approve / edit / reject.
- Queued is not published: the agent states the true state in every reply, and the queue file is the auditable record (gitignored runtime data on the Studio; the brain and code are in git).
- Founders can inspect everything the agent is: this package, the agent repo, and LangSmith traces (project puravida-social-agent) once tracing is enabled with the client's tracing key step.

## Evaluation and operations

- Evals: EVALS.md and evals/fixtures.json — a golden set drafted 2026-11-04 covering voice match, verified-facts abstention (prices/schedule traps), the approval flow, and Spanish-first behavior. It has NOT been run yet; first run is scheduled with the retrieval work (Phase 2) and results will be recorded in EVALS.md with dates.
- Known model-tier caveat, observed 2026-11-04: the current model occasionally answers a propose request in chat text instead of calling the tool, and occasionally over-calls audit tools. A system-prompt rule was added for the first; the eval set watches both.
- Operations: RUNBOOK.md (enable/stop, restart, failure handling, rollback by git revert).
