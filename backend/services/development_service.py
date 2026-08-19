import json
import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional

import docker


DEFAULT_REPOSITORY_PATH = "/opt/command-center"
DEFAULT_CODE_SERVER_URL = "http://192.168.50.10:8443"
DEFAULT_WORKER_STATUS_FILE = "/tmp/development-worker-status.json"
WORKER_STATUS_VALUES = {"Starting", "Ready", "Busy", "Degraded", "Offline"}


def _tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def _run_git(args: List[str], repository_path: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "-C", repository_path, *args],
            capture_output=True,
            text=True,
            timeout=8,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return None


def _get_docker_client():
    try:
        client = docker.from_env()
        client.ping()
        return client, None
    except Exception as e:
        return None, str(e)


def _get_container_status(client, container_name: str) -> Dict[str, Any]:
    if not client:
        return {
            "name": container_name,
            "exists": False,
            "running": False,
            "state": "unavailable",
        }

    try:
        container = client.containers.get(container_name)
        try:
            container.reload()
        except Exception:
            pass

        state = getattr(container, "status", "unknown")
        return {
            "name": container_name,
            "exists": True,
            "running": state == "running",
            "state": state,
        }
    except Exception:
        return {
            "name": container_name,
            "exists": False,
            "running": False,
            "state": "missing",
        }


def _worker_tool_available(client, container_name: str, command: str) -> bool:
    if not client:
        return False
    try:
        container = client.containers.get(container_name)
        container.reload()
        if container.status != "running":
            return False
        result = container.exec_run(["/bin/sh", "-lc", f"command -v {command} >/dev/null 2>&1"])
        return result.exit_code == 0
    except Exception:
        return False


def _read_worker_bootstrap_status(client, container_name: str) -> Dict[str, Any]:
    if not client:
        return {"worker_status": "Offline"}

    status_file = os.getenv("WORKER_STATUS_FILE", DEFAULT_WORKER_STATUS_FILE)
    try:
        container = client.containers.get(container_name)
        container.reload()
        if container.status != "running":
            return {"worker_status": "Offline"}

        result = container.exec_run(["/bin/sh", "-lc", f"cat {status_file} 2>/dev/null"])
        if result.exit_code != 0:
            return {"worker_status": "Starting"}

        payload = result.output.decode("utf-8", errors="replace").strip()
        if not payload:
            return {"worker_status": "Starting"}

        data = json.loads(payload)
        worker_status = str(data.get("worker_status") or data.get("status") or "Starting")
        if worker_status not in WORKER_STATUS_VALUES:
            worker_status = "Starting"
        return {**data, "worker_status": worker_status}
    except Exception:
        return {"worker_status": "Starting"}


def _get_development_worker_status(client) -> Dict[str, Any]:
    container_name = os.getenv("DEVELOPMENT_WORKER_CONTAINER", "development-worker")
    status = _get_container_status(client, container_name)
    if not status.get("exists"):
        return {
            "exists": False,
            "online": False,
            "status": "Not Installed",
            "worker_status": "Offline",
            "tools": {},
        }

    bootstrap_status = _read_worker_bootstrap_status(client, container_name)
    worker_status = bootstrap_status.get("worker_status", "Starting")
    tools = {
        "git": _worker_tool_available(client, container_name, "git"),
        "docker": _worker_tool_available(client, container_name, "docker"),
        "python": _worker_tool_available(client, container_name, "python3"),
        "node": _worker_tool_available(client, container_name, "node"),
        "npm": _worker_tool_available(client, container_name, "npm"),
        "jq": _worker_tool_available(client, container_name, "jq"),
    }
    return {
        **status,
        **bootstrap_status,
        "worker_status": worker_status,
        "online": status.get("running", False),
        "ready": worker_status == "Ready",
        "tools": tools,
    }


def _get_git_status(repository_path: str) -> Dict[str, Any]:
    branch = _run_git(["branch", "--show-current"], repository_path)
    dirty_output = _run_git(["status", "--porcelain"], repository_path)
    commits_output = _run_git(["log", "-5", "--pretty=format:%h%x09%an%x09%ar%x09%s"], repository_path)

    recent_commits = []
    if commits_output:
        for line in commits_output.splitlines():
            parts = line.split("\t", 3)
            if len(parts) == 4:
                recent_commits.append({
                    "hash": parts[0],
                    "author": parts[1],
                    "relative_time": parts[2],
                    "message": parts[3],
                })

    return {
        "branch": branch or "unknown",
        "dirty": bool(dirty_output),
        "status": "dirty" if dirty_output else "clean" if dirty_output == "" else "unknown",
        "recent_commits": recent_commits,
    }


def get_status() -> Dict[str, Any]:
    repository_path = os.getenv("COMMAND_CENTER_REPOSITORY_PATH", DEFAULT_REPOSITORY_PATH)
    code_server_container_name = os.getenv("CODE_SERVER_CONTAINER_NAME", "code-server")
    code_server_url = os.getenv("CODE_SERVER_URL", DEFAULT_CODE_SERVER_URL)
    docker_client, docker_error = _get_docker_client()
    git_status = _get_git_status(repository_path)
    development_worker = _get_development_worker_status(docker_client)

    return {
        "ok": True,
        "worker_status": development_worker.get("worker_status", "Offline"),
        "repository_path": repository_path,
        "code_server_url": code_server_url,
        "code_server": _get_container_status(docker_client, code_server_container_name),
        "development_worker": development_worker,
        "codex_cli_available": _tool_available("codex"),
        "node_available": _tool_available("node"),
        "npm_available": _tool_available("npm"),
        "python_available": _tool_available("python3") or _tool_available("python"),
        "git_available": _tool_available("git"),
        "docker_available": docker_client is not None,
        "docker_error": docker_error,
        "git": git_status,
    }
