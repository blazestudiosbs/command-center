import re
import subprocess
from typing import Any, Dict, List, Optional


def _run_dmidecode() -> Optional[str]:
    try:
        result = subprocess.run(
            ["dmidecode", "-t", "16"],
            capture_output=True,
            text=True,
            timeout=8,
            check=True,
        )
        return result.stdout
    except Exception:
        return None


def get_memory_max_capacity_gb() -> Optional[int]:
    output = _run_dmidecode()
    if not output:
        return None

    match = re.search(r"Maximum Capacity:\s*([0-9]+)\s*GB", output, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None

    return None


def _as_number(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _minecraft_action(*items: str) -> str:
    return "; ".join(items) + "."


def _minecraft_cpu_phrase(cpu: Optional[float]) -> str:
    if cpu is None:
        return "current CPU data is unavailable"
    return f"Minecraft CPU is {cpu}%"


def build_recommendations(status: Dict[str, Any]) -> List[Dict[str, str]]:
    recommendations: List[Dict[str, str]] = []

    cpu_usage = status.get("cpu_usage_percent", 0) or 0
    memory_total = status.get("memory_total_gb", 0) or 0
    memory_used = status.get("memory_used_percent", 0) or 0
    disk_used = status.get("disk_used_percent", 0) or 0
    docker = status.get("docker", {}) or {}
    media_disk = status.get("media_disk", {}) or {}
    minecraft_status = status.get("minecraft", {}) or {}
    minecraft_analysis = minecraft_status.get("minecraft_analysis", {}) or {}

    memory_max_gb = get_memory_max_capacity_gb()
    memory_at_motherboard_limit = (
        memory_max_gb is not None
        and 30 <= memory_total <= 34
        and abs(memory_total - memory_max_gb) <= 2
    )

    if memory_at_motherboard_limit:
        recommendations.append({
            "category": "Hardware",
            "priority": "low",
            "title": "Do not buy more DDR3 RAM",
            "summary": "The motherboard is already at its maximum supported 32 GB. RAM is not the current bottleneck.",
            "reason": f"The system reports {memory_total}GB installed and a motherboard maximum of {memory_max_gb}GB.",
            "estimated_cost": "N/A",
            "benefit": "Avoid spending on memory that the platform cannot use.",
            "action": "Focus tuning and upgrade planning on CPU/platform limits instead of additional DDR3 RAM.",
        })

    if memory_total and 30 <= memory_total <= 34 and not memory_at_motherboard_limit:
        if memory_used < 40:
            recommendations.append({
                "category": "Hardware",
                "priority": "low",
                "title": "Avoid unnecessary RAM purchases",
                "summary": "Your system has roughly 32GB of RAM and current usage is low.",
                "reason": f"Memory is {memory_used}% used of {memory_total}GB, so there is healthy headroom.",
                "estimated_cost": "Free",
                "benefit": "Avoid spending on RAM before actual demand increases.",
                "action": "Monitor memory usage over time and upgrade only if sustained usage exceeds 70%.",
            })

    minecraft_cpu = _as_number(minecraft_status.get("cpu_usage"))
    minecraft_ram = _as_number(minecraft_status.get("ram_usage"))
    minecraft_cpu_high = minecraft_cpu is not None and minecraft_cpu >= 70
    minecraft_ram_high = minecraft_ram is not None and minecraft_ram >= 75
    minecraft_ram_not_high = (minecraft_ram is not None and minecraft_ram < 75) or (minecraft_ram is None and memory_used < 75)
    keep_up_count = minecraft_analysis.get("keep_up_warning_count", 0) or 0
    max_ticks_behind = minecraft_analysis.get("max_ticks_behind", 0) or 0
    disconnect_count = minecraft_analysis.get("disconnect_count", 0) or 0
    timeout_count = minecraft_analysis.get("timeout_count", 0) or 0
    severe_recent_tick_lag = keep_up_count > 0 and max_ticks_behind > 100

    if keep_up_count > 0 and (minecraft_cpu_high or severe_recent_tick_lag) and minecraft_ram_not_high:
        recommendations.append({
            "category": "Minecraft",
            "priority": "high",
            "title": "Minecraft is CPU-bound",
            "summary": "ATM10 is lagging because the server thread is overloaded, not because RAM is full.",
            "reason": f"Logs show {keep_up_count} keep-up warning(s) in the {minecraft_analysis.get('analysis_window', 'recent')} window, max tick lag is {max_ticks_behind} tick(s), {_minecraft_cpu_phrase(minecraft_cpu)}, RAM is {minecraft_ram}%, player count is {minecraft_status.get('player_count', 0)}, and uptime is {minecraft_status.get('uptime', 'unknown')}.",
            "estimated_cost": "Medium",
            "benefit": "Reduce tick lag and improve stability without buying RAM that is not solving the bottleneck.",
            "action": _minecraft_action(
                "lower view-distance",
                "lower simulation-distance",
                "avoid multiple players generating new chunks",
                "consider a newer CPU/platform for long-term improvement",
            ),
        })

    if minecraft_analysis.get("oom_detected"):
        recommendations.append({
            "category": "Minecraft",
            "priority": "high",
            "title": "Minecraft may need more memory",
            "summary": "Minecraft logs contain an out-of-memory or killed-process symptom.",
            "reason": f"Container RAM is {minecraft_ram}% and system memory is {memory_used}% used of {memory_total}GB.",
            "estimated_cost": "Low",
            "benefit": "Reduce crash risk from JVM or container memory pressure.",
            "action": _minecraft_action("increase Java memory", "check container memory limits"),
        })

    if minecraft_analysis.get("disconnect_near_keep_up") or ((disconnect_count + timeout_count) > 0 and keep_up_count > 0):
        recommendations.append({
            "category": "Minecraft",
            "priority": "high",
            "title": "Player disconnects likely caused by server tick lag",
            "summary": "Disconnect or timeout events appear near Minecraft keep-up warnings.",
            "reason": f"Logs show {disconnect_count} disconnect(s), {timeout_count} timeout(s), and {keep_up_count} keep-up warning(s).",
            "estimated_cost": "Free",
            "benefit": "Reduce disconnects during world generation and heavy server ticks.",
            "action": _minecraft_action("reduce simulation distance", "pre-generate chunks", "avoid world generation with multiple players"),
        })
    elif minecraft_cpu_high:
        recommendations.append({
            "category": "Minecraft",
            "priority": "medium",
            "title": "Minecraft CPU usage is elevated",
            "summary": "Minecraft container CPU use is above 70%.",
            "reason": "High container CPU usage can cause lag during active gameplay.",
            "estimated_cost": "Medium",
            "benefit": "Reduce future server slowdowns and improve player experience.",
            "action": "Tune Minecraft settings and monitor; consider a CPU or platform upgrade if usage stays high.",
        })

    if cpu_usage >= 90:
        recommendations.append({
            "category": "Hardware",
            "priority": "high",
            "title": "CPU is under sustained pressure",
            "summary": f"Current CPU usage is {cpu_usage}%.",
            "reason": "Sustained high CPU usage reduces headroom for background tasks and service responsiveness.",
            "estimated_cost": "High",
            "benefit": "Keep the system responsive under load and avoid future performance bottlenecks.",
            "action": "Investigate heavy processes and plan a CPU or platform upgrade if high load continues.",
        })
    elif cpu_usage >= 70:
        recommendations.append({
            "category": "Hardware",
            "priority": "medium",
            "title": "CPU load is trending high",
            "summary": f"Current CPU usage is {cpu_usage}%.",
            "reason": "CPU load in the 70-90% range suggests future upgrade planning is wise.",
            "estimated_cost": "Low",
            "benefit": "Avoid future performance issues with moderate demand growth.",
            "action": "Track CPU usage during peak hours and apply software tuning before buying new hardware.",
        })

    if media_disk.get("status") != "mounted":
        recommendations.append({
            "category": "Hardware",
            "priority": "high",
            "title": "Media storage is unavailable",
            "summary": "The media drive is not mounted or visible to Command Center.",
            "reason": "Missing media storage can interrupt media services and backups.",
            "estimated_cost": "Medium",
            "benefit": "Restore stable media storage access for your media server and file library.",
            "action": "Verify the media disk mount and reconnect or replace the drive if needed.",
        })
    elif isinstance(media_disk.get("used_percent"), (int, float)) and media_disk["used_percent"] >= 85:
        recommendations.append({
            "category": "Hardware",
            "priority": "medium",
            "title": "Media disk capacity is high",
            "summary": f"Media storage is {media_disk['used_percent']}% full.",
            "reason": "High media disk usage increases the risk of outages and slow file operations.",
            "estimated_cost": "Medium",
            "benefit": "Keep media services running smoothly and avoid running out of storage.",
            "action": "Clean or expand media storage before capacity becomes critical.",
        })

    if disk_used >= 90:
        recommendations.append({
            "category": "Hardware",
            "priority": "high",
            "title": "System disk is nearing capacity",
            "summary": f"Root disk usage is {disk_used}%.",
            "reason": "Very high disk usage can degrade performance and leave little room for logs or updates.",
            "estimated_cost": "Low",
            "benefit": "Improve system reliability by freeing space or adding storage.",
            "action": "Delete unneeded files or move data to another volume to create headroom.",
        })
    elif disk_used >= 80:
        recommendations.append({
            "category": "Hardware",
            "priority": "medium",
            "title": "System disk is moderately full",
            "summary": f"Root disk usage is {disk_used}%.",
            "reason": "Disk usage above 80% reduces flexibility for updates and temporary files.",
            "estimated_cost": "Free",
            "benefit": "Avoid future storage pressure and keep the system responsive.",
            "action": "Perform a storage cleanup or move bulk data off the root volume.",
        })

    if not docker.get("available"):
        recommendations.append({
            "category": "Service",
            "priority": "high",
            "title": "Docker is unavailable",
            "summary": "Command Center cannot access Docker on this host.",
            "reason": "Docker is required for many containers and service checks in Command Center.",
            "estimated_cost": "Low",
            "benefit": "Restore container visibility and service monitoring.",
            "action": "Confirm Docker is installed and running, then restart the Command Center backend.",
        })

    if memory_total and memory_total < 16 and memory_used >= 75:
        recommendations.append({
            "category": "Hardware",
            "priority": "high",
            "title": "RAM is tight for current workload",
            "summary": f"System has {memory_total}GB RAM and is using {memory_used}%.",
            "reason": "Limited RAM can force swap use and slow down services.",
            "estimated_cost": "Medium",
            "benefit": "Improve multitasking and container performance.",
            "action": "Add RAM if the motherboard supports it, or reduce memory-heavy services.",
        })

    if not recommendations:
        recommendations.append({
            "category": "Hardware",
            "priority": "low",
            "title": "No immediate upgrades recommended",
            "summary": "Current system data does not show urgent hardware or service upgrade needs.",
            "reason": "Resources are within normal ranges and media storage is accessible.",
            "estimated_cost": "Free",
            "benefit": "Continue monitoring and prioritize upgrades only when usage increases.",
            "action": "Review this advisor regularly as workload changes.",
        })

    return recommendations
