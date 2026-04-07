"""Storage adapters for local data synchronization.

Supports: SQLite, PostgreSQL (via SQLAlchemy), CSV, Parquet.
"""

from __future__ import annotations

import csv
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class BaseStorageAdapter(ABC):
    """Abstract storage adapter interface."""

    @abstractmethod
    def write_rows(self, table_name: str, rows: list[dict[str, Any]]) -> int:
        """Persist *rows* to *table_name* and return the number of rows written."""

    @abstractmethod
    def read_rows(self, table_name: str, limit: int = 1000) -> list[dict[str, Any]]:
        """Return up to *limit* rows from *table_name*."""

    @abstractmethod
    def get_last_cursor(self, table_name: str) -> str | None:
        """Return the last sync cursor (e.g. max ``updated_at``) for incremental sync."""


class SQLiteAdapter(BaseStorageAdapter):
    """Stores rows in a local SQLite database using sqlite3 directly."""

    def __init__(self, db_path: str | Path) -> None:
        import sqlite3

        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    def _ensure_table(self, table_name: str, columns: list[str]) -> None:
        col_defs = ", ".join(f'"{c}" TEXT' for c in columns)
        self._conn.execute(
            f'CREATE TABLE IF NOT EXISTS "{table_name}" ({col_defs})'
        )
        # Add any missing columns (schema evolution)
        existing = {row[1] for row in self._conn.execute(f'PRAGMA table_info("{table_name}")')}
        for col in columns:
            if col not in existing:
                self._conn.execute(f'ALTER TABLE "{table_name}" ADD COLUMN "{col}" TEXT')
        self._conn.commit()

    def write_rows(self, table_name: str, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        columns = list(rows[0].keys())
        self._ensure_table(table_name, columns)
        placeholders = ", ".join("?" for _ in columns)
        col_names = ", ".join(f'"{c}"' for c in columns)
        sql = f'INSERT OR REPLACE INTO "{table_name}" ({col_names}) VALUES ({placeholders})'
        values = [
            [json.dumps(v) if isinstance(v, (dict, list)) else v for v in row.values()]
            for row in rows
        ]
        self._conn.executemany(sql, values)
        self._conn.commit()
        return len(rows)

    def read_rows(self, table_name: str, limit: int = 1000) -> list[dict[str, Any]]:
        cursor = self._conn.execute(f'SELECT * FROM "{table_name}" LIMIT {limit}')
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def get_last_cursor(self, table_name: str) -> str | None:
        try:
            row = self._conn.execute(
                f'SELECT MAX(updated_at) FROM "{table_name}"'
            ).fetchone()
            return row[0] if row else None
        except Exception:  # noqa: BLE001
            return None

    def close(self) -> None:
        self._conn.close()


class CSVAdapter(BaseStorageAdapter):
    """Appends rows to CSV files in a directory."""

    def __init__(self, output_dir: str | Path) -> None:
        self._dir = Path(output_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, table_name: str) -> Path:
        return self._dir / f"{table_name}.csv"

    def write_rows(self, table_name: str, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        path = self._path(table_name)
        write_header = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), extrasaction="ignore")
            if write_header:
                writer.writeheader()
            writer.writerows(rows)
        return len(rows)

    def read_rows(self, table_name: str, limit: int = 1000) -> list[dict[str, Any]]:
        path = self._path(table_name)
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            return [row for _, row in zip(range(limit), reader)]

    def get_last_cursor(self, table_name: str) -> str | None:
        rows = self.read_rows(table_name, limit=999_999)
        cursors = [r.get("updated_at") for r in rows if r.get("updated_at")]
        return max(cursors) if cursors else None


class ParquetAdapter(BaseStorageAdapter):
    """Writes rows to Parquet files using PyArrow."""

    def __init__(self, output_dir: str | Path) -> None:
        self._dir = Path(output_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, table_name: str) -> Path:
        return self._dir / f"{table_name}.parquet"

    def write_rows(self, table_name: str, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        import pyarrow as pa
        import pyarrow.parquet as pq

        path = self._path(table_name)
        new_table = pa.Table.from_pylist(rows)
        if path.exists():
            existing = pq.read_table(str(path))
            combined = pa.concat_tables([existing, new_table])
        else:
            combined = new_table
        pq.write_table(combined, str(path))
        return len(rows)

    def read_rows(self, table_name: str, limit: int = 1000) -> list[dict[str, Any]]:
        import pyarrow.parquet as pq

        path = self._path(table_name)
        if not path.exists():
            return []
        table = pq.read_table(str(path))
        return table.slice(0, limit).to_pylist()

    def get_last_cursor(self, table_name: str) -> str | None:
        rows = self.read_rows(table_name, limit=999_999)
        cursors = [str(r["updated_at"]) for r in rows if r.get("updated_at")]
        return max(cursors) if cursors else None


def get_adapter(target_type: str, path: str | Path) -> BaseStorageAdapter:
    """Factory function returning the appropriate storage adapter."""
    target_type = target_type.lower()
    if target_type == "sqlite":
        return SQLiteAdapter(path)
    if target_type == "csv":
        return CSVAdapter(path)
    if target_type == "parquet":
        return ParquetAdapter(path)
    raise ValueError(f"Unsupported storage adapter: {target_type!r}")
