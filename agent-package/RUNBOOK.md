# Pura Vida Social Manager (client-puravida-social-v1) Runbook

## Enable and stop

The agent's only write tool (propose_post) is disabled unless the
server-only env var `PURAVIDA_AGENT_ENABLED=true` is set in
`agent/.env` on the Studio. Any other value — or the variable missing —
means the tool is not registered at all (fail-closed; verified both ways
on 2026-11-04). Changing the variable requires a server restart (below);
it does not change queue data or authorize any deployment.

Runtime today (test rig): LangGraph dev server on the Studio, port 2024;
dashboard (Next.js production build) on port 3100. Model:
`openai:deepseek/deepseek-chat` via OpenRouter, key in `agent/.env`
(Studio only, chmod 600, never in git).

## Operator procedure

1. SSH to the Studio (tailnet `studio`, user jefe).
2. Agent dir: `~/JKVault/projects/puravida-social-agent/agent`.
3. Restart the agent server: kill the `langgraph dev` process, then
   `nohup uv run langgraph dev --port 2024 --host 0.0.0.0 --no-browser`
   with output to `~/Library/Logs/puravida-langgraph.log`. Wait ~12s and
   confirm `curl http://localhost:2024/ok` returns ok:true. (Give the
   old process a full 4+ seconds to release the port; a stale process
   holding 2024 is the known restart trap.)
4. Dashboard: production build served on 3100 (`yarn start`); rebuild
   with `yarn build` after UI changes. Port 3000 belongs to Arceus —
   never take it.
5. To stop the agent's write path only: set
   `PURAVIDA_AGENT_ENABLED=false` in `agent/.env` and restart. To stop
   everything: kill both server processes.

## Failure handling

- Server fails to load the graph: read the tail of
  `~/Library/Logs/puravida-langgraph.log`; the usual cause is a syntax
  error in agent.py (compile-check with `python3 -m py_compile agent.py`
  before restarting).
- Model errors mentioning credits/balance: the OpenRouter balance is
  empty — top up at openrouter.ai. Errors naming other providers'
  keys are stale config; the only live brain route is OpenRouter.
- Approval interrupt never appears on a propose request: check the
  server is the current process (see the port trap above) and that the
  model called propose_post; a chat-text-only answer is a known
  model-tier behavior — resend the request; the eval set tracks it.
- GitHub push rejected with a remote internal error: transient;
  the local commit is safe — retry the push later.

## Rollback and decommission

- Rollback: `git revert` the offending commit in
  `jk-automations/puravida-social-agent`, restart the server, re-run the
  three-part smoke (Spanish Q&A, propose → interrupt → approve, Lens
  audit).
- Decommission: set the kill switch off, stop both servers, remove the
  Dojo registry entries (config/agents.yaml + config/dojo.yaml in
  ~/projects/agent-dojo) and this package copy in opsManager/agents.
  The client's brain and queue files remain in the repo as the record.
