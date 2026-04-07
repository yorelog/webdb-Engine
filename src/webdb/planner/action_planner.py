"""Rule-based action planner.

Generates an ActionPlan for common web tasks using heuristics derived from
the page classification and element recognition results.  A future iteration
can replace or augment this planner with an LLM-based policy.
"""

from __future__ import annotations

from webdb.database.models import ActionType, PageType
from webdb.planner.action_types import ActionPlan, PlannedAction
from webdb.understanding.element_recognizer import RecognisedElement
from webdb.understanding.page_classifier import ClassificationResult


class ActionPlanner:
    """Generates action plans for common page tasks.

    Parameters
    ----------
    page_type_result:
        Output of :class:`~webdb.understanding.page_classifier.PageClassifier`.
    elements:
        Output of :class:`~webdb.understanding.element_recognizer.ElementRecognizer`.
    """

    def __init__(
        self,
        page_type_result: ClassificationResult,
        elements: list[RecognisedElement],
    ) -> None:
        self._page_type = page_type_result.page_type
        self._elements = elements

    def plan_login(self, username: str, password: str) -> ActionPlan:
        """Build a plan to fill a login form."""
        plan = ActionPlan(goal="login")

        user_field = self._find_field(["email", "user", "username", "account", "login"])
        pass_field = self._find_input_by_type("password")
        submit = self._find_action(["login", "sign in", "submit"])

        if user_field:
            plan.append(PlannedAction(
                action_type=ActionType.FILL,
                selector=user_field.selector,
                value=username,
                description="Fill username / email",
            ))
        if pass_field:
            plan.append(PlannedAction(
                action_type=ActionType.FILL,
                selector=pass_field.selector,
                value=password,
                description="Fill password",
            ))
        if submit:
            plan.append(PlannedAction(
                action_type=ActionType.CLICK,
                selector=submit.selector,
                description="Click login / submit",
            ))
        plan.append(PlannedAction(
            action_type=ActionType.WAIT,
            description="Wait for navigation after login",
            timeout_ms=5000,
        ))
        return plan

    def plan_extract(self) -> ActionPlan:
        """Build a plan to extract tabular data from a list/table page."""
        plan = ActionPlan(goal="extract_data")
        plan.append(PlannedAction(
            action_type=ActionType.EXTRACT,
            description="Extract all data rows from page",
            meta={"strategy": "table" if self._page_type == PageType.LIST else "dom"},
        ))
        return plan

    def plan_paginate_and_extract(self, max_pages: int = 50) -> ActionPlan:
        """Build a plan to paginate through a list and extract data from every page."""
        plan = ActionPlan(goal="paginate_and_extract")
        plan.append(PlannedAction(
            action_type=ActionType.EXTRACT,
            description="Extract data from current page",
        ))
        next_btn = self._find_action(["next", "›", "»", "next page"])
        for _ in range(max_pages - 1):
            if next_btn:
                plan.append(PlannedAction(
                    action_type=ActionType.CLICK,
                    selector=next_btn.selector,
                    description="Click next page",
                ))
                plan.append(PlannedAction(
                    action_type=ActionType.WAIT,
                    description="Wait for page load",
                    timeout_ms=3000,
                ))
                plan.append(PlannedAction(
                    action_type=ActionType.EXTRACT,
                    description="Extract data from page",
                ))
        return plan

    def plan_download(self) -> ActionPlan:
        """Build a plan to click a download link."""
        plan = ActionPlan(goal="download_file")
        dl_el = self._find_action(["download", "export", "csv", "excel", "xlsx"])
        if dl_el:
            plan.append(PlannedAction(
                action_type=ActionType.DOWNLOAD,
                selector=dl_el.selector,
                description="Click download / export link",
            ))
        return plan

    def plan_search(self, query: str) -> ActionPlan:
        """Build a plan to type a query into a search field and submit."""
        plan = ActionPlan(goal=f"search:{query}")
        search_field = self._find_field(["search", "query", "keyword", "find"])
        if search_field:
            plan.append(PlannedAction(
                action_type=ActionType.FILL,
                selector=search_field.selector,
                value=query,
                description="Enter search query",
            ))
            plan.append(PlannedAction(
                action_type=ActionType.SUBMIT,
                selector=search_field.selector,
                description="Submit search form",
            ))
            plan.append(PlannedAction(
                action_type=ActionType.WAIT,
                description="Wait for search results",
                timeout_ms=4000,
            ))
        return plan

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _find_field(self, keywords: list[str]) -> RecognisedElement | None:
        from webdb.database.models import ElementRole
        candidates = [e for e in self._elements if e.role == ElementRole.FIELD]
        for kw in keywords:
            for el in candidates:
                if kw.lower() in (el.text + el.selector + str(el.attributes)).lower():
                    return el
        return candidates[0] if candidates else None

    def _find_input_by_type(self, input_type: str) -> RecognisedElement | None:
        for el in self._elements:
            if el.attributes.get("type") == input_type:
                return el
        return None

    def _find_action(self, keywords: list[str]) -> RecognisedElement | None:
        from webdb.database.models import ElementRole
        candidates = [e for e in self._elements if e.role in (ElementRole.ACTION, ElementRole.NAVIGATION)]
        for kw in keywords:
            for el in candidates:
                combined = (el.text + el.selector + str(el.attributes)).lower()
                if kw.lower() in combined:
                    return el
        return candidates[0] if candidates else None
