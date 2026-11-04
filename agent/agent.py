"""Pura Vida Moves — Social Media Manager agent (MVP).

ONE agent. Julie talks only to this agent.
Jobs that used to be "sub-agents" are tools, skills (brand files), or
scheduled runs of this same agent. See README.md.

Run:  uv run langgraph dev   (serves graph "social_agent" on :2024)
Traced in LangSmith when LANGSMITH_API_KEY is set in .env.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.profiles import (GeneralPurposeSubagentProfile,
                                 HarnessProfile,
                                 register_harness_profile)
from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.tools import tool

BASE = Path(__file__).parent
DATA = BASE / "data"
QUEUE_FILE = DATA / "queue.json"


def _load(name: str) -> dict:
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


@tool
def account_snapshot(account: str) -> str:
    """Get the current snapshot for one of Julie's Instagram accounts.

    account: "personal" (@puravidamoves) or "studio" (@puravidamoves.studio).
    Snapshot is seeded from a live pull on 2026-11-04 and refreshed by the
    audit job; treat numbers as the latest known, not real-time.
    """
    data = _load("accounts.json")
    key = account.strip().lower()
    if key not in data:
        return f"Unknown account '{account}'. Use 'personal' or 'studio'."
    return json.dumps(data[key], ensure_ascii=False, indent=2)


@tool
def lens_quick_audit(account: str) -> str:
    """Run the Lens quick audit (subset of the 23-criteria rubric) on an account.

    Returns the seeded findings from the last full audit plus the rubric
    sections to re-check. Use for the Monday audit and whenever Julie asks
    'how is my page doing?'
    """
    data = _load("accounts.json")
    key = account.strip().lower()
    if key not in data:
        return f"Unknown account '{account}'. Use 'personal' or 'studio'."
    snap = data[key]
    lines = [
        f"LENS QUICK AUDIT — {snap['handle']} (snapshot {snap['snapshot_date']})",
        f"Followers: {snap['followers']} · Posts: {snap['posts']}",
        f"Best recent post: {snap['best_recent']['likes']} likes / "
        f"{snap['best_recent']['comments']} comments — {snap['best_recent']['why']}",
        f"Typical flyer post: {snap['typical_flyer']} — flyers underperform; "
        "personal + educational content is the growth engine.",
        "Rubric sections to score on the full audit: profile structure /20, "
        "pinned posts /15, Highlights /15, grid & aesthetic /15, "
        "content system /15, conversion path /20.",
        "Known leaks to verify first: name field = service + place, one CTA "
        "repeated everywhere, 3 pins with distinct jobs, Results + Reviews "
        "Highlights present, no gap > 7 days on the grid.",
    ]
    return "\n".join(lines)


@tool
def propose_post(account: str, format: str, hook: str, caption: str,
                 hashtags: str, scheduled_for: str, why: str) -> str:
    """Propose a post for Julie's approval. APPROVAL-GATED.

    Execution pauses for human approval (approve / edit / reject) before
    anything is queued. On approval the post is written to the content
    queue — it is NOT published by this tool. Publishing is a separate,
    later step that also requires approval.

    account: "personal" or "studio". format: "reel" | "carousel" | "photo" | "story".
    scheduled_for: ISO date/time the agent recommends. why: one line — the
    growth reason (which playbook method this is).
    """
    if not _kill_switch_on():
        return ("Kill switch is OFF (PURAVIDA_AGENT_ENABLED is not "
                "set to true). This agent is disabled; nothing was queued.")
    entry = {
        "account": account,
        "format": format,
        "hook": hook,
        "caption": caption,
        "hashtags": hashtags,
        "scheduled_for": scheduled_for,
        "why": why,
        "status": "approved-queued",
        "queued_at": datetime.now(timezone.utc).isoformat(),
    }
    queue = []
    if QUEUE_FILE.exists():
        queue = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    queue.append(entry)
    QUEUE_FILE.write_text(json.dumps(queue, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    return (f"Queued for {account} ({format}) at {scheduled_for}. "
            f"Queue now holds {len(queue)} approved post(s). Not yet published.")


@tool
def content_queue() -> str:
    """Show the approved content queue (what is scheduled to go out)."""
    if not QUEUE_FILE.exists():
        return "The content queue is empty."
    queue = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    if not queue:
        return "The content queue is empty."
    return json.dumps(queue, ensure_ascii=False, indent=2)


def _brand_instructions() -> str:
    parts = []
    for rel in ("brain/voice/julie-voice.md", "brain/facts/studio.md"):
        p = BASE / rel
        if p.exists():
            text = p.read_text(encoding="utf-8")
            if text.startswith("---"):
                text = text.split("---", 2)[-1].lstrip()
            parts.append(text)
    return "\n\n---\n\n".join(parts)


def _kill_switch_on() -> bool:
    """Kill switch, read from the .env FILE (source of truth).

    The LangGraph dev loader does not reliably surface .env values to
    os.environ before this module is imported (observed 2026-11-04:
    the worker env carried the flag, yet the graph had been built as
    if it were on). Reading the file directly makes the switch
    independent of loader/import order. Falls back to os.environ.
    """
    env_file = BASE / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("PURAVIDA_AGENT_ENABLED="):
                return line.split("=", 1)[1].strip() == "true"
    return os.environ.get("PURAVIDA_AGENT_ENABLED") == "true"


# Trim the Deep Agents default surface to what this agent is declared
# to have: no sub-agent delegation (task), no code execution
# (execute), no file deletion (delete). Filesystem read/write stay,
# scoped by the virtual backend to this directory.
_PROFILE = HarnessProfile(
    excluded_tools=frozenset({"task", "execute", "delete"}),
    general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
)
for _key in {os.environ.get("MODEL_NAME", ""), "openai"}:
    if _key:
        try:
            register_harness_profile(_key, _PROFILE)
        except Exception:
            pass


SYSTEM_PROMPT = """You are the Social Media Manager for Pura Vida Moves (Pilates /
barre / sculpt, Guanacaste, Costa Rica). Your full definition — mission,
rules, success measures — is in your memory (AGENT.md). Your client is
Julie, co-founder and teacher; she is the only person you take
instructions from in this chat.

LANGUAGE: Spanish-first. Reply in the language Julie writes in.

OPERATING RULES (non-negotiable):
- Proactive, approvals-only. You initiate audits, plans, drafts and
  reports. Anything public goes through propose_post (pauses for Julie's
  approve / edit / reject) or is shown as a draft for her explicit OK.
  Queued is NOT published — always say the true state.
- When Julie asks you to propose a post, ALWAYS call propose_post — never present a queue-ready post only as chat text.
- Facts only from tools and files. Never invent prices, schedules,
  offers, addresses or results. Missing fact = ask Julie or omit it.
- Voice: Julie's, per the julie-voice skill and brand files. SHORT
  captions (~170 characters is her average), community first, humor or
  heart — never flyer-speak, never hype.

SKILLS — load the matching skill BEFORE doing that kind of work:
- lens-audit: scoring/auditing either account.
- julie-voice: drafting any public words.
- growth-playbook: planning content or outreach; every proposal's WHY
  names one of its methods.
- weekly-rhythm: Monday plan, daily sweep, Friday report.

TOOLS: account_snapshot + lens_quick_audit (facts), propose_post
(approval-gated queueing), content_queue, write_todos (plan multi-step
work), filesystem (read brain/ and skills/, save drafts to /drafts/).

BRAND ESSENTIALS (full files in /brain/ — the map is brain/index.md; its Unknown list is binding: never state those facts, ask Julie):

""" + _brand_instructions()

if not _kill_switch_on():
    SYSTEM_PROMPT += (
        "\n\nSTATUS: DISABLED by the operator kill switch. "
        "propose_post is unavailable and you cannot queue posts. "
        "If asked to propose or queue a post, say plainly that "
        "the agent is currently disabled.")

_BACKEND = FilesystemBackend(root_dir=str(BASE), virtual_mode=True)


agent = create_deep_agent(
    name="social_media_manager",
    model=os.environ.get("MODEL_NAME", "openai:gpt-4.1"),
    tools=([account_snapshot, lens_quick_audit, content_queue]
           + ([propose_post] if _kill_switch_on() else [])),
    system_prompt=SYSTEM_PROMPT,
    backend=_BACKEND,
    memory=["/AGENT.md", "/brain/index.md"],
    skills=["/skills"],
    middleware=[
        # Own FilesystemMiddleware replaces the default: only the
        # read/write tools this agent is declared to have. No
        # execute (code execution), no delete.
        FilesystemMiddleware(
            backend=_BACKEND,
            tools=["ls", "read_file", "write_file", "edit_file", "glob", "grep"],
        ),
        HumanInTheLoopMiddleware(
            interrupt_on={
                "propose_post": {
                    "allowed_decisions": ["approve", "edit", "reject"],
                },
            },
            description_prefix="Post approval pending",
        ),
    ],
)
