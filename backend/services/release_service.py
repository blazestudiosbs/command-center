import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

import docker

from storage import connection


WORKER = os.getenv("DEVELOPMENT_WORKER_CONTAINER", "development-worker")
REPOSITORY = os.getenv("DEVELOPMENT_WORKER_WORKDIR", "/workspace/command-center")
TTL_MINUTES = 30
BLOCKED_PATHS = (".env", "secrets/", "config/", ".git/", "outputs/")


def _now():
    return datetime.now(timezone.utc)


def _iso(value):
    return value.isoformat().replace("+00:00", "Z")


def _worker():
    client = docker.from_env()
    container = client.containers.get(WORKER)
    container.reload()
    if container.status != "running":
        client.close()
        raise RuntimeError("Development worker is not running.")
    return client, container


def _exec(container, args, *, environment=None):
    result = container.exec_run(args, workdir=REPOSITORY, environment=environment)
    output = result.output.decode("utf-8", errors="replace").strip()
    if result.exit_code != 0:
        raise RuntimeError(output or f"Command failed with exit {result.exit_code}.")
    return output


def _snapshot(container):
    branch = _exec(container, ["git", "branch", "--show-current"])
    if not branch.startswith("codex/") or not re.fullmatch(r"codex/[A-Za-z0-9._/-]+", branch):
        raise ValueError("Approved releases are limited to codex/* branches.")
    remote = _exec(container, ["git", "remote", "get-url", "origin"])
    if not re.search(r"(?:https://|git@)github\.com[/:][^/]+/[^/]+(?:\.git)?$", remote):
        raise ValueError("The origin remote must be a GitHub repository.")
    head = _exec(container, ["git", "rev-parse", "HEAD"])
    status = _exec(container, ["git", "status", "--porcelain=v1", "--untracked-files=all"])
    if not status:
        raise ValueError("There are no changes to release.")
    files = []
    for line in status.splitlines():
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.strip('"')
        if not path or path.startswith("/") or ".." in path.split("/"):
            raise ValueError("The worktree contains an unsafe path.")
        if path == ".env" or any(path.startswith(prefix) for prefix in BLOCKED_PATHS):
            raise ValueError(f"Release preparation blocked sensitive or runtime path: {path}")
        files.append(path)
    return {"branch": branch, "remote": remote, "head": head, "status": status, "files": files, "snapshot_hash": hashlib.sha256(status.encode()).hexdigest(), "diff_stat": _exec(container, ["git", "diff", "--stat", "HEAD", "--", *files])}


def connection_status():
    client = None
    try:
        client, container = _worker()
        secret = container.exec_run(["/bin/sh", "-c", "test -s /run/secrets/github_token"]).exit_code == 0
        return {"worker_ready": True, "github_push_configured": secret, "approval_required": True, "allowed_branch_pattern": "codex/*", "deploy_services": ["command-center", "command-center-ui", "vera-discord"]}
    except Exception as exc:
        return {"worker_ready": False, "github_push_configured": False, "approval_required": True, "detail": str(exc)}
    finally:
        if client:
            client.close()


def prepare(user_id, *, commit_message, deploy_requested=True):
    message = " ".join(commit_message.strip().split())
    if not message or len(message) > 120 or re.search(r"[\r\n]", commit_message):
        raise ValueError("Use a single-line commit message of 120 characters or fewer.")
    client = None
    try:
        client, container = _worker()
        snapshot = _snapshot(container)
        now, release_id = _now(), str(uuid.uuid4())
        with connection() as conn:
            conn.execute("INSERT INTO release_approvals (id,user_id,branch,expected_head,snapshot_hash,files_json,commit_message,deploy_requested,status,created_utc,expires_utc) VALUES (?,?,?,?,?,?,?,?, 'pending',?,?)", (release_id, user_id, snapshot["branch"], snapshot["head"], snapshot["snapshot_hash"], json.dumps(snapshot["files"]), message, int(deploy_requested), _iso(now), _iso(now + timedelta(minutes=TTL_MINUTES))))
        return {**snapshot, "id": release_id, "status": "pending", "commit_message": message, "deploy_requested": bool(deploy_requested), "expires_utc": _iso(now + timedelta(minutes=TTL_MINUTES))}
    finally:
        if client:
            client.close()


def list_releases(user_id, limit=20):
    now = _iso(_now())
    with connection() as conn:
        conn.execute("UPDATE release_approvals SET status='expired' WHERE user_id=? AND status='pending' AND expires_utc<=?", (user_id, now))
        rows = conn.execute("SELECT * FROM release_approvals WHERE user_id=? ORDER BY created_utc DESC LIMIT ?", (user_id, max(1, min(int(limit), 50)))).fetchall()
    return [{**dict(row), "files": json.loads(row["files_json"]), "deploy_requested": bool(row["deploy_requested"])} for row in rows]


def execute(user_id, release_id):
    now = _now()
    with connection() as conn:
        row = conn.execute("SELECT * FROM release_approvals WHERE id=? AND user_id=?", (release_id, user_id)).fetchone()
        if not row or row["status"] != "pending":
            raise ValueError("This release is not awaiting approval.")
        if row["expires_utc"] <= _iso(now):
            conn.execute("UPDATE release_approvals SET status='expired' WHERE id=?", (release_id,))
            raise ValueError("This release approval expired. Prepare it again.")
    client = None
    try:
        client, container = _worker()
        if container.exec_run(["/bin/sh", "-c", "test -s /run/secrets/github_token"]).exit_code != 0:
            raise RuntimeError("GitHub push secret is not configured in the development worker.")
        current = _snapshot(container)
        if current["head"] != row["expected_head"] or current["snapshot_hash"] != row["snapshot_hash"] or current["branch"] != row["branch"]:
            raise ValueError("The repository changed after this release was prepared. Prepare a new approval.")
        with connection() as conn:
            conn.execute("UPDATE release_approvals SET status='executing' WHERE id=? AND status='pending'", (release_id,))
        files = json.loads(row["files_json"])
        _exec(container, ["git", "add", "--", *files])
        _exec(container, ["git", "-c", "user.name=Vera Command Center", "-c", "user.email=vera@command-center.local", "commit", "-m", row["commit_message"], "--", *files])
        commit_hash = _exec(container, ["git", "rev-parse", "HEAD"])
        _exec(container, ["git", "push", "origin", row["branch"]], environment={"GIT_ASKPASS": "/usr/local/bin/github-askpass.sh", "GIT_TERMINAL_PROMPT": "0"})
        if row["deploy_requested"]:
            command = "sleep 3; docker compose up -d --build command-center command-center-ui vera-discord > config/release-deploy.log 2>&1"
            _exec(container, ["/bin/sh", "-c", f"nohup /bin/sh -c '{command}' >/dev/null 2>&1 &"])
        with connection() as conn:
            conn.execute("UPDATE release_approvals SET status='completed',commit_hash=?,completed_utc=? WHERE id=?", (commit_hash, _iso(_now()), release_id))
        return {"id": release_id, "status": "completed", "commit_hash": commit_hash, "pushed": True, "deployment_started": bool(row["deploy_requested"])}
    except Exception as exc:
        with connection() as conn:
            conn.execute("UPDATE release_approvals SET status='failed',error=?,completed_utc=? WHERE id=?", (type(exc).__name__ + ": " + str(exc)[:500], _iso(_now()), release_id))
        raise
    finally:
        if client:
            client.close()
