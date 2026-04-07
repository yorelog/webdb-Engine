"""Rule-based page-type classifier.

A lightweight, zero-dependency classifier that works without an ML model.
It can be replaced or augmented with an ML classifier in a later iteration.
"""

from __future__ import annotations

from dataclasses import dataclass

from webdb.database.models import PageType
from webdb.understanding.dom_parser import DOMParser


@dataclass
class ClassificationResult:
    page_type: PageType
    confidence: float
    signals: dict[str, bool]


# Scoring weights (tag / keyword → (page_type, score))
_SIGNAL_RULES: list[tuple[str, PageType, float]] = [
    # Login
    ("has_password_field", PageType.LOGIN, 0.9),
    ("has_login_keyword", PageType.LOGIN, 0.6),
    # Search / List
    ("has_search_field", PageType.SEARCH, 0.7),
    ("has_table", PageType.LIST, 0.6),
    ("has_list_items", PageType.LIST, 0.4),
    ("has_pagination", PageType.LIST, 0.5),
    # Form
    ("has_many_inputs", PageType.FORM, 0.6),
    ("has_submit_button", PageType.FORM, 0.3),
    # Dashboard
    ("has_charts", PageType.DASHBOARD, 0.7),
    ("has_dashboard_keyword", PageType.DASHBOARD, 0.5),
    # Download
    ("has_download_link", PageType.DOWNLOAD, 0.8),
    # Detail
    ("has_detail_keyword", PageType.DETAIL, 0.4),
]


class PageClassifier:
    """Rule-based page-type classifier.

    Parameters
    ----------
    html:
        Raw or rendered HTML of the page.
    title:
        Page title (used as an additional signal).
    url:
        Page URL (used as an additional signal).
    """

    def __init__(self, html: str, title: str = "", url: str = "") -> None:
        self._parser = DOMParser(html)
        self._title = (title + " " + url).lower()
        self._html_lower = html.lower()

    def classify(self) -> ClassificationResult:
        signals = self._extract_signals()
        scores: dict[PageType, float] = {}
        for signal_name, page_type, weight in _SIGNAL_RULES:
            if signals.get(signal_name):
                scores[page_type] = scores.get(page_type, 0.0) + weight

        if not scores:
            return ClassificationResult(
                page_type=PageType.UNKNOWN,
                confidence=0.0,
                signals=signals,
            )

        best = max(scores, key=lambda k: scores[k])
        total = sum(scores.values())
        confidence = min(scores[best] / total, 1.0) if total else 0.0
        return ClassificationResult(page_type=best, confidence=confidence, signals=signals)

    def _extract_signals(self) -> dict[str, bool]:
        html = self._html_lower
        title = self._title
        forms = self._parser.get_forms()
        elements = self._parser.get_interactive_elements()

        input_types = [i.get("type", "text") for f in forms for i in f["inputs"]]
        input_count = len([e for e in elements if e.tag == "input"])

        return {
            "has_password_field": "password" in input_types,
            "has_login_keyword": any(k in title for k in ("login", "sign in", "signin", "log in")),
            "has_search_field": "search" in input_types or "search" in html,
            "has_table": "<table" in html,
            "has_list_items": html.count("<li") > 5,
            "has_pagination": any(k in html for k in ("pagination", "page-next", "pager", "?page=", "&page=")),
            "has_many_inputs": input_count >= 4,
            "has_submit_button": any(
                e.attrs.get("type") == "submit" or e.tag == "button"
                for e in elements
            ),
            "has_charts": any(k in html for k in ("chart", "echarts", "highcharts", "d3.js", "canvas")),
            "has_dashboard_keyword": any(k in title for k in ("dashboard", "overview", "summary")),
            "has_download_link": any(k in html for k in ('href="', "download", ".csv", ".xlsx", ".zip")),
            "has_detail_keyword": any(k in title for k in ("detail", "profile", "view", "show", "record")),
        }
