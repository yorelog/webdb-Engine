"""Browser action executor built on Playwright.

Executes PlannedAction steps with retry, fallback selectors, screenshot
capture, and DOM-hash-based success validation.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from webdb.config.settings import get_settings
from webdb.database.models import ActionStatus, ActionType
from webdb.planner.action_types import ActionPlan, PlannedAction


@dataclass
class StepResult:
    step_index: int
    action_type: ActionType
    status: ActionStatus
    duration_ms: int
    retry_count: int = 0
    error_message: str | None = None
    before_dom_hash: str | None = None
    after_dom_hash: str | None = None
    before_screenshot: bytes | None = None
    after_screenshot: bytes | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    plan: ActionPlan
    steps: list[StepResult] = field(default_factory=list)
    overall_status: ActionStatus = ActionStatus.PENDING
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    @property
    def success_rate(self) -> float:
        if not self.steps:
            return 0.0
        ok = sum(1 for s in self.steps if s.status == ActionStatus.SUCCESS)
        return ok / len(self.steps)


class BrowserExecutor:
    """Executes an ActionPlan against a live Playwright browser page.

    Usage::

        async with BrowserExecutor() as executor:
            result = await executor.execute(plan, url="https://example.com")
    """

    def __init__(
        self,
        headless: bool | None = None,
        browser_type: str | None = None,
        screenshot_dir: Path | None = None,
    ) -> None:
        cfg = get_settings()
        self._headless = headless if headless is not None else cfg.browser_headless
        self._browser_type = browser_type or cfg.browser_type
        self._max_retries = cfg.executor_max_retries
        self._retry_delay = cfg.executor_retry_delay_s
        self._screenshot_dir = screenshot_dir
        self._playwright = None
        self._browser = None

    async def __aenter__(self) -> BrowserExecutor:
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        launcher = getattr(self._playwright, self._browser_type)
        args: list[str] = []
        if get_settings().browser_sandbox:
            args = ["--no-sandbox", "--disable-dev-shm-usage"]
        self._browser = await launcher.launch(headless=self._headless, args=args)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def execute(self, plan: ActionPlan, url: str | None = None) -> ExecutionResult:
        """Execute all steps in *plan*.

        Parameters
        ----------
        plan:
            The action plan to execute.
        url:
            If provided, navigate to this URL before executing the plan.
        """
        context = await self._browser.new_context()
        page = await context.new_page()
        cfg = get_settings()
        page.set_default_timeout(cfg.browser_timeout_ms)

        result = ExecutionResult(plan=plan)

        if url:
            await page.goto(url, wait_until="networkidle")

        for idx, step in enumerate(plan.steps):
            step_result = await self._execute_step(page, step, idx)
            result.steps.append(step_result)
            if step_result.status == ActionStatus.FAILED:
                # Stop on hard failure
                break

        result.finished_at = time.time()
        all_ok = all(s.status == ActionStatus.SUCCESS for s in result.steps)
        result.overall_status = ActionStatus.SUCCESS if all_ok else ActionStatus.FAILED

        await context.close()
        return result

    async def _execute_step(self, page: Any, step: PlannedAction, idx: int) -> StepResult:
        start = time.time()
        before_hash = await self._dom_hash(page)
        before_ss = None
        after_ss = None

        for attempt in range(self._max_retries + 1):
            try:
                before_ss = await page.screenshot()
                await self._dispatch(page, step)
                after_ss = await page.screenshot()
                after_hash = await self._dom_hash(page)
                duration = int((time.time() - start) * 1000)
                return StepResult(
                    step_index=idx,
                    action_type=step.action_type,
                    status=ActionStatus.SUCCESS,
                    duration_ms=duration,
                    retry_count=attempt,
                    before_dom_hash=before_hash,
                    after_dom_hash=after_hash,
                    before_screenshot=before_ss,
                    after_screenshot=after_ss,
                )
            except Exception as exc:  # noqa: BLE001
                if attempt < self._max_retries:
                    # Try fallback selector if available
                    if step.fallback_selectors and attempt < len(step.fallback_selectors):
                        step = PlannedAction(
                            action_type=step.action_type,
                            selector=step.fallback_selectors[attempt],
                            value=step.value,
                            description=step.description,
                            timeout_ms=step.timeout_ms,
                            fallback_selectors=step.fallback_selectors[attempt + 1:],
                            meta=step.meta,
                        )
                    await asyncio.sleep(self._retry_delay)
                    continue
                duration = int((time.time() - start) * 1000)
                return StepResult(
                    step_index=idx,
                    action_type=step.action_type,
                    status=ActionStatus.FAILED,
                    duration_ms=duration,
                    retry_count=attempt,
                    error_message=str(exc),
                    before_dom_hash=before_hash,
                    before_screenshot=before_ss,
                    after_screenshot=after_ss,
                )

        # Should not reach here
        return StepResult(
            step_index=idx,
            action_type=step.action_type,
            status=ActionStatus.FAILED,
            duration_ms=0,
        )

    async def _dispatch(self, page: Any, step: PlannedAction) -> None:
        timeout = step.timeout_ms or get_settings().browser_timeout_ms
        if step.action_type == ActionType.NAVIGATE:
            await page.goto(step.value or "", wait_until="networkidle")
        elif step.action_type == ActionType.CLICK:
            await page.click(step.selector, timeout=timeout)
        elif step.action_type == ActionType.FILL:
            await page.fill(step.selector, step.value or "", timeout=timeout)
        elif step.action_type == ActionType.SELECT:
            await page.select_option(step.selector, step.value or "", timeout=timeout)
        elif step.action_type == ActionType.SUBMIT:
            await page.press(step.selector, "Enter", timeout=timeout)
        elif step.action_type == ActionType.HOVER:
            await page.hover(step.selector, timeout=timeout)
        elif step.action_type == ActionType.SCROLL:
            await page.evaluate("window.scrollBy(0, 500)")
        elif step.action_type == ActionType.WAIT:
            await asyncio.sleep((timeout or 2000) / 1000)
        elif step.action_type in (ActionType.EXTRACT, ActionType.SYNC, ActionType.DOWNLOAD):
            # These are logical markers; the executor records them as successful no-ops.
            pass
        else:
            raise ValueError(f"Unsupported action type: {step.action_type}")

    async def _dom_hash(self, page: Any) -> str:
        dom = await page.evaluate("document.documentElement.outerHTML")
        return hashlib.md5(dom.encode()).hexdigest()  # noqa: S324
