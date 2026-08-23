import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from services import release_service
from storage import initialize_storage


class ReleaseServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"VERA_DATABASE_PATH": os.path.join(self.temp.name, "vera.db")}, clear=False)
        self.environment.start()
        initialize_storage()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    @patch("services.release_service._worker")
    @patch("services.release_service._snapshot")
    def test_prepare_records_exact_snapshot_without_executing(self, snapshot, worker):
        client, container = Mock(), Mock()
        worker.return_value = (client, container)
        snapshot.return_value = {"branch": "codex/test", "remote": "https://github.com/example/repo.git", "head": "a" * 40, "status": " M backend/app.py", "files": ["backend/app.py"], "snapshot_hash": "hash", "diff_stat": "backend/app.py | 1 +"}
        release = release_service.prepare("owner", commit_message="Add safe release", deploy_requested=True)
        self.assertEqual(release["status"], "pending")
        self.assertEqual(release["files"], ["backend/app.py"])
        container.exec_run.assert_not_called()

    @patch("services.release_service._exec")
    def test_snapshot_blocks_runtime_and_secret_paths(self, execute):
        execute.side_effect = ["codex/test", "https://github.com/example/repo.git", "a" * 40, "?? secrets/token"]
        with self.assertRaisesRegex(ValueError, "blocked sensitive"):
            release_service._snapshot(Mock())

    @patch("services.release_service._exec")
    @patch("services.release_service._worker")
    @patch("services.release_service._snapshot")
    def test_execute_rechecks_snapshot_then_commits_pushes_and_deploys(self, snapshot, worker, execute):
        client, container = Mock(), Mock()
        worker.return_value = (client, container)
        container.exec_run.return_value = Mock(exit_code=0)
        exact = {"branch": "codex/test", "remote": "https://github.com/example/repo.git", "head": "a" * 40, "status": " M backend/app.py", "files": ["backend/app.py"], "snapshot_hash": "hash", "diff_stat": "stat"}
        snapshot.return_value = exact
        with patch("services.release_service._snapshot", return_value=exact):
            release = release_service.prepare("owner", commit_message="Release it", deploy_requested=True)
        execute.side_effect = ["", "", "b" * 40, "", ""]
        result = release_service.execute("owner", release["id"])
        self.assertTrue(result["pushed"])
        self.assertTrue(result["deployment_started"])
        push_call = next(call for call in execute.call_args_list if call.args[1][:2] == ["git", "push"])
        self.assertEqual(push_call.kwargs["environment"]["GIT_TERMINAL_PROMPT"], "0")


if __name__ == "__main__":
    unittest.main()
