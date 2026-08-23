# Vera Backup & Recovery Agent

The backup agent runs daily at 2:30 AM in `America/Detroit`, before the Monday 3:00 AM maintenance window.

It uses SQLite's online backup API, runs an integrity check, creates an atomic compressed archive, verifies its checksum and database integrity, and then applies retention. The default destination is `/mnt/media/backups/command-center` with 14 daily backups plus the newest backup from each of 8 weeks.

Included:

- `config/vera.db`, copied through SQLite's consistent backup API
- `config/projects.json` and `config/tasks.json` when present
- A checksum manifest

Always excluded:

- `.env`
- The `secrets/` directory
- Gmail OAuth client secrets

Refresh tokens already stored inside Vera's database remain encrypted with the existing token-encryption key. That key is intentionally not included, so the server's separately protected secret files are still required during recovery.

## Install

After migration 18 is applied:

```bash
cd /opt/command-center
sudo ./backup-agent/install.sh
```

The installer waits up to 60 seconds for migration 18 and refuses to continue when `/mnt/media` is not mounted, preventing startup races and accidental backups onto the root disk.

## Verify

```bash
systemctl list-timers vera-backup.timer --no-pager
sudo systemctl status vera-backup.service --no-pager
sudo cat /opt/command-center/config/backup-agent-status.json
sudo /opt/command-center/backup-agent/agent.py verify /mnt/media/backups/command-center/ARCHIVE.tar.gz
```

## Manual restore procedure

Vera cannot trigger a restore. A server administrator must perform it locally:

1. Verify the selected archive with `agent.py verify`.
2. Stop `command-center`, `vera-discord`, and `development-worker` so nothing writes the database.
3. Copy the current `config/vera.db` to a separately named rollback file.
4. Extract only `vera.db` from the verified archive into a temporary directory.
5. Replace `config/vera.db`, preserve its owner and permissions, then restart the containers.
6. Confirm authentication, Gmail status, agent settings, and the Infrastructure page before deleting the rollback copy.

Do not restore `.env` or secret files from an application backup. Manage those through the server's separate secret recovery process.
