#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run this installer with sudo."
  exit 1
fi
if [[ ! -f /etc/vera/server-agent.env ]]; then
  echo "Create /etc/vera/server-agent.env with VERA_COMMAND_CENTER_URL and VERA_SERVER_TOKEN first."
  exit 1
fi
install -d -m 0755 /opt/vera-server-agent
install -m 0755 "$(dirname "$0")/agent.py" /opt/vera-server-agent/agent.py
install -m 0644 "$(dirname "$0")/vera-server-agent.service" /etc/systemd/system/vera-server-agent.service
install -m 0644 "$(dirname "$0")/vera-server-agent.timer" /etc/systemd/system/vera-server-agent.timer
systemctl daemon-reload
systemctl enable --now vera-server-agent.timer
systemctl start vera-server-agent.service
systemctl status vera-server-agent.service --no-pager
