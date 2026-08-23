import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import docker
import json
import os
import platform
import psutil
import socket
import subprocess
import time
from datetime import datetime
from typing import List, Optional

from routers.auth import router as auth_router
from routers.backups import router as backups_router
from routers.calendar import router as calendar_router
from routers.agents import router as agents_router
from routers.auth import require_csrf
from routers.control import router as control_router
from routers.home_assistant import router as home_assistant_router
from routers.infrastructure import router as infrastructure_router
from routers.gmail import router as gmail_router
from routers.monitoring import router as monitoring_router
from routers.projects import router as projects_router
from services import advisor_service, agent_permission_service, auth_service, backup_service, budget_service, cloud_response_service, development_service, discord_alert_service, gmail_cloud_learning_service, gmail_rule_service, gmail_service, infrastructure_service, minecraft_service, openai_service, plex_service, policy_service, router_service, security_service, service_monitoring_service, task_service, worker_service
from storage import initialize_storage


async def service_monitor_loop():
    while True:
        try:
            if agent_permission_service.is_allowed("owner", "service_monitor", "background_checks"):
                await asyncio.to_thread(service_monitoring_service.check_once)
        except Exception as exc:
            print(f"Service monitoring check failed: {exc}")
        await asyncio.sleep(service_monitoring_service.interval_seconds())


async def gmail_organizer_loop():
    while True:
        try:
            if agent_permission_service.is_allowed("owner", "gmail", "organize_and_file"):
                await asyncio.to_thread(gmail_service.run_organizer, "owner")
            await asyncio.to_thread(gmail_rule_service.run_active_rules, "owner")
        except Exception as exc:
            print(f"Gmail organizer check failed: {exc}")
        await asyncio.sleep(300)


async def gmail_cloud_learning_loop():
    while True:
        try:
            await asyncio.to_thread(gmail_cloud_learning_service.run_if_due, "owner")
        except Exception as exc:
            print(f"Gmail cloud learning check failed safely: {type(exc).__name__}")
        await asyncio.sleep(3600)


async def infrastructure_alert_loop():
    while True:
        try:
            await asyncio.to_thread(infrastructure_service.alert_on_new_issues)
        except Exception as exc:
            print(f"Infrastructure alert check failed safely: {type(exc).__name__}")
        await asyncio.sleep(300)


async def backup_alert_loop():
    while True:
        try:
            await asyncio.to_thread(backup_service.alert_on_change)
        except Exception as exc:
            print(f"Backup alert check failed safely: {type(exc).__name__}")
        await asyncio.sleep(300)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_storage()
    auth_service.sync_owner()
    monitor_task = asyncio.create_task(service_monitor_loop())
    gmail_task = asyncio.create_task(gmail_organizer_loop())
    gmail_learning_task = asyncio.create_task(gmail_cloud_learning_loop())
    infrastructure_task = asyncio.create_task(infrastructure_alert_loop())
    backup_task = asyncio.create_task(backup_alert_loop())
    try:
        yield
    finally:
        monitor_task.cancel()
        gmail_task.cancel()
        gmail_learning_task.cancel()
        infrastructure_task.cancel()
        backup_task.cancel()
        with suppress(asyncio.CancelledError):
            await monitor_task
        with suppress(asyncio.CancelledError):
            await gmail_task
        with suppress(asyncio.CancelledError):
            await gmail_learning_task
        with suppress(asyncio.CancelledError):
            await infrastructure_task
        with suppress(asyncio.CancelledError):
            await backup_task


app = FastAPI(title="Command Center V0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(backups_router)
app.include_router(calendar_router)
app.include_router(agents_router)
app.include_router(control_router)
app.include_router(home_assistant_router)
app.include_router(infrastructure_router)
app.include_router(gmail_router)
app.include_router(monitoring_router)
app.include_router(projects_router)

class AskRequest(BaseModel):
    question: str


class BudgetSimulationRequest(BaseModel):
    prompt: str = Field(default="", max_length=1_000_000)
    max_output_tokens: int = Field(default=400, ge=0, le=32768)
    input_tokens: Optional[int] = Field(default=None, ge=0, le=2_000_000)
    domain: str = Field(default="general", max_length=100)
    model: str = Field(default="gpt-4.1-mini", max_length=100)


class TaskCreateRequest(BaseModel):
    project: str = "Command Center"
    workspace: str = "Development"
    title: str
    goal: str
    constraints: List[str] = Field(default_factory=list)
    execution_mode: str = "safe_edit"
    allowed_paths: List[str] = Field(default_factory=list)
    validation_commands: List[str] = Field(default_factory=lambda: [
        "python3 -m py_compile backend/app.py",
        "cd frontend-react && npm run build",
    ])
    requires_manual_approval: bool = False
    priority: str = "medium"


class TaskPatchRequest(BaseModel):
    project: Optional[str] = None
    workspace: Optional[str] = None
    title: Optional[str] = None
    goal: Optional[str] = None
    constraints: Optional[List[str]] = None
    execution_mode: Optional[str] = None
    allowed_paths: Optional[List[str]] = None
    validation_commands: Optional[List[str]] = None
    requires_manual_approval: Optional[bool] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    execution_stage: Optional[str] = None
    started_utc: Optional[str] = None
    completed_utc: Optional[str] = None
    result_summary: Optional[str] = None


class TaskResultRequest(BaseModel):
    result_summary: str = ""


class TaskStageRequest(BaseModel):
    execution_stage: str


class TaskLogAppendRequest(BaseModel):
    message: str


class TaskRunCommandRequest(BaseModel):
    command_key: str


class TaskPhaseResultRequest(BaseModel):
    summary: str = ""


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


def send_discord_alert(title: str, message: str, severity: str = "info"):
    return discord_alert_service.send(title, message, severity)


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



def get_router_health():
    router_ip = os.getenv("ROUTER_HOST", "192.168.50.1")

    ping_output = run_cmd(["ping", "-c", "3", router_ip])
    router_online = "0% packet loss" in ping_output

    latency_ms = None
    for line in ping_output.splitlines():
        if "rtt min/avg/max" in line:
            try:
                latency_ms = round(float(line.split("=")[1].split("/")[1]), 2)
            except Exception:
                latency_ms = None

    http_output = run_cmd(["curl", "-I", "--max-time", "3", f"http://{router_ip}"])
    web_online = "200 OK" in http_output or "HTTP/" in http_output

    internet_ping = run_cmd(["ping", "-c", "2", "1.1.1.1"])
    internet_online = "0% packet loss" in internet_ping

    dns_test = run_cmd(["getent", "hosts", "google.com"])
    dns_online = bool(dns_test.strip())

    return {
        "name": "ASUS Router",
        "host": router_ip,
        "router_online": router_online,
        "web_admin_online": web_online,
        "internet_online": internet_online,
        "dns_online": dns_online,
        "latency_ms": latency_ms,
        "status": "online" if router_online and internet_online and dns_online else "warning"
    }



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
    
def get_service_status():
    services = []
    docker_status = get_docker_status()
    cloud_routing = router_service.get_cloud_routing_state()

    services.append({
        "name": "Docker",
        "status": "online" if docker_status.get("available") else "offline",
        "detail": f"{docker_status.get('running', 0)} running container(s)"
    })

    openai_status = openai_service.get_status()
    services.append({
        "name": "OpenAI",
        "status": openai_status["status"],
        "detail": openai_status["detail"],
    })

    services.append({
        "name": "Vera Budget",
        "status": "guarded",
        "detail": "Live cloud requests reserve budget before submission",
    })

    services.append({
        "name": "Vera Policy",
        "status": "simulation",
        "detail": "Domain model, risk, budget, and approval rules are active",
    })

    services.append({
        "name": "Vera Router",
        "status": "enabled" if cloud_routing["effective_enabled"] else "disabled",
        "detail": "Cloud API access is owner-controlled; route decisions remain simulated",
    })

    services.append({
        "name": "Tailscale",
        "status": "unknown",
        "detail": "Status unavailable from container"
    })

    services.append({
        "name": "FastAPI Backend",
        "status": "online",
        "detail": "Serving API on port 8787"
    })

    plex_running = any(
        c.get("name") == "plex" and c.get("status") == "running"
        for c in docker_status.get("containers", [])
    )

    services.append({
        "name": "Plex",
        "status": "online" if plex_running else "offline",
        "detail": "Media server"
    })

    return services


def build_status():
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    cpu_percent = psutil.cpu_percent(interval=1)

    host_name = read_text("/host/etc/hostname", socket.gethostname())

    block_devices = get_block_devices()

    try:
        media_usage = psutil.disk_usage("/host/mnt/media")
        media_disk = {
            "name": "Media Drive",
            "mountpoint": "/mnt/media",
            "total_gb": round(media_usage.total / (1024**3), 2),
            "used_percent": media_usage.percent,
            "status": "mounted"
        }
    except Exception:
        media_disk = {
            "name": "Media Drive",
            "mountpoint": "/mnt/media",
            "status": "unavailable"
        }

    network_devices = get_network_devices()
    router_health = get_router_health()
    docker_status = get_docker_status()
    minecraft_status = minecraft_service.get_status()
    projects = get_projects()
    services = get_service_status()

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
        "media_disk": media_disk,
        "network_devices": network_devices,
        "router_health": router_health,
        "docker": docker_status,
        "minecraft": minecraft_status,
        "minecraft_analysis": minecraft_status.get("minecraft_analysis", {}),
        "projects": projects,
        "services": services,
    }

    recommendations = []

    if score >= 90:
        recommendations.append("System health is strong. No urgent resource issues detected.")

    if data["memory_used_percent"] < 25:
        recommendations.append("Memory headroom is excellent.")

    if data["cpu_usage_percent"] < 25:
        recommendations.append("CPU load is low right now.")

    if media_disk.get("status") != "mounted":
        recommendations.append("Media drive is not mounted or not visible to Command Center.")

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


@app.get("/api/advisor/recommendations")
def advisor_recommendations():
    data = build_status()
    return {
        "recommendations": advisor_service.build_recommendations(data),
        "minecraft_analysis": data.get("minecraft_analysis", {}),
    }


@app.get("/api/status")
def status():
    return build_status()


@app.get("/api/openai/status")
def openai_status():
    return {
        **openai_service.get_status(),
        "cloud_routing_enabled": router_service.cloud_routing_enabled(),
    }


@app.get("/api/budget/status")
def budget_status():
    return budget_service.get_status()


@app.post("/api/budget/simulate")
def budget_simulate(request: BudgetSimulationRequest):
    return budget_service.simulate(
        prompt=request.prompt,
        max_output_tokens=request.max_output_tokens,
        input_tokens=request.input_tokens,
        domain=request.domain,
        model=request.model,
    )


@app.get("/api/budget/ledger")
def budget_ledger(limit: int = 100):
    return {"entries": budget_service.list_ledger(limit)}


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






class MinecraftCommand(BaseModel):
    command: str


@app.get("/api/minecraft/status")
def minecraft_status():
    return minecraft_service.get_status()


@app.get("/api/minecraft/logs")
def minecraft_logs(tail: int = 120):
    return minecraft_service.get_logs(tail)


@app.post("/api/minecraft/command")
def minecraft_command(request: MinecraftCommand):
    return minecraft_service.command(request.command)


@app.post("/api/minecraft/save")
def minecraft_save():
    return minecraft_service.save_world()


@app.post("/api/minecraft/start")
def minecraft_start():
    return minecraft_service.container_action("start")


@app.post("/api/minecraft/stop")
def minecraft_stop():
    return minecraft_service.container_action("stop")


@app.post("/api/minecraft/restart")
def minecraft_restart():
    return minecraft_service.container_action("restart")


@app.post("/api/minecraft/op")
def minecraft_op(player: str):
    return minecraft_service.op_player(player)


@app.post("/api/minecraft/deop")
def minecraft_deop(player: str):
    return minecraft_service.deop_player(player)


@app.post("/api/minecraft/kick")
def minecraft_kick(player: str):
    return minecraft_service.kick_player(player)


@app.post("/api/minecraft/ban")
def minecraft_ban(player: str):
    return minecraft_service.ban_player(player)


@app.post("/api/minecraft/say")
def minecraft_say(message: str):
    return minecraft_service.say(message)


@app.get("/api/plex/status")
def plex_status():
    return plex_service.get_status()


@app.get("/api/plex/logs")
def plex_logs(tail: int = 160):
    return plex_service.get_logs(tail)


@app.post("/api/plex/start")
def plex_start():
    return plex_service.container_action("start")


@app.post("/api/plex/stop")
def plex_stop():
    return plex_service.container_action("stop")


@app.post("/api/plex/restart")
def plex_restart():
    return plex_service.container_action("restart")


@app.get("/api/security/status")
def security_status():
    return security_service.get_status()


@app.get("/api/development/status")
def development_status():
    return development_service.get_status()


@app.get("/api/workers/status")
def workers_status():
    return worker_service.get_status()


@app.get("/api/tasks")
def list_tasks():
    return {"tasks": task_service.list_tasks()}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    task = task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@app.post("/api/tasks")
def create_task(request: TaskCreateRequest):
    try:
        return task_service.create_task(request.dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/api/tasks/{task_id}")
def update_task(task_id: str, request: TaskPatchRequest):
    try:
        task = task_service.update_task(task_id, request.dict(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@app.post("/api/tasks/{task_id}/start")
def start_task(task_id: str):
    task = task_service.start_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@app.post("/api/tasks/{task_id}/complete")
def complete_task(task_id: str, request: TaskResultRequest):
    task = task_service.complete_task(task_id, request.result_summary)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@app.post("/api/tasks/{task_id}/fail")
def fail_task(task_id: str, request: TaskResultRequest):
    task = task_service.fail_task(task_id, request.result_summary)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@app.post("/api/tasks/{task_id}/retry")
def retry_task(task_id: str):
    try:
        task = task_service.retry_task(task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@app.patch("/api/tasks/{task_id}/stage")
def set_task_execution_stage(task_id: str, request: TaskStageRequest):
    try:
        task = task_service.set_execution_stage(task_id, request.execution_stage)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@app.post("/api/tasks/{task_id}/log")
def append_task_log(task_id: str, request: TaskLogAppendRequest):
    try:
        task = task_service.append_task_log(task_id, request.message)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return {"ok": True, "task_id": task_id}


@app.get("/api/tasks/{task_id}/events")
def get_task_events(task_id: str):
    events = task_service.get_task_events(task_id)
    if events is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return {"task_id": task_id, "events": events}


@app.post("/api/tasks/{task_id}/run-command")
def run_task_command(task_id: str, request: TaskRunCommandRequest, session: dict = Depends(require_csrf)):
    try:
        agent_permission_service.require(session["user_id"], "development_worker", "manual_tasks")
    except agent_permission_service.AgentPermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        result = task_service.run_task_command(task_id, request.command_key, actor_user_id=session["user_id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except policy_service.PolicyDeniedError as e:
        raise HTTPException(status_code=423, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if result is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return result


@app.post("/api/tasks/{task_id}/run-validation")
def run_task_validation(task_id: str, session: dict = Depends(require_csrf)):
    try:
        agent_permission_service.require(session["user_id"], "development_worker", "manual_tasks")
    except agent_permission_service.AgentPermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    results = []
    for command_key in task_service.VALIDATION_COMMAND_KEYS:
        try:
            result = task_service.run_task_command(task_id, command_key, actor_user_id=session["user_id"])
        except policy_service.PolicyDeniedError as e:
            raise HTTPException(status_code=423, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        if result is None:
            raise HTTPException(status_code=404, detail="Task not found.")
        results.append(result)
    return {"task_id": task_id, "results": results}


@app.post("/api/tasks/{task_id}/run-rebuild")
def run_task_rebuild(task_id: str, session: dict = Depends(require_csrf)):
    try:
        agent_permission_service.require(session["user_id"], "development_worker", "manual_tasks")
    except agent_permission_service.AgentPermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    results = []
    for command_key in task_service.REBUILD_COMMAND_KEYS:
        try:
            result = task_service.run_task_command(task_id, command_key, actor_user_id=session["user_id"])
        except policy_service.PolicyDeniedError as e:
            raise HTTPException(status_code=423, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        if result is None:
            raise HTTPException(status_code=404, detail="Task not found.")
        results.append(result)
    return {"task_id": task_id, "results": results}


@app.post("/api/tasks/{task_id}/phases/initialize")
def initialize_task_phases(task_id: str):
    task = task_service.initialize_task_phases(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@app.post("/api/tasks/{task_id}/phases/{phase_name}/start")
def start_task_phase(task_id: str, phase_name: str):
    try:
        task = task_service.start_task_phase(task_id, phase_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@app.post("/api/tasks/{task_id}/phases/{phase_name}/complete")
def complete_task_phase(task_id: str, phase_name: str, request: TaskPhaseResultRequest):
    try:
        task = task_service.complete_task_phase(task_id, phase_name, request.summary)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@app.post("/api/tasks/{task_id}/phases/{phase_name}/fail")
def fail_task_phase(task_id: str, phase_name: str, request: TaskPhaseResultRequest):
    try:
        task = task_service.fail_task_phase(task_id, phase_name, request.summary)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@app.get("/api/tasks/{task_id}/logs")
def get_task_logs(task_id: str):
    logs = task_service.get_task_logs(task_id)
    if logs is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return {"task_id": task_id, "logs": logs}


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str):
    if not task_service.delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found.")
    return {"ok": True, "deleted": task_id}


@app.post("/api/alerts/test")
def test_alert():
    data = build_status()

    result = send_discord_alert(
        title="Test Alert",
        message=f"Command Center alert system is online.\n\nHealth: {data.get('health')} ({data.get('health_score')}/100)",
        severity="success"
    )

    return result

@app.post("/api/analyze")
def analyze(session: dict = Depends(require_csrf)):
    if not router_service.cloud_routing_enabled():
        return {"analysis": "Cloud routing is off. Local status and recommendations remain available.", "provider": "local"}

    data = build_status()

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
        response, ledger = cloud_response_service.run_guarded(
            input_data=prompt, budget_text=prompt, max_output_tokens=800
        )
        return {
            "analysis": response.output_text,
            "provider": "openai",
            "model": openai_service.get_model(),
            "cost_usd": ledger.get("actual_cost_usd", ledger.get("reserved_cost_usd")),
        }
    except Exception as e:
        return {"analysis": f"OpenAI analysis failed: {str(e)}"}


@app.post("/api/briefing")
def briefing(session: dict = Depends(require_csrf)):
    if not router_service.cloud_routing_enabled():
        return {"briefing": "Cloud routing is off. Local system status remains available.", "provider": "local"}

    data = build_status()

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
        response, ledger = cloud_response_service.run_guarded(
            input_data=prompt, budget_text=prompt, max_output_tokens=500
        )
        return {
            "briefing": response.output_text,
            "provider": "openai",
            "model": openai_service.get_model(),
            "cost_usd": ledger.get("actual_cost_usd", ledger.get("reserved_cost_usd")),
        }
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
