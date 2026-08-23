#!/usr/bin/env bash
set -euo pipefail

agent_dir="/opt/command-center/backup-agent"
if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo $0" >&2
  exit 1
fi
if [[ ! -f /opt/command-center/config/vera.db ]]; then
  echo "Command Center database was not found." >&2
  exit 1
fi
if ! mountpoint -q /mnt/media; then
  echo "/mnt/media is not mounted; refusing to place backups on the root disk." >&2
  exit 1
fi
install -m 0644 "$agent_dir/vera-backup.service" /etc/systemd/system/
install -m 0644 "$agent_dir/vera-backup.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now vera-backup.timer
systemctl start vera-backup.service
systemctl list-timers vera-backup.timer --no-pager
