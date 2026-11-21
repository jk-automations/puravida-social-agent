"""Pura Vida Moves — Social Media Manager agent (MVP).

ONE agent. Julie talks only to this agent.
Jobs that used to be "sub-agents" are tools, skills (brand files), or
scheduled runs of this same agent. See README.md.

Run:  uv run langgraph dev   (serves graph "social_agent" on :2024)
Traced in LangSmith when LANGSMITH_API_KEY is set in .env.
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from deepagents import create_deep_agent
from deepagents.profiles import (GeneralPurposeSubagentProfile,
                                 HarnessProfile,
                                 register_harness_profile)
from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from langchain.agents.middleware import (AgentMiddleware, HumanInTheLoopMiddleware,
                                         ModelRetryMiddleware)
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool

BASE = Path(__file__).parent
DATA = BASE / "data"
QUEUE_FILE = DATA / "queue.json"


def _load(name: str) -> dict:
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


ACCOUNTS = '"personal" (@puravidamoves) or "studio" (@puravidamoves.studio)'


# --- M1 safety (2026-11-04): deterministic checks on every proposal -------
# Run twice: (a) as the approval gate's `when` predicate, so an invalid
# proposal never reaches the owner's approval card, and (b) inside the tool
# body, so an invalid proposal can never be queued either way.
OWNER_TZ_NAME = "America/Costa_Rica"
OWNER_TZ = ZoneInfo(OWNER_TZ_NAME)
VALID_FORMATS = ("reel", "carousel", "photo", "story")
MAX_DAYS_AHEAD = 90

# Results/outcome claims the agent may not make up. Matching text is
# rejected; a real, verified case has to be added to the brain and the
# post written by a person.
_CLAIM_PATTERNS = [
    r"\b(doubl|tripl|quadrupl)(e|ed|es|ing)\b",
    r"\b\d+(?:[.,]\d+)?\s?%",
    r"\b\d+(?:[.,]\d+)?\s?(x|×)(?=\W|$)",
    r"\b(increased|grew|boosted|skyrocketed|tripled|doubled)\b[^.!?]{0,60}"
    r"\b(bookings?|sales|revenue|leads?|clients?|customers?|followers?)\b",
    r"\b(our|a|one of our)\s+clients?\b[^.!?]{0,80}"
    r"\b(got|gained|increased|grew|saw|went from|booked|closed|made)\b",
    # Spanish (Julie writes Spanish-first)
    r"\b(duplic|triplic|cuadruplic)\w*",
    r"\b(aument|increment|crec)\w*[^.!?]{0,60}"
    r"\b(reservas?|ventas?|clientes?|seguidor\w*|alumn\w*|ingresos)\b",
    r"\b(pierd|perd|baj)\w*\s+\d+\s?(kilos?|kg|libras?|lbs?|tallas?)\b",
    r"\b\d+\s?(kilos?|kg|libras?|lbs)\s+(menos|en\s+\d+)",
]


# Exact class schedule is on the brain's Unknown list: any clock time in
# public copy is a schedule claim Julie hasn't given us (eval 14.2, 2026-11-04).
_SCHEDULE_PATTERNS = [
    r"\b\d{1,2}(?::\d{2})?\s?(?:am|pm|a\.m\.|p\.m\.)(?=\W|$)",
    r"\b(?:a las|a la|at)\s+\d{1,2}(?::\d{2})?\b",
    r"\b\d{1,2}:\d{2}\s?(?:hs|h)?\b",
]


def find_schedule_claims(text: str) -> list[str]:
    hits = []
    for pat in _SCHEDULE_PATTERNS:
        hits += [m.group(0).strip() for m in re.finditer(pat, text or "", flags=re.IGNORECASE)]
    return hits


def _valid_accounts() -> list[str]:
    return sorted(_load("accounts.json").keys())


def _parse_when(value: str) -> datetime:
    text = str(value).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=OWNER_TZ)
    return dt


def find_claims(text: str) -> list[str]:
    hits = []
    for pat in _CLAIM_PATTERNS:
        for m in re.finditer(pat, text or "", flags=re.IGNORECASE):
            hits.append(m.group(0).strip())
    return hits


def validate_post(args: dict, now: datetime | None = None) -> list[str]:
    """Return a list of problems with a proposal; empty list = valid."""
    now = now or datetime.now(OWNER_TZ)
    problems = []
    account = str(args.get("account", "")).strip().lower()
    if account not in _valid_accounts():
        problems.append(f"account '{args.get('account')}' is not valid; use {ACCOUNTS}.")
    if str(args.get("format", "")).strip().lower() not in VALID_FORMATS:
        problems.append(f"format must be one of {', '.join(VALID_FORMATS)}.")
    try:
        when = _parse_when(args.get("scheduled_for", ""))
        if when < now - timedelta(minutes=10):
            problems.append(
                f"scheduled_for {args.get('scheduled_for')} is in the past; "
                f"today is {now:%Y-%m-%d} ({OWNER_TZ_NAME}).")
        elif when > now + timedelta(days=MAX_DAYS_AHEAD):
            problems.append(
                f"scheduled_for {args.get('scheduled_for')} is more than "
                f"{MAX_DAYS_AHEAD} days out; today is {now:%Y-%m-%d}.")
    except (TypeError, ValueError):
        problems.append(
            "scheduled_for must be an ISO date-time, e.g. "
            f"{(now + timedelta(days=1)):%Y-%m-%d}T09:00:00-08:00.")
    times = find_schedule_claims(f"{args.get('hook', '')}\n{args.get('caption', '')}")
    if times:
        problems.append(
            "class times in public copy: " + "; ".join(f'"{t}"' for t in times)
            + ". The exact schedule is UNKNOWN. Remove the time, or ask Julie "
              "for it first.")
    claims = find_claims(f"{args.get('hook', '')}\n{args.get('caption', '')}")
    if claims:
        problems.append(
            "unverified results claim(s): " + "; ".join(f'"{c}"' for c in claims)
            + ". Never invent results, and do NOT rewrite it into a different "
              "client story: no made-up client, customer, patient or business "
              "presented as real. Stop and say a verified case is needed; offer a "
              "how-it-works post instead. Remove the claim, or ask Julie for a "
              "real, verified case.")
    return problems


def _model_busy_message(exc: Exception) -> str:
    """Owner-facing text when the model provider keeps failing (e.g. 429)."""
    return "El modelo de IA está ocupado en este momento (límite de uso). No se envió ni se agregó nada a la cola. Probá de nuevo en un minuto."


def _needs_approval(request) -> bool:
    """Approval gate `when` predicate: only valid proposals reach the card.

    Invalid ones skip the card and are refused by the tool body, so the
    model gets the problem list back and must fix the proposal.
    """
    return not validate_post(request.tool_call.get("args", {}))


class DateGroundingMiddleware(AgentMiddleware):
    """Append the current date/time to the system message on every model call.

    The system prompt is built once at import; without this the model
    guessed dates in 2023 (eval 2026-11-04, cases 6 and 10).
    """

    @staticmethod
    def date_line(now: datetime | None = None) -> str:
        now = now or datetime.now(OWNER_TZ)
        offset = now.strftime("%z")
        offset = f"{offset[:3]}:{offset[3:]}"
        days = ", ".join(f"{(now + timedelta(days=i)):%a %Y-%m-%d}" for i in range(1, 8))
        return (f"\n\nCURRENT DATE AND TIME: {now:%A %Y-%m-%d %H:%M} "
                f"({OWNER_TZ_NAME}, UTC offset {offset}). Use this year for every date.\n"
                f"NEXT 7 DAYS: {days}. Look weekdays up here; never compute them.\n"
                f"scheduled_for must be a future ISO date-time with an offset: use "
                f"{offset} by default, but if the owner names another time zone "
                f"(e.g. 'UTC', 'PT') use that zone's offset (UTC = +00:00). "
                f"Example: {(now + timedelta(days=1)):%Y-%m-%d}T09:00:00{offset}.")

    def _with_date(self, request):
        line = self.date_line()
        sm = request.system_message
        if sm is None:
            return request.override(system_message=SystemMessage(content=line.strip()))
        content = sm.content
        if isinstance(content, str):
            new = content + line
        else:
            new = list(content) + [{"type": "text", "text": line}]
        return request.override(system_message=SystemMessage(content=new))

    def wrap_model_call(self, request, handler):
        return handler(self._with_date(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._with_date(request))


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
    problems = validate_post({"account": account, "format": format, "hook": hook,
                              "caption": caption, "scheduled_for": scheduled_for})
    if problems:
        return ("NOT QUEUED. The proposal failed the safety checks and was not "
                "shown for approval:\n- " + "\n- ".join(problems)
                + "\nFix every point and call propose_post again, or tell "
                  "Julie plainly why you can't.")
    account = account.strip().lower()
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
- Facts only from tools and files. Never invent prices, schedules,
  offers, addresses or results. Missing fact = ask Julie or omit it.
- If a request asks for something these rules forbid (an invented result,
  a price, a schedule or address you don't have), REFUSE it in plain words
  and offer a truthful alternative. Never put a forbidden claim on an
  approval card.
- Reply to Julie in plain conversational text (markdown is fine). Never
  reply with JSON, status objects or code blocks unless asked, and don't
  narrate loading skills or files — just do the work.
- Public words (captions, comment and DM replies) never mention internal
  notes, rules, unset prices, programs or offers that aren't in the brain,
  or your reasoning.
- Never invent a client, customer, patient or business, or a story about
  one, and present it as real. A hypothetical must be labeled as one
  ("Example:" / "Imagine a ...") and carries no outcome claim.
- Otherwise, when Julie asks you to propose a post, call propose_post —
  never present a queue-ready post only as chat text, and never return an
  empty reply. Worked example: "proponé un post" (any wording) -> you call
  propose_post with concrete values (account, format, hook, caption,
  hashtags, scheduled_for as a future ISO date-time with offset, why) and
  let the approval card speak. If it comes back NOT QUEUED, fix every
  listed problem and call it again.
- Voice: Julie's, per the julie-voice skill and brand files. SHORT
  captions (~170 characters is her average), community first, humor or
  heart — never flyer-speak, never hype.

SKILLS are files, not tools. Load one with read_file on
/skills/<name>/SKILL.md BEFORE doing that kind of work. Never call a skill
name as a tool:
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


_graph = create_deep_agent(
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
                    "when": _needs_approval,
                },
            },
            description_prefix="Post approval pending",
        ),
        DateGroundingMiddleware(),
        # 429s from the model provider made runs die silently (eval
        # 2026-11-04: empty replies). Retry with backoff, then say so.
        ModelRetryMiddleware(max_retries=4, initial_delay=2.0, backoff_factor=2.0,
                             max_delay=30.0, on_failure=_model_busy_message),
    ],
)

# Agent Dojo links LangSmith root runs to this agent by the `agent:<dojo id>` tag
# (project name must start with `jk-`). with_config keeps a CompiledStateGraph, so
# langgraph.json / `langgraph dev` still load it and every root run carries the tag.
DOJO_AGENT_ID = "agent-repo.client-puravida-social-v1"
agent = _graph.with_config({"tags": ["agent:" + DOJO_AGENT_ID], "metadata": {"dojo_agent": DOJO_AGENT_ID}})
