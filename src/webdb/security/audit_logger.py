"""Audit logger: writes structured audit events to an append-only JSONL file
and optionally to the database.

Every privileged or state-changing operation in the system should call
``audit_logger.log(...)`` so there is a tamper-evident, human-readable
record of all activity.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from webdb.config.settings import get_settings

logger = structlog.get_logger(__name__)


class AuditLogger:
    """Append-only audit logger backed by a JSONL file.

    Parameters
    ----------
    log_path:
        Path to the JSONL audit log.  Parent directories are created if missing.
    also_log_to_db:
        If True, also write each event to the ``audit_logs`` database table.
    """

    def __init__(
        self,
        log_path: Path | None = None,
        also_log_to_db: bool = False,
    ) -> None:
        self._log_path = log_path or get_settings().audit_log_path
        self._also_db = also_log_to_db
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        actor: str,
        action: str,
        outcome: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        detail: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> None:
        """Write an audit event.

        Parameters
        ----------
        actor:
            User or service that performed the action.
        action:
            Dot-separated action identifier, e.g. ``"credential.store"``.
        outcome:
            ``"success"`` or ``"failure"``.
        resource_type / resource_id:
            Optional reference to the affected resource.
        detail:
            Arbitrary additional context (must be JSON-serialisable).
        ip_address:
            Remote IP of the request, if applicable.
        """
        event: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "actor": actor,
            "action": action,
            "outcome": outcome,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "ip_address": ip_address,
            "detail": detail or {},
        }

        with self._log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

        logger.info("audit", **event)

        if self._also_db:
            try:
                from webdb.database.engine import get_session
                from webdb.database.repository import write_audit

                with get_session() as session:
                    write_audit(
                        session,
                        actor=actor,
                        action=action,
                        outcome=outcome,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        detail=detail,
                        ip_address=ip_address,
                    )
            except Exception:  # noqa: BLE001
                # Never let audit persistence failure crash the main flow
                logger.warning("audit.db_write_failed", action=action)
