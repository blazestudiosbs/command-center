#!/usr/bin/env python3
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(os.getenv("COMMAND_CENTER_ROOT", "/opt/command-center"))
CONFIG = ROOT / "config"
DATABASE = CONFIG / "vera.db"
STATUS_FILE = CONFIG / "backup-agent-status.json"
APPROVED_CONFIG = ("projects.json", "tasks.json")


def now():
    return datetime.now(timezone.utc)


def iso(value=None):
    return (value or now()).isoformat().replace("+00:00", "Z")


def settings():
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM backup_agent_settings WHERE id = 'global'").fetchone()
    if not row:
        raise RuntimeError("Backup settings are unavailable; apply Command Center migrations first.")
    return dict(row)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_status(payload):
    CONFIG.mkdir(parents=True, exist_ok=True)
    temporary = STATUS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, STATUS_FILE)


def snapshot_database(target):
    source = sqlite3.connect(f"file:{DATABASE}?mode=ro", uri=True)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
        result = destination.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {result}")
    finally:
        destination.close()
        source.close()


def verify_archive(path):
    with tarfile.open(path, "r:gz") as archive:
        names = set(archive.getnames())
        if "manifest.json" not in names or "vera.db" not in names:
            raise RuntimeError("Backup archive is missing required files.")
        allowed_names = {"manifest.json", "vera.db", *APPROVED_CONFIG}
        if not names.issubset(allowed_names):
            raise RuntimeError("Backup archive contains an unexpected file.")
        manifest = json.load(archive.extractfile("manifest.json"))
        if set(manifest.get("files", {})) != names - {"manifest.json"}:
            raise RuntimeError("Backup manifest does not match the archive contents.")
        with tempfile.TemporaryDirectory(prefix="vera-verify-") as temporary:
            for name, expected_checksum in manifest["files"].items():
                extracted = Path(temporary) / name
                with archive.extractfile(name) as source, extracted.open("wb") as target:
                    shutil.copyfileobj(source, target)
                if sha256(extracted) != expected_checksum:
                    raise RuntimeError(f"Backup checksum failed for {name}.")
            database = Path(temporary) / "vera.db"
            with sqlite3.connect(database) as conn:
                if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Backup database failed its integrity check.")
    return manifest


def prune(destination, daily_retention, weekly_retention):
    archives = sorted(destination.glob("command-center-*.tar.gz"), reverse=True)
    keep = set(archives[:daily_retention])
    weeks = set()
    for archive in archives:
        try:
            stamp = archive.name.removeprefix("command-center-").removesuffix(".tar.gz")
            created = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        week = created.strftime("%G-W%V")
        if week not in weeks and len(weeks) < weekly_retention:
            weeks.add(week)
            keep.add(archive)
    removed = 0
    for archive in archives:
        if archive not in keep:
            archive.unlink()
            removed += 1
    return removed


def run_backup():
    started = now()
    try:
        config = settings()
        if not config["enabled"]:
            write_status({"status": "disabled", "started_utc": iso(started), "completed_utc": iso()})
            return 0
        destination = Path(config["destination"])
        if str(destination).startswith("/mnt/media/") and not os.path.ismount("/mnt/media"):
            raise RuntimeError("The media backup disk is not mounted; refusing to write backups to the root disk.")
        destination.mkdir(parents=True, exist_ok=True)
        os.chmod(destination, 0o700)
        filename = f"command-center-{started.strftime('%Y%m%dT%H%M%SZ')}.tar.gz"
        final_path = destination / filename
        with tempfile.TemporaryDirectory(prefix="vera-backup-") as temporary_name:
            temporary = Path(temporary_name)
            database_copy = temporary / "vera.db"
            snapshot_database(database_copy)
            files = {"vera.db": sha256(database_copy)}
            included = ["vera.db"]
            for name in APPROVED_CONFIG:
                source = CONFIG / name
                if source.is_file():
                    copied = temporary / name
                    shutil.copy2(source, copied)
                    files[name] = sha256(copied)
                    included.append(name)
            manifest = {
                "created_utc": iso(started), "format_version": 1,
                "files": files, "excluded": [".env", "secrets/", "OAuth client secrets"],
            }
            (temporary / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            partial = destination / f".{filename}.partial"
            with tarfile.open(partial, "w:gz") as archive:
                archive.add(temporary / "manifest.json", arcname="manifest.json")
                for name in included:
                    archive.add(temporary / name, arcname=name)
            os.chmod(partial, 0o600)
            os.replace(partial, final_path)
        verified = verify_archive(final_path)
        removed = prune(destination, int(config["daily_retention"]), int(config["weekly_retention"]))
        write_status({
            "status": "completed", "started_utc": iso(started), "completed_utc": iso(),
            "archive": str(final_path), "size_bytes": final_path.stat().st_size,
            "verified": True, "database_integrity": "ok", "files": list(verified["files"]),
            "pruned_archives": removed, "secrets_included": False,
        })
        return 0
    except Exception as exc:
        write_status({"status": "failed", "started_utc": iso(started), "completed_utc": iso(), "error": f"{type(exc).__name__}: {exc}"[:1000]})
        return 1


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "run"
    if action == "run":
        raise SystemExit(run_backup())
    if action == "verify" and len(sys.argv) == 3:
        print(json.dumps(verify_archive(Path(sys.argv[2])), indent=2))
        raise SystemExit(0)
    raise SystemExit("Usage: agent.py [run | verify ARCHIVE]")
