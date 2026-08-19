import json
import os
import shlex
from typing import Any, Dict, Optional

import docker


DEFAULT_WORKER_STATUS_FILE = "/tmp/development-worker-status.json"
DEVELOPMENT_WORKER_CONTAINER = os.getenv("DEVELOPMENT_WORKER_CONTAINER", "development-worker")
WORKER_STATUSES = {"Starting", "Ready", "Busy", "Degraded", "Offline"}
DEVELOPMENT_WORKER_CAPABILITIES = [
    "git",
    "docker",
    "python",
    "node",
    "npm",
    "jq",
    "validation",
    "rebuild",
    "diff",
]
DEVELOPMENT_WORKER_TOOL_COMMANDS = {
    "git": "git",
    "docker": "docker",
    "python": "python3",
    "node": "node",
    "npm": "npm",
    "jq": "jq",
}


def _offline_worker(message: str, tools: Optional[Dict[str, bool]] = None) -> Dict[str, Any]:
    return {
        "name": DEVELOPMENT_WORKER_CONTAINER,
        "type": "development",
        "status": "Offline",
        "online": False,
        "ready": False,
        "capabilities": list(DEVELOPMENT_WORKER_CAPABILITIES),
        "tools": tools or {name: False for name in DEVELOPMENT_WORKER_TOOL_COMMANDS},
        "current_task": None,
        "last_heartbeat": None,
        "status_message": message,
    }


def _get_docker_client():
    try:
        client = docker.from_env()
        client.ping()
        return client, None
    except Exception as e:
        return None, str(e)


def _read_bootstrap_status(container) -> Dict[str, Any]:
    status_file = os.getenv("WORKER_STATUS_FILE", DEFAULT_WORKER_STATUS_FILE)
    try:
        result = container.exec_run(["/bin/sh", "-lc", f"cat {shlex.quote(status_file)} 2>/dev/null"])
        if result.exit_code != 0:
            return {"worker_status": "Starting", "message": "Worker boot status file is not available yet."}

        payload = result.output.decode("utf-8", errors="replace").strip()
        if not payload:
            return {"worker_status": "Starting", "message": "Worker boot status file is empty."}

        data = json.loads(payload)
        return data if isinstance(data, dict) else {"worker_status": "Starting", "message": "Worker boot status file is invalid."}
    except Exception as e:
        return {"worker_status": "Starting", "message": f"Worker boot status could not be read: {e}"}


def _tool_available(container, command: str) -> bool:
    try:
        result = container.exec_run(["/bin/sh", "-lc", f"command -v {shlex.quote(command)} >/dev/null 2>&1"])
        return result.exit_code == 0
    except Exception:
        return False


def _normalize_status(value: Any) -> str:
    status = str(value or "Starting").strip()
    return status if status in WORKER_STATUSES else "Starting"


def get_development_worker_status() -> Dict[str, Any]:
    client, docker_error = _get_docker_client()
    if not client:
        return _offline_worker(f"Docker unavailable: {docker_error or 'unknown error'}")

    try:
        container = client.containers.get(DEVELOPMENT_WORKER_CONTAINER)
        container.reload()
    except Exception:
        return _offline_worker("development-worker container is missing.")

    if container.status != "running":
        return _offline_worker(f"development-worker container is {container.status or 'not running'}.")

    bootstrap_status = _read_bootstrap_status(container)
    tools = {
        name: _tool_available(container, command)
        for name, command in DEVELOPMENT_WORKER_TOOL_COMMANDS.items()
    }
    missing_tools = [name for name, available in tools.items() if not available]
    status = _normalize_status(bootstrap_status.get("worker_status") or bootstrap_status.get("status"))
    if status == "Ready" and missing_tools:
        status = "Degraded"

    status_message = str(bootstrap_status.get("status_message") or bootstrap_status.get("message") or "").strip()
    if status == "Degraded" and missing_tools:
        tool_message = f"Missing tools: {', '.join(missing_tools)}."
        status_message = f"{status_message} {tool_message}".strip()
    if not status_message:
        status_message = {
            "Starting": "Worker booting.",
            "Ready": "Worker ready.",
            "Busy": "Worker busy.",
            "Degraded": "Worker degraded.",
            "Offline": "Worker offline.",
        }[status]

    return {
        "name": DEVELOPMENT_WORKER_CONTAINER,
        "type": "development",
        "status": status,
        "online": True,
        "ready": status == "Ready",
        "capabilities": list(DEVELOPMENT_WORKER_CAPABILITIES),
        "tools": tools,
        "current_task": bootstrap_status.get("current_task") or None,
        "last_heartbeat": bootstrap_status.get("last_heartbeat") or bootstrap_status.get("updated_utc") or None,
        "status_message": status_message,
    }


def get_status() -> Dict[str, Any]:
    development_worker = get_development_worker_status()
    return {
        "ok": True,
        "workers": [development_worker],
        "development_worker": development_worker,
    }