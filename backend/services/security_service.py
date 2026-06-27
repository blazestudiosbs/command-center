import ipaddress
import re
import subprocess
from typing import Any

try:
    import docker
except Exception:  # pragma: no cover - depends on deployment environment
    docker = None


LAN_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

KNOWN_PUBLIC_PORTS = {22, 80, 443, 25565, 32400}
RCON_PORT = 25575
COMMAND_CENTER_API_PORT = 8787


def _run_cmd(cmd: list[str], timeout: int = 8) -> dict[str, Any]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except FileNotFoundError:
        return {"ok": False, "stdout": "", "stderr": f"{cmd[0]} is not installed.", "returncode": 127}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e), "returncode": 1}


def _is_lan_ip(ip: ipaddress._BaseAddress) -> bool:
    return any(ip in network for network in LAN_NETWORKS)


def _is_private_source(source: str) -> bool:
    source = source.strip()
    try:
        network = ipaddress.ip_network(source, strict=False)
        return any(network.subnet_of(lan) or network.overlaps(lan) for lan in LAN_NETWORKS)
    except Exception:
        return False


def _parse_ip(value: str):
    value = value.strip().strip("[]")
    if value in {"", "*", "0.0.0.0", "::"}:
        return None

    try:
        return ipaddress.ip_address(value)
    except Exception:
        return None


def _split_address_port(endpoint: str) -> tuple[str, int | None]:
    endpoint = endpoint.strip()
    if endpoint.startswith("[") and "]:" in endpoint:
        address, port = endpoint.rsplit(":", 1)
        return address.strip("[]"), int(port) if port.isdigit() else None

    if endpoint.count(":") > 1:
        address, port = endpoint.rsplit(":", 1)
        return address, int(port) if port.isdigit() else None

    if ":" in endpoint:
        address, port = endpoint.rsplit(":", 1)
        return address, int(port) if port.isdigit() else None

    return endpoint, None


def _extract_process(raw: str) -> str:
    match = re.search(r'users:\(\("([^"]+)"', raw)
    if match:
        return match.group(1)
    return "unknown"


def get_ufw_status() -> dict[str, Any]:
    result = _run_cmd(["ufw", "status", "verbose"])
    output = result.get("stdout", "")
    lines = output.splitlines()

    enabled = False
    default_policy = "unknown"
    allowed_inbound_rules = []

    for line in lines:
        stripped = line.strip()
        lowered = stripped.lower()

        if lowered.startswith("status:"):
            enabled = "active" in lowered

        if lowered.startswith("default:"):
            default_policy = stripped.split(":", 1)[1].strip()

        if not stripped or stripped.startswith("--") or stripped.lower().startswith(("status:", "logging:", "default:", "new profiles:", "to ")):
            continue

        parts = re.split(r"\s{2,}", stripped)
        if len(parts) >= 3 and parts[1].upper().startswith("ALLOW"):
            allowed_inbound_rules.append({
                "to": parts[0],
                "action": parts[1],
                "from": parts[2],
                "raw": stripped,
            })

    return {
        "available": result.get("returncode") != 127,
        "enabled": enabled,
        "default_policy": default_policy,
        "allowed_inbound_rules": allowed_inbound_rules,
        "raw": output or result.get("stderr", ""),
    }


def _port_from_rule_to(rule_to: str) -> int | None:
    match = re.search(r"(?:^|/)(\d{1,5})(?:/tcp|\b)", rule_to)
    if match:
        port = int(match.group(1))
        if 0 < port <= 65535:
            return port
    if rule_to.isdigit():
        port = int(rule_to)
        if 0 < port <= 65535:
            return port
    return None


def _rule_source_category(source: str) -> str:
    source = source.strip()
    lowered = source.lower()
    if lowered in {"anywhere", "anywhere (v6)", "0.0.0.0/0", "::/0"}:
        return "public"

    if _is_private_source(source):
        return "lan"

    return "public"


def _ufw_port_categories(ufw_status: dict[str, Any]) -> dict[int, set[str]]:
    categories: dict[int, set[str]] = {}
    for rule in ufw_status.get("allowed_inbound_rules", []):
        port = _port_from_rule_to(rule.get("to", ""))
        if port is None:
            continue
        categories.setdefault(port, set()).add(_rule_source_category(rule.get("from", "")))
    return categories


def _matching_ufw_rules(ufw_status: dict[str, Any], port: int) -> list[dict[str, Any]]:
    matches = []
    for rule in ufw_status.get("allowed_inbound_rules", []):
        if _port_from_rule_to(rule.get("to", "")) != port:
            continue
        matches.append({**rule, "source_category": _rule_source_category(rule.get("from", ""))})
    return matches


def _bind_scope(address: str) -> str:
    parsed = _parse_ip(address)
    if parsed and parsed.is_loopback:
        return "localhost"

    if parsed and _is_lan_ip(parsed):
        return "lan"

    if address in {"127.0.0.1", "::1", "localhost"}:
        return "localhost"

    if address in {"", "*", "0.0.0.0", "::"}:
        return "all-interfaces"

    return "non-local"


def get_listening_tcp_ports() -> list[dict[str, Any]]:
    result = _run_cmd(["ss", "-ltnp"])
    if not result.get("ok"):
        result = _run_cmd(["netstat", "-ltnp"])

    ports_by_key: dict[tuple[int, str, str], dict[str, Any]] = {}

    for line in result.get("stdout", "").splitlines():
        if not line or line.lower().startswith(("state", "proto", "active")):
            continue

        parts = line.split()
        local_endpoint = ""
        if parts[0].lower().startswith("tcp") and len(parts) >= 4:
            local_endpoint = parts[3]
        elif len(parts) >= 4:
            local_endpoint = parts[3]

        address, port = _split_address_port(local_endpoint)
        if port is None:
            continue

        bind_scope = _bind_scope(address)
        process = _extract_process(line)
        key = (port, bind_scope, process)
        existing = ports_by_key.get(key)
        if existing:
            if address not in existing["addresses"]:
                existing["addresses"].append(address)
            continue

        ports_by_key[key] = {
            "port": port,
            "protocol": "tcp",
            "bind_scope": bind_scope,
            "addresses": [address],
            "process": process,
            "source": "socket",
        }

    return sorted(ports_by_key.values(), key=lambda item: (item["port"], item["bind_scope"], item["process"]))


def get_docker_published_ports() -> list[dict[str, Any]]:
    if docker is None:
        return []

    try:
        client_docker = docker.from_env()
        containers = client_docker.containers.list()
    except Exception:
        return []

    published_ports = []
    for container in containers:
        ports = (container.attrs.get("NetworkSettings", {}) or {}).get("Ports", {}) or {}
        for container_port, bindings in ports.items():
            if not bindings:
                continue
            for binding in bindings:
                host_ip = binding.get("HostIp") or "0.0.0.0"
                host_port = binding.get("HostPort")
                if not host_port:
                    continue
                published_ports.append({
                    "container": container.name,
                    "container_port": container_port,
                    "host_ip": host_ip,
                    "host_port": int(host_port) if str(host_port).isdigit() else host_port,
                })

    return sorted(published_ports, key=lambda item: (str(item["host_port"]), item["container"], item["container_port"]))


def docker_ports_as_listeners(docker_published_ports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    listeners = []

    for published in docker_published_ports:
        host_port = published.get("host_port")
        if not isinstance(host_port, int):
            continue

        host_ip = published.get("host_ip") or "0.0.0.0"
        listeners.append({
            "port": host_port,
            "protocol": "tcp",
            "bind_scope": _bind_scope(host_ip),
            "addresses": [host_ip],
            "process": f"docker:{published.get('container', 'unknown')}",
            "source": "docker",
        })

    return listeners


def correlate_port_exposure(entries: list[dict[str, Any]], ufw_status: dict[str, Any]) -> list[dict[str, Any]]:
    firewall_enabled = bool(ufw_status.get("enabled"))
    by_port: dict[int, dict[str, Any]] = {}

    for entry in entries:
        port = entry["port"]
        current = by_port.setdefault(
            port,
            {
                "port": port,
                "protocol": "tcp",
                "processes": set(),
                "addresses": set(),
                "bind_scopes": set(),
                "sources": set(),
            },
        )
        current["processes"].add(entry.get("process", "unknown"))
        current["addresses"].update(entry.get("addresses", []))
        current["bind_scopes"].add(entry.get("bind_scope", "unknown"))
        current["sources"].add(entry.get("source", "socket"))

    correlated = []
    for port, entry in by_port.items():
        matching_rules = _matching_ufw_rules(ufw_status, port) if firewall_enabled else []
        source_categories = {rule["source_category"] for rule in matching_rules}
        local_only = entry["bind_scopes"] == {"localhost"}

        if local_only:
            category = "localhost"
            status = "Local Only"
            severity = "good"
        elif firewall_enabled and "public" in source_categories:
            category = "public"
            status = "Public"
            severity = "problem"
        elif firewall_enabled and source_categories and source_categories.issubset({"lan"}):
            category = "lan"
            status = "Secure"
            severity = "good"
        else:
            category = "informational"
            status = "Informational"
            severity = "info"

        correlated.append({
            "port": port,
            "protocol": entry["protocol"],
            "processes": sorted(entry["processes"]),
            "addresses": sorted(entry["addresses"]),
            "bind_scopes": sorted(entry["bind_scopes"]),
            "sources": sorted(entry["sources"]),
            "ufw_rules": matching_rules,
            "category": category,
            "status": status,
            "severity": severity,
        })

    return sorted(correlated, key=lambda item: item["port"])


def _dedupe_ports(entries: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    by_port: dict[int, dict[str, Any]] = {}
    for entry in entries:
        if entry.get("category") != category:
            continue
        port = entry["port"]
        current = by_port.setdefault(port, {**entry, "processes": set(), "addresses": set(), "bind_scopes": set(), "sources": set()})
        current["processes"].update(entry.get("processes", []))
        current["addresses"].update(entry.get("addresses", []))
        current["bind_scopes"].update(entry.get("bind_scopes", []))
        current["sources"].update(entry.get("sources", []))

    normalized = []
    for port, entry in by_port.items():
        normalized.append({**entry, "processes": sorted(entry["processes"]), "addresses": sorted(entry["addresses"]), "bind_scopes": sorted(entry["bind_scopes"]), "sources": sorted(entry["sources"])})
    return sorted(normalized, key=lambda item: item["port"])


def get_ssh_status(public_ports: list[dict[str, Any]], lan_ports: list[dict[str, Any]], localhost_ports: list[dict[str, Any]], informational_ports: list[dict[str, Any]]) -> dict[str, Any]:
    result = _run_cmd(["pgrep", "-x", "sshd"])
    sshd_running = result.get("ok")
    public = any(port.get("port") == 22 for port in public_ports)
    lan = any(port.get("port") == 22 for port in lan_ports)
    localhost = any(port.get("port") == 22 for port in localhost_ports)
    informational = any(port.get("port") == 22 for port in informational_ports)

    if public:
        exposure = "public"
    elif lan:
        exposure = "lan-only"
    elif localhost:
        exposure = "localhost-only"
    elif informational:
        exposure = "informational"
    else:
        exposure = "not-listening"

    return {"running": sshd_running or public or lan or localhost or informational, "exposure": exposure}


def _add_recommendation(recommendations: list[dict[str, str]], severity: str, title: str, detail: str):
    recommendations.append({"severity": severity, "title": title, "detail": detail})


def build_recommendations(firewall_enabled: bool, default_policy: str, public_ports: list[dict[str, Any]], lan_ports: list[dict[str, Any]], localhost_ports: list[dict[str, Any]], informational_ports: list[dict[str, Any]], ssh_status: dict[str, Any]) -> list[dict[str, str]]:
    recommendations: list[dict[str, str]] = []
    public_port_numbers = {entry["port"] for entry in public_ports}
    lan_port_numbers = {entry["port"] for entry in lan_ports}
    localhost_port_numbers = {entry["port"] for entry in localhost_ports}
    informational_port_numbers = {entry["port"] for entry in informational_ports}

    if firewall_enabled:
        _add_recommendation(recommendations, "good", "Firewall enabled.", f"UFW is active with default policy: {default_policy}.")
    else:
        _add_recommendation(recommendations, "problem", "Firewall disabled.", "UFW status reports inactive; enable UFW before treating listener exposure as firewall-restricted.")

    if RCON_PORT in public_port_numbers:
        _add_recommendation(recommendations, "problem", "RCON publicly allowed by UFW.", "Port 25575 is listening and has an active UFW allow rule from Anywhere.")
    elif RCON_PORT in localhost_port_numbers or RCON_PORT in lan_port_numbers:
        _add_recommendation(recommendations, "good", "RCON not publicly exposed.", "Minecraft RCON is localhost-only or restricted to private subnets by UFW.")
    elif RCON_PORT in informational_port_numbers:
        _add_recommendation(recommendations, "info", "RCON listener informational.", "RCON is listening, but no active public UFW allow rule was found.")
    else:
        _add_recommendation(recommendations, "info", "RCON listener not detected.", "No listening RCON port was detected in sockets or Docker published ports.")

    if COMMAND_CENTER_API_PORT in public_port_numbers:
        _add_recommendation(recommendations, "problem", "Command Center API publicly allowed by UFW.", "Port 8787 is listening and has an active UFW allow rule from Anywhere.")
    elif COMMAND_CENTER_API_PORT in lan_port_numbers or COMMAND_CENTER_API_PORT in localhost_port_numbers:
        _add_recommendation(recommendations, "good", "Command Center API limited to LAN.", "Port 8787 is localhost-only or restricted to private subnets by UFW.")
    elif COMMAND_CENTER_API_PORT in informational_port_numbers:
        _add_recommendation(recommendations, "info", "Command Center API informational.", "Port 8787 is listening, but no active public UFW allow rule was found.")
    else:
        _add_recommendation(recommendations, "info", "Command Center API listener not detected.", "No listener for port 8787 was detected.")

    if ssh_status.get("exposure") == "public":
        _add_recommendation(recommendations, "problem", "SSH publicly allowed by UFW.", "Port 22 is listening and has an active UFW allow rule from Anywhere.")
    elif ssh_status.get("running"):
        severity = "info" if ssh_status.get("exposure") == "informational" else "good"
        _add_recommendation(recommendations, severity, "SSH not publicly allowed by UFW.", f"SSH exposure status is {ssh_status.get('exposure')}.")
    else:
        _add_recommendation(recommendations, "good", "SSH not listening.", "No SSH listener was detected.")

    unknown_public = sorted(port for port in public_port_numbers if port not in KNOWN_PUBLIC_PORTS)
    if unknown_public:
        _add_recommendation(recommendations, "problem", "Unknown public ports detected.", f"These ports are listening and publicly allowed by UFW: {', '.join(str(port) for port in unknown_public)}.")
    else:
        _add_recommendation(recommendations, "good", "No unknown public ports detected.", "No unknown listening ports have active UFW allow rules from Anywhere.")

    unknown_informational = sorted(port for port in informational_port_numbers if port not in KNOWN_PUBLIC_PORTS and port not in {RCON_PORT, COMMAND_CENTER_API_PORT})
    if unknown_informational:
        _add_recommendation(recommendations, "info", "Unknown listening ports are informational.", f"These ports are listening but are not publicly allowed by UFW: {', '.join(str(port) for port in unknown_informational)}.")

    return recommendations


def calculate_score(firewall_enabled: bool, public_ports: list[dict[str, Any]], ssh_status: dict[str, Any], recommendations: list[dict[str, str]]) -> int:
    score = 100
    public_port_numbers = {entry["port"] for entry in public_ports}

    if not firewall_enabled:
        score -= 25
    if ssh_status.get("exposure") == "public":
        score -= 20
    if RCON_PORT in public_port_numbers:
        score -= 30
    if COMMAND_CENTER_API_PORT in public_port_numbers:
        score -= 25

    unknown_public = [port for port in public_port_numbers if port not in KNOWN_PUBLIC_PORTS]
    score -= min(25, len(unknown_public) * 8)

    return max(0, min(100, score))


def get_status() -> dict[str, Any]:
    ufw_status = get_ufw_status()
    listening_ports = get_listening_tcp_ports()
    docker_published_ports = get_docker_published_ports()
    observed_ports = listening_ports + docker_ports_as_listeners(docker_published_ports)
    correlated_ports = correlate_port_exposure(observed_ports, ufw_status)
    public_ports = _dedupe_ports(correlated_ports, "public")
    lan_ports = _dedupe_ports(correlated_ports, "lan")
    localhost_ports = _dedupe_ports(correlated_ports, "localhost")
    informational_ports = _dedupe_ports(correlated_ports, "informational")
    ssh_status = get_ssh_status(public_ports, lan_ports, localhost_ports, informational_ports)
    firewall_enabled = bool(ufw_status.get("enabled"))
    default_policy = ufw_status.get("default_policy", "unknown")
    recommendations = build_recommendations(
        firewall_enabled,
        default_policy,
        public_ports,
        lan_ports,
        localhost_ports,
        informational_ports,
        ssh_status,
    )
    score = calculate_score(firewall_enabled, public_ports, ssh_status, recommendations)

    return {
        "score": score,
        "firewall_enabled": firewall_enabled,
        "default_policy": default_policy,
        "ufw": ufw_status,
        "ssh": ssh_status,
        "public_ports": public_ports,
        "lan_ports": lan_ports,
        "localhost_ports": localhost_ports,
        "informational_ports": informational_ports,
        "correlated_ports": correlated_ports,
        "listening_ports": listening_ports,
        "docker_published_ports": docker_published_ports,
        "recommendations": recommendations,
    }
