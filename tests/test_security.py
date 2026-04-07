"""Tests for the security layer: PII handler, credential manager, audit logger."""

from __future__ import annotations

import pytest

from webdb.security.pii_handler import PIIHandler


class TestPIIHandler:
    @pytest.fixture
    def handler(self):
        return PIIHandler()

    def test_redact_email(self, handler):
        text = "Contact us at user@example.com for help."
        redacted = handler.redact_text(text)
        assert "user@example.com" not in redacted
        assert "[REDACTED]" in redacted

    def test_redact_phone(self, handler):
        text = "Call +1-800-555-1234 now."
        redacted = handler.redact_text(text)
        assert "[REDACTED]" in redacted

    def test_redact_dict_password(self, handler):
        data = {"username": "alice", "password": "supersecret"}
        redacted = handler.redact_dict(data)
        assert redacted["password"] == "[REDACTED]"
        assert redacted["username"] == "alice"

    def test_redact_nested_dict(self, handler):
        data = {"user": {"email": "x@y.com", "name": "Bob"}}
        redacted = handler.redact_dict(data)
        assert "[REDACTED]" in redacted["user"]["email"]

    def test_redact_list_in_dict(self, handler):
        data = {"emails": ["a@b.com", "c@d.com"]}
        redacted = handler.redact_dict(data)
        for email in redacted["emails"]:
            assert "@" not in email or email == "[REDACTED]"

    def test_no_pii(self, handler):
        text = "Hello world, no sensitive data here."
        assert not handler.contains_pii(text)
        assert handler.redact_text(text) == text

    def test_contains_pii_true(self, handler):
        assert handler.contains_pii("email: test@example.org")

    def test_find_pii_returns_types(self, handler):
        text = "email: foo@bar.com"
        found = handler.find_pii(text)
        assert "email" in found
        assert len(found["email"]) >= 1

    def test_custom_placeholder(self):
        handler = PIIHandler(placeholder="***")
        text = "user@example.com"
        assert "***" in handler.redact_text(text)

    def test_chinese_id_card(self, handler):
        text = "ID: 11010519491231002X"
        redacted = handler.redact_text(text)
        assert "11010519491231002X" not in redacted

    def test_ipv4(self, handler):
        text = "Server: 192.168.1.100"
        redacted = handler.redact_text(text)
        assert "192.168.1.100" not in redacted


class TestAuditLogger:
    def test_writes_to_file(self, tmp_path):
        from webdb.security.audit_logger import AuditLogger
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=log_path, also_log_to_db=False)
        logger.log(actor="test", action="test.action", outcome="success")
        assert log_path.exists()
        content = log_path.read_text()
        assert "test.action" in content

    def test_creates_parent_dirs(self, tmp_path):
        from webdb.security.audit_logger import AuditLogger
        log_path = tmp_path / "a" / "b" / "audit.jsonl"
        logger = AuditLogger(log_path=log_path, also_log_to_db=False)
        logger.log(actor="x", action="x.y", outcome="success")
        assert log_path.exists()

    def test_multiple_entries(self, tmp_path):
        from webdb.security.audit_logger import AuditLogger
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=log_path, also_log_to_db=False)
        logger.log(actor="a", action="a.1", outcome="success")
        logger.log(actor="b", action="b.2", outcome="failure")
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_detail_serialised(self, tmp_path):
        import json

        from webdb.security.audit_logger import AuditLogger
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=log_path, also_log_to_db=False)
        logger.log(actor="u", action="op", outcome="success", detail={"rows": 42})
        line = json.loads(log_path.read_text().strip())
        assert line["detail"]["rows"] == 42


class TestCredentialManager:
    @pytest.fixture(autouse=True)
    def _use_test_db(self, tmp_path, monkeypatch):
        """Redirect database to a tmp SQLite file."""
        db_url = f"sqlite:///{tmp_path}/test.db"
        monkeypatch.setenv("WEBDB_DB_URL", db_url)
        # Reset cached engine/session
        import webdb.database.engine as eng
        eng._engine = None
        eng._SessionFactory = None
        from webdb.database.engine import init_db
        init_db(db_url)

    def _key(self):
        from cryptography.fernet import Fernet
        return Fernet.generate_key().decode()

    def test_store_and_retrieve(self, tmp_path):
        from webdb.database.engine import get_session
        from webdb.database.repository import get_or_create_site
        from webdb.security.credential_manager import CredentialManager

        with get_session() as session:
            site = get_or_create_site(session, "https://example.com")
            site_id = site.id

        key = self._key()
        mgr = CredentialManager(encryption_key=key)
        mgr.store(site_id=site_id, username="admin", secret="hunter2")
        secret = mgr.retrieve(site_id=site_id, username="admin")
        assert secret == "hunter2"

    def test_retrieve_missing_returns_none(self, tmp_path):
        from webdb.security.credential_manager import CredentialManager
        mgr = CredentialManager(encryption_key=self._key())
        assert mgr.retrieve("nonexistent", "user") is None

    def test_delete(self, tmp_path):
        from webdb.database.engine import get_session
        from webdb.database.repository import get_or_create_site
        from webdb.security.credential_manager import CredentialManager

        with get_session() as session:
            site = get_or_create_site(session, "https://example.com")
            site_id = site.id

        key = self._key()
        mgr = CredentialManager(encryption_key=key)
        mgr.store(site_id=site_id, username="user", secret="pass")
        deleted = mgr.delete(site_id=site_id, username="user")
        assert deleted is True
        assert mgr.retrieve(site_id=site_id, username="user") is None
