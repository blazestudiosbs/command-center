from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from openai import OpenAI
import docker
import json
import os
import platform
import psutil
import socket
import subprocess
import time

app = FastAPI(title="Command Center V0")

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=30.0,
    max_retries=1,
)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


class AskRequest(BaseModel):
    question: str


def read_text(path: str, fallback: str = "unknown") -> str:
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except Exception:
        return fallback


def run_cmd(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        return result.stdout.strip()
    except Exception as e:
        return str(e)


def format_uptime(seconds: float) -> str:
    seconds = int(seconds)
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60

    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def get_block_devices():
    output = run_cmd(["lsblk", "-J", "-o", "NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,MODEL"])

    try:
        data = json.loads(output)
        return data.get("blockdevices", [])
    except Exception:
        return []


def get_projects():
    path = "/app/config/projects.json"

    try:
        with open(path, "r") as f:
            data = json.load(f)

        return data.get("projects", [])
    except Exception as e:
        return [
            {
                "name": "Projects config unavailable",
                "type": "system",
                "priority": "unknown",
                "status": str(e),
                "path": "",
            }
        ]


def get_network_devices():
    output = run_cmd(["ip", "neigh"])
    devices = []

    for line in output.splitlines():
        parts = line.split()

        if not parts:
            continue

        ip = parts[0]
        dev = parts[parts.index("dev") + 1] if "dev" in parts else "unknown"
        mac = parts[parts.index("lladdr") + 1] if "lladdr" in parts else "unknown"
        state = parts[-1]

        name = "Unknown Device"

        if ip.endswith(".1"):
            name = "Likely Router/Gateway"
        elif ip == "192.168.50.10":
            name = "Command Center"

        try:
            reverse = socket.gethostbyaddr(ip)[0]
            if reverse:
                name = reverse
        except Exception:
            pass

        devices.append(
            {
                "name": name,
                "ip": ip,
                "interface": dev,
                "mac": mac,
                "state": state,
            }
        )

    return devices


def get_docker_status():
    try:
        client_docker = docker.from_env()
        containers = client_docker.containers.list(all=True)

        return {
            "available": True,
            "total": len(containers),
            "running": len([c for c in containers if c.status == "running"]),
            "containers": [
                {
                    "name": c.name,
                    "status": c.status,
                    "image": c.image.tags[0] if c.image.tags else "unknown",
                }
                for c in containers
            ],
        }
    except Exception as e:
        return {
            "available": False,
            "error": str(e),
            "total": 0,
            "running": 0,
            "containers": [],
        }


def get_health_score(cpu, ram, disk, docker_status):
    score = 100

    if cpu > 90:
        score -= 35
    elif cpu > 75:
        score -= 20
    elif cpu > 50:
        score -= 8

    if ram > 90:
        score -= 35
    elif ram > 75:
        score -= 20
    elif ram > 50:
        score -= 8

    if disk > 95:
        score -= 35
    elif disk > 85:
        score -= 20
    elif disk > 70:
        score -= 8

    if not docker_status["available"]:
        score -= 20

    return max(score, 0)


def get_health(score):
    if score >= 90:
        return "Healthy", "green"
    if score >= 70:
        return "Warning", "yellow"
    return "Critical", "red"


def build_status():
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    cpu_percent = psutil.cpu_percent(interval=1)

    host_name = read_text("/host/etc/hostname", socket.gethostname())

    block_devices = get_block_devices()
    network_devices = get_network_devices()
    docker_status = get_docker_status()
    projects = get_projects()

    score = get_health_score(cpu_percent, memory.percent, disk.percent, docker_status)
    health, health_color = get_health(score)

    data = {
        "hostname": host_name,
        "container_hostname": socket.gethostname(),
        "platform": platform.platform(),
        "cpu_threads": psutil.cpu_count(logical=True),
        "cpu_usage_percent": cpu_percent,
        "memory_total_gb": round(memory.total / (1024**3), 2),
        "memory_used_percent": memory.percent,
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "disk_used_percent": disk.percent,
        "uptime": format_uptime(time.time() - psutil.boot_time()),
        "health": health,
        "health_color": health_color,
        "health_score": score,
        "block_devices": block_devices,
        "network_devices": network_devices,
        "docker": docker_status,
        "projects": projects,
    }

    recommendations = []

    if score >= 90:
        recommendations.append("System health is strong. No urgent resource issues detected.")

    if data["memory_used_percent"] < 25:
        recommendations.append("Memory headroom is excellent.")

    if data["cpu_usage_percent"] < 25:
        recommendations.append("CPU load is low right now.")

    disks = [d for d in block_devices if d.get("type") == "disk"]
    unmounted_disks = []

    for disk_device in disks:
        children = disk_device.get("children", [])

        if children:
            mounted = any(child.get("mountpoint") for child in children)
        else:
            mounted = bool(disk_device.get("mountpoint"))

        if not mounted:
            unmounted_disks.append(disk_device)

    if unmounted_disks:
        recommendations.append(
            "One or more physical disks appear unmounted. The 2TB drive may be available for Minecraft, backups, Plex media, or bulk storage."
        )

    if docker_status["available"]:
        recommendations.append(
            f"Docker is online with {docker_status['running']} running container(s)."
        )

    if network_devices:
        recommendations.append(f"{len(network_devices)} network neighbor(s) detected.")
    else:
        recommendations.append(
            "No neighboring network devices detected yet. This may populate after more LAN traffic."
        )

    if projects:
        recommendations.append(f"{len(projects)} configured project(s) detected.")

    data["recommendations"] = recommendations

    return data


@app.get("/api/status")
def status():
    return build_status()


@app.post("/api/ask")
def ask(req: AskRequest):
    question = req.question.lower().strip()
    data = build_status()

    if "score" in question:
        return {
            "answer": f"Server health score is {data['health_score']}/100. Status: {data['health']}."
        }

    if "healthy" in question or "health" in question:
        return {
            "answer": f"System health is {data['health']} with a score of {data['health_score']}/100."
        }

    if "memory" in question or "ram" in question:
        return {
            "answer": f"Memory usage is {data['memory_used_percent']}% of {data['memory_total_gb']} GB."
        }

    if "cpu" in question:
        return {
            "answer": f"CPU usage is {data['cpu_usage_percent']}% across {data['cpu_threads']} threads."
        }

    if "disk" in question or "storage" in question:
        disks = [d for d in data["block_devices"] if d.get("type") == "disk"]
        disk_text = ", ".join([f"{d.get('name')} {d.get('size')}" for d in disks])
        return {
            "answer": f"Main disk usage is {data['disk_used_percent']}% of {data['disk_total_gb']} GB. Physical disks detected: {disk_text or 'No disks found.'}"
        }

    if "network" in question or "devices" in question:
        return {
            "answer": f"I can currently see {len(data['network_devices'])} neighboring network device(s)."
        }

    if "docker" in question or "container" in question:
        docker_status = data["docker"]

        if docker_status["available"]:
            return {
                "answer": f"Docker is online. {docker_status['running']} of {docker_status['total']} container(s) are running."
            }

        return {
            "answer": "Docker status is unavailable: "
            + docker_status.get("error", "unknown error")
        }

    if "project" in question:
        names = ", ".join([p.get("name", "Unnamed") for p in data["projects"]])
        return {"answer": f"Configured projects: {names}" if names else "No projects configured."}

    if (
        "recommend" in question
        or "suggest" in question
        or "next" in question
        or "analyze" in question
    ):
        return {"answer": " ".join(data["recommendations"])}

    return {
        "answer": "I can answer basic questions about health, score, CPU, memory, disk, Docker, network devices, projects, and recommendations."
    }


@app.post("/api/analyze")
def analyze():
    data = build_status()

    if not os.getenv("OPENAI_API_KEY"):
        return {
            "analysis": "OpenAI API key is not configured yet. Add OPENAI_API_KEY to /opt/command-center/.env and rebuild the container."
        }

    prompt = f"""
You are Command Center, a read-only home server operations assistant.

Analyze this server status JSON and give a concise, practical report.

Rules:
- Do not suggest destructive actions.
- Do not claim access to anything not in the JSON.
- Prioritize likely issues, risks, and next steps.
- Mention if the system looks healthy.
- Be direct and useful.

Server status JSON:
{json.dumps(data, indent=2)}
"""

    try:
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=prompt,
            max_output_tokens=400,
        )

        return {"analysis": response.output_text}
    except Exception as e:
        return {"analysis": f"OpenAI analysis failed: {str(e)}"}


@app.post("/api/briefing")
def briefing():
    data = build_status()

    if not os.getenv("OPENAI_API_KEY"):
        return {"briefing": "OpenAI API key is not configured yet."}

    briefing_payload = {
        "system": {
            "health": data.get("health"),
            "health_score": data.get("health_score"),
            "recommendations": data.get("recommendations", []),
        },
        "projects": data.get("projects", []),
    }

    prompt = f"""
You are Command Center, a read-only home operations and project planning assistant.

Create a concise daily briefing from this JSON.

Rules:
- Keep it under 300 words.
- Prioritize projects by priority.
- Mention infrastructure concerns only if they matter.
- Be practical, not motivational fluff.
- End with one recommended focus for today.

Daily briefing JSON:
{json.dumps(briefing_payload, indent=2)}
"""

    try:
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=prompt,
            max_output_tokens=500,
        )

        return {"briefing": response.output_text}
    except Exception as e:
        return {"briefing": f"Daily briefing failed: {str(e)}"}


@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Command Center V0</title>
</head>
<body>
    <h1>Command Center API</h1>
    <p>Backend is online.</p>
    <ul>
        <li><a href="/api/status">/api/status</a></li>
    </ul>
</body>
</html>
"""
