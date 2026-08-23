import json
import os
import re
from pathlib import Path

import docker
import requests

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


def _github_token():
    direct = os.getenv("GITHUB_TOKEN", "").strip()
    if direct:
        return direct
    try:
        return Path(os.getenv("GITHUB_TOKEN_FILE", "/run/secrets/github_token")).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _github_summary(repository, token):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2026-03-10",
        "User-Agent": "Vera-Command-Center",
    }
    try:
        issues_response = requests.get(f"https://api.github.com/repos/{repository}/issues", headers=headers, params={"state": "open", "per_page": 20}, timeout=12)
        pulls_response = requests.get(f"https://api.github.com/repos/{repository}/pulls", headers=headers, params={"state": "open", "per_page": 20}, timeout=12)
        issues_response.raise_for_status()
        pulls_response.raise_for_status()
        issues = [item for item in issues_response.json() if "pull_request" not in item]
        pulls = pulls_response.json()
        return {
            "status": "connected", "open_issue_count": len(issues), "open_pull_request_count": len(pulls),
            "issues": [{"number": item["number"], "title": item["title"], "url": item["html_url"], "updated_utc": item["updated_at"]} for item in issues[:5]],
            "pull_requests": [{"number": item["number"], "title": item["title"], "url": item["html_url"], "draft": bool(item.get("draft")), "updated_utc": item["updated_at"]} for item in pulls[:5]],
            "permission": "read_only", "content_bodies_loaded": False,
        }
    except requests.RequestException as exc:
        return {"status": "unavailable", "detail": f"GitHub API request failed safely ({type(exc).__name__}).", "issues": [], "pull_requests": []}


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
    github_token = _github_token()
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
            github = _github_summary(repository["github_repository"], github_token) if github_token and repository and repository.get("github_repository") else None
            result.append({**project, "linked": bool(path), "repository": repository, "github": github})
    finally:
        if client:
            client.close()
    return {
        "mode": "read_only", "network_calls_made": bool(github_token),
        "github_token_configured": bool(github_token),
        "projects": result,
    }
