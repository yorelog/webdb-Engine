"""Repository (data-access) helpers for the page knowledge base.

Each function is a thin wrapper around SQLAlchemy queries; callers
provide an open Session and receive model instances.
"""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from webdb.database.models import (
    ActionStatus,
    ActionStep,
    AnnotationStatus,
    AnnotationTask,
    AuditLog,
    Credential,
    Page,
    PageType,
    Site,
    TrainingRecord,
    Trajectory,
)

# ── Site ─────────────────────────────────────────────────────────────────────

def get_or_create_site(session: Session, origin: str, **kwargs: Any) -> Site:
    site = session.scalar(select(Site).where(Site.origin == origin))
    if site is None:
        site = Site(origin=origin, **kwargs)
        session.add(site)
        session.flush()
    return site


# ── Page ─────────────────────────────────────────────────────────────────────

def create_page(session: Session, site_id: str, url: str, **kwargs: Any) -> Page:
    page = Page(site_id=site_id, url=url, **kwargs)
    session.add(page)
    session.flush()
    return page


def get_page_by_url(session: Session, url: str) -> Page | None:
    return session.scalar(select(Page).where(Page.url == url).order_by(Page.version.desc()))


def find_similar_pages(session: Session, page_type: PageType, limit: int = 10) -> list[Page]:
    return list(session.scalars(
        select(Page).where(Page.page_type == page_type).limit(limit)
    ))


def compute_content_hash(html: str) -> str:
    return hashlib.sha256(html.encode()).hexdigest()


# ── Trajectory ───────────────────────────────────────────────────────────────

def create_trajectory(session: Session, page_id: str, goal: str | None = None, **kwargs: Any) -> Trajectory:
    traj = Trajectory(page_id=page_id, goal=goal, **kwargs)
    session.add(traj)
    session.flush()
    return traj


def get_successful_trajectories(session: Session, page_id: str) -> list[Trajectory]:
    return list(session.scalars(
        select(Trajectory)
        .where(Trajectory.page_id == page_id, Trajectory.status == ActionStatus.SUCCESS)
    ))


def get_failed_trajectories(session: Session, page_id: str) -> list[Trajectory]:
    return list(session.scalars(
        select(Trajectory)
        .where(Trajectory.page_id == page_id, Trajectory.status == ActionStatus.FAILED)
    ))


# ── ActionStep ───────────────────────────────────────────────────────────────

def create_action_step(
    session: Session,
    trajectory_id: str,
    step_index: int,
    action_type: str,
    **kwargs: Any,
) -> ActionStep:
    step = ActionStep(
        trajectory_id=trajectory_id,
        step_index=step_index,
        action_type=action_type,
        **kwargs,
    )
    session.add(step)
    session.flush()
    return step


# ── Credential ───────────────────────────────────────────────────────────────

def upsert_credential(
    session: Session,
    site_id: str,
    username: str,
    encrypted_secret: bytes,
    credential_type: str = "password",
) -> Credential:
    cred = session.scalar(
        select(Credential).where(
            Credential.site_id == site_id,
            Credential.username == username,
        )
    )
    if cred is None:
        cred = Credential(
            site_id=site_id,
            username=username,
            encrypted_secret=encrypted_secret,
            credential_type=credential_type,
        )
        session.add(cred)
    else:
        cred.encrypted_secret = encrypted_secret
        cred.credential_type = credential_type
    session.flush()
    return cred


# ── Annotation ───────────────────────────────────────────────────────────────

def queue_annotation(
    session: Session,
    annotation_type: str,
    page_id: str | None = None,
    trajectory_id: str | None = None,
    priority: int = 5,
    prompt: str | None = None,
) -> AnnotationTask:
    task = AnnotationTask(
        annotation_type=annotation_type,
        page_id=page_id,
        trajectory_id=trajectory_id,
        priority=priority,
        prompt=prompt,
    )
    session.add(task)
    session.flush()
    return task


def get_pending_annotations(session: Session, limit: int = 20) -> list[AnnotationTask]:
    return list(session.scalars(
        select(AnnotationTask)
        .where(AnnotationTask.status == AnnotationStatus.PENDING)
        .order_by(AnnotationTask.priority.desc(), AnnotationTask.created_at)
        .limit(limit)
    ))


# ── Training ─────────────────────────────────────────────────────────────────

def create_training_record(
    session: Session,
    data_type: str,
    input_payload: dict,
    output_payload: dict,
    trajectory_id: str | None = None,
    reward: float | None = None,
    split: str = "train",
) -> TrainingRecord:
    record = TrainingRecord(
        data_type=data_type,
        input_payload=input_payload,
        output_payload=output_payload,
        trajectory_id=trajectory_id,
        reward=reward,
        split=split,
    )
    session.add(record)
    session.flush()
    return record


def get_unexported_records(session: Session, data_type: str | None = None, limit: int = 1000) -> list[TrainingRecord]:
    q = select(TrainingRecord).where(TrainingRecord.exported == False)  # noqa: E712
    if data_type:
        q = q.where(TrainingRecord.data_type == data_type)
    return list(session.scalars(q.limit(limit)))


# ── Audit ─────────────────────────────────────────────────────────────────────

def write_audit(
    session: Session,
    actor: str,
    action: str,
    outcome: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: dict | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    log = AuditLog(
        actor=actor,
        action=action,
        outcome=outcome,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        ip_address=ip_address,
    )
    session.add(log)
    session.flush()
    return log
