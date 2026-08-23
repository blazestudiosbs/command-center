#!/usr/bin/env bash
set -euo pipefail

agent_dir="/opt/command-center/infrastructure-agent"
if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo $0" >&2
  exit 1
fi
if ! command -v unattended-upgrade >/dev/null 2>&1; then
  echo "unattended-upgrade is required. Install it with: sudo apt install unattended-upgrades" >&2
  exit 1
fi
allowed_origins="$(apt-config dump | grep -E 'Unattended-Upgrade::(Allowed-Origins|Origins-Pattern)' || true)"
if grep -Eiq -- '-updates|-backports|LP-PPA|site=' <<<"$allowed_origins"; then
  echo "Refusing installation: unattended-upgrades currently allows a non-security update origin." >&2
  echo "$allowed_origins" >&2
  echo "Restrict the allowed origins to Ubuntu security/ESM security sources, then retry." >&2
  exit 1
fi
install -m 0644 "$agent_dir/99vera-no-automatic-reboot" /etc/apt/apt.conf.d/99vera-no-automatic-reboot
install -m 0644 "$agent_dir/vera-infrastructure-health.service" /etc/systemd/system/
install -m 0644 "$agent_dir/vera-infrastructure-health.timer" /etc/systemd/system/
install -m 0644 "$agent_dir/vera-security-update.service" /etc/systemd/system/
install -m 0644 "$agent_dir/vera-security-update.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl disable --now apt-daily-upgrade.timer >/dev/null 2>&1 || true
systemctl enable --now vera-infrastructure-health.timer vera-security-update.timer
systemctl start vera-infrastructure-health.service
systemctl list-timers vera-infrastructure-health.timer vera-security-update.timer --no-pager
