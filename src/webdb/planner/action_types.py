"""Action type definitions and data structures for the planning layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from webdb.database.models import ActionType


@dataclass
class PlannedAction:
    """A single executable action in a plan."""

    action_type: ActionType
    selector: str | None = None
    value: str | None = None
    description: str = ""
    timeout_ms: int | None = None
    fallback_selectors: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type.value,
            "selector": self.selector,
            "value": self.value,
            "description": self.description,
            "timeout_ms": self.timeout_ms,
            "fallback_selectors": self.fallback_selectors,
            "meta": self.meta,
        }


@dataclass
class ActionPlan:
    """An ordered sequence of PlannedActions to accomplish a goal."""

    goal: str
    steps: list[PlannedAction] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def append(self, action: PlannedAction) -> ActionPlan:
        self.steps.append(action)
        return self

    def __len__(self) -> int:
        return len(self.steps)
