import json
import os
import re
from pathlib import Path

import docker

from storage import database_path


def _projects():
    path = database_path().parent / "projects.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("projects") or []
    except (OSError, json.JSONDecodeError):
        return []


def _worker_path(project_path):
    host_root = os.getenv("COMMAND_CENTER_REPOSITORY_PATH", "/opt/command-center")
    worker_root = os.getenv("COMMAND_CENTER_WORKER_REPOSITORY_PATH", "/workspace/command-center")
    return worker_root if project_path == host_root else None


def _git(container, path, *args):
    result = container.exec_run(["git", "-C", path, *args])
    if result.exit_code != 0:
        return None
    return result.output.decode("utf-8", errors="replace").strip()


def _github_repository(remote):
    if not remote:
        return None
    match = re.search(r"github\.com[/:]([^/]+/[^/]+?)(?:\.git)?$", remote)
    return match.group(1) if match else None


def _repository_status(container, path):
    branch = _git(container, path, "branch", "--show-current")
    status = _git(container, path, "status", "--porcelain")
    commit = _git(container, path, "log", "-1", "--pretty=format:%h%x09%aI%x09%s")
    remote = _git(container, path, "remote", "get-url", "origin")
    upstream = _git(container, path, "rev-list", "--left-right", "--count", "HEAD...@{upstream}")
    latest = None
    if commit:
        parts = commit.split("\t", 2)
        if len(parts) == 3:
            latest = {"hash": parts[0], "created_utc": parts[1], "message": parts[2]}
    ahead = behind = None
    if upstream:
        parts = upstream.split()
        if len(parts) == 2:
            ahead, behind = int(parts[0]), int(parts[1])
    github_repo = _github_repository(remote)
    return {
        "available": branch is not None, "branch": branch or "unknown",
        "worktree": "dirty" if status else "clean" if status == "" else "unknown",
        "changed_file_count": len(status.splitlines()) if status else 0,
        "latest_commit": latest, "remote": remote, "github_repository": github_repo,
        "github_url": f"https://github.com/{github_repo}" if github_repo else None,
        "ahead": ahead, "behind": behind, "remote_state_note": "Based on locally stored tracking refs; no fetch was performed.",
    }


def get_overview():
    projects = _projects()
    client = None
    worker = None
    try:
        client = docker.from_env()
        worker = client.containers.get(os.getenv("DEVELOPMENT_WORKER_CONTAINER", "development-worker"))
        worker.reload()
        if worker.status != "running":
            worker = None
    except Exception:
        worker = None
    result = []
    try:
        for project in projects:
            path = _worker_path(project.get("path", ""))
            repository = _repository_status(worker, path) if worker and path else None
            result.append({**project, "linked": bool(path), "repository": repository})
    finally:
        if client:
            client.close()
    return {
        "mode": "read_only", "network_calls_made": False,
        "github_token_configured": bool(os.getenv("GITHUB_TOKEN", "").strip()),
        "projects": result,
    }
