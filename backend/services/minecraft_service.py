import os
import re
import socket
import struct
import subprocess
import time
from datetime import datetime

import docker

def _packet(request_id: int, packet_type: int, body: str) -> bytes:
    body_bytes = body.encode("utf-8")
    length = len(body_bytes) + 10
    return struct.pack("<iii", length, request_id, packet_type) + body_bytes + b"\x00\x00"


def _read_packet(sock):
    raw_len = sock.recv(4)
    if len(raw_len) < 4:
        raise RuntimeError("No RCON response length received.")

    length = struct.unpack("<i", raw_len)[0]
    data = b""

    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            break
        data += chunk

    request_id, packet_type = struct.unpack("<ii", data[:8])
    body = data[8:-2].decode("utf-8", errors="replace")
    return request_id, packet_type, body


def rcon(command: str):
    host = os.getenv("MINECRAFT_RCON_HOST", "127.0.0.1")
    port = int(os.getenv("MINECRAFT_RCON_PORT", "25575"))
    password = os.getenv("MINECRAFT_RCON_PASSWORD")

    if not password:
        return {"ok": False, "command": command, "error": "MINECRAFT_RCON_PASSWORD is not configured."}

    try:
        with socket.create_connection((host, port), timeout=10) as sock:
            sock.sendall(_packet(1, 3, password))
            auth_id, _, _ = _read_packet(sock)

            if auth_id == -1:
                return {"ok": False, "command": command, "error": "RCON authentication failed."}

            sock.sendall(_packet(2, 2, command))
            _, _, response = _read_packet(sock)

        return {"ok": True, "command": command, "response": response}
    except Exception as e:
        return {"ok": False, "command": command, "error": str(e)}


def parse_players(list_response: str):
    if ":" not in list_response:
        return []

    after_colon = list_response.split(":", 1)[1].strip()
    if not after_colon:
        return []

    return [p.strip() for p in after_colon.split(",") if p.strip()]


def parse_player_capacity(list_response: str):
    match = re.search(r"There are\s+(\d+)\s+of\s+a\s+max\s+of\s+(\d+)\s+players", list_response)
    if not match:
        return None, None

    return int(match.group(1)), int(match.group(2))


def _normalize_command(command_text: str) -> str:
    return command_text.strip().lstrip("/")


def _validate_player(player: str):
    player = (player or "").strip()
    if not player:
        return None, {"ok": False, "error": "Player cannot be empty."}

    if not re.fullmatch(r"[A-Za-z0-9_]{1,16}", player):
        return None, {"ok": False, "error": "Player must be a valid Minecraft username."}

    return player, None


def _format_uptime(seconds: float) -> str:
    seconds = int(seconds)
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60

    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def get_container(container_name: str = "minecraft-atm10"):
    try:
        client_docker = docker.from_env()
        return client_docker.containers.get(container_name)
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
            "cpu_percent": cpu_percentage,
            "memory_usage_percent": memory_percent,
            "memory_usage_bytes": memory_usage,
            "memory_limit_bytes": memory_limit,
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


def is_routine_rcon_log(line: str) -> bool:
    lowered = line.lower()
    return (
        "rcon client" in lowered and ("started" in lowered or "shutting down" in lowered)
    ) or "rcon listener" in lowered or "rcon running" in lowered


def _decode_logs(raw) -> str:
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace")
    if raw is None:
        return ""
    return str(raw)


def _filtered_log_lines(raw):
    output = _decode_logs(raw)
    return [line for line in output.splitlines() if not is_routine_rcon_log(line)]


def get_logs(tail: int = 120):
    container = get_container()
    if not container:
        return {"ok": False, "error": "Minecraft container not found.", "stdout": []}

    try:
        raw = container.logs(tail=tail, stdout=True, stderr=True)
        return {"ok": True, "stdout": _filtered_log_lines(raw)}
    except Exception as e:
        return {"ok": False, "error": str(e), "stdout": []}


def get_recent_logs_for_analysis():
    container = get_container("minecraft-atm10")
    if not container:
        return {"ok": False, "error": "Minecraft container not found.", "stdout": [], "source": "docker_sdk_since_24h"}

    log_requests = [
        ("docker_sdk_since_24h", {"since": int(time.time() - 24 * 60 * 60)}),
        ("docker_sdk_tail_3000", {"tail": 3000}),
    ]
    analysis_error = None

    for index, (source, log_options) in enumerate(log_requests):
        try:
            raw = container.logs(
                stdout=True,
                stderr=True,
                **log_options,
            )
            output = _decode_logs(raw)
            if index == 0 and len(output) > 2_000_000:
                analysis_error = "docker_sdk_since_24h output exceeded analysis limit."
                continue

            lines = _filtered_log_lines(output)
            if index == 0 and not _has_analysis_events(lines):
                analysis_error = "docker_sdk_since_24h returned no analysis events; fell back to docker_sdk_tail_3000."
                continue

            return {
                "ok": True,
                "stdout": lines,
                "source": source,
                "error": analysis_error if source != "docker_sdk_since_24h" else None,
            }
        except Exception as e:
            analysis_error = str(e)
            if index == len(log_requests) - 1:
                return {"ok": False, "error": analysis_error, "stdout": [], "source": source}

    return {"ok": False, "error": analysis_error or "Unable to read Minecraft logs.", "stdout": [], "source": "docker_sdk_tail_3000"}


def _has_analysis_events(lines):
    for line in lines or []:
        lowered = line.lower()
        if "can't keep up" in lowered or "server overloaded" in lowered or "lost connection" in lowered:
            return True
        if re.search(r"running\s+([0-9,]+)ms\s+or\s+([0-9,]+)\s+ticks\s+behind", line, re.IGNORECASE):
            return True

    return False


def _parse_log_timestamp(line: str):
    iso_match = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?", line)
    if iso_match:
        return iso_match.group(0)

    minecraft_match = re.search(r"\[(\d{1,2}[A-Za-z]{3}\d{4}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\]", line)
    if minecraft_match:
        return minecraft_match.group(1)

    return None


def analyze_logs(lines):
    analysis = {
        "analysis_window": "24h",
        "keep_up_warning_count": 0,
        "max_ticks_behind": 0,
        "max_ms_behind": 0,
        "disconnect_count": 0,
        "timeout_count": 0,
        "oom_detected": False,
        "watchdog_detected": False,
        "disconnect_near_keep_up": False,
        "last_keep_up_at": None,
        "last_disconnect_at": None,
    }
    keep_up_indexes = []
    disconnect_indexes = []

    for index, line in enumerate(lines or []):
        lowered = line.lower()
        keep_up = "can't keep up" in lowered or "server overloaded" in lowered
        if keep_up:
            analysis["keep_up_warning_count"] += 1
            keep_up_indexes.append(index)
            analysis["last_keep_up_at"] = _parse_log_timestamp(line) or analysis["last_keep_up_at"]

        behind_match = re.search(r"running\s+([0-9,]+)ms\s+or\s+([0-9,]+)\s+ticks\s+behind", line, re.IGNORECASE)
        if behind_match:
            ms_behind = int(behind_match.group(1).replace(",", ""))
            ticks_behind = int(behind_match.group(2).replace(",", ""))
            analysis["max_ms_behind"] = max(analysis["max_ms_behind"], ms_behind)
            analysis["max_ticks_behind"] = max(analysis["max_ticks_behind"], ticks_behind)
            if not keep_up:
                analysis["keep_up_warning_count"] += 1
                keep_up_indexes.append(index)
                analysis["last_keep_up_at"] = _parse_log_timestamp(line) or analysis["last_keep_up_at"]

        if "lost connection" in lowered:
            analysis["disconnect_count"] += 1
            disconnect_indexes.append(index)
            analysis["last_disconnect_at"] = _parse_log_timestamp(line) or analysis["last_disconnect_at"]

        if "timed out" in lowered:
            analysis["timeout_count"] += 1
            disconnect_indexes.append(index)
            analysis["last_disconnect_at"] = _parse_log_timestamp(line) or analysis["last_disconnect_at"]

        if "outofmemoryerror" in lowered or "killed process" in lowered:
            analysis["oom_detected"] = True

        if "server watchdog" in lowered:
            analysis["watchdog_detected"] = True

    analysis["disconnect_near_keep_up"] = any(
        abs(disconnect_index - keep_up_index) <= 20
        for disconnect_index in disconnect_indexes
        for keep_up_index in keep_up_indexes
    )
    return analysis


def get_status():
    list_result = rcon("list")
    container = get_container()
    container_status = "missing"
    if container:
        try:
            container.reload()
            container_status = container.status
        except Exception:
            container_status = getattr(container, "status", "unknown")

    container_running = container_status == "running"
    metrics = get_container_metrics(container) if container else {}
    uptime = get_container_uptime(container)
    logs = get_recent_logs_for_analysis()
    minecraft_analysis = analyze_logs(logs.get("stdout", []))
    minecraft_analysis["analysis_log_line_count"] = len(logs.get("stdout", []))
    minecraft_analysis["analysis_source"] = logs.get("source")
    minecraft_analysis["analysis_error"] = logs.get("error")
    server_type = "ATM10 / NeoForge"

    if not list_result.get("ok"):
        return {
            "online": False,
            "running": container_running,
            "state": "Running" if container_running else "Offline",
            "container_status": container_status,
            "rcon_online": False,
            "server_name": "ATM10",
            "players": [],
            "player_count": 0,
            "max_players": None,
            "server_type": server_type,
            "version": server_type,
            "raw": list_result,
            "tps": None,
            "mspt": None,
            "ram_usage": metrics.get("memory_usage_percent"),
            "ram_usage_bytes": metrics.get("memory_usage_bytes"),
            "ram_limit_bytes": metrics.get("memory_limit_bytes"),
            "cpu_usage": metrics.get("cpu_percent"),
            "uptime": uptime or "unknown",
            "minecraft_analysis": minecraft_analysis,
        }

    list_response = list_result.get("response", "")
    players = parse_players(list_response)
    parsed_count, max_players = parse_player_capacity(list_response)

    return {
        "online": True,
        "running": container_running,
        "state": "Running",
        "container_status": container_status,
        "rcon_online": True,
        "server_name": "ATM10",
        "players": players,
        "player_count": parsed_count if parsed_count is not None else len(players),
        "max_players": max_players,
        "server_type": server_type,
        "version": server_type,
        "raw": list_result,
        "tps": None,
        "mspt": None,
        "ram_usage": metrics.get("memory_usage_percent"),
        "ram_usage_bytes": metrics.get("memory_usage_bytes"),
        "ram_limit_bytes": metrics.get("memory_limit_bytes"),
        "cpu_usage": metrics.get("cpu_percent"),
        "uptime": uptime or "unknown",
        "minecraft_analysis": minecraft_analysis,
    }


def command(command_text: str):
    command_text = _normalize_command(command_text)
    if not command_text:
        return {"ok": False, "error": "Command cannot be empty."}

    return rcon(command_text)


def save_world():
    return rcon("save-all")


def op_player(player: str):
    player, error = _validate_player(player)
    if error:
        return error

    return rcon(f"op {player}")


def deop_player(player: str):
    player, error = _validate_player(player)
    if error:
        return error

    return rcon(f"deop {player}")


def kick_player(player: str):
    player, error = _validate_player(player)
    if error:
        return error

    return rcon(f"kick {player}")


def ban_player(player: str):
    player, error = _validate_player(player)
    if error:
        return error

    return rcon(f"ban {player}")


def say(message: str):
    message = (message or "").strip()
    if not message:
        return {"ok": False, "error": "Broadcast message cannot be empty."}

    return rcon(f"say {message}")

def container_action(action: str):
    allowed = {
        "start": ["docker", "start", "minecraft-atm10"],
        "stop": ["docker", "stop", "minecraft-atm10"],
        "restart": ["docker", "restart", "minecraft-atm10"],
    }

    if action not in allowed:
        return {"ok": False, "error": "Unsupported container action."}

    try:
        result = subprocess.run(
            allowed[action],
            capture_output=True,
            text=True,
            timeout=30,
        )

        return {
            "ok": result.returncode == 0,
            "action": action,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except Exception as e:
        return {"ok": False, "action": action, "error": str(e)}
