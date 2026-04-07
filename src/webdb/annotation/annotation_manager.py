"""Annotation manager.

Manages the queue of annotation tasks and collects human feedback.
Feedback is stored in the database and converted to training records.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from webdb.database.engine import get_session
from webdb.database.models import (
    AnnotationStatus,
    AnnotationTask,
    TrainingDataType,
)
from webdb.database.repository import (
    create_training_record,
    get_pending_annotations,
    queue_annotation,
    write_audit,
)


@dataclass
class AnnotationResult:
    """Structured result submitted by a human annotator."""

    annotation_task_id: str
    annotation_type: str
    annotator_id: str
    # For page-type or element-role corrections
    corrected_label: str | None = None
    # For preference comparisons
    chosen_trajectory_id: str | None = None
    rejected_trajectory_id: str | None = None
    # For action-step corrections
    corrected_steps: list[dict[str, Any]] | None = None
    # Free-form notes
    notes: str | None = None
    submitted_at: datetime | None = None


class AnnotationManager:
    """Coordinates the annotation lifecycle.

    Usage::

        mgr = AnnotationManager()
        # Queue a failed trajectory for annotation
        task_id = mgr.queue_failure(trajectory_id="...", prompt="Why did this fail?")
        # Later, submit feedback
        result = AnnotationResult(annotation_task_id=task_id, ...)
        mgr.submit(result)
    """

    def queue_page_type_correction(
        self, page_id: str, prompt: str | None = None, priority: int = 5
    ) -> str:
        with get_session() as session:
            task = queue_annotation(
                session,
                annotation_type="page_type",
                page_id=page_id,
                priority=priority,
                prompt=prompt or "Please verify or correct the detected page type.",
            )
            return task.id

    def queue_element_role_correction(
        self, page_id: str, prompt: str | None = None, priority: int = 5
    ) -> str:
        with get_session() as session:
            task = queue_annotation(
                session,
                annotation_type="element_role",
                page_id=page_id,
                priority=priority,
                prompt=prompt or "Please review element roles on this page.",
            )
            return task.id

    def queue_failure(
        self, trajectory_id: str, prompt: str | None = None, priority: int = 8
    ) -> str:
        """Queue a failed trajectory for high-priority annotation."""
        with get_session() as session:
            task = queue_annotation(
                session,
                annotation_type="trajectory_failure",
                trajectory_id=trajectory_id,
                priority=priority,
                prompt=prompt or "A step in this trajectory failed.  Please review and correct.",
            )
            return task.id

    def queue_preference_comparison(
        self, trajectory_a_id: str, trajectory_b_id: str, priority: int = 6
    ) -> str:
        """Queue a pair of trajectories for preference labelling (DPO/RLHF)."""
        with get_session() as session:
            task = queue_annotation(
                session,
                annotation_type="preference",
                priority=priority,
                prompt="Which trajectory is better?  Mark chosen vs rejected.",
                trajectory_id=trajectory_a_id,
            )
            task.meta = {"trajectory_b_id": trajectory_b_id}  # type: ignore[attr-defined]
            return task.id

    def get_pending(self, limit: int = 20) -> list[AnnotationTask]:
        with get_session() as session:
            tasks = get_pending_annotations(session, limit=limit)
            session.expunge_all()
            return tasks

    def submit(self, result: AnnotationResult, actor: str = "annotator") -> None:
        """Submit human annotation feedback and convert it to training records."""
        with get_session() as session:
            # Load task
            task: AnnotationTask | None = session.get(AnnotationTask, result.annotation_task_id)
            if task is None:
                raise ValueError(f"AnnotationTask {result.annotation_task_id!r} not found")

            task.status = AnnotationStatus.COMPLETED
            task.annotator_id = result.annotator_id
            task.result = {
                "corrected_label": result.corrected_label,
                "chosen_trajectory_id": result.chosen_trajectory_id,
                "rejected_trajectory_id": result.rejected_trajectory_id,
                "corrected_steps": result.corrected_steps,
                "notes": result.notes,
            }

            # Generate training record(s) from the annotation
            if result.annotation_type == "page_type" and result.corrected_label:
                create_training_record(
                    session,
                    data_type=TrainingDataType.SFT,
                    input_payload={"page_id": task.page_id, "annotation_type": "page_type"},
                    output_payload={"corrected_label": result.corrected_label},
                    trajectory_id=task.trajectory_id,
                )
            elif result.annotation_type == "preference" and result.chosen_trajectory_id:
                create_training_record(
                    session,
                    data_type=TrainingDataType.PREFERENCE,
                    input_payload={"annotation_task_id": task.id},
                    output_payload={
                        "chosen": result.chosen_trajectory_id,
                        "rejected": result.rejected_trajectory_id,
                    },
                    trajectory_id=result.chosen_trajectory_id,
                )
            elif result.annotation_type == "trajectory_failure" and result.corrected_steps:
                create_training_record(
                    session,
                    data_type=TrainingDataType.FAILURE,
                    input_payload={"trajectory_id": task.trajectory_id},
                    output_payload={"corrected_steps": result.corrected_steps},
                    trajectory_id=task.trajectory_id,
                )

            write_audit(
                session,
                actor=actor,
                action="annotation.submit",
                outcome="success",
                resource_type="annotation_task",
                resource_id=task.id,
            )
