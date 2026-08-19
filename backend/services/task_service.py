import json
import os
import re
import shlex
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import docker

from services import audit_service, policy_service


PRIORITIES = {"low", "medium", "high"}
STATUSES = {"Queued", "Planning", "Reading", "Editing", "Building", "Testing", "Running", "Review", "Completed", "Failed"}
EXECUTION_STAGES = {"Queued", "Planning", "Reading", "Editing", "Building", "Testing", "Review", "Completed", "Failed"}
ACTIVE_EXECUTION_STAGES = {"Planning", "Reading", "Editing", "Building", "Testing"}
EXECUTION_MODES = {"read_only", "safe_edit", "full_agent"}
EVENT_TYPES = {"command_started", "command_output", "command_finished", "diff_preview", "stage_changed", "phase_started", "phase_completed", "phase_failed", "error"}
DEFAULT_PHASE_NAMES = ["Inspect", "Plan", "Implement", "Validate", "Report"]
PHASE_STATUSES = {"Pending", "Running", "Completed", "Failed", "Skipped"}
DEFAULT_VALIDATION_COMMANDS = [
    "python3 -m py_compile backend/app.py",
    "cd frontend-react && npm run build",
]
ALLOWLISTED_COMMANDS = {
    "backend_compile": "python3 -m py_compile backend/app.py backend/services/task_service.py",
    "frontend_build": "cd frontend-react && npm run build",
    "clear_frontend": "rm -rf frontend/*",
    "copy_frontend_dist": "cp -r frontend-react/dist/* frontend/",
    "docker_compose_build": "docker compose up -d --build",
    "git_diff_stat": "git diff --stat",
    "git_status_short": "git status --short",
}
VALIDATION_COMMAND_KEYS = ["backend_compile", "frontend_build"]
REBUILD_COMMAND_KEYS = ["clear_frontend", "copy_frontend_dist", "docker_compose_build"]
DEVELOPMENT_WORKER_CONTAINER = os.getenv("DEVELOPMENT_WORKER_CONTAINER", "development-worker")
DEVELOPMENT_WORKER_WORKDIR = os.getenv("DEVELOPMENT_WORKER_WORKDIR", "/workspace/command-center")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCAL_STORE = REPOSITORY_ROOT / "config" / "tasks.json"
DEFAULT_CONTAINER_STORE = Path("/app/config/tasks.json")
DEFAULT_LOCAL_RUN_DIR = REPOSITORY_ROOT / "config" / "task_runs"
DEFAULT_CONTAINER_RUN_DIR = Path("/app/config/task_runs")


def _store_path() -> Path:
    configured = os.getenv("TASK_STORE_PATH")
    if configured:
        return Path(configured)
    if DEFAULT_CONTAINER_STORE.parent.exists():
        return DEFAULT_CONTAINER_STORE
    return DEFAULT_LOCAL_STORE


def _run_dir() -> Path:
    configured = os.getenv("TASK_RUN_DIR")
    if configured:
        return Path(configured)
    if DEFAULT_CONTAINER_RUN_DIR.parent.exists():
        return DEFAULT_CONTAINER_RUN_DIR
    return DEFAULT_LOCAL_RUN_DIR


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _empty_store() -> Dict[str, List[Dict[str, Any]]]:
    return {"tasks": []}


def _read_store() -> Dict[str, List[Dict[str, Any]]]:
    path = _store_path()
    if not path.exists():
        return _empty_store()

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return _empty_store()

    tasks = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(tasks, list):
        return _empty_store()

    return {"tasks": [task for task in tasks if isinstance(task, dict)]}


def _write_store(store: Dict[str, List[Dict[str, Any]]]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)
        f.write("\n")
    temp_path.replace(path)


def _log_path(task_id: str) -> Path:
    return _run_dir() / f"{task_id}.log"


def _event_path(task_id: str) -> Path:
    return _run_dir() / f"{task_id}.events.jsonl"


def _command_cwd(cwd: str) -> str:
    return cwd or DEVELOPMENT_WORKER_WORKDIR


def _redact_secrets(value: str) -> str:
    redacted = re.sub(
        r"(?i)(api[_-]?key|token|password|passwd|secret)(\s*[=:]\s*)\S+",
        r"\1\2[REDACTED]",
        value,
    )
    for key, secret in os.environ.items():
        if not secret or len(secret) < 8:
            continue
        if any(marker in key.upper() for marker in ["KEY", "TOKEN", "PASSWORD", "SECRET"]):
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def _resolve_command(command: str) -> tuple[str, str]:
    cleaned = str(command or "").strip()
    if cleaned in ALLOWLISTED_COMMANDS:
        return cleaned, ALLOWLISTED_COMMANDS[cleaned]
    for key, allowlisted_command in ALLOWLISTED_COMMANDS.items():
        if cleaned == allowlisted_command:
            return key, allowlisted_command
    raise ValueError("Command is not allowlisted.")


def _worker_shell_command(command: str, working_dir: str) -> str:
    prefix = f"cd {shlex.quote(working_dir)}"
    stripped = command.strip()
    if stripped.startswith(prefix):
        return stripped
    return f"{prefix} && {stripped}"


def _quiet_success_message(command_key: str) -> Optional[str]:
    if command_key == "backend_compile":
        return "Backend compile passed"
    if command_key == "git_diff_stat":
        return "Git diff stat completed"
    if command_key in {"clear_frontend", "copy_frontend_dist", "docker_compose_build"}:
        return "Rebuild command completed"
    return None


def _get_development_worker():
    try:
        client = docker.from_env()
        container = client.containers.get(DEVELOPMENT_WORKER_CONTAINER)
        container.reload()
        if container.status != "running":
            raise RuntimeError("development-worker is not running.")
        return client, container
    except Exception as e:
        raise RuntimeError(f"development-worker unavailable: {e}")


def _append_task_log(task_id: str, message: str) -> None:
    log_dir = _run_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    with _log_path(task_id).open("a", encoding="utf-8") as f:
        f.write(f"[{_utc_now()}] {message}\n")


def append_task_log(task_id: str, message: str) -> Optional[Dict[str, Any]]:
    task = get_task(task_id)
    if not task:
        return None

    cleaned_message = str(message or "").strip()
    if not cleaned_message:
        raise ValueError("Log message is required.")

    _append_task_log(task_id, cleaned_message)
    return task


def append_task_event(task_id: str, event_type: str, message: str, data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    task = get_task(task_id)
    if not task:
        return None

    normalized_type = str(event_type or "").strip()
    if normalized_type not in EVENT_TYPES:
        raise ValueError("Event type is not supported.")

    event = {
        "utc": _utc_now(),
        "type": normalized_type,
        "message": _redact_secrets(str(message or "").strip()),
        "data": data if isinstance(data, dict) else {},
    }
    event["data"] = json.loads(json.dumps(event["data"], default=str))

    event_path = _event_path(task_id)
    event_path.parent.mkdir(parents=True, exist_ok=True)
    with event_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
    return task


def get_task_events(task_id: str) -> Optional[List[Dict[str, Any]]]:
    if not get_task(task_id):
        return None

    event_path = _event_path(task_id)
    if not event_path.exists():
        return []

    events = []
    with event_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def run_task_command(task_id: str, command: str, cwd: str = "/opt/command-center", actor_user_id: str = "owner") -> Optional[Dict[str, Any]]:
    if not get_task(task_id):
        return None

    command_key, allowlisted_command = _resolve_command(command)
    try:
        decision = policy_service.require(
            user_id=actor_user_id,
            domain="development",
            capability="agent_execute",
        )
    except policy_service.PolicyDeniedError as exc:
        audit_service.append_event(
            actor_user_id=actor_user_id,
            action="development.command",
            resource_type="task",
            resource_id=task_id,
            outcome="denied",
            details={"command_key": command_key, "reason": exc.decision.reason},
        )
        raise
    audit_service.append_event(
        actor_user_id=actor_user_id,
        action="development.command",
        resource_type="task",
        resource_id=task_id,
        outcome="allowed",
        details={
            "command_key": command_key,
            "permission_id": decision.permission_id,
            "control_mode": decision.mode,
        },
    )
    working_dir = _command_cwd(DEVELOPMENT_WORKER_WORKDIR)
    append_task_event(
        task_id,
        "command_started",
        f"Started: {allowlisted_command}",
        {"command_key": command_key, "command": allowlisted_command, "cwd": working_dir, "worker": DEVELOPMENT_WORKER_CONTAINER},
    )

    output_lines = []
    try:
        client, container = _get_development_worker()
        shell_command = _worker_shell_command(allowlisted_command, working_dir)
        exec_id = client.api.exec_create(
            container.id,
            cmd=["/bin/sh", "-lc", shell_command],
            workdir=working_dir,
            stdout=True,
            stderr=True,
        )["Id"]
        output_buffer = ""
        for chunk in client.api.exec_start(exec_id, stream=True):
            if not chunk:
                continue
            output_buffer += chunk.decode("utf-8", errors="replace")
            while "\n" in output_buffer:
                line, output_buffer = output_buffer.split("\n", 1)
                cleaned_line = _redact_secrets(line.rstrip())
                if cleaned_line:
                    output_lines.append(cleaned_line)
                    append_task_event(task_id, "command_output", cleaned_line, {"command_key": command_key})
        if output_buffer.strip():
            cleaned_line = _redact_secrets(output_buffer.strip())
            output_lines.append(cleaned_line)
            append_task_event(task_id, "command_output", cleaned_line, {"command_key": command_key})

        exit_code = client.api.exec_inspect(exec_id).get("ExitCode")
        success_message = _quiet_success_message(command_key)
        if exit_code == 0 and success_message and len(output_lines) <= 1:
            output_lines.append(success_message)
            append_task_event(task_id, "command_output", success_message, {"command_key": command_key})
        append_task_event(
            task_id,
            "command_finished",
            f"Finished: {allowlisted_command} (exit {exit_code})",
            {"command_key": command_key, "command": allowlisted_command, "exit_code": exit_code, "worker": DEVELOPMENT_WORKER_CONTAINER},
        )
        if exit_code != 0:
            append_task_event(
                task_id,
                "error",
                f"Command {allowlisted_command} failed with exit code {exit_code}",
                {"command_key": command_key, "command": allowlisted_command, "exit_code": exit_code, "worker": DEVELOPMENT_WORKER_CONTAINER},
            )
        if command_key == "git_diff_stat":
            append_task_event(
                task_id,
                "diff_preview",
                "Git diff stat updated.",
                {"command_key": command_key, "stat": "\n".join(output_lines).strip()},
            )
        audit_service.append_event(
            actor_user_id=actor_user_id,
            action="development.command",
            resource_type="task",
            resource_id=task_id,
            outcome="succeeded" if exit_code == 0 else "failed",
            details={"command_key": command_key, "exit_code": exit_code},
        )
        return {"command_key": command_key, "command": allowlisted_command, "exit_code": exit_code, "worker": DEVELOPMENT_WORKER_CONTAINER}
    except Exception as e:
        message = _redact_secrets(str(e))
        append_task_event(task_id, "error", message, {"command_key": command_key, "command": allowlisted_command, "worker": DEVELOPMENT_WORKER_CONTAINER})
        if not isinstance(e, policy_service.PolicyDeniedError):
            audit_service.append_event(
                actor_user_id=actor_user_id,
                action="development.command",
                resource_type="task",
                resource_id=task_id,
                outcome="failed",
                details={"command_key": command_key, "error": message},
            )
        raise


def get_task_logs(task_id: str) -> Optional[str]:
    if not get_task(task_id):
        return None

    path = _log_path(task_id)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _normalize_constraints(value: Optional[List[str]]) -> List[str]:
    if not value:
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_string_list(value: Optional[List[str]]) -> List[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.splitlines() if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def _validate_execution_mode(mode: Optional[str]) -> str:
    normalized = (mode or "safe_edit").strip()
    if normalized not in EXECUTION_MODES:
        raise ValueError("Execution mode must be read_only, safe_edit, or full_agent.")
    return normalized


def _validate_execution_stage(stage: Optional[str], fallback: str = "Queued") -> str:
    normalized = (stage or fallback).strip()
    if normalized not in EXECUTION_STAGES:
        raise ValueError("Execution stage must be Queued, Planning, Reading, Editing, Building, Testing, Review, Completed, or Failed.")
    return normalized


def _default_phase(name: str) -> Dict[str, Any]:
    return {
        "name": name,
        "status": "Pending",
        "started_utc": None,
        "completed_utc": None,
        "summary": None,
    }


def _normalize_phase(value: Any, fallback_name: str) -> Dict[str, Any]:
    phase = value if isinstance(value, dict) else {}
    name = str(phase.get("name") or fallback_name).strip() or fallback_name
    status = str(phase.get("status") or "Pending").strip()
    if status not in PHASE_STATUSES:
        status = "Pending"
    summary = phase.get("summary")
    return {
        "name": name,
        "status": status,
        "started_utc": phase.get("started_utc") or None,
        "completed_utc": phase.get("completed_utc") or None,
        "summary": str(summary).strip() if summary else None,
    }


def _normalize_phases(value: Any) -> List[Dict[str, Any]]:
    supplied = value if isinstance(value, list) else []
    by_name = {}
    for phase in supplied:
        if isinstance(phase, dict):
            name = str(phase.get("name") or "").strip()
            if name:
                by_name[name.lower()] = phase
    return [_normalize_phase(by_name.get(name.lower()), name) for name in DEFAULT_PHASE_NAMES]


def _phase_index(task: Dict[str, Any], phase_name: str) -> int:
    normalized_name = str(phase_name or "").strip().lower()
    for index, phase in enumerate(task.get("phases", [])):
        if str(phase.get("name") or "").strip().lower() == normalized_name:
            return index
    raise ValueError("Phase not found.")


def _default_execution_stage(task: Dict[str, Any]) -> str:
    status = str(task.get("status") or "Queued").strip()
    if status in EXECUTION_STAGES:
        return status
    if status == "Running":
        return "Planning"
    return "Queued"


def _normalize_task(task: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(task)
    try:
        normalized["execution_mode"] = _validate_execution_mode(normalized.get("execution_mode"))
    except ValueError:
        normalized["execution_mode"] = "safe_edit"
    normalized["allowed_paths"] = _normalize_string_list(normalized.get("allowed_paths"))
    validation_commands = normalized.get("validation_commands")
    normalized["validation_commands"] = (
        _normalize_string_list(validation_commands)
        if validation_commands is not None
        else list(DEFAULT_VALIDATION_COMMANDS)
    )
    normalized["requires_manual_approval"] = bool(normalized.get("requires_manual_approval", False))
    try:
        normalized["execution_stage"] = _validate_execution_stage(
            normalized.get("execution_stage"),
            _default_execution_stage(normalized),
        )
    except ValueError:
        normalized["execution_stage"] = _default_execution_stage(normalized)
    normalized["phases"] = _normalize_phases(normalized.get("phases"))
    return normalized


def _validate_priority(priority: Optional[str]) -> str:
    normalized = (priority or "medium").strip().lower()
    if normalized not in PRIORITIES:
        raise ValueError("Priority must be low, medium, or high.")
    return normalized


def _validate_status(status: Optional[str], fallback: str = "Queued") -> str:
    normalized = (status or fallback).strip()
    if normalized not in STATUSES:
        raise ValueError("Status must be Queued, Planning, Reading, Editing, Building, Testing, Running, Review, Completed, or Failed.")
    return normalized


def list_tasks() -> List[Dict[str, Any]]:
    return [_normalize_task(task) for task in _read_store()["tasks"]]


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    return next((task for task in list_tasks() if task.get("id") == task_id), None)


def create_task(data: Dict[str, Any]) -> Dict[str, Any]:
    now = _utc_now()
    title = str(data.get("title") or "").strip()
    goal = str(data.get("goal") or "").strip()

    if not title:
        raise ValueError("Title is required.")
    if not goal:
        raise ValueError("Goal is required.")

    task = {
        "id": str(uuid.uuid4()),
        "project": str(data.get("project") or "Command Center").strip() or "Command Center",
        "workspace": str(data.get("workspace") or "Development").strip() or "Development",
        "title": title,
        "goal": goal,
        "constraints": _normalize_constraints(data.get("constraints")),
        "execution_mode": _validate_execution_mode(data.get("execution_mode")),
        "allowed_paths": _normalize_string_list(data.get("allowed_paths")),
        "validation_commands": (
            _normalize_string_list(data.get("validation_commands"))
            if data.get("validation_commands") is not None
            else list(DEFAULT_VALIDATION_COMMANDS)
        ),
        "requires_manual_approval": bool(data.get("requires_manual_approval", False)),
        "priority": _validate_priority(data.get("priority")),
        "status": _validate_status(data.get("status"), "Queued"),
        "execution_stage": _validate_execution_stage(data.get("execution_stage"), "Queued"),
        "phases": _normalize_phases(data.get("phases")),
        "created_utc": now,
        "started_utc": None,
        "completed_utc": None,
        "result_summary": None,
    }

    store = _read_store()
    store["tasks"].insert(0, task)
    _write_store(store)
    return task


def update_task(task_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    store = _read_store()
    now = _utc_now()

    for task in store["tasks"]:
        if task.get("id") != task_id:
            continue

        task.update(_normalize_task(task))

        for key in ["project", "workspace", "title", "goal"]:
            if key in data and data[key] is not None:
                value = str(data[key]).strip()
                if key in {"title", "goal"} and not value:
                    raise ValueError(f"{key.replace('_', ' ').title()} is required.")
                task[key] = value

        if "constraints" in data and data["constraints"] is not None:
            task["constraints"] = _normalize_constraints(data["constraints"])

        if "execution_mode" in data and data["execution_mode"] is not None:
            task["execution_mode"] = _validate_execution_mode(data["execution_mode"])

        if "allowed_paths" in data and data["allowed_paths"] is not None:
            task["allowed_paths"] = _normalize_string_list(data["allowed_paths"])

        if "validation_commands" in data and data["validation_commands"] is not None:
            task["validation_commands"] = _normalize_string_list(data["validation_commands"])

        if "requires_manual_approval" in data and data["requires_manual_approval"] is not None:
            task["requires_manual_approval"] = bool(data["requires_manual_approval"])

        if "execution_stage" in data and data["execution_stage"] is not None:
            task["execution_stage"] = _validate_execution_stage(data["execution_stage"], task.get("execution_stage", "Queued"))

        if "priority" in data and data["priority"] is not None:
            task["priority"] = _validate_priority(data["priority"])

        if "status" in data and data["status"] is not None:
            next_status = _validate_status(data["status"], task.get("status", "Queued"))
            previous_status = task.get("status")
            task["status"] = next_status
            if next_status in EXECUTION_STAGES:
                task["execution_stage"] = next_status
            if next_status == "Running" and not task.get("started_utc"):
                task["started_utc"] = now
            if next_status in {"Completed", "Failed"} and previous_status != next_status:
                task["completed_utc"] = now
            if next_status not in {"Completed", "Failed"}:
                task["completed_utc"] = None

        if "result_summary" in data:
            summary = data["result_summary"]
            task["result_summary"] = str(summary).strip() if summary else None

        _write_store(store)
        return task

    return None


def start_task(task_id: str) -> Optional[Dict[str, Any]]:
    store = _read_store()
    now = _utc_now()

    for task in store["tasks"]:
        if task.get("id") != task_id:
            continue

        task.update(_normalize_task(task))
        task["status"] = "Running"
        task["execution_stage"] = "Planning"
        task["started_utc"] = now
        task["completed_utc"] = None
        task["result_summary"] = None
        _write_store(store)
        _append_task_log(task_id, "Task started")
        return task

    return None


def complete_task(task_id: str, result_summary: str) -> Optional[Dict[str, Any]]:
    return _finish_task(task_id, "Completed", result_summary, "Task completed")


def fail_task(task_id: str, result_summary: str) -> Optional[Dict[str, Any]]:
    return _finish_task(task_id, "Failed", result_summary, "Task failed")


def retry_task(task_id: str) -> Optional[Dict[str, Any]]:
    store = _read_store()

    for task in store["tasks"]:
        if task.get("id") != task_id:
            continue

        task.update(_normalize_task(task))
        if task.get("status") != "Failed":
            raise ValueError("Only failed tasks can be retried.")

        task["status"] = "Queued"
        task["execution_stage"] = "Queued"
        task["started_utc"] = None
        task["completed_utc"] = None
        task["result_summary"] = None
        _write_store(store)
        _append_task_log(task_id, "Task queued for retry")
        return task

    return None


def set_execution_stage(task_id: str, stage: str) -> Optional[Dict[str, Any]]:
    store = _read_store()
    normalized_stage = _validate_execution_stage(stage)
    now = _utc_now()

    for task in store["tasks"]:
        if task.get("id") != task_id:
            continue

        task.update(_normalize_task(task))
        task["execution_stage"] = normalized_stage
        if normalized_stage in ACTIVE_EXECUTION_STAGES:
            task["status"] = "Running"
            if not task.get("started_utc"):
                task["started_utc"] = now
            task["completed_utc"] = None
        elif normalized_stage in {"Queued", "Review", "Completed", "Failed"}:
            task["status"] = normalized_stage
            if normalized_stage == "Queued":
                task["started_utc"] = None
                task["completed_utc"] = None
            if normalized_stage in {"Completed", "Failed"} and not task.get("completed_utc"):
                task["completed_utc"] = now

        _write_store(store)
        _append_task_log(task_id, f"Execution stage set to {normalized_stage}")
        append_task_event(task_id, "stage_changed", f"Execution stage set to {normalized_stage}", {"execution_stage": normalized_stage})
        return task

    return None


def initialize_task_phases(task_id: str) -> Optional[Dict[str, Any]]:
    store = _read_store()

    for task in store["tasks"]:
        if task.get("id") != task_id:
            continue

        task.update(_normalize_task(task))
        task["phases"] = _normalize_phases(task.get("phases"))
        _write_store(store)
        return task

    return None


def start_task_phase(task_id: str, phase_name: str) -> Optional[Dict[str, Any]]:
    return _set_task_phase(task_id, phase_name, "Running", "phase_started", None)


def complete_task_phase(task_id: str, phase_name: str, summary: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return _set_task_phase(task_id, phase_name, "Completed", "phase_completed", summary)


def fail_task_phase(task_id: str, phase_name: str, summary: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return _set_task_phase(task_id, phase_name, "Failed", "phase_failed", summary)


def _set_task_phase(task_id: str, phase_name: str, status: str, event_type: str, summary: Optional[str]) -> Optional[Dict[str, Any]]:
    store = _read_store()
    now = _utc_now()

    for task in store["tasks"]:
        if task.get("id") != task_id:
            continue

        task.update(_normalize_task(task))
        index = _phase_index(task, phase_name)
        phase = task["phases"][index]
        phase["status"] = status
        if status == "Running":
            phase["started_utc"] = now
            phase["completed_utc"] = None
            phase["summary"] = None
        elif status in {"Completed", "Failed"}:
            if not phase.get("started_utc"):
                phase["started_utc"] = now
            phase["completed_utc"] = now
            phase["summary"] = str(summary or "").strip() or None

        _write_store(store)
        append_task_event(
            task_id,
            event_type,
            f"Phase {phase['name']} {status.lower()}.",
            {"phase": phase},
        )
        return task

    return None


def _finish_task(task_id: str, status: str, result_summary: str, log_message: str) -> Optional[Dict[str, Any]]:
    store = _read_store()
    now = _utc_now()

    for task in store["tasks"]:
        if task.get("id") != task_id:
            continue

        task.update(_normalize_task(task))
        summary = str(result_summary or "").strip()
        task["status"] = status
        task["execution_stage"] = status
        task["completed_utc"] = now
        task["result_summary"] = summary or None
        _write_store(store)
        _append_task_log(task_id, log_message)
        return task

    return None


def delete_task(task_id: str) -> bool:
    store = _read_store()
    original_count = len(store["tasks"])
    store["tasks"] = [task for task in store["tasks"] if task.get("id") != task_id]
    if len(store["tasks"]) == original_count:
        return False
    _write_store(store)
    return True
