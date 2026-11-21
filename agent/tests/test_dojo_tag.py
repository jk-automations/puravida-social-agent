"""Dojo link: every root run of the graph carries the agent:<dojo id> tag.

Run from agent/:  python tests/test_dojo_tag.py   (no model is called)
"""
import importlib.util
import os
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
AGENT = Path(__file__).resolve().parents[1] / "agent.py"


class DojoTagTests(unittest.TestCase):
    def test_graph_config_has_agent_tag(self):
        os.environ.setdefault("OPENAI_API_KEY", "dummy-not-used")
        sys.path.insert(0, str(AGENT.parent))
        spec = importlib.util.spec_from_file_location("agent_under_test", AGENT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(type(mod.agent).__name__, "CompiledStateGraph")
        self.assertIn("agent:agent-repo.client-puravida-social-v1", mod.agent.config["tags"])


if __name__ == "__main__":
    unittest.main()
