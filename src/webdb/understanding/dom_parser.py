"""HTML/DOM parser utilities for extracting structured data from a collected page."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup, Tag


@dataclass
class ParsedElement:
    """A semantically enriched DOM element."""

    tag: str
    text: str
    attrs: dict[str, Any] = field(default_factory=dict)
    selector: str = ""
    xpath: str = ""
    is_interactive: bool = False
    inferred_role: str = "unknown"


# Tags considered interactive by default
_INTERACTIVE_TAGS = {"a", "button", "input", "select", "textarea", "label", "form"}

# Heuristics mapping tag/type/role to ElementRole labels
_ROLE_RULES: list[tuple[dict, str]] = [
    ({"tag": "input", "type": "text"}, "field"),
    ({"tag": "input", "type": "password"}, "field"),
    ({"tag": "input", "type": "email"}, "field"),
    ({"tag": "input", "type": "search"}, "field"),
    ({"tag": "input", "type": "submit"}, "action"),
    ({"tag": "button"}, "action"),
    ({"tag": "a"}, "navigation"),
    ({"tag": "select"}, "field"),
    ({"tag": "textarea"}, "field"),
    ({"role": "navigation"}, "navigation"),
    ({"role": "search"}, "field"),
    ({"role": "button"}, "action"),
    ({"role": "link"}, "navigation"),
    ({"class_contains": "paginat"}, "pagination"),
    ({"class_contains": "next"}, "pagination"),
    ({"class_contains": "prev"}, "pagination"),
    ({"tag": "table"}, "data"),
    ({"tag": "tr"}, "data"),
    ({"tag": "td"}, "data"),
    ({"tag": "th"}, "data"),
]


def _match_rule(el: Tag, rule: dict) -> bool:
    for k, v in rule.items():
        if k == "tag" and el.name != v:
            return False
        if k == "type" and el.get("type", "").lower() != v:
            return False
        if k == "role" and el.get("role", "").lower() != v:
            return False
        if k == "class_contains":
            classes = " ".join(el.get("class", []))
            if v.lower() not in classes.lower():
                return False
    return True


def _infer_role(el: Tag) -> str:
    for rule, role in _ROLE_RULES:
        if _match_rule(el, rule):
            return role
    return "unknown"


def _css_selector(el: Tag) -> str:
    """Build a simple but stable CSS selector for an element."""
    parts: list[str] = []
    current: Tag | None = el
    while current and current.name not in (None, "[document]", "html", "body"):
        if current.get("id"):
            parts.append(f"#{current['id']}")
            break
        siblings = [s for s in current.parent.children if isinstance(s, Tag) and s.name == current.name]
        if len(siblings) > 1:
            idx = siblings.index(current) + 1
            parts.append(f"{current.name}:nth-of-type({idx})")
        else:
            parts.append(current.name)
        current = current.parent
    return " > ".join(reversed(parts))


class DOMParser:
    """Extracts and enriches DOM elements from an HTML string."""

    def __init__(self, html: str) -> None:
        self._soup = BeautifulSoup(html, "lxml")

    @property
    def title(self) -> str:
        t = self._soup.find("title")
        return t.get_text(strip=True) if t else ""

    def get_text(self) -> str:
        return self._soup.get_text(separator=" ", strip=True)

    def get_interactive_elements(self) -> list[ParsedElement]:
        """Return all interactive elements with inferred semantic roles."""
        elements: list[ParsedElement] = []
        for tag_name in _INTERACTIVE_TAGS:
            for el in self._soup.find_all(tag_name):
                elements.append(self._to_parsed(el))
        return elements

    def get_all_elements(self, tags: list[str] | None = None) -> list[ParsedElement]:
        targets = tags or list(_INTERACTIVE_TAGS) + ["table", "tr", "td", "th"]
        elements: list[ParsedElement] = []
        for tag_name in targets:
            for el in self._soup.find_all(tag_name):
                elements.append(self._to_parsed(el))
        return elements

    def get_links(self) -> list[dict[str, str]]:
        return [
            {"href": a.get("href", ""), "text": a.get_text(strip=True)}
            for a in self._soup.find_all("a", href=True)
        ]

    def get_forms(self) -> list[dict[str, Any]]:
        forms = []
        for form in self._soup.find_all("form"):
            inputs = []
            for inp in form.find_all(["input", "select", "textarea"]):
                inputs.append({
                    "tag": inp.name,
                    "name": inp.get("name"),
                    "type": inp.get("type"),
                    "placeholder": inp.get("placeholder"),
                    "required": inp.has_attr("required"),
                })
            forms.append({
                "action": form.get("action"),
                "method": form.get("method", "get"),
                "inputs": inputs,
            })
        return forms

    def _to_parsed(self, el: Tag) -> ParsedElement:
        text = el.get_text(strip=True)[:300]
        attrs = {k: (v if isinstance(v, str) else " ".join(v)) for k, v in el.attrs.items()}
        return ParsedElement(
            tag=el.name,
            text=text,
            attrs=attrs,
            selector=_css_selector(el),
            is_interactive=el.name in _INTERACTIVE_TAGS,
            inferred_role=_infer_role(el),
        )
