"""Element role recognizer.

Converts raw ParsedElement objects (from DOMParser) into Element ORM instances
with enriched semantic role labels.
"""

from __future__ import annotations

from dataclasses import dataclass

from webdb.database.models import ElementRole
from webdb.understanding.dom_parser import ParsedElement

# Confidence adjustments based on aria-label presence
_ARIA_BOOST = 0.15


@dataclass
class RecognisedElement:
    tag: str
    text: str
    selector: str
    role: ElementRole
    confidence: float
    is_interactive: bool
    attributes: dict


def _map_role(inferred: str) -> ElementRole:
    mapping = {
        "field": ElementRole.FIELD,
        "action": ElementRole.ACTION,
        "navigation": ElementRole.NAVIGATION,
        "status": ElementRole.STATUS,
        "data": ElementRole.DATA,
        "pagination": ElementRole.PAGINATION,
    }
    return mapping.get(inferred, ElementRole.UNKNOWN)


class ElementRecognizer:
    """Assigns semantic roles and confidence scores to DOM elements."""

    def recognize(self, elements: list[ParsedElement]) -> list[RecognisedElement]:
        result: list[RecognisedElement] = []
        for el in elements:
            role = _map_role(el.inferred_role)
            confidence = self._base_confidence(el)
            if el.attrs.get("aria_label") or el.attrs.get("aria-label"):
                confidence = min(confidence + _ARIA_BOOST, 1.0)
            result.append(
                RecognisedElement(
                    tag=el.tag,
                    text=el.text,
                    selector=el.selector,
                    role=role,
                    confidence=confidence,
                    is_interactive=el.is_interactive,
                    attributes=el.attrs,
                )
            )
        return result

    def _base_confidence(self, el: ParsedElement) -> float:
        # Higher confidence when we have explicit semantic markers
        score = 0.5
        if el.attrs.get("id"):
            score += 0.1
        if el.attrs.get("name"):
            score += 0.1
        if el.attrs.get("role"):
            score += 0.15
        if el.inferred_role != "unknown":
            score += 0.1
        return min(score, 1.0)
