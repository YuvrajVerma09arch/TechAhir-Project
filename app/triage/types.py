"""Shared contracts for the Support Ticket Triage system.

This module is the single source of truth for the taxonomy and the interfaces between
the classification engine, the service layer, the API and the dashboard.

Taxonomy is taken from the PROVIDED dataset (candidate/README.txt), not from any generic
default: categories = Billing/Technical/Account/Shipping/Other, priorities = Low/Medium/
High/Urgent. Do not change these values.
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


class Status(str, Enum):
    """Mutually exclusive lifecycle states — a ticket is in exactly one of these."""

    AUTO_CLASSIFIED = "auto_classified"
    PENDING_REVIEW = "pending_review"
    HUMAN_REVIEWED = "human_reviewed"
    FAILED = "failed"


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
class Prediction:
    """Raw output of a classification engine, before routing decisions are applied."""

    category: Category
    priority: Priority
    category_confidence: float
    priority_confidence: float
    signals: Dict[str, Any] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    engine: str = "rules"


@dataclass
class TriageResult:
    """A fully decided ticket: prediction + routing + audit information."""

    id: str
    category: Optional[Category]
    priority: Optional[Priority]
    needs_review: bool
    status: Status
    category_confidence: float = 0.0
    priority_confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)
    signals: Dict[str, Any] = field(default_factory=dict)
    engine: str = "rules"
    latency_ms: float = 0.0

    # --- compatibility aliases used by the assessment's structured-prediction spec ---
    @property
    def ticket_id(self) -> str:
        return self.id

    @property
    def requires_human_review(self) -> bool:
        return self.needs_review

    @property
    def review_reason(self) -> str:
        return "; ".join(self.reasons)

    def to_output_row(self) -> Dict[str, str]:
        """The exact 4-column shape required by results.csv."""
        return {
            "id": self.id,
            "category": "" if self.category is None else self.category.value,
            "priority": "" if self.priority is None else self.priority.value,
            "needs_review": "yes" if self.needs_review else "no",
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticket_id": self.id,
            "category": self.category.value if self.category else None,
            "priority": self.priority.value if self.priority else None,
            "category_confidence": round(self.category_confidence, 4),
            "priority_confidence": round(self.priority_confidence, 4),
            "requires_human_review": self.needs_review,
            "review_reason": self.review_reason,
            "status": self.status.value,
            "engine": self.engine,
        }


class TriageEngine(Protocol):
    """A classification engine must always return a Prediction for a ticket."""

    name: str

    def predict(self, ticket: Ticket) -> Prediction:
        ...


class Classifier(Protocol):
    """Legacy/simple classifier protocol retained for compatibility."""

    name: str

    def classify(self, ticket: Ticket) -> TriageResult:
        ...
