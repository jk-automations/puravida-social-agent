"""Golden-set eval runner for the social agent (LangGraph dev server).

Usage: python3 run_evals.py <port> <fixtures.json> <queue.json> <out.json>

One fresh thread per case. Every approval interrupt is resumed with REJECT,
so an eval run must never change the content queue (queue_delta == 0).
Grading against each case's `expect` is done by a reviewer reading out.json.

Origin: Lorenzo's /tmp/eval_runner.py (2026-11-04), committed unchanged
except for the summary block at the end and recording propose_post
arguments + thread ids (2026-11-04, Claude) so cards can be graded;
runs that stop before finishing are reported as errors, not empty replies.
"""
import json, sys, urllib.request, urllib.error
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def call(port, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request("http://localhost:%d" % port + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    with opener.open(req, timeout=300) as r:
        return json.loads(r.read().decode())
def text_of(st):
    txt = ""
    for m in st.get("messages") or []:
        if m.get("type") == "ai":
            c = m.get("content")
            if isinstance(c, str): txt = c
            elif isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "text": txt = b.get("text", "")
    return txt
def proposals_of(st):
    # propose_post arguments: what the approval card would have shown.
    out = []
    for m in st.get("messages") or []:
        if m.get("type") == "ai":
            for tc in m.get("tool_calls") or []:
                if tc.get("name") == "propose_post":
                    out.append(tc.get("args"))
    return out
def tools_of(st):
    out = []
    for m in st.get("messages") or []:
        if m.get("type") == "ai":
            for tc in m.get("tool_calls") or []:
                out.append(tc.get("name"))
    return out

port = int(sys.argv[1]); fixtures_path = sys.argv[2]; queue_path = sys.argv[3]; out_path = sys.argv[4]
fx = json.load(open(fixtures_path))
def qlen():
    try: return len(json.load(open(queue_path)))
    except Exception: return 0
results = []
for case in fx["cases"]:
    rec = {"id": case["id"], "kind": case["kind"], "input": case["input"], "expect": case["expect"]}
    q_before = qlen()
    try:
        t = call(port, "POST", "/threads", {})["thread_id"]
        st = call(port, "POST", "/threads/%s/runs/wait" % t, {"assistant_id": "social_agent", "input": {"messages": [{"role": "user", "content": case["input"]}]}})
        state = call(port, "GET", "/threads/%s/state" % t)
        if state.get("next") and not st.get("__interrupt__"):
            rec["error"] = "run did not finish (next=%s); see server log" % state.get("next")
        rec["tools"] = tools_of(st)
        rec["interrupts"] = len(st.get("__interrupt__") or [])
        rec["proposals"] = proposals_of(st)
        rec["thread_id"] = t
        rec["text"] = text_of(st)[:900]
        if st.get("__interrupt__"):
            st2 = call(port, "POST", "/threads/%s/runs/wait" % t, {"assistant_id": "social_agent", "command": {"resume": {"decisions": [{"type": "reject", "message": "eval run - rejected to keep the queue clean"}]}}})
            rec["after_reject_text"] = text_of(st2)[:300]
    except Exception as e:
        rec["error"] = str(e)[:300]
    rec["queue_delta"] = qlen() - q_before
    results.append(rec)
    print("case", case["id"], "done", flush=True)
json.dump(results, open(out_path, "w"), ensure_ascii=False, indent=1)
print("WROTE", out_path, len(results))
errors = [r["id"] for r in results if "error" in r]
nonzero = [r["id"] for r in results if r["queue_delta"] != 0]
print("SUMMARY cases=%d interrupts=%d errors=%s queue_delta_nonzero=%s" % (
    len(results), sum(r.get("interrupts", 0) for r in results), errors, nonzero))
sys.exit(1 if (nonzero or errors) else 0)
