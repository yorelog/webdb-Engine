"""Tests for database models, engine, and repository functions."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from webdb.database.models import (
    ActionStatus,
    ActionType,
    AnnotationStatus,
    Base,
    PageType,
    TrainingDataType,
)
from webdb.database.repository import (
    compute_content_hash,
    create_action_step,
    create_page,
    create_training_record,
    create_trajectory,
    find_similar_pages,
    get_or_create_site,
    get_page_by_url,
    get_pending_annotations,
    get_successful_trajectories,
    queue_annotation,
    upsert_credential,
    write_audit,
)


@pytest.fixture
def in_memory_session(tmp_path, monkeypatch):
    """Provide an isolated in-memory SQLite session for each test."""
    db_url = "sqlite://"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    yield session
    session.close()
    engine.dispose()


class TestSiteRepository:
    def test_create_site(self, in_memory_session):
        site = get_or_create_site(in_memory_session, "https://example.com", name="Example")
        in_memory_session.commit()
        assert site.id is not None
        assert site.origin == "https://example.com"
        assert site.name == "Example"

    def test_get_existing_site(self, in_memory_session):
        s1 = get_or_create_site(in_memory_session, "https://example.com")
        in_memory_session.commit()
        s2 = get_or_create_site(in_memory_session, "https://example.com")
        assert s1.id == s2.id


class TestPageRepository:
    def test_create_page(self, in_memory_session):
        site = get_or_create_site(in_memory_session, "https://example.com")
        in_memory_session.commit()
        page = create_page(in_memory_session, site.id, "https://example.com/list")
        in_memory_session.commit()
        assert page.id is not None
        assert page.url == "https://example.com/list"

    def test_get_page_by_url(self, in_memory_session):
        site = get_or_create_site(in_memory_session, "https://example.com")
        in_memory_session.commit()
        create_page(in_memory_session, site.id, "https://example.com/page1")
        in_memory_session.commit()
        page = get_page_by_url(in_memory_session, "https://example.com/page1")
        assert page is not None
        assert page.url == "https://example.com/page1"

    def test_page_not_found(self, in_memory_session):
        assert get_page_by_url(in_memory_session, "https://missing.com") is None

    def test_find_similar_pages(self, in_memory_session):
        site = get_or_create_site(in_memory_session, "https://example.com")
        in_memory_session.commit()
        for i in range(3):
            p = create_page(in_memory_session, site.id, f"https://example.com/list/{i}")
            p.page_type = PageType.LIST
        in_memory_session.commit()
        results = find_similar_pages(in_memory_session, PageType.LIST, limit=10)
        assert len(results) == 3

    def test_content_hash(self):
        h = compute_content_hash("<html>hello</html>")
        assert len(h) == 64
        assert compute_content_hash("<html>hello</html>") == h


class TestTrajectoryRepository:
    def _setup(self, session):
        site = get_or_create_site(session, "https://example.com")
        session.commit()
        page = create_page(session, site.id, "https://example.com/data")
        session.commit()
        return page

    def test_create_trajectory(self, in_memory_session):
        page = self._setup(in_memory_session)
        traj = create_trajectory(in_memory_session, page.id, goal="extract data")
        in_memory_session.commit()
        assert traj.id is not None
        assert traj.goal == "extract data"

    def test_create_action_step(self, in_memory_session):
        page = self._setup(in_memory_session)
        traj = create_trajectory(in_memory_session, page.id)
        in_memory_session.commit()
        step = create_action_step(
            in_memory_session, traj.id, 0, ActionType.CLICK, selector="#btn"
        )
        in_memory_session.commit()
        assert step.id is not None
        assert step.action_type == ActionType.CLICK

    def test_get_successful_trajectories(self, in_memory_session):
        page = self._setup(in_memory_session)
        t1 = create_trajectory(in_memory_session, page.id)
        t1.status = ActionStatus.SUCCESS
        t2 = create_trajectory(in_memory_session, page.id)
        t2.status = ActionStatus.FAILED
        in_memory_session.commit()
        ok = get_successful_trajectories(in_memory_session, page.id)
        assert len(ok) == 1


class TestCredentialRepository:
    def test_upsert_credential(self, in_memory_session):
        site = get_or_create_site(in_memory_session, "https://example.com")
        in_memory_session.commit()
        cred = upsert_credential(
            in_memory_session, site.id, "admin", b"encrypted_bytes"
        )
        in_memory_session.commit()
        assert cred.id is not None
        assert cred.encrypted_secret == b"encrypted_bytes"

    def test_update_credential(self, in_memory_session):
        site = get_or_create_site(in_memory_session, "https://example.com")
        in_memory_session.commit()
        upsert_credential(in_memory_session, site.id, "admin", b"old")
        in_memory_session.commit()
        upsert_credential(in_memory_session, site.id, "admin", b"new")
        in_memory_session.commit()
        from sqlalchemy import select

        from webdb.database.models import Credential
        cred = in_memory_session.scalar(
            select(Credential).where(Credential.username == "admin")
        )
        assert cred.encrypted_secret == b"new"


class TestAnnotationRepository:
    def test_queue_annotation(self, in_memory_session):
        site = get_or_create_site(in_memory_session, "https://example.com")
        in_memory_session.commit()
        page = create_page(in_memory_session, site.id, "https://example.com/")
        in_memory_session.commit()
        task = queue_annotation(
            in_memory_session, "page_type", page_id=page.id, priority=7
        )
        in_memory_session.commit()
        assert task.id is not None
        assert task.status == AnnotationStatus.PENDING

    def test_get_pending_annotations(self, in_memory_session):
        site = get_or_create_site(in_memory_session, "https://example.com")
        in_memory_session.commit()
        page = create_page(in_memory_session, site.id, "https://example.com/")
        in_memory_session.commit()
        for _ in range(5):
            queue_annotation(in_memory_session, "page_type", page_id=page.id)
        in_memory_session.commit()
        pending = get_pending_annotations(in_memory_session, limit=3)
        assert len(pending) == 3


class TestTrainingRepository:
    def test_create_training_record(self, in_memory_session):
        rec = create_training_record(
            in_memory_session,
            data_type=TrainingDataType.SFT,
            input_payload={"page_id": "abc"},
            output_payload={"label": "login"},
        )
        in_memory_session.commit()
        assert rec.id is not None
        assert rec.exported is False


class TestAuditRepository:
    def test_write_audit(self, in_memory_session):
        log = write_audit(
            in_memory_session,
            actor="test",
            action="test.action",
            outcome="success",
            detail={"key": "value"},
        )
        in_memory_session.commit()
        assert log.id is not None
        assert log.action == "test.action"
