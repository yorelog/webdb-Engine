"""SQLAlchemy ORM models for the webdb page knowledge base.

Entity hierarchy
----------------
Site → Page → Element
              Action → ActionStep
              Trajectory (ordered list of ActionSteps)
              SyncTask
              AnnotationTask
              TrainingRecord
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# ── Helpers ──────────────────────────────────────────────────────────────────

def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


# ── Base ─────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Enumerations ─────────────────────────────────────────────────────────────

class PageType(enum.StrEnum):
    LOGIN = "login"
    LIST = "list"
    DETAIL = "detail"
    FORM = "form"
    DASHBOARD = "dashboard"
    SEARCH = "search"
    DOWNLOAD = "download"
    UNKNOWN = "unknown"


class ElementRole(enum.StrEnum):
    FIELD = "field"
    ACTION = "action"
    NAVIGATION = "navigation"
    STATUS = "status"
    DATA = "data"
    PAGINATION = "pagination"
    UNKNOWN = "unknown"


class ActionType(enum.StrEnum):
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    SUBMIT = "submit"
    DOWNLOAD = "download"
    WAIT = "wait"
    NAVIGATE = "navigate"
    SCROLL = "scroll"
    HOVER = "hover"
    EXTRACT = "extract"
    SYNC = "sync"


class ActionStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


class AnnotationStatus(enum.StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"


class SyncStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class TrainingDataType(enum.StrEnum):
    SFT = "sft"                 # Supervised fine-tuning sample
    PREFERENCE = "preference"   # Chosen/rejected pair for DPO/RLHF
    REWARD = "reward"           # Scalar reward label
    FAILURE = "failure"         # Failed trajectory for negative training


# ── Core entities ─────────────────────────────────────────────────────────────

class Site(Base):
    """Represents a unique website / origin."""

    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    origin: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    login_url: Mapped[str | None] = mapped_column(String(2048))
    meta: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    pages: Mapped[list[Page]] = relationship(back_populates="site", cascade="all, delete-orphan")
    credentials: Mapped[list[Credential]] = relationship(back_populates="site", cascade="all, delete-orphan")
    sync_tasks: Mapped[list[SyncTask]] = relationship(back_populates="site", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Site origin={self.origin!r}>"


class Page(Base):
    """A collected snapshot of a specific page URL."""

    __tablename__ = "pages"
    __table_args__ = (
        Index("ix_pages_site_url", "site_id", "url"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512))
    page_type: Mapped[PageType] = mapped_column(Enum(PageType), default=PageType.UNKNOWN)
    html: Mapped[str | None] = mapped_column(Text)
    rendered_dom: Mapped[str | None] = mapped_column(Text)
    screenshot_path: Mapped[str | None] = mapped_column(String(1024))
    accessibility_tree: Mapped[dict | None] = mapped_column(JSON)
    har: Mapped[dict | None] = mapped_column(JSON)
    bounding_boxes: Mapped[dict | None] = mapped_column(JSON)
    meta: Mapped[dict | None] = mapped_column(JSON)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    site: Mapped[Site] = relationship(back_populates="pages")
    elements: Mapped[list[Element]] = relationship(back_populates="page", cascade="all, delete-orphan")
    trajectories: Mapped[list[Trajectory]] = relationship(back_populates="page", cascade="all, delete-orphan")
    annotation_tasks: Mapped[list[AnnotationTask]] = relationship(back_populates="page", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Page url={self.url!r} type={self.page_type}>"


class Element(Base):
    """A semantic element extracted from a collected page."""

    __tablename__ = "elements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    page_id: Mapped[str] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[ElementRole] = mapped_column(Enum(ElementRole), default=ElementRole.UNKNOWN)
    tag: Mapped[str | None] = mapped_column(String(64))
    label: Mapped[str | None] = mapped_column(String(512))
    selector: Mapped[str | None] = mapped_column(Text)
    xpath: Mapped[str | None] = mapped_column(Text)
    aria_label: Mapped[str | None] = mapped_column(String(512))
    bounding_box: Mapped[dict | None] = mapped_column(JSON)
    attributes: Mapped[dict | None] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_interactive: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    page: Mapped[Page] = relationship(back_populates="elements")

    def __repr__(self) -> str:
        return f"<Element role={self.role} label={self.label!r}>"


# ── Action & Trajectory ───────────────────────────────────────────────────────

class Trajectory(Base):
    """An ordered sequence of ActionSteps that together complete a task."""

    __tablename__ = "trajectories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    page_id: Mapped[str] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    goal: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ActionStatus] = mapped_column(Enum(ActionStatus), default=ActionStatus.PENDING)
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    successful_steps: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict | None] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    page: Mapped[Page] = relationship(back_populates="trajectories")
    steps: Mapped[list[ActionStep]] = relationship(
        back_populates="trajectory",
        order_by="ActionStep.step_index",
        cascade="all, delete-orphan",
    )
    annotation_tasks: Mapped[list[AnnotationTask]] = relationship(
        back_populates="trajectory", cascade="all, delete-orphan"
    )
    training_records: Mapped[list[TrainingRecord]] = relationship(
        back_populates="trajectory", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Trajectory goal={self.goal!r} status={self.status}>"


class ActionStep(Base):
    """A single executable action within a Trajectory."""

    __tablename__ = "action_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trajectory_id: Mapped[str] = mapped_column(
        ForeignKey("trajectories.id", ondelete="CASCADE"), nullable=False
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[ActionType] = mapped_column(Enum(ActionType), nullable=False)
    selector: Mapped[str | None] = mapped_column(Text)
    value: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ActionStatus] = mapped_column(Enum(ActionStatus), default=ActionStatus.PENDING)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    before_screenshot_path: Mapped[str | None] = mapped_column(String(1024))
    after_screenshot_path: Mapped[str | None] = mapped_column(String(1024))
    before_dom_hash: Mapped[str | None] = mapped_column(String(64))
    after_dom_hash: Mapped[str | None] = mapped_column(String(64))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    meta: Mapped[dict | None] = mapped_column(JSON)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    trajectory: Mapped[Trajectory] = relationship(back_populates="steps")

    def __repr__(self) -> str:
        return f"<ActionStep #{self.step_index} {self.action_type} status={self.status}>"


# ── Credentials ───────────────────────────────────────────────────────────────

class Credential(Base):
    """Encrypted credential for a site (username + password / token)."""

    __tablename__ = "credentials"
    __table_args__ = (
        UniqueConstraint("site_id", "username", name="uq_credential_site_user"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    username: Mapped[str] = mapped_column(String(512), nullable=False)
    encrypted_secret: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    credential_type: Mapped[str] = mapped_column(String(32), default="password")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    site: Mapped[Site] = relationship(back_populates="credentials")

    def __repr__(self) -> str:
        return f"<Credential site={self.site_id} user={self.username!r}>"


# ── Sync ──────────────────────────────────────────────────────────────────────

class SyncTask(Base):
    """Describes an ongoing or scheduled data sync from a page to local storage."""

    __tablename__ = "sync_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    field_mapping: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[SyncStatus] = mapped_column(Enum(SyncStatus), default=SyncStatus.PENDING)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_cursor: Mapped[str | None] = mapped_column(Text)
    rows_synced: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    site: Mapped[Site] = relationship(back_populates="sync_tasks")

    def __repr__(self) -> str:
        return f"<SyncTask url={self.source_url!r} target={self.target_type}>"


# ── Annotation ────────────────────────────────────────────────────────────────

class AnnotationTask(Base):
    """Queues a page snapshot or trajectory step for human annotation."""

    __tablename__ = "annotation_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    page_id: Mapped[str | None] = mapped_column(ForeignKey("pages.id", ondelete="SET NULL"))
    trajectory_id: Mapped[str | None] = mapped_column(ForeignKey("trajectories.id", ondelete="SET NULL"))
    annotation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=5)
    status: Mapped[AnnotationStatus] = mapped_column(Enum(AnnotationStatus), default=AnnotationStatus.PENDING)
    prompt: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSON)
    annotator_id: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    page: Mapped[Page | None] = relationship(back_populates="annotation_tasks")
    trajectory: Mapped[Trajectory | None] = relationship(back_populates="annotation_tasks")

    def __repr__(self) -> str:
        return f"<AnnotationTask type={self.annotation_type!r} status={self.status}>"


# ── Training ──────────────────────────────────────────────────────────────────

class TrainingRecord(Base):
    """A single training example derived from a trajectory or annotation."""

    __tablename__ = "training_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trajectory_id: Mapped[str | None] = mapped_column(ForeignKey("trajectories.id", ondelete="SET NULL"))
    data_type: Mapped[TrainingDataType] = mapped_column(Enum(TrainingDataType), nullable=False)
    input_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    output_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    reward: Mapped[float | None] = mapped_column(Float)
    split: Mapped[str] = mapped_column(String(16), default="train")
    exported: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    trajectory: Mapped[Trajectory | None] = relationship(back_populates="training_records")

    def __repr__(self) -> str:
        return f"<TrainingRecord type={self.data_type} split={self.split!r}>"


# ── Audit ─────────────────────────────────────────────────────────────────────

class AuditLog(Base):
    """Immutable audit log entry for every privileged or sensitive operation."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor: Mapped[str] = mapped_column(String(256), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(36))
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, server_default=func.now())

    def __repr__(self) -> str:
        return f"<AuditLog actor={self.actor!r} action={self.action!r} outcome={self.outcome!r}>"
