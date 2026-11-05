"""M1 safety tests (stdlib unittest; no model calls).

Run from agent/:  .venv/bin/python -m unittest tests/test_safety.py -v
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("PURAVIDA_AGENT_ENABLED", "true")
os.environ.setdefault("OPENAI_API_KEY", "test-not-a-key")

import agent as A  # noqa: E402

NOW = datetime(2026, 11, 4, 16, 0, tzinfo=A.OWNER_TZ)
GOOD = {"account": "studio", "format": "reel", "hook": "Julie corrige: hombros en el plank",
        "caption": "3 cues para un plank más fuerte. ¿Lo probaste en clase?",
        "hashtags": "#pilates #barre", "scheduled_for": "2026-11-10T09:00:00-06:00", "why": "Julie corrige series"}


def bad(**kw):
    d = dict(GOOD)
    d.update(kw)
    return d


class ValidatePost(unittest.TestCase):
    def test_good_post_passes(self):
        self.assertEqual(A.validate_post(GOOD, NOW), [])

    def test_bad_account(self):
        self.assertTrue(any("account" in p for p in A.validate_post(bad(account="puravidamoves.studio"), NOW)))

    def test_bad_format(self):
        self.assertTrue(A.validate_post(bad(format="tweet"), NOW))

    def test_wrong_year_rejected(self):
        probs = A.validate_post(bad(scheduled_for="2023-11-06T10:00:00Z"), NOW)
        self.assertTrue(any("past" in p for p in probs))

    def test_too_far_ahead(self):
        self.assertTrue(A.validate_post(bad(scheduled_for="2027-06-01T09:00:00-07:00"), NOW))

    def test_free_text_date_rejected(self):
        self.assertTrue(any("ISO" in p for p in A.validate_post(bad(scheduled_for="tomorrow 9am"), NOW)))

    def test_naive_date_uses_owner_tz(self):
        self.assertEqual(A.validate_post(bad(scheduled_for="2026-11-10T09:00:00"), NOW), [])

    def test_invented_result_rejected(self):
        cap = "One of our clients just doubled their bookings last month thanks to a voice agent."
        probs = A.validate_post(bad(caption=cap), NOW)
        self.assertTrue(any("claim" in p for p in probs))

    def test_percent_and_multiplier_rejected(self):
        self.assertTrue(A.validate_post(bad(hook="Cut admin time by 40%"), NOW))
        self.assertTrue(A.validate_post(bad(hook="3x more leads"), NOW))

    def test_spanish_invented_results_rejected(self):
        for cap in ["Nuestras alumnas pierden 5 kilos en un mes.",
                    "Duplicamos las reservas del estudio.",
                    "Aumentamos un 30% las ventas."]:
            self.assertTrue(A.find_claims(cap), cap)

    def test_schedule_times_rejected(self):
        for cap in ["Mañana a las 7am en el estudio, Julie te corrige.",
                    "Clase de barre 18:30 hs", "Nos vemos at 9 en el estudio"]:
            self.assertTrue(any("UNKNOWN" in p for p in A.validate_post(bad(caption=cap), NOW)), cap)

    def test_no_false_positive_on_ordinary_numbers(self):
        for hook in ["3 cues para un plank más fuerte",
                     "5 minutos de barre", "Barreaños de 2 alumnas"]:
            self.assertEqual(A.find_claims(hook), [], hook)


class GateAndTool(unittest.TestCase):
    def test_when_predicate(self):
        self.assertTrue(A._needs_approval(SimpleNamespace(tool_call={"args": GOOD})))
        self.assertFalse(A._needs_approval(SimpleNamespace(tool_call={"args": bad(account="nope")})))

    def test_tool_refuses_invalid_and_queue_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            q = Path(d) / "queue.json"
            q.write_text("[]", encoding="utf-8")
            old = A.QUEUE_FILE
            A.QUEUE_FILE = q
            try:
                out = A.propose_post.invoke(bad(caption="Triplicamos las reservas en una semana."))
                self.assertIn("NOT QUEUED", out)
                self.assertEqual(json.loads(q.read_text()), [])
            finally:
                A.QUEUE_FILE = old

    def test_tool_queues_valid_post(self):
        future = (datetime.now(A.OWNER_TZ) + timedelta(days=3)).replace(microsecond=0).isoformat()
        with tempfile.TemporaryDirectory() as d:
            q = Path(d) / "queue.json"
            q.write_text("[]", encoding="utf-8")
            old = A.QUEUE_FILE
            A.QUEUE_FILE = q
            try:
                out = A.propose_post.invoke(bad(scheduled_for=future))
                self.assertIn("Queued", out)
                self.assertEqual(len(json.loads(q.read_text())), 1)
            finally:
                A.QUEUE_FILE = old

    def test_gate_configured_with_predicate(self):
        src = (HERE / "agent.py").read_text(encoding="utf-8")
        self.assertIn('"when": _needs_approval', src)
        self.assertIn("DateGroundingMiddleware()", src)


class DateGrounding(unittest.TestCase):
    def test_date_line_has_current_year(self):
        line = A.DateGroundingMiddleware.date_line()
        self.assertIn(str(datetime.now(A.OWNER_TZ).year), line)

    def test_appends_to_string_and_block_system_messages(self):
        mw = A.DateGroundingMiddleware()
        for content in ["base prompt", [{"type": "text", "text": "base prompt"}]]:
            captured = {}
            req = SimpleNamespace(system_message=A.SystemMessage(content=content),
                                  override=lambda **kw: captured.update(kw) or kw)
            mw._with_date(req)
            text = json.dumps(captured["system_message"].content)
            self.assertIn("base prompt", text)
            self.assertIn("CURRENT DATE AND TIME", text)


class Patch2(unittest.TestCase):
    def test_calendar_and_offset_in_date_line(self):
        now = datetime(2026, 11, 4, 16, 0, tzinfo=A.OWNER_TZ)
        line = A.DateGroundingMiddleware.date_line(now)
        self.assertIn("Thu 2026-11-05", line)
        self.assertIn("Mon 2026-11-09", line)
        off = now.strftime("%z")
        self.assertIn(f"{off[:3]}:{off[3:]}", line)

    def test_owner_named_zone_allowed(self):
        self.assertIn("UTC = +00:00", A.DateGroundingMiddleware.date_line())
        self.assertEqual(A.validate_post(bad(scheduled_for="2026-11-10T07:00:00Z"), NOW), [])

    def test_plain_text_rule_in_prompt(self):
        self.assertIn("Never\n  reply with JSON", A.SYSTEM_PROMPT)

    def test_retry_configured_and_busy_message(self):
        src = (HERE / "agent.py").read_text(encoding="utf-8")
        self.assertIn("ModelRetryMiddleware(max_retries=4", src)
        self.assertTrue(len(A._model_busy_message(RuntimeError("429"))) > 20)

    def test_claim_message_forbids_swapped_story(self):
        probs = A.validate_post(bad(caption="We doubled bookings."), NOW)
        self.assertTrue(any("do NOT rewrite" in p for p in probs))


if __name__ == "__main__":
    unittest.main()
