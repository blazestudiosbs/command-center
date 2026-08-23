# Vera Infrastructure Agents

These host-side agents deliberately run outside the Command Center container so the web application does not receive unrestricted root access to the server.

## Update agent

- Runs Monday at 3:00 AM in `America/Detroit`.
- Uses Ubuntu's `unattended-upgrade` configuration, which should be restricted to configured security origins.
- Does not update Docker images.
- Does not reboot the server.
- Runs the health agent after maintenance and reports when a manual reboot is required.

The installer checks APT's effective unattended-upgrade origins and refuses to continue if it detects updates, backports, or third-party/PPA origins. It also installs a final APT override that forces automatic reboot off. Ubuntu's default daily upgrade timer is disabled so Vera's Monday maintenance window is authoritative; the package-list refresh timer remains untouched.

## Health agent

- Runs every 15 minutes.
- Reads disk and memory pressure, failed systemd units, Docker container state, and recent error-priority journal entries.
- Records findings in `config/infrastructure-agent-status.json` for Command Center.
- Never restarts services or changes system configuration.
- Command Center sends a Discord alert only when the detected issue set changes.

## Install on the server

After pulling the release and rebuilding Command Center so migration 17 is applied:

```bash
cd /opt/command-center
sudo ./infrastructure-agent/install.sh
```

Verify the timers and initial report:

```bash
systemctl list-timers vera-infrastructure-health.timer vera-security-update.timer --no-pager
sudo systemctl status vera-infrastructure-health.service --no-pager
cat /opt/command-center/config/infrastructure-agent-status.json
```

The agents can be turned off from the Infrastructure page. Disabling a setting leaves its systemd timer installed, but the runner exits safely without performing that operation.

## Remove the timers

```bash
sudo systemctl disable --now vera-infrastructure-health.timer vera-security-update.timer
sudo rm /etc/systemd/system/vera-infrastructure-health.service \
  /etc/systemd/system/vera-infrastructure-health.timer \
  /etc/systemd/system/vera-security-update.service \
  /etc/systemd/system/vera-security-update.timer
sudo rm -f /etc/apt/apt.conf.d/99vera-no-automatic-reboot
sudo systemctl enable --now apt-daily-upgrade.timer
sudo systemctl daemon-reload
```
