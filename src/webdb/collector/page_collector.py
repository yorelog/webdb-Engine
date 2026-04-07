"""Page data collector using Playwright.

Collects: HTML, rendered DOM, screenshot, accessibility tree, HAR, bounding boxes.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from webdb.config.settings import get_settings


@dataclass
class CollectedPage:
    """All raw data gathered for a single page visit."""

    url: str
    html: str
    rendered_dom: str
    title: str
    screenshot_bytes: bytes | None = None
    accessibility_tree: dict[str, Any] = field(default_factory=dict)
    har: dict[str, Any] = field(default_factory=dict)
    bounding_boxes: list[dict[str, Any]] = field(default_factory=list)
    collected_at: float = field(default_factory=time.time)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.html.encode()).hexdigest()


class PageCollector:
    """Asynchronous page collector built on Playwright.

    Usage::

        async with PageCollector() as collector:
            page_data = await collector.collect("https://example.com")
    """

    def __init__(
        self,
        headless: bool | None = None,
        browser_type: str | None = None,
        timeout_ms: int | None = None,
    ) -> None:
        cfg = get_settings()
        self._headless = headless if headless is not None else cfg.browser_headless
        self._browser_type = browser_type or cfg.browser_type
        self._timeout_ms = timeout_ms or cfg.browser_timeout_ms
        self._playwright = None
        self._browser = None

    async def __aenter__(self) -> PageCollector:
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        launcher = getattr(self._playwright, self._browser_type)
        launch_args: list[str] = []
        if get_settings().browser_sandbox:
            launch_args = ["--no-sandbox", "--disable-dev-shm-usage"]
        self._browser = await launcher.launch(headless=self._headless, args=launch_args)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def collect(
        self,
        url: str,
        screenshot_dir: Path | None = None,
        capture_har: bool = True,
        extra_wait_ms: int = 500,
    ) -> CollectedPage:
        """Navigate to *url* and collect all page artifacts.

        Parameters
        ----------
        url:
            Target URL.
        screenshot_dir:
            Directory to persist the screenshot PNG.  ``None`` keeps it in memory only.
        capture_har:
            Whether to record network requests as a HAR object.
        extra_wait_ms:
            Additional settle time after ``networkidle``.
        """
        context = await self._browser.new_context()
        if capture_har:
            context = await self._browser.new_context(record_har_path=None)

        har_data: dict = {}
        if capture_har:
            context = await self._browser.new_context()
            # Playwright's HAR capture is done via route; we collect manually below.

        page = await context.new_page()
        page.set_default_timeout(self._timeout_ms)

        # Network request log (lightweight HAR substitute)
        network_log: list[dict] = []

        async def _on_request(req):  # noqa: ANN001
            network_log.append({
                "url": req.url,
                "method": req.method,
                "resource_type": req.resource_type,
            })

        async def _on_response(resp):  # noqa: ANN001
            network_log.append({"url": resp.url, "status": resp.status})

        page.on("request", _on_request)
        page.on("response", _on_response)

        await page.goto(url, wait_until="networkidle")
        if extra_wait_ms:
            await asyncio.sleep(extra_wait_ms / 1000)

        html = await page.content()
        title = await page.title()

        # Rendered DOM (outer HTML of document element – post-JS)
        rendered_dom = await page.evaluate("document.documentElement.outerHTML")

        # Screenshot
        screenshot_bytes = await page.screenshot(full_page=True)
        if screenshot_dir is not None:
            screenshot_dir = Path(screenshot_dir)
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            fname = screenshot_dir / f"{hashlib.md5(url.encode()).hexdigest()}.png"
            fname.write_bytes(screenshot_bytes)

        # Accessibility tree
        ax_tree = await page.accessibility.snapshot() or {}

        # Bounding boxes for interactive elements
        bbox_js = """
        () => {
            const selectors = ['a', 'button', 'input', 'select', 'textarea', '[role]'];
            const results = [];
            document.querySelectorAll(selectors.join(',')).forEach(el => {
                const r = el.getBoundingClientRect();
                results.push({
                    tag: el.tagName.toLowerCase(),
                    id: el.id || null,
                    name: el.name || null,
                    text: (el.innerText || el.value || el.placeholder || '').slice(0, 200),
                    role: el.getAttribute('role') || null,
                    aria_label: el.getAttribute('aria-label') || null,
                    x: r.x, y: r.y, width: r.width, height: r.height
                });
            });
            return results;
        }
        """
        bounding_boxes: list[dict] = await page.evaluate(bbox_js)

        har_data = {"requests": network_log}

        await context.close()

        return CollectedPage(
            url=url,
            html=html,
            rendered_dom=rendered_dom,
            title=title,
            screenshot_bytes=screenshot_bytes,
            accessibility_tree=ax_tree,
            har=har_data,
            bounding_boxes=bounding_boxes,
        )
