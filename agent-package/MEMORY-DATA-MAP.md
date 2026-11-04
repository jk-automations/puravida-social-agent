# Pura Vida Social Manager (client-puravida-social-v1) Memory and Data Map

| Store/context | Purpose | Read/write | Scope | Retention/correction |
|---|---|---|---|---|
| Business Brain files (agent/brain/) | Verified facts, voice, rules, index with binding Unknown list | read | exact client; verified/current only for statements | Owner correction happens in the brain files (git); agent-proposed corrections land in lessons/corrections-inbox.md for human promotion |
| Agent definition (agent/AGENT.md) | Standing orders: mission, approvals-only, never-list | read (always loaded) | this deployment | Founders edit via git only |
| Skills (agent/skills/) | Procedures: lens-audit, julie-voice, growth-playbook, weekly-rhythm | read on demand | this deployment | Founders edit via git only |
| Account snapshot (agent/data/accounts.json) | Dated Instagram snapshot (129-post pull, 2026-11-04) | read | exact client, both accounts | Refreshed by re-pull; numbers always presented with their date |
| Content queue (agent/data/queue.json) | Approved post records awaiting a publishing step that does not exist yet | write (only via approval-gated propose_post) | exact client | Append-only in v1; founders may edit the file directly; runtime data, not in git |
| Chat threads (LangGraph checkpointer) | Conversation state incl. pending approval interrupts | read/write by the runtime | this deployment, Studio-local | In-memory dev checkpointer on the Studio test rig; hosted persistence arrives with the Phase 5 hosting move |
| Drafts (agent/drafts/) | Post drafts saved by the agent | write | agent directory only | In git when committed by founders; drafts are inert, never public |
| LangSmith traces (project puravida-social-agent) | Run traces for evals and debugging | write by the runtime when tracing key is present | JK LangSmith org | Tracing not yet enabled (pending the tracing-key step); no client data beyond run inputs/outputs once enabled |
| Model provider (OpenRouter → DeepSeek) | Inference only | transient | one run | Prompts include brain excerpts and chat content; no retention claimed by JK; provider terms govern their side |
