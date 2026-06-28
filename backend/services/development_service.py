import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional

import docker


DEFAULT_REPOSITORY_PATH = "/opt/command-center"
DEFAULT_CODE_SERVER_URL = "http://192.168.50.10:8443"


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

    return {
        "ok": True,
        "repository_path": repository_path,
        "code_server_url": code_server_url,
        "code_server": _get_container_status(docker_client, code_server_container_name),
        "codex_cli_available": _tool_available("codex"),
        "node_available": _tool_available("node"),
        "npm_available": _tool_available("npm"),
        "python_available": _tool_available("python3") or _tool_available("python"),
        "git_available": _tool_available("git"),
        "docker_available": docker_client is not None,
        "docker_error": docker_error,
        "git": git_status,
    }
