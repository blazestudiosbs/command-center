import importlib.util
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location("infrastructure_agent", Path(__file__).with_name("agent.py"))
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class InfrastructureAgentTests(unittest.TestCase):
    def test_ignores_cleanly_exited_unmanaged_container(self):
        self.assertIsNone(agent.container_issue("mystifying_lichterman", "Exited (0) 2 months ago"))

    def test_expected_stopped_container_is_critical(self):
        issue = agent.container_issue("command-center", "Exited (0) 1 minute ago")
        self.assertEqual(issue["severity"], "critical")

    def test_unmanaged_failed_container_is_warning(self):
        issue = agent.container_issue("experiment", "Exited (137) 1 minute ago")
        self.assertEqual(issue["severity"], "warning")


if __name__ == "__main__":
    unittest.main()
