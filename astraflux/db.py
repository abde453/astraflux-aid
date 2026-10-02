"""SQLite persistence (stdlib only). Path from env ASTRAFLUX_DB, default ~/.astraflux/astraflux.db."""
import os, sqlite3, uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, name TEXT NOT NULL, notes TEXT DEFAULT '', archived INTEGER DEFAULT 0, created TEXT, updated TEXT, workspace TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS formulations(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, name TEXT, body TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, run_id TEXT, request TEXT, summary TEXT, series TEXT, model_version TEXT, data_version TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS datasets(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, name TEXT, kind TEXT, raw_csv TEXT, mapping TEXT, points TEXT, source TEXT, conditions TEXT, warnings TEXT, created TEXT);
"""
TABLES = ("projects", "formulations", "runs", "datasets")


def db_path() -> Path:
    return Path(os.environ.get("ASTRAFLUX_DB") or Path.home() / ".astraflux" / "astraflux.db")


def now() -> str: return datetime.now(timezone.utc).isoformat(timespec="seconds")
def new_id() -> str: return uuid.uuid4().hex[:12]


@contextmanager
def conn():
    p = db_path(); p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p, timeout=10); c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); c.executescript(SCHEMA)
    if "workspace" not in [r[1] for r in c.execute("PRAGMA table_info(projects)")]:
        c.execute("ALTER TABLE projects ADD COLUMN workspace TEXT DEFAULT ''")
    try:
        yield c; c.commit()
    finally:
        c.close()
