import os
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
    ) or "rcon listener" in lowered


def get_logs(tail: int = 120):
    container = get_container()
    if not container:
        return {"ok": False, "error": "Minecraft container not found.", "stdout": []}

    try:
        raw = container.logs(tail=tail, stdout=True, stderr=True)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")

        return {"ok": True, "stdout": [line for line in raw.splitlines() if not is_routine_rcon_log(line)]}
    except Exception as e:
        return {"ok": False, "error": str(e), "stdout": []}


def get_status():
    list_result = rcon("list")
    container = get_container()
    metrics = get_container_metrics(container) if container else {}
    uptime = get_container_uptime(container)

    if not list_result.get("ok"):
        return {
            "online": False,
            "server_name": "ATM10",
            "players": [],
            "player_count": 0,
            "version": "ATM10 / NeoForge",
            "raw": list_result,
            "tps": None,
            "mspt": None,
            "ram_usage": metrics.get("memory_usage_percent"),
            "cpu_usage": metrics.get("cpu_percent"),
            "uptime": uptime or "unknown",
        }

    players = parse_players(list_result.get("response", ""))

    return {
        "online": True,
        "server_name": "ATM10",
        "players": players,
        "player_count": len(players),
        "version": "ATM10 / NeoForge",
        "raw": list_result,
        "tps": None,
        "mspt": None,
        "ram_usage": metrics.get("memory_usage_percent"),
        "cpu_usage": metrics.get("cpu_percent"),
        "uptime": uptime or "unknown",
    }


def command(command_text: str):
    command_text = command_text.strip()
    if not command_text:
        return {"ok": False, "error": "Command cannot be empty."}

    return rcon(command_text)


def save_world():
    return rcon("save-all")


def op_player(player: str):
    return rcon(f"op {player}")


def deop_player(player: str):
    return rcon(f"deop {player}")


def say(message: str):
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
