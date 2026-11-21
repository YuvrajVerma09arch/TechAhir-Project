"""Shared contracts for the triage engine.

All agents build against these types. Do not change this file without coordinating
with the orchestrator — it is the interface between the classifier, API and UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol


class Category(str, Enum):
    BILLING = "Billing"
    TECHNICAL = "Technical"
    ACCOUNT = "Account"
    SHIPPING = "Shipping"
    OTHER = "Other"


class Priority(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    URGENT = "Urgent"


@dataclass(frozen=True)
class Ticket:
    id: str
    received_at: str
    customer: str
    subject: str
    body: str

    @property
    def text(self) -> str:
        return f"{self.subject}\n{self.body}"


@dataclass
class TriageResult:
    id: str
    category: Optional[Category]
    priority: Optional[Priority]
    needs_review: bool
    category_confidence: float = 0.0
    priority_confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)
    signals: Dict[str, Any] = field(default_factory=dict)
    engine: str = "heuristic"
    latency_ms: float = 0.0

    def to_output_row(self) -> Dict[str, str]:
        """The exact 4-column shape required by results.csv."""
        return {
            "id": self.id,
            "category": "" if self.needs_review or self.category is None else self.category.value,
            "priority": "" if self.needs_review or self.priority is None else self.priority.value,
            "needs_review": "yes" if self.needs_review else "no",
        }


class Classifier(Protocol):
    """A classifier must return a TriageResult for every ticket, always."""

    name: str

    def classify(self, ticket: Ticket) -> TriageResult:
        ...
