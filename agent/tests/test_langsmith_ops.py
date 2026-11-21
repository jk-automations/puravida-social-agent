"""Code checks used by agent-package/evals/langsmith_ops.py (no network, no key)."""
import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "langsmith_ops", Path(__file__).resolve().parents[2] / "agent-package" / "evals" / "langsmith_ops.py")
ops = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ops)


def ai(text="", calls=None):
    return {"type": "ai", "content": text, "tool_calls": calls or []}


def serialized_ai(text):
    return {"lc": 1, "type": "constructor", "id": ["langchain", "schema", "messages", "AIMessage"],
            "kwargs": {"content": [{"type": "text", "text": text}], "tool_calls": []}}


class Checks(unittest.TestCase):
    def test_plain_dict_and_serialized_messages(self):
        self.assertEqual(ops.summarize({"messages": [ai("hello")]})["text"], "hello")
        self.assertEqual(ops.summarize({"messages": [serialized_ai("hola")]})["text"], "hola")

    def test_good_reply_passes_everything(self):
        s = ops.checks(ops.summarize({"messages": [ai("Pricing is set on the call.")]}))
        self.assertTrue(all(s.values()), s)

    def test_failures_are_caught(self):
        self.assertEqual(ops.checks(ops.summarize({"messages": [ai("")]}))["social.not_empty"], 0)
        self.assertEqual(ops.checks(ops.summarize({"messages": [ai('{"status": 403}')]}))["social.plain_text"], 0)
        self.assertEqual(ops.checks(ops.summarize({"messages": [ai("Stage 1 is $500")]}))["social.no_price"], 0)
        self.assertEqual(ops.checks(ops.summarize({"messages": [ai("ok")]}), error="boom")["social.no_error"], 0)
        self.assertEqual(ops.checks(ops.summarize({"messages": [ai("ok")]}), queue_delta=1)["social.hard_rules"], 0)

    def test_pending_approval_is_not_empty(self):
        out = {"messages": [ai("", [{"name": "propose_post", "args": {"account": "jkauto"}}])]}
        self.assertEqual(ops.checks(ops.summarize(out))["social.not_empty"], 1)

    def test_card_validity_uses_agent_validator(self):
        out = {"messages": [ai("", [{"name": "propose_post", "args": {"account": "bad"}}])]}
        bad = ops.checks(ops.summarize(out), validate_post=lambda a: ["account not valid"])
        good = ops.checks(ops.summarize(out), validate_post=lambda a: [])
        self.assertEqual((bad["social.valid_cards"], good["social.valid_cards"]), (0, 1))
        self.assertEqual(bad["social.hard_rules"], 0)

    def test_names_follow_the_repo(self):
        self.assertTrue(ops.DATASET.endswith("-golden-v1") and ops.REVIEW_QUEUE.endswith("-failures-v1"))
        self.assertIn(ops.SLUG, ("jk-social-agent", "client-puravida-social"))


if __name__ == "__main__":
    unittest.main()
