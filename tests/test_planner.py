"""Tests for the action planner."""

from __future__ import annotations

from webdb.database.models import ActionType, ElementRole, PageType
from webdb.planner.action_planner import ActionPlanner
from webdb.planner.action_types import ActionPlan, PlannedAction
from webdb.understanding.element_recognizer import RecognisedElement
from webdb.understanding.page_classifier import ClassificationResult


def _make_elements(*specs) -> list[RecognisedElement]:
    """Build minimal RecognisedElement objects from (tag, role, text, attrs) tuples."""
    result = []
    for tag, role, text, attrs in specs:
        result.append(RecognisedElement(
            tag=tag,
            text=text,
            selector=f"#{attrs.get('id', tag)}",
            role=role,
            confidence=0.8,
            is_interactive=True,
            attributes=attrs,
        ))
    return result


def _login_page_result() -> ClassificationResult:
    return ClassificationResult(
        page_type=PageType.LOGIN,
        confidence=0.9,
        signals={"has_password_field": True},
    )


def _list_page_result() -> ClassificationResult:
    return ClassificationResult(
        page_type=PageType.LIST,
        confidence=0.8,
        signals={"has_table": True},
    )


class TestActionPlannerLogin:
    def _elements(self):
        return _make_elements(
            ("input", ElementRole.FIELD, "", {"type": "text", "name": "username", "id": "user"}),
            ("input", ElementRole.FIELD, "", {"type": "password", "name": "password", "id": "pass"}),
            ("button", ElementRole.ACTION, "Login", {"type": "submit", "id": "btn-login"}),
        )

    def test_plan_login_has_three_main_steps(self):
        planner = ActionPlanner(_login_page_result(), self._elements())
        plan = planner.plan_login("user@example.com", "s3cret")
        # fill user + fill password + click + wait
        assert len(plan) >= 3

    def test_plan_login_fill_types(self):
        planner = ActionPlanner(_login_page_result(), self._elements())
        plan = planner.plan_login("user@example.com", "s3cret")
        types = [s.action_type for s in plan.steps]
        assert ActionType.FILL in types
        assert ActionType.CLICK in types

    def test_plan_login_values(self):
        planner = ActionPlanner(_login_page_result(), self._elements())
        plan = planner.plan_login("user@example.com", "s3cret")
        fills = [s for s in plan.steps if s.action_type == ActionType.FILL]
        values = [f.value for f in fills]
        assert "user@example.com" in values
        assert "s3cret" in values


class TestActionPlannerExtract:
    def test_plan_extract(self):
        elements = _make_elements(
            ("table", ElementRole.DATA, "", {}),
        )
        planner = ActionPlanner(_list_page_result(), elements)
        plan = planner.plan_extract()
        assert len(plan) >= 1
        assert plan.steps[0].action_type == ActionType.EXTRACT

    def test_plan_paginate(self):
        elements = _make_elements(
            ("a", ElementRole.NAVIGATION, "Next", {"href": "?page=2"}),
        )
        planner = ActionPlanner(_list_page_result(), elements)
        plan = planner.plan_paginate_and_extract(max_pages=3)
        types = [s.action_type for s in plan.steps]
        assert ActionType.EXTRACT in types
        assert ActionType.CLICK in types


class TestActionPlannerSearch:
    def test_plan_search(self):
        elements = _make_elements(
            ("input", ElementRole.FIELD, "", {"type": "search", "name": "q", "id": "search"}),
        )
        result = ClassificationResult(
            page_type=PageType.SEARCH, confidence=0.7, signals={}
        )
        planner = ActionPlanner(result, elements)
        plan = planner.plan_search("python")
        types = [s.action_type for s in plan.steps]
        assert ActionType.FILL in types
        assert ActionType.SUBMIT in types


class TestPlannedAction:
    def test_to_dict(self):
        action = PlannedAction(
            action_type=ActionType.CLICK,
            selector="#btn",
            description="click something",
        )
        d = action.to_dict()
        assert d["action_type"] == "click"
        assert d["selector"] == "#btn"


class TestActionPlan:
    def test_append_and_len(self):
        plan = ActionPlan(goal="test")
        plan.append(PlannedAction(action_type=ActionType.WAIT))
        assert len(plan) == 1
