import os
import subprocess
import time
from datetime import datetime

import docker


DEFAULT_WEB_URL = "http://192.168.50.10:32400/web"


def _format_uptime(seconds: float) -> str:
    seconds = max(0, int(seconds))
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60

    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def get_container_name() -> str:
    return os.getenv("PLEX_CONTAINER_NAME", "plex")


def get_web_url() -> str:
    return os.getenv("PLEX_WEB_URL", DEFAULT_WEB_URL)


def get_container(container_name: str | None = None):
    try:
        client_docker = docker.from_env()
        return client_docker.containers.get(container_name or get_container_name())
    except Exception:
        return None


def get_container_metrics(container):
    try:
        stats = container.stats(stream=False)
        cpu_stats = stats.get("cpu_stats", {})
        precpu_stats = stats.get("precpu_stats", {})
        cpu_percentage = None

        if cpu_stats.get("cpu_usage") and precpu_stats.get("cpu_usage"):
            cpu_delta = cpu_stats["cpu_usage"]["total_usage"] - precpu_stats["cpu_usage"]["total_usage"]
            system_delta = cpu_stats.get("system_cpu_usage", 0) - precpu_stats.get("system_cpu_usage", 0)
            percpu = cpu_stats["cpu_usage"].get("percpu_usage") or []
            cpu_count = len(percpu)

            if system_delta > 0 and cpu_count > 0:
                cpu_percentage = round((cpu_delta / system_delta) * cpu_count * 100.0, 1)

        memory_stats = stats.get("memory_stats", {})
        memory_usage = memory_stats.get("usage")
        memory_limit = memory_stats.get("limit")
        memory_percent = None

        if memory_usage is not None and memory_limit:
            memory_percent = round((memory_usage / memory_limit) * 100.0, 1)

        return {
            "cpu_usage": cpu_percentage,
            "ram_usage": memory_percent,
            "ram_usage_bytes": memory_usage,
            "ram_limit_bytes": memory_limit,
        }
    except Exception:
        return {}


def get_container_uptime(container):
    if not container:
        return None

    started_at = container.attrs.get("State", {}).get("StartedAt")
    if not started_at:
        return None

    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        return _format_uptime(time.time() - started.timestamp())
    except Exception:
        return None


def _container_state(container):
    if not container:
        return "missing"

    try:
        container.reload()
        return container.status
    except Exception:
        return getattr(container, "status", "unknown")


def get_status():
    container = get_container()
    container_state = _container_state(container)
    running = container_state == "running"
    metrics = get_container_metrics(container) if container and running else {}
    uptime = get_container_uptime(container) if container and running else None

    return {
        "ok": True,
        "running": running,
        "online": running,
        "state": "Running" if running else "Offline",
        "container_state": container_state,
        "container_name": get_container_name(),
        "uptime": uptime or "unknown",
        "cpu_usage": metrics.get("cpu_usage"),
        "ram_usage": metrics.get("ram_usage"),
        "ram_usage_bytes": metrics.get("ram_usage_bytes"),
        "ram_limit_bytes": metrics.get("ram_limit_bytes"),
        "web_url": get_web_url(),
    }


def is_important_log(line: str) -> bool:
    lowered = line.lower()
    return any(token in lowered for token in ["error", "warn", "exception", "fatal", "critical", "failed"])


def is_routine_log(line: str) -> bool:
    if is_important_log(line):
        return False

    lowered = line.strip().lower()
    routine_fragments = [
        "starting container with version",
        "user uid:",
        "user gid:",
        "umask:",
        "setting permissions",
        "no update required",
        "services are up",
        "tailing file",
    ]
    return any(fragment in lowered for fragment in routine_fragments)


def get_logs(tail: int = 160):
    container = get_container()
    if not container:
        return {"ok": False, "error": "Plex container not found.", "stdout": []}

    try:
        raw = container.logs(tail=max(1, min(int(tail), 1000)), stdout=True, stderr=True)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")

        lines = [line for line in raw.splitlines() if line.strip() and not is_routine_log(line)]
        return {"ok": True, "stdout": lines}
    except Exception as e:
        return {"ok": False, "error": str(e), "stdout": []}


def container_action(action: str):
    if action not in {"start", "stop", "restart"}:
        return {"ok": False, "error": "Unsupported Plex container action."}

    try:
        result = subprocess.run(
            ["docker", action, get_container_name()],
            capture_output=True,
            text=True,
            timeout=45,
        )

        return {
            "ok": result.returncode == 0,
            "action": action,
            "container_name": get_container_name(),
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except Exception as e:
        return {"ok": False, "action": action, "error": str(e)}
