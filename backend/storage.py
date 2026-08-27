import os
import sqlite3
import fcntl
from contextlib import contextmanager
from pathlib import Path


DEFAULT_DATABASE_PATH = Path("/app/config/vera.db")
MIGRATIONS_PATH = Path(__file__).resolve().parent / "migrations"


def database_path() -> Path:
    configured = os.getenv("VERA_DATABASE_PATH")
    if configured:
        return Path(configured)
    if DEFAULT_DATABASE_PATH.parent.exists():
        return DEFAULT_DATABASE_PATH
    return Path(__file__).resolve().parents[1] / "config" / "vera.db"


@contextmanager
def connection():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_storage() -> None:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".migrations.lock")
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        with connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    applied_utc TEXT NOT NULL
                )
                """,
            )
            applied = {
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
            }
            for migration in sorted(MIGRATIONS_PATH.glob("*.sql")):
                version_text, _, name = migration.stem.partition("_")
                version = int(version_text)
                if version in applied:
                    continue
                conn.executescript(migration.read_text(encoding="utf-8"))
                conn.execute(
                    """
                    INSERT INTO schema_migrations (version, name, applied_utc)
                    VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    """,
                    (version, name),
                )
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
