"""SQLite + automatic, tracked migrations.

Migrations live in image_service/migrations/NNN_*.sql and are applied in
filename order. Each applied migration is recorded in the schema_migrations
table inside a transaction, so a partial run leaves the DB in a known state
and the failure shows up loudly in the log.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)

SERVICE_DIR = Path(__file__).resolve().parent
DATA_DIR = SERVICE_DIR / "data"
DB_PATH = DATA_DIR / "images.db"
IMAGES_DIR = DATA_DIR / "images"
THUMBS_DIR = DATA_DIR / "thumbs"
MIGRATIONS_DIR = SERVICE_DIR / "migrations"


def ensure_dirs() -> None:
    for d in (DATA_DIR, IMAGES_DIR, THUMBS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def connect() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name        TEXT PRIMARY KEY,
            applied_at  TEXT NOT NULL DEFAULT (datetime('now')),
            status      TEXT NOT NULL              -- 'ok' or 'failed:<msg>'
        )
        """
    )


def _applied(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM schema_migrations WHERE status = 'ok'"
    ).fetchall()
    return {r["name"] for r in rows}


def _migration_files() -> Iterator[Path]:
    if not MIGRATIONS_DIR.exists():
        return iter(())
    return iter(sorted(MIGRATIONS_DIR.glob("*.sql")))


def migrate() -> None:
    """Apply any pending migrations. Loud failures, partial-run safe."""
    ensure_dirs()
    conn = connect()
    try:
        _ensure_migrations_table(conn)
        applied = _applied(conn)
        for path in _migration_files():
            if path.name in applied:
                continue
            sql = path.read_text()
            log.info("applying migration %s", path.name)
            try:
                # executescript manages its own transaction wrapping; just run it.
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (name, status) VALUES (?, 'ok')",
                    (path.name,),
                )
            except Exception as e:
                conn.execute(
                    "INSERT OR REPLACE INTO schema_migrations (name, status) "
                    "VALUES (?, ?)",
                    (path.name, f"failed:{e}"),
                )
                log.error("migration %s failed: %s", path.name, e)
                raise
    finally:
        conn.close()
