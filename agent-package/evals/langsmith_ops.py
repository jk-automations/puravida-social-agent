"""LangSmith ops for the social agent: dataset, review queue, free daily triage, experiments.

Run on the Studio with the agent's own Python (reads the LangSmith key from agent/.env,
never prints it):

  .venv/bin/python ../agent-package/evals/langsmith_ops.py setup
  .venv/bin/python ../agent-package/evals/langsmith_ops.py triage --hours 24 [--dry-run]
  .venv/bin/python ../agent-package/evals/langsmith_ops.py experiment --port 2025

All code checks are free (no model calls). Reuses the JK Arceus pattern of 2026-10-27
(daily triage -> annotation queue, feedback keys, no automation rules). Written 2026-11-04.
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
AGENT = REPO / "agent"
FIXTURES = HERE.parent / "fixtures.json"
QUEUE_FILE = AGENT / "data" / "queue.json"
MANIFEST = REPO / "agent-package" / "AGENT-MANIFEST.yaml"
_pid = re.search(r"^package_id:\s*([a-z0-9-]+)", MANIFEST.read_text(encoding="utf-8"), re.M)
SLUG = re.sub(r"-v\d+$", "", _pid.group(1)) if _pid else REPO.name   # e.g. jk-social-agent
DATASET = f"{SLUG}-golden-v1"
REVIEW_QUEUE = f"{SLUG}-failures-v1"
KEYS = ("social.no_error", "social.not_empty", "social.plain_text", "social.no_price",
        "social.valid_cards", "social.hard_rules")


# ---------- settings (key read from the agent's .env, never printed) ----------
def load_env():
    env = {}
    path = AGENT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("LANGSMITH_API_KEY", "LANGSMITH_ENDPOINT", "LANGSMITH_PROJECT"):
        if env.get(k):
            os.environ[k] = env[k]
    if not os.environ.get("LANGSMITH_API_KEY"):
        sys.exit("No LANGSMITH_API_KEY in agent/.env. Add it first (hidden paste), then rerun.")
    return os.environ.get("LANGSMITH_PROJECT", SLUG)


def validator():
    """The agent's own validate_post, imported without starting a model."""
    os.environ.setdefault("OPENAI_API_KEY", "ops-script-no-model-calls")
    sys.path.insert(0, str(AGENT))
    import agent as A  # noqa: E402
    return A.validate_post


# ---------- code checks (shared by triage and experiments) ----------
def _messages(outputs):
    msgs = (outputs or {}).get("messages") or []
    out = []
    for m in msgs:
        if isinstance(m, dict) and "kwargs" in m:          # serialized LangChain message
            kind = (m.get("id") or [""])[-1].lower().replace("message", "")
            m = {**m["kwargs"], "type": m["kwargs"].get("type") or kind}
        if isinstance(m, dict):
            out.append(m)
    return out


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def summarize(outputs):
    msgs = _messages(outputs)
    ai = [m for m in msgs if m.get("type") == "ai"]
    text = _text(ai[-1].get("content")) if ai else ""
    calls = [tc for m in ai for tc in (m.get("tool_calls") or [])]
    pending = bool(ai and ai[-1].get("tool_calls"))
    proposals = [tc.get("args", {}) for tc in calls if tc.get("name") == "propose_post"]
    return {"text": text.strip(), "tools": [tc.get("name") for tc in calls],
            "proposals": proposals, "pending_tool_call": pending}


PRICE = re.compile(r"(?:\$|USD\s?|₡)\s?\d")


def checks(summary, error=None, validate_post=None, queue_delta=0):
    text = summary["text"]
    s = {
        "social.no_error": 0 if error else 1,
        "social.not_empty": 1 if (text or summary["pending_tool_call"]) else 0,
        "social.plain_text": 0 if re.match(r"^\s*(\{|```json)", text) else 1,
        "social.no_price": 0 if PRICE.search(text) else 1,
    }
    if validate_post is not None and summary["proposals"]:
        # The last proposal is the one that reached a card (invalid ones were refused).
        s["social.valid_cards"] = 0 if validate_post(summary["proposals"][-1]) else 1
    else:
        s["social.valid_cards"] = 1
    s["social.hard_rules"] = 1 if all(s.values()) and queue_delta == 0 else 0
    return s


# ---------- commands ----------
def cmd_setup(client, project):
    from langsmith import schemas
    if client.has_dataset(dataset_name=DATASET):
        ds = client.read_dataset(dataset_name=DATASET)
    else:
        ds = client.create_dataset(DATASET, description=f"{REPO.name} golden cases (agent-package/evals/fixtures.json)")
    have = {(e.metadata or {}).get("case_id") for e in client.list_examples(dataset_id=ds.id)}
    cases = json.loads(FIXTURES.read_text(encoding="utf-8"))["cases"]
    new = [{"inputs": {"message": c["input"]}, "outputs": {"expect": c["expect"]},
            "metadata": {"case_id": str(c["id"]), "kind": c["kind"]}}
           for c in cases if str(c["id"]) not in have]
    if new:
        client.create_examples(dataset_id=ds.id, examples=new)
    queues = list(client.list_annotation_queues(name=REVIEW_QUEUE))
    queue = queues[0] if queues else client.create_annotation_queue(
        name=REVIEW_QUEUE,
        description=f"Runs from {project} that failed a code check (error, empty, JSON reply, price, invalid card).",
        rubric_instructions="Was the failure real? Note the correct behavior. Real failures become dataset cases.")
    for key in KEYS:
        try:
            client.create_feedback_config(key, feedback_config=schemas.FeedbackConfig(type="continuous", min=0, max=1))
        except Exception:
            pass  # already registered
    print(f"Dataset {DATASET}: {len(cases)} cases ({len(new)} added) id={ds.id}")
    print(f"Review queue {REVIEW_QUEUE}: id={queue.id}")
    print(f"Feedback keys: {', '.join(KEYS)}")


def cmd_triage(client, project, hours, dry_run):
    vp = validator()
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    runs = list(client.list_runs(project_name=project, is_root=True, start_time=since))
    queue = None if dry_run else next(iter(client.list_annotation_queues(name=REVIEW_QUEUE)), None)
    if not dry_run and queue is None:
        sys.exit("Run `setup` first (review queue missing).")
    failed, counts = [], {k: 0 for k in KEYS}
    for run in runs:
        scores = checks(summarize(run.outputs), run.error, vp)
        for k, v in scores.items():
            counts[k] += 0 if v else 1
        if not dry_run:
            for k, v in scores.items():
                client.create_feedback(run.id, key=k, score=v, comment="langsmith_ops triage (code check)")
        if not scores["social.hard_rules"]:
            failed.append(run.id)
    if failed and not dry_run:
        client.add_runs_to_annotation_queue(queue.id, run_ids=failed)
    print(f"Triage {project}, last {hours}h: {len(runs)} runs scanned, {len(failed)} failed"
          f"{' (dry run, nothing written)' if dry_run else ', queued for review'}")
    print("Failures by check: " + ", ".join(f"{k.split('.')[1]}={v}" for k, v in counts.items()))


def _call(port, method, path, body=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=300) as r:
        return json.loads(r.read().decode())


def cmd_experiment(client, project, port, prefix):
    vp = validator()

    def qlen():
        try:
            return len(json.loads(QUEUE_FILE.read_text(encoding="utf-8")))
        except Exception:
            return 0

    def target(inputs):
        before = qlen()
        t = _call(port, "POST", "/threads", {})["thread_id"]
        st = _call(port, "POST", f"/threads/{t}/runs/wait",
                   {"assistant_id": "social_agent", "input": {"messages": [{"role": "user", "content": inputs["message"]}]}})
        interrupted = bool(st.get("__interrupt__"))
        if interrupted:  # never let an eval queue a post
            _call(port, "POST", f"/threads/{t}/runs/wait",
                  {"assistant_id": "social_agent",
                   "command": {"resume": {"decisions": [{"type": "reject", "message": "eval run"}]}}})
        state = _call(port, "GET", f"/threads/{t}/state")
        summary = summarize({"messages": st.get("messages", [])})
        summary["pending_tool_call"] = summary["pending_tool_call"] or interrupted
        return {**summary, "unfinished": bool(state.get("next")) and not interrupted,
                "queue_delta": qlen() - before}

    def code_checks(run, example):
        o = run.outputs or {}
        scores = checks(o, "unfinished run" if o.get("unfinished") else run.error, vp, o.get("queue_delta", 0))
        return {"results": [{"key": k, "score": v} for k, v in scores.items()]}

    sha = os.popen(f"git -C {REPO} rev-parse --short HEAD").read().strip() or "unknown"
    results = client.evaluate(target, data=DATASET, evaluators=[code_checks],
                              experiment_prefix=f"{prefix or SLUG}-{sha}", max_concurrency=1,
                              metadata={"git_sha": sha, "port": port})
    print(f"Experiment done: {results.experiment_name}. Open the dataset {DATASET} in LangSmith to compare runs.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup")
    t = sub.add_parser("triage"); t.add_argument("--hours", type=int, default=24); t.add_argument("--dry-run", action="store_true")
    e = sub.add_parser("experiment"); e.add_argument("--port", type=int, default=2025); e.add_argument("--prefix", default="")
    args = ap.parse_args()
    project = load_env()
    from langsmith import Client
    client = Client()
    if args.cmd == "setup":
        cmd_setup(client, project)
    elif args.cmd == "triage":
        cmd_triage(client, project, args.hours, args.dry_run)
    else:
        cmd_experiment(client, project, args.port, args.prefix)


if __name__ == "__main__":
    main()
