from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Optional

DEFAULT_DB = Path.home() / ".cache" / "archive_indexer" / "index.sqlite"


def default_db_path() -> Path:
    return DEFAULT_DB


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_schema(db_path: str | Path) -> None:
    Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS files (
              id INTEGER PRIMARY KEY,
              root TEXT,
              path TEXT UNIQUE,
              size INTEGER,
              mtime REAL,
              inode INTEGER,
              device INTEGER,
              type TEXT,
              mime TEXT,
              detected_by TEXT,
              last_seen REAL
            );

            CREATE TABLE IF NOT EXISTS scan_errors (
              id INTEGER PRIMARY KEY,
              path TEXT,
              error TEXT,
              timestamp REAL
            );

            CREATE INDEX IF NOT EXISTS idx_files_root ON files(root);
            CREATE INDEX IF NOT EXISTS idx_files_type ON files(type);
            CREATE INDEX IF NOT EXISTS idx_files_last_seen ON files(last_seen);
            CREATE INDEX IF NOT EXISTS idx_errors_timestamp ON scan_errors(timestamp);
            """
        )


class ArchiveDB:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path or default_db_path()).expanduser()
        ensure_schema(self.db_path)

    def connection(self) -> sqlite3.Connection:
        return _connect(self.db_path)

    def upsert_file(self, *, root: str, path: str, size: int, mtime: float, inode: int, device: int, ftype: Optional[str], mime: Optional[str], detected_by: Optional[str], last_seen: float) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO files(root, path, size, mtime, inode, device, type, mime, detected_by, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                  root=excluded.root,
                  size=excluded.size,
                  mtime=excluded.mtime,
                  inode=excluded.inode,
                  device=excluded.device,
                  type=excluded.type,
                  mime=excluded.mime,
                  detected_by=excluded.detected_by,
                  last_seen=excluded.last_seen
                """,
                (root, path, size, mtime, inode, device, ftype, mime, detected_by, last_seen),
            )

    def touch_seen(self, path: str, last_seen: float | None = None) -> None:
        with self.connection() as conn:
            conn.execute("UPDATE files SET last_seen=? WHERE path=?", (last_seen or time.time(), path))

    def get_file(self, path: str):
        with self.connection() as conn:
            return conn.execute("SELECT * FROM files WHERE path=?", (path,)).fetchone()

    def delete_stale_root(self, root: str, scan_started_at: float) -> int:
        with self.connection() as conn:
            cur = conn.execute("DELETE FROM files WHERE root=? AND last_seen < ?", (root, scan_started_at))
            return cur.rowcount or 0

    def insert_error(self, path: str, error: str, timestamp: float | None = None) -> None:
        with self.connection() as conn:
            conn.execute("INSERT INTO scan_errors(path, error, timestamp) VALUES (?, ?, ?)", (path, error, timestamp or time.time()))

    def list_archives(self, q: str | None = None, sort: str = "mtime", limit: int = 1000, offset: int = 0):
        order_map = {
            "mtime": "mtime DESC",
            "size": "size DESC",
            "path": "path ASC",
            "type": "type ASC, path ASC",
            "root": "root ASC, path ASC",
        }
        order_clause = order_map.get(sort, "mtime DESC")
        sql = "SELECT * FROM files WHERE type IS NOT NULL"
        params: list[object] = []
        if q:
            sql += " AND path LIKE ?"
            params.append(f"%{q}%")
        sql += f" ORDER BY {order_clause} LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self.connection() as conn:
            return conn.execute(sql, params).fetchall()

    def list_errors(self, limit: int = 1000, offset: int = 0):
        with self.connection() as conn:
            return conn.execute("SELECT * FROM scan_errors ORDER BY timestamp DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()

    def stats(self) -> dict:
        with self.connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            archives = conn.execute("SELECT COUNT(*) FROM files WHERE type IS NOT NULL").fetchone()[0]
            errors = conn.execute("SELECT COUNT(*) FROM scan_errors").fetchone()[0]
            roots = conn.execute("SELECT COUNT(DISTINCT root) FROM files").fetchone()[0]
            latest = conn.execute("SELECT MAX(last_seen) FROM files").fetchone()[0]
        return {
            "files": total,
            "archives": archives,
            "errors": errors,
            "roots": roots,
            "latest_scan_seen": latest,
            "db_path": str(self.db_path),
        }
