#!/bin/sh
set -u

WORKSPACE_PATH="${COMMAND_CENTER_WORKSPACE:-/workspace/command-center}"
STATUS_FILE="${WORKER_STATUS_FILE:-/tmp/development-worker-status.json}"

write_status() {
    status="$1"
    message="$2"
    updated_utc="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    printf '{"worker_status":"%s","status":"%s","message":"%s","updated_utc":"%s"}\n' \
        "$status" "$status" "$message" "$updated_utc" > "$STATUS_FILE"
}

echo "Worker starting..."
write_status "Starting" "Worker starting..."

degraded=0

echo "Checking workspace..."
if [ -d "$WORKSPACE_PATH" ]; then
    echo "Workspace found."
else
    echo "Workspace missing."
    degraded=1
fi

echo "Configuring git..."
if command -v git >/dev/null 2>&1 && git config --global --add safe.directory "$WORKSPACE_PATH"; then
    echo "Git configured."
else
    echo "Git configuration failed."
    degraded=1
fi

echo "Checking tools..."
check_tool() {
    command_name="$1"
    display_name="$2"
    if command -v "$command_name" >/dev/null 2>&1; then
        echo "$display_name ✓"
    else
        echo "$display_name missing"
        degraded=1
    fi
}

check_tool git "Git"
check_tool docker "Docker"
check_tool python3 "Python"
check_tool node "Node"
check_tool npm "NPM"
check_tool jq "JQ"

if [ "$degraded" -eq 0 ]; then
    write_status "Ready" "Worker ready."
    echo "Worker ready."
else
    write_status "Degraded" "Worker degraded."
    echo "Worker degraded."
fi

exec tail -f /dev/null