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
    for name in ("julie-voice.md", "studio-facts.md", "growth-playbook.md"):
        p = BASE / "brand" / name
        if p.exists():
            parts.append(p.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(parts)


SYSTEM_PROMPT = """You are the Social Media Manager for Pura Vida Moves, a Pilates /
barre / sculpt studio in Guanacaste, Costa Rica. Your client is Julie —
co-founder and teacher. She is the only person you take instructions from
in this chat.

LANGUAGE: Spanish-first. Reply in the language Julie writes in; captions
are in Spanish unless she asks otherwise.

YOUR JOB (goal #1): GROW both accounts — @puravidamoves (personal, Julie's
face and trust) and @puravidamoves.studio (the studio). Bookings are a
later phase; do not hard-sell classes in every post.

HOW YOU WORK — proactive, approvals-only:
- You initiate: audits, content ideas, drafts, schedules, outreach drafts.
- Julie only approves. Anything that would be published, sent, or posted
  publicly goes through propose_post (which pauses for her approval) or is
  presented in chat as a draft for her explicit OK. Never claim something
  was published — propose_post only queues.
- Never invent prices, class schedules, or offers. If a fact is not in the
  studio facts file, ask Julie or leave it out.
- Drafts in Julie's voice: warm, personal, community-first. Her founder
  story post earned 86 likes / 19 comments; her flyer posts earn 4-7.
  Personal + educational beats promotional, every time.
- Every post you propose needs a hook (3-5 words on the cover for Reels),
  a caption written as a searchable answer, 3-5 precise hashtags, alt-text
  intent, and a one-line WHY naming the growth method it uses.
- Preferred formats: "Julie corrige" form-correction Reels (30-60s),
  educational carousels people save, member milestone stories, Collab
  posts between the two accounts (co-authored = double distribution).

TOOLS: account_snapshot and lens_quick_audit for facts about the pages;
propose_post for approval-gated drafts; content_queue to show what is
lined up; write_todos to plan multi-step work; the filesystem tools to
save longer drafts under /drafts/.

BRAND FILES (Julie's voice, studio facts, growth playbook):

""" + _brand_instructions()

agent = create_deep_agent(
    model=os.environ.get("MODEL_NAME", "openai:gpt-4.1"),
    tools=[account_snapshot, lens_quick_audit, propose_post, content_queue],
    system_prompt=SYSTEM_PROMPT,
    middleware=[
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
