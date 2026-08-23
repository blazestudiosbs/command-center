#!/usr/bin/env python3
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(os.getenv("COMMAND_CENTER_ROOT", "/opt/command-center"))
CONFIG = ROOT / "config"
DATABASE = CONFIG / "vera.db"
STATUS_FILE = CONFIG / "infrastructure-agent-status.json"


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def enabled(column):
    try:
        with sqlite3.connect(DATABASE) as conn:
            row = conn.execute(f"SELECT {column} FROM infrastructure_agent_settings WHERE id = 'global'").fetchone()
        return bool(row and row[0])
    except sqlite3.Error:
        return False


def command(args, timeout=900):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    return {"returncode": result.returncode, "output": (result.stdout + result.stderr)[-12000:]}


def load_status():
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save(section, payload):
    CONFIG.mkdir(parents=True, exist_ok=True)
    status = load_status()
    status[section] = payload
    temporary = STATUS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(status, indent=2), encoding="utf-8")
    os.replace(temporary, STATUS_FILE)


def health():
    if not enabled("health_checks_enabled"):
        save("health", {"status": "disabled", "checked_utc": now(), "issues": []})
        return 0
    issues = []
    disk = shutil.disk_usage("/")
    disk_percent = round(disk.used * 100 / disk.total, 1)
    if disk_percent >= 85:
        issues.append({"severity": "critical" if disk_percent >= 95 else "warning", "kind": "disk", "detail": f"Root disk is {disk_percent}% full."})
    memory = {}
    try:
        values = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            values[key] = int(value.strip().split()[0])
        memory_percent = round((1 - values["MemAvailable"] / values["MemTotal"]) * 100, 1)
        memory = {"used_percent": memory_percent}
        if memory_percent >= 90:
            issues.append({"severity": "warning", "kind": "memory", "detail": f"Memory use is {memory_percent}%."})
    except (OSError, KeyError, ValueError):
        issues.append({"severity": "warning", "kind": "memory", "detail": "Memory status could not be read."})
    failed = command(["systemctl", "--failed", "--no-legend", "--plain"], 30)
    failed_units = [line.strip() for line in failed["output"].splitlines() if line.strip()]
    for unit in failed_units[:20]:
        issues.append({"severity": "critical", "kind": "systemd", "detail": unit[:500]})
    docker = command(["docker", "ps", "-a", "--format", "{{.Names}}|{{.Status}}"], 30)
    containers = []
    if docker["returncode"] == 0:
        for line in docker["output"].splitlines():
            name, _, state = line.partition("|")
            containers.append({"name": name, "status": state})
            if state and not state.startswith("Up") and name != "hello-world":
                issues.append({"severity": "critical", "kind": "container", "detail": f"{name}: {state}"})
    else:
        issues.append({"severity": "critical", "kind": "docker", "detail": "Docker status could not be read."})
    journal = command(["journalctl", "-p", "err", "--since", "15 minutes ago", "--no-pager", "-n", "50"], 30)
    error_lines = [line for line in journal["output"].splitlines() if line and not line.startswith("-- No entries")]
    if error_lines:
        issues.append({"severity": "warning", "kind": "system_log", "detail": f"{len(error_lines)} system error log entries appeared in the last 15 minutes."})
    save("health", {
        "status": "issues_found" if issues else "healthy", "checked_utc": now(), "issues": issues,
        "metrics": {"disk_used_percent": disk_percent, **memory}, "containers": containers,
        "recent_error_count": len(error_lines), "recent_errors": error_lines[-10:],
    })
    return 0


def security_update():
    started = now()
    if not enabled("security_updates_enabled"):
        save("updates", {"status": "disabled", "started_utc": started, "completed_utc": now(), "reboot_performed": False})
        return 0
    if not shutil.which("unattended-upgrade"):
        save("updates", {"status": "failed", "started_utc": started, "completed_utc": now(), "detail": "unattended-upgrade is not installed.", "reboot_performed": False})
        return 1
    result = command(["unattended-upgrade", "--verbose"], 3600)
    reboot_required = Path("/var/run/reboot-required").exists()
    status = "completed" if result["returncode"] == 0 else "failed"
    save("updates", {
        "status": status, "started_utc": started, "completed_utc": now(),
        "detail": result["output"], "reboot_required": reboot_required,
        "reboot_performed": False, "scope": "Ubuntu security updates only",
    })
    health()
    return result["returncode"]


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "health"
    raise SystemExit(security_update() if action == "security-update" else health())
