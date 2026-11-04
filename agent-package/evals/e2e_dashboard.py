"""Real-browser E2E for the social-agent dashboard (headless Chromium, Playwright).

Usage: python3 e2e_dashboard.py <dashboard_url> <queue.json> <out_dir> <propose_prompt>

Flow, each in a fresh browser context (fresh thread):
  A. ask the agent to propose a post -> approval card appears -> click Approve
     -> queue grows by exactly 1
  B. ask again -> approval card -> Reject -> Confirm Reject -> queue unchanged
The queue file is backed up first and restored at the end (also on failure),
so the run leaves the queue exactly as it found it. Screenshots go to out_dir.
If E2E_QUEUE_SSH=<host> is set, <queue.json> is a path on that host and is
read/backed up/restored over ssh (run the browser where real users sit, e.g.
the MacBook over Tailscale; the Studio cannot hairpin to its own Tailscale IP).
Exit code 0 only if both A and B behave as above.
"""
import json, os, shlex, shutil, subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

url, queue_arg, out_dir, prompt = sys.argv[1], sys.argv[2], Path(sys.argv[3]), sys.argv[4]
out_dir.mkdir(parents=True, exist_ok=True)
SSH = os.environ.get("E2E_QUEUE_SSH")
backup_arg = queue_arg + ".e2e-backup"

def sh(cmd):
    return subprocess.run(["ssh", "-o", "BatchMode=yes", SSH, cmd], check=True,
                          capture_output=True, text=True).stdout

def read_queue():
    if SSH:
        return json.loads(sh("cat " + shlex.quote(queue_arg)))
    return json.loads(Path(queue_arg).read_text(encoding="utf-8"))

def copy(src, dst):
    if SSH:
        sh("cp -p %s %s" % (shlex.quote(src), shlex.quote(dst)))
    else:
        shutil.copy2(src, dst)

def qlen():
    return len(read_queue())

copy(queue_arg, backup_arg)

def run_case(browser, name, decide):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)[:200]))
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.get_by_placeholder("Write your message...").wait_for(state="visible", timeout=60000)
    page.screenshot(path=str(out_dir / f"{name}-1-open.png"))
    box = page.get_by_placeholder("Write your message...")
    box.fill(prompt)
    page.get_by_role("button", name="Send").click()
    approve = page.get_by_role("button", name="Approve")
    approve.wait_for(state="visible", timeout=240000)
    page.screenshot(path=str(out_dir / f"{name}-2-approval-card.png"), full_page=True)
    before = qlen()
    if decide == "approve":
        approve.click()
    else:
        page.get_by_role("button", name="Reject").click()
        page.get_by_role("button", name="Confirm Reject").click()
    # wait until the run finishes: input placeholder returns from "Running..."
    time.sleep(3)
    page.get_by_placeholder("Write your message...").wait_for(state="visible", timeout=240000)
    time.sleep(2)
    page.screenshot(path=str(out_dir / f"{name}-3-after-{decide}.png"), full_page=True)
    after = qlen()
    ctx.close()
    return {"case": name, "decision": decide, "queue_before": before,
            "queue_after": after, "delta": after - before, "page_errors": errors}

results, ok = [], False
try:
    with sync_playwright() as p:
        # E2E_CHROMIUM: optional path to a Chromium build when the Playwright
        # package and the cached browser revision differ (Studio, 2026-11-04).
        exe = os.environ.get("E2E_CHROMIUM")
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        results.append(run_case(browser, "A", "approve"))
        results.append(run_case(browser, "B", "reject"))
        browser.close()
    ok = results[0]["delta"] == 1 and results[1]["delta"] == 0
    added = read_queue()[-1] if results[0]["delta"] == 1 else None
    results.append({"approved_entry": added})
except Exception as e:
    results.append({"error": f"{type(e).__name__}: {str(e)[:400]}"})
finally:
    copy(backup_arg, queue_arg)
    if SSH:
        sh("rm " + shlex.quote(backup_arg))
    else:
        Path(backup_arg).unlink()
    results.append({"queue_restored_len": qlen()})

(out_dir / "e2e-result.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
print(json.dumps(results, ensure_ascii=False, indent=1))
print("E2E", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
