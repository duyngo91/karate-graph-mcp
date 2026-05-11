"""Persistent scan output store for run history and file manifests."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List


class ScanDataStore:
    """Store scan run summaries and file-level change metadata."""

    def __init__(self, storage_dir: Path) -> None:
        self.db_path = storage_dir / "scan_store.sqlite"
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS scan_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                started_at REAL NOT NULL,
                finished_at REAL,
                total_files INTEGER NOT NULL DEFAULT 0,
                changed_files INTEGER NOT NULL DEFAULT 0,
                unchanged_files INTEGER NOT NULL DEFAULT 0,
                deleted_files INTEGER NOT NULL DEFAULT 0,
                nodes INTEGER NOT NULL DEFAULT 0,
                edges INTEGER NOT NULL DEFAULT 0,
                used_cached_graph INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS file_manifest (
                project_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                mtime_ns INTEGER NOT NULL,
                size_bytes INTEGER NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY(project_name, file_path)
            );
            """
        )
        self._conn.commit()

    def start_run(self, project_name: str, total_files: int) -> int:
        now = time.time()
        cur = self._conn.execute(
            """
            INSERT INTO scan_runs(project_name, started_at, total_files)
            VALUES(?, ?, ?)
            """,
            (project_name, now, total_files),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def compare_with_manifest(self, project_name: str, files: List[str]) -> Dict[str, int]:
        previous = {
            row["file_path"]: (int(row["mtime_ns"]), int(row["size_bytes"]))
            for row in self._conn.execute(
                "SELECT file_path, mtime_ns, size_bytes FROM file_manifest WHERE project_name = ?",
                (project_name,),
            )
        }
        current: Dict[str, tuple[int, int]] = {}
        changed = 0
        unchanged = 0

        for file_path in files:
            path_obj = Path(file_path)
            try:
                stat = path_obj.stat()
            except OSError:
                continue
            mtime_ns = int(stat.st_mtime_ns)
            size_bytes = int(stat.st_size)
            current[file_path] = (mtime_ns, size_bytes)
            if previous.get(file_path) == (mtime_ns, size_bytes):
                unchanged += 1
            else:
                changed += 1

        deleted = max(0, len(previous) - len(current))
        return {
            "total_files": len(current),
            "changed_files": changed,
            "unchanged_files": unchanged,
            "deleted_files": deleted,
        }

    def update_manifest(self, project_name: str, files: List[str]) -> None:
        now = time.time()
        rows: List[tuple[str, str, int, int, float]] = []
        existing = set()
        for file_path in files:
            path_obj = Path(file_path)
            try:
                stat = path_obj.stat()
            except OSError:
                continue
            rows.append(
                (
                    project_name,
                    file_path,
                    int(stat.st_mtime_ns),
                    int(stat.st_size),
                    now,
                )
            )
            existing.add(file_path)

        self._conn.execute(
            "DELETE FROM file_manifest WHERE project_name = ?",
            (project_name,),
        )
        self._conn.executemany(
            """
            INSERT INTO file_manifest(project_name, file_path, mtime_ns, size_bytes, updated_at)
            VALUES(?, ?, ?, ?, ?)
            """,
            rows,
        )
        self._conn.commit()

    def finish_run(
        self,
        run_id: int,
        changed_files: int,
        unchanged_files: int,
        deleted_files: int,
        nodes: int,
        edges: int,
        used_cached_graph: bool,
    ) -> None:
        self._conn.execute(
            """
            UPDATE scan_runs
            SET finished_at = ?,
                changed_files = ?,
                unchanged_files = ?,
                deleted_files = ?,
                nodes = ?,
                edges = ?,
                used_cached_graph = ?
            WHERE id = ?
            """,
            (
                time.time(),
                changed_files,
                unchanged_files,
                deleted_files,
                nodes,
                edges,
                1 if used_cached_graph else 0,
                run_id,
            ),
        )
        self._conn.commit()

    def latest_run(self, project_name: str) -> Dict[str, Any]:
        row = self._conn.execute(
            """
            SELECT *
            FROM scan_runs
            WHERE project_name = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (project_name,),
        ).fetchone()
        if row is None:
            return {}
        return dict(row)
