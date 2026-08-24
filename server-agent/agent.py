#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import time
import urllib.request

VERSION = "1.0"


def memory_percent():
    values = {}
    with open("/proc/meminfo", encoding="utf-8") as handle:
        for line in handle:
            key, value = line.split(":", 1)
            values[key] = int(value.strip().split()[0])
    return round((1 - values["MemAvailable"] / values["MemTotal"]) * 100, 1)


def docker_counts():
    try:
        output = subprocess.run(["docker", "ps", "-a", "--format", "{{.State}}"], capture_output=True, text=True, timeout=10, check=True).stdout.splitlines()
        return sum(state == "running" for state in output), len(output)
    except (OSError, subprocess.SubprocessError):
        return 0, 0


def collect():
    disk = shutil.disk_usage("/")
    running, total = docker_counts()
    with open("/proc/uptime", encoding="utf-8") as handle:
        uptime = int(float(handle.read().split()[0]))
    return {
        "uptime_seconds": uptime,
        "load_1m": round(os.getloadavg()[0], 2),
        "memory_used_percent": memory_percent(),
        "disk_used_percent": round(disk.used / disk.total * 100, 1),
        "services_running": running,
        "services_total": total,
    }


def main():
    endpoint = os.environ["VERA_COMMAND_CENTER_URL"].rstrip("/") + "/api/servers/heartbeat"
    token = os.environ["VERA_SERVER_TOKEN"]
    data = json.dumps({"agent_version": VERSION, "status": collect()}).encode()
    request = urllib.request.Request(endpoint, data=data, method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"Heartbeat rejected with HTTP {response.status}")


if __name__ == "__main__":
    main()
