"""PII handler: detects and redacts personally identifiable information
from collected page data before it is persisted.

Uses simple pattern matching; a more sophisticated NER-based approach can
replace this in a later iteration.
"""

from __future__ import annotations

import re
from typing import Any

# ── Patterns ─────────────────────────────────────────────────────────────────

_PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    # Email addresses
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b")),
    # Chinese ID card
    ("id_card", re.compile(r"\b\d{17}[\dXx]\b")),
    # Phone numbers (simple international + Chinese)
    ("phone", re.compile(r"(?<!\d)(\+?\d[\d\s\-\(\)]{7,14}\d)(?!\d)")),
    # Credit/debit card numbers (Luhn-like 13-19 digits)
    ("credit_card", re.compile(r"\b(?:\d[ \-]?){13,19}\b")),
    # IPv4 addresses
    ("ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
]

# Fields whose names suggest they contain PII (used for structured dicts)
_PII_FIELD_NAMES: set[str] = {
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "ssn", "social_security", "credit_card", "card_number",
    "phone", "mobile", "email", "id_card",
}


class PIIHandler:
    """Detects and redacts PII from text strings or structured data.

    Usage::

        handler = PIIHandler()
        clean_html = handler.redact_text(raw_html)
        clean_record = handler.redact_dict(data_row)
    """

    def __init__(self, placeholder: str = "[REDACTED]") -> None:
        self._placeholder = placeholder

    def redact_text(self, text: str) -> str:
        """Replace all detected PII patterns with the placeholder."""
        for _name, pattern in _PII_PATTERNS:
            text = pattern.sub(self._placeholder, text)
        return text

    def redact_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively redact PII from a dictionary's values."""
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(key, str) and key.lower() in _PII_FIELD_NAMES:
                result[key] = self._placeholder
            elif isinstance(value, str):
                result[key] = self.redact_text(value)
            elif isinstance(value, dict):
                result[key] = self.redact_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self.redact_dict(v) if isinstance(v, dict)
                    else self.redact_text(v) if isinstance(v, str)
                    else v
                    for v in value
                ]
            else:
                result[key] = value
        return result

    def contains_pii(self, text: str) -> bool:
        """Return True if any PII pattern is found in *text*."""
        return any(pattern.search(text) for _, pattern in _PII_PATTERNS)

    def find_pii(self, text: str) -> dict[str, list[str]]:
        """Return a dict mapping PII type → list of matched strings."""
        found: dict[str, list[str]] = {}
        for name, pattern in _PII_PATTERNS:
            matches = pattern.findall(text)
            if matches:
                found[name] = [str(m) for m in matches]
        return found
