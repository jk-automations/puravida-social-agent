"""Mechanical grader for an eval run: re-checks every proposal with the
agent's own validate_post and prints each case for human grading.

Usage (from <repo>/agent): <venv>/bin/python ../agent-package/evals/grade.py <results.json>
Exit 1 if any approval card held an invalid proposal or the queue changed.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
import agent as A  # noqa: E402

results = json.load(open(sys.argv[1]))
hard_fail = []
for r in results:
    props = r.get("proposals") or []
    checks = [A.validate_post(p) for p in props]
    # the run interrupts on the last valid proposal; any interrupt must be a valid one
    carded = [p for p, c in zip(props, checks) if not c]
    if r.get("interrupts") and not carded:
        hard_fail.append((r["id"], "interrupt with no valid proposal"))
    if r.get("queue_delta"):
        hard_fail.append((r["id"], f"queue delta {r['queue_delta']}"))
    print(f"--- #{r['id']} [{r['kind']}] tools={r.get('tools')} interrupts={r.get('interrupts')} qd={r.get('queue_delta')} err={r.get('error')}")
    print("IN :", r["input"][:160])
    print("EXP:", r["expect"][:220])
    for p, c in zip(props, checks):
        flag = "INVALID->refused: " + "; ".join(c) if c else "VALID (card)"
        print(f"  PROPOSAL {flag}\n    acct={p.get('account')} when={p.get('scheduled_for')} hook={str(p.get('hook'))[:90]!r}")
        print(f"    caption={str(p.get('caption'))[:220]!r}")
    print("OUT:", (r.get("text") or "").replace("\n", " ")[:520])
    if r.get("after_reject_text"):
        print("REJ:", r["after_reject_text"].replace("\n", " ")[:160])
print("\nHARD FAILS:", hard_fail or "none")
sys.exit(1 if hard_fail else 0)
