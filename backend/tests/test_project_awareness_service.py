import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from services import project_awareness_service


class ProjectAwarenessServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "vera.db"
        self.environment = patch.dict(os.environ, {"VERA_DATABASE_PATH": str(self.database)}, clear=False)
        self.environment.start()
        (self.database.parent / "projects.json").write_text(json.dumps({"projects": [
            {"name": "Command Center", "path": "/opt/command-center", "type": "infrastructure", "priority": "high", "status": "active"},
            {"name": "Unlinked", "path": "", "type": "app", "priority": "medium", "status": "active"},
        ]}))

    def tearDown(self):
        self.environment.stop()
        self.temporary.cleanup()

    @patch("services.project_awareness_service.docker.from_env")
    def test_reads_repository_without_network_operations(self, from_env):
        client = Mock()
        container = Mock()
        container.status = "running"
        outputs = {
            ("branch", "--show-current"): "codex/vera-slice-1",
            ("status", "--porcelain"): "",
            ("log", "-1", "--pretty=format:%h%x09%aI%x09%s"): "abc123\t2026-08-23T00:00:00Z\tLatest work",
            ("remote", "get-url", "origin"): "https://github.com/blazestudiosbs/command-center.git",
            ("rev-list", "--left-right", "--count", "HEAD...@{upstream}"): "0 0",
        }
        def execute(command):
            value = outputs[tuple(command[3:])]
            return Mock(exit_code=0, output=value.encode())
        container.exec_run.side_effect = execute
        client.containers.get.return_value = container
        from_env.return_value = client

        overview = project_awareness_service.get_overview()

        repository = overview["projects"][0]["repository"]
        self.assertEqual(repository["branch"], "codex/vera-slice-1")
        self.assertEqual(repository["worktree"], "clean")
        self.assertEqual(repository["github_repository"], "blazestudiosbs/command-center")
        self.assertFalse(overview["network_calls_made"])
        self.assertFalse(overview["projects"][1]["linked"])

    def test_github_remote_parser_accepts_https_and_ssh(self):
        self.assertEqual(project_awareness_service._github_repository("git@github.com:owner/repo.git"), "owner/repo")
        self.assertEqual(project_awareness_service._github_repository("https://github.com/owner/repo.git"), "owner/repo")


if __name__ == "__main__":
    unittest.main()
