"""Central configuration via environment variables or .env file.

All settings are prefixed with ``WEBDB_`` when read from the environment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for webdb-Engine."""

    model_config = SettingsConfigDict(
        env_prefix="WEBDB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ────────────────────────────────────────────────────────────
    db_url: str = Field(
        default="sqlite:///webdb.db",
        description="SQLAlchemy database URL for the page knowledge base.",
    )

    # ── Browser / Playwright ─────────────────────────────────────────────────
    browser_type: Literal["chromium", "firefox", "webkit"] = Field(
        default="chromium",
        description="Playwright browser to use for page collection.",
    )
    browser_headless: bool = Field(
        default=True,
        description="Run browser in headless mode.",
    )
    browser_timeout_ms: int = Field(
        default=30_000,
        description="Default Playwright timeout in milliseconds.",
    )
    browser_sandbox: bool = Field(
        default=True,
        description="Enforce extra browser sandbox args.",
    )

    # ── Executor ─────────────────────────────────────────────────────────────
    executor_max_retries: int = Field(
        default=3,
        description="Maximum number of retries per action step.",
    )
    executor_retry_delay_s: float = Field(
        default=1.5,
        description="Seconds to wait between retries.",
    )

    # ── Security / Credentials ───────────────────────────────────────────────
    credential_encryption_key: SecretStr = Field(
        default=SecretStr(""),
        description=(
            "Fernet symmetric key for encrypting stored credentials. "
            "Generate with: python -c "
            "\"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        ),
    )
    audit_log_path: Path = Field(
        default=Path("logs/audit.jsonl"),
        description="Path to the append-only audit log.",
    )

    # ── PII handling ─────────────────────────────────────────────────────────
    pii_redact_enabled: bool = Field(
        default=True,
        description="Redact PII fields in collected page data before storage.",
    )

    # ── Sync ─────────────────────────────────────────────────────────────────
    sync_batch_size: int = Field(
        default=500,
        description="Number of rows per batch during incremental sync.",
    )
    sync_default_target: Literal["sqlite", "postgres", "csv", "parquet"] = Field(
        default="sqlite",
        description="Default sync storage backend.",
    )

    # ── Training pipeline ────────────────────────────────────────────────────
    training_data_dir: Path = Field(
        default=Path("data/training"),
        description="Root directory for all training data artifacts.",
    )

    # ── Annotation ───────────────────────────────────────────────────────────
    annotation_auto_capture: bool = Field(
        default=True,
        description="Automatically queue failed steps for human annotation.",
    )

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Minimum log level.",
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return (and cache) the global Settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
