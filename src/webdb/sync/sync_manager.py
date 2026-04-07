"""Sync manager: orchestrates incremental data sync from web pages to local storage."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from webdb.database.engine import get_session
from webdb.database.models import SyncStatus, SyncTask
from webdb.database.repository import write_audit
from webdb.sync.storage_adapters import get_adapter


@dataclass
class SyncReport:
    task_id: str
    status: SyncStatus
    rows_written: int
    duration_s: float
    error: str | None = None


class SyncManager:
    """Manages the lifecycle of SyncTask records and drives storage writes.

    Typical usage::

        manager = SyncManager()
        manager.register_task(
            site_id="...",
            source_url="https://example.com/data",
            target_type="sqlite",
            target_path="local.db",
            field_mapping={"Name": "name", "Date": "date"},
        )
        report = manager.run_task(task_id="...")
    """

    def register_task(
        self,
        site_id: str,
        source_url: str,
        target_type: str,
        target_path: str,
        field_mapping: dict[str, str] | None = None,
    ) -> str:
        with get_session() as session:
            task = SyncTask(
                site_id=site_id,
                source_url=source_url,
                target_type=target_type,
                target_path=target_path,
                field_mapping=field_mapping,
            )
            session.add(task)
            session.flush()
            return task.id

    def run_task(self, task_id: str, rows: list[dict[str, Any]]) -> SyncReport:
        """Write *rows* (already extracted from the web page) to the configured target.

        Parameters
        ----------
        task_id:
            ID of the SyncTask record.
        rows:
            Extracted data rows (list of dicts) ready for writing.
        """
        start = time.time()

        with get_session() as session:
            task: SyncTask | None = session.get(SyncTask, task_id)
            if task is None:
                raise ValueError(f"SyncTask {task_id!r} not found")

            task.status = SyncStatus.RUNNING
            session.flush()

            try:
                mapped_rows = self._apply_mapping(rows, task.field_mapping)
                adapter = get_adapter(task.target_type, task.target_path)
                written = adapter.write_rows(
                    table_name=_url_to_table_name(task.source_url),
                    rows=mapped_rows,
                )
                task.rows_synced = (task.rows_synced or 0) + written
                task.status = SyncStatus.SUCCESS
                from datetime import datetime
                task.last_synced_at = datetime.utcnow()

                write_audit(
                    session,
                    actor="sync_manager",
                    action="sync.run",
                    outcome="success",
                    resource_type="sync_task",
                    resource_id=task_id,
                    detail={"rows": written},
                )

                duration = time.time() - start
                return SyncReport(
                    task_id=task_id,
                    status=SyncStatus.SUCCESS,
                    rows_written=written,
                    duration_s=duration,
                )
            except Exception as exc:  # noqa: BLE001
                task.status = SyncStatus.FAILED
                task.error_message = str(exc)

                write_audit(
                    session,
                    actor="sync_manager",
                    action="sync.run",
                    outcome="failure",
                    resource_type="sync_task",
                    resource_id=task_id,
                    detail={"error": str(exc)},
                )

                duration = time.time() - start
                return SyncReport(
                    task_id=task_id,
                    status=SyncStatus.FAILED,
                    rows_written=0,
                    duration_s=duration,
                    error=str(exc),
                )

    @staticmethod
    def _apply_mapping(rows: list[dict], mapping: dict | None) -> list[dict]:
        if not mapping:
            return rows
        result = []
        for row in rows:
            new_row = {}
            for src_key, dst_key in mapping.items():
                if src_key in row:
                    new_row[dst_key] = row[src_key]
            # Carry over unmapped keys
            for k, v in row.items():
                if k not in mapping:
                    new_row[k] = v
            result.append(new_row)
        return result


def _url_to_table_name(url: str) -> str:
    """Convert a URL to a safe table name."""
    import re
    name = re.sub(r"https?://", "", url)
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:64] or "webdb_table"
