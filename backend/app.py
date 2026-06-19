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
        return [{
            "name": "Projects config unavailable",
            "type": "system",
            "priority": "unknown",
            "status": str(e),
            "path": ""
        }]


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

        devices.append({
            "name": name,
            "ip": ip,
            "interface": dev,
            "mac": mac,
            "state": state
        })

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
                    "image": c.image.tags[0] if c.image.tags else "unknown"
                }
                for c in containers
            ]
        }
    except Exception as e:
        return {
            "available": False,
            "error": str(e),
            "total": 0,
            "running": 0,
            "containers": []
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

    recs = []

    if score >= 90:
        recs.append("System health is strong. No urgent resource issues detected.")

    if data["memory_used_percent"] < 25:
        recs.append("Memory headroom is excellent.")

    if data["cpu_usage_percent"] < 25:
        recs.append("CPU load is low right now.")

    disks = [d for d in block_devices if d.get("type") == "disk"]
    unmounted_disks = []
    for d in disks:
        children = d.get("children", [])
        if children:
            mounted = any(c.get("mountpoint") for c in children)
        else:
            mounted = bool(d.get("mountpoint"))
        if not mounted:
            unmounted_disks.append(d)

    if unmounted_disks:
        recs.append("One or more physical disks appear unmounted. The 2TB drive may be available for Minecraft, backups, Plex media, or bulk storage.")

    if docker_status["available"]:
        recs.append(f"Docker is online with {docker_status['running']} running container(s).")

    if network_devices:
        recs.append(f"{len(network_devices)} network neighbor(s) detected.")
    else:
        recs.append("No neighboring network devices detected yet. This may populate after more LAN traffic.")

    if projects:
        recs.append(f"{len(projects)} configured project(s) detected.")

    data["recommendations"] = recs
    return data


@app.get("/api/status")
def status():
    return build_status()


@app.post("/api/ask")
def ask(req: AskRequest):
    q = req.question.lower().strip()
    data = build_status()

    if "score" in q:
        return {"answer": f"Server health score is {data['health_score']}/100. Status: {data['health']}."}

    if "healthy" in q or "health" in q:
        return {"answer": f"System health is {data['health']} with a score of {data['health_score']}/100."}

    if "memory" in q or "ram" in q:
        return {"answer": f"Memory usage is {data['memory_used_percent']}% of {data['memory_total_gb']} GB."}

    if "cpu" in q:
        return {"answer": f"CPU usage is {data['cpu_usage_percent']}% across {data['cpu_threads']} threads."}

    if "disk" in q or "storage" in q:
        disks = [d for d in data["block_devices"] if d.get("type") == "disk"]
        disk_text = ", ".join([f"{d.get('name')} {d.get('size')}" for d in disks]) or "No disks found."
        return {"answer": f"Main disk usage is {data['disk_used_percent']}% of {data['disk_total_gb']} GB. Physical disks detected: {disk_text}"}

    if "network" in q or "devices" in q:
        return {"answer": f"I can currently see {len(data['network_devices'])} neighboring network device(s)."}

    if "docker" in q or "container" in q:
        d = data["docker"]
        if d["available"]:
            return {"answer": f"Docker is online. {d['running']} of {d['total']} container(s) are running."}
        return {"answer": "Docker status is unavailable: " + d.get("error", "unknown error")}

    if "project" in q:
        names = ", ".join([p.get("name", "Unnamed") for p in data["projects"]])
        return {"answer": f"Configured projects: {names}" if names else "No projects configured."}

    if "recommend" in q or "suggest" in q or "next" in q or "analyze" in q:
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


@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Command Center V0</title>
    <style>
        body { font-family: Arial, sans-serif; background: #10131a; color: #f1f5f9; padding: 32px; }
        h1 { margin-bottom: 4px; }
        .subtitle { color: #94a3b8; margin-bottom: 24px; }
        button { padding: 10px 14px; border-radius: 8px; border: 0; cursor: pointer; font-weight: bold; margin-right: 8px; }
        input { padding: 12px; border-radius: 8px; border: 1px solid #334155; background: #020617; color: #f1f5f9; width: min(700px, 80%); }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-top: 24px; }
        .card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 16px; }
        .label { color: #94a3b8; font-size: 13px; }
        .value { font-size: 22px; margin-top: 6px; }
        .green { color: #22c55e; }
        .yellow { color: #facc15; }
        .red { color: #ef4444; }
        .panel { background: #020617; border: 1px solid #334155; border-radius: 12px; padding: 16px; margin-top: 24px; }
        li { margin-bottom: 8px; }
        pre { background: #020617; border: 1px solid #334155; border-radius: 12px; padding: 16px; overflow-x: auto; margin-top: 24px; display: none; }
        .small { color: #94a3b8; font-size: 13px; }
        .answer { margin-top: 12px; font-size: 18px; color: #dbeafe; white-space: pre-wrap; }
    </style>
</head>
<body>
    <h1>Command Center V0</h1>
    <div class="subtitle">System observer online.</div>

    <button onclick="loadStatus()">Refresh Scan</button>
    <button onclick="toggleRaw()">Toggle Raw Data</button>
    <button onclick="analyzeStatus()">Analyze Status</button>

    <div class="grid" id="cards"></div>

    <div class="panel">
        <h2>Ask Command Center</h2>
        <input id="question" placeholder="Try: Analyze status. What projects do I have? What disks do I have?">
        <button onclick="ask()">Ask</button>
        <div class="answer" id="answer"></div>
    </div>

    <div class="panel">
        <h2>AI Analysis</h2>
        <div class="answer" id="analysis">Click Analyze Status for a plain-English report.</div>
    </div>

    <div class="panel">
        <h2>Recommendations</h2>
        <ul id="recommendations"></ul>
    </div>

    <div class="panel">
        <h2>Projects</h2>
        <ul id="projects"></ul>
    </div>

    <div class="panel">
        <h2>Network Devices</h2>
        <ul id="network"></ul>
    </div>

    <div class="panel">
        <h2>Docker Containers</h2>
        <ul id="docker"></ul>
    </div>

    <div class="panel">
        <h2>Physical Storage</h2>
        <ul id="storage"></ul>
    </div>

    <pre id="raw"></pre>

    <script>
    function badgeClass(color) {
        if (color === "green") return "green";
        if (color === "yellow") return "yellow";
        if (color === "red") return "red";
        return "";
    }

    async function loadStatus() {
        const response = await fetch('/api/status');
        const data = await response.json();

        const cards = [
            ["Health", `<span class="${badgeClass(data.health_color)}">${data.health}</span>`],
            ["Health Score", data.health_score + "/100"],
            ["Hostname", data.hostname],
            ["CPU Threads", data.cpu_threads],
            ["CPU Usage", data.cpu_usage_percent + "%"],
            ["Memory", data.memory_total_gb + " GB"],
            ["Memory Used", data.memory_used_percent + "%"],
            ["Disk", data.disk_total_gb + " GB"],
            ["Disk Used", data.disk_used_percent + "%"],
            ["Projects", data.projects.length],
            ["Network Devices", data.network_devices.length],
            ["Docker Running", data.docker.running + " / " + data.docker.total],
            ["Uptime", data.uptime]
        ];

        document.getElementById('cards').innerHTML = cards.map(card => `
            <div class="card"><div class="label">${card[0]}</div><div class="value">${card[1]}</div></div>
        `).join('');

        document.getElementById('recommendations').innerHTML =
            data.recommendations.map(r => `<li>${r}</li>`).join('');

        document.getElementById('projects').innerHTML =
            data.projects.map(p =>
                `<li><strong>${p.name}</strong> <span class="small">${p.type} | priority: ${p.priority} | ${p.status}</span></li>`
            ).join('') || "<li>No projects configured.</li>";

        document.getElementById('network').innerHTML =
            data.network_devices.map(d => `<li><strong>${d.name}</strong> <span class="small">${d.ip} | ${d.mac} | ${d.interface} | ${d.state}</span></li>`).join('') || "<li>No devices detected yet.</li>";

        document.getElementById('docker').innerHTML =
            data.docker.containers.map(c => `<li><strong>${c.name}</strong> <span class="small">${c.status} | ${c.image}</span></li>`).join('') || "<li>No containers detected.</li>";

        document.getElementById('storage').innerHTML =
            data.block_devices.map(d => `<li><strong>${d.name}</strong> <span class="small">${d.size} | ${d.type} | ${d.model || "unknown model"}</span></li>`).join('');

        document.getElementById('raw').innerText = JSON.stringify(data, null, 2);
    }

    async function ask() {
        const question = document.getElementById('question').value;
        const response = await fetch('/api/ask', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({question})
        });
        const data = await response.json();
        document.getElementById('answer').innerText = data.answer;
    }

    async function analyzeStatus() {
        document.getElementById('analysis').innerText = "Analyzing current status...";
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        const data = await response.json();
        document.getElementById('analysis').innerText = data.analysis;
    }

    function toggleRaw() {
        const raw = document.getElementById('raw');
        raw.style.display = raw.style.display === 'none' ? 'block' : 'none';
    }

    loadStatus();
    </script>
</body>
</html>
"""
