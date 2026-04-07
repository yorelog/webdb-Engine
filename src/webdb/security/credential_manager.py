"""Credential manager: stores and retrieves encrypted site credentials.

Credentials are encrypted with Fernet symmetric encryption before being
persisted to the database.  The key is loaded from the WEBDB_CREDENTIAL_ENCRYPTION_KEY
environment variable.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from webdb.config.settings import get_settings
from webdb.database.engine import get_session
from webdb.database.repository import upsert_credential, write_audit


class CredentialManager:
    """Manages encrypted site credentials.

    Usage::

        mgr = CredentialManager()
        mgr.store(site_id="...", username="admin", secret="p@ssw0rd")
        secret = mgr.retrieve(site_id="...", username="admin")
    """

    def __init__(self, encryption_key: str | None = None) -> None:
        key = encryption_key or get_settings().credential_encryption_key.get_secret_value()
        if not key:
            # Generate an ephemeral key (dev / test only; warn loudly)
            key = Fernet.generate_key().decode()
            import warnings
            warnings.warn(
                "No WEBDB_CREDENTIAL_ENCRYPTION_KEY set.  "
                "Using a one-time ephemeral key — credentials cannot be recovered after restart.",
                stacklevel=2,
            )
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def store(
        self,
        site_id: str,
        username: str,
        secret: str,
        credential_type: str = "password",
        actor: str = "system",
    ) -> None:
        """Encrypt and store a credential."""
        encrypted = self._fernet.encrypt(secret.encode())
        with get_session() as session:
            upsert_credential(session, site_id, username, encrypted, credential_type)
            write_audit(
                session,
                actor=actor,
                action="credential.store",
                outcome="success",
                resource_type="credential",
                resource_id=site_id,
            )

    def retrieve(self, site_id: str, username: str) -> str | None:
        """Decrypt and return the credential secret, or None if not found."""
        from sqlalchemy import select

        from webdb.database.models import Credential

        with get_session() as session:
            cred = session.scalar(
                select(Credential).where(
                    Credential.site_id == site_id,
                    Credential.username == username,
                )
            )
            if cred is None:
                return None
            try:
                return self._fernet.decrypt(cred.encrypted_secret).decode()
            except InvalidToken:
                return None

    def delete(self, site_id: str, username: str, actor: str = "system") -> bool:
        """Delete a stored credential.  Returns True if found and deleted."""
        from sqlalchemy import select

        from webdb.database.models import Credential

        with get_session() as session:
            cred = session.scalar(
                select(Credential).where(
                    Credential.site_id == site_id,
                    Credential.username == username,
                )
            )
            if cred is None:
                return False
            session.delete(cred)
            write_audit(
                session,
                actor=actor,
                action="credential.delete",
                outcome="success",
                resource_type="credential",
                resource_id=site_id,
            )
            return True
