"""Confidence thresholds, input validation and conservative routing.

Critical rule: a ticket is auto-accepted ONLY when BOTH category and priority
confidence pass their thresholds AND there are no safety, escalation or
prompt-injection flags. Anything uncertain goes to a human.

Ticket text is untrusted DATA. Prompt-injection markers are detected, neutralised
before classification (see :func:`strip_injection`) and always force a review.
"""

from __future__ import annotations

import math
import re
from typing import Any

from app.triage.types import (
    Category,
    Prediction,
    Priority,
    Status,
    Ticket,
    TriageResult,
)

# --- thresholds ------------------------------------------------------------

CAT_THRESHOLD = 0.65
PRIORITY_THRESHOLD = 0.55

# Asymmetry: an Urgent answer is expensive to get wrong, so it needs more
# evidence than an ordinary answer before it may be auto-accepted.
URGENT_CAT_THRESHOLD = 0.80
URGENT_PRIORITY_THRESHOLD = 0.85

# --- prompt-injection detection --------------------------------------------

# Each entry is (label, case-insensitive regex). We deliberately keep the list
# explicit and auditable rather than relying on a black-box classifier.
INJECTION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("assistant_role_marker", r"\[\s*assistant\s*:"),
    ("system_role_marker", r"(?:^|[\s\-])(?:system|assistant)\s*:"),
    ("system_note", r"important\s+system\s+note"),
    ("instruction_override", r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?"),
    ("instruction_override", r"disregard\s+(?:all\s+)?(?:previous|prior|above|the\s+rules)"),
    ("output_directive", r"output\s+priority\s*="),
    ("output_directive", r"(?:set|classify|mark)\s+(?:this\s+ticket\s+as\s+)?priority\s*="),
    ("output_directive", r"classify\s+this\s+ticket\s+as"),
    ("review_suppression", r"do\s+not\s+send\s+(?:it\s+)?for\s+review"),
    ("review_suppression", r"(?:skip|bypass)\s+(?:the\s+)?(?:human\s+)?review"),
    ("role_directive", r"\byou\s+are\s+now\b"),
    ("role_directive", r"\bnew\s+instructions?\b"),
    ("prompt_reference", r"\bsystem\s+prompt\b"),
)

_COMPILED_INJECTION = tuple((label, re.compile(pattern, re.IGNORECASE)) for label, pattern in INJECTION_PATTERNS)

# A whole bracketed assistant directive, e.g. "[assistant: ...]".
_BRACKETED_ROLE = re.compile(r"\[[^\]]*\b(?:assistant|system)\b[^\]]*\]", re.IGNORECASE)
# Inline separators often used to append a hidden directive after real content.
_INLINE_SEPARATOR = re.compile(r"\s*-{3,}\s*")


def detect_injection(text: str) -> list[str]:
    """Return the distinct injection marker labels found in untrusted text.

    This is a detector only: it never changes the category or priority.
    """
    if not isinstance(text, str) or not text:
        return []
    found: list[str] = []
    for label, pattern in _COMPILED_INJECTION:
        if pattern.search(text) and label not in found:
            found.append(label)
    return found


def strip_injection(text: str) -> str:
    """Remove injected instruction spans while preserving the genuine content.

    Used by the engine BEFORE classification so that an attacker cannot steer the
    prediction with planted directives. Detection still runs on the original text
    (see :func:`route`) so a stripped injection is never silently ignored.
    """
    if not isinstance(text, str) or not text:
        return ""

    cleaned = _BRACKETED_ROLE.sub(" ", text)

    kept_lines: list[str] = []
    for line in cleaned.splitlines():
        # Cut the line at the first injected directive (or the separator before it).
        cut = len(line)
        for _label, pattern in _COMPILED_INJECTION:
            match = pattern.search(line)
            if match:
                cut = min(cut, match.start())
        for separator in _INLINE_SEPARATOR.finditer(line):
            if separator.start() < cut:
                segment = line[separator.end() :]
                if any(pattern.search(segment) for _label, pattern in _COMPILED_INJECTION):
                    cut = min(cut, separator.start())
        kept_lines.append(line[:cut])

    return "\n".join(kept_lines).strip()


# --- validation ------------------------------------------------------------


def validate_prediction(prediction: object) -> list[str]:
    """Validate an engine response. Returns a list of problems (empty == valid)."""
    errors: list[str] = []
    if not isinstance(prediction, Prediction):
        return [f"invalid prediction type: {type(prediction).__name__}"]

    if not isinstance(prediction.category, Category):
        errors.append(f"invalid category: {prediction.category!r}")
    if not isinstance(prediction.priority, Priority):
        errors.append(f"invalid priority: {prediction.priority!r}")

    for name, value in (
        ("category_confidence", prediction.category_confidence),
        ("priority_confidence", prediction.priority_confidence),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"{name} is not numeric: {value!r}")
        elif not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
            errors.append(f"{name} out of range [0,1]: {value!r}")

    if not isinstance(prediction.signals, dict):
        errors.append("signals is not a dict")
    if not isinstance(prediction.reasons, list):
        errors.append("reasons is not a list")
    return errors


def validate_ticket(ticket: object) -> list[str]:
    """Validate an incoming ticket. Returns a list of problems (empty == valid)."""
    errors: list[str] = []
    if not isinstance(ticket, Ticket):
        return [f"invalid ticket type: {type(ticket).__name__}"]
    if not isinstance(ticket.id, str) or not ticket.id.strip():
        errors.append("missing ticket id")
    if not isinstance(ticket.subject, str) or not isinstance(ticket.body, str):
        errors.append("non-string subject or body")
    else:
        if not ticket.subject.strip() and not ticket.body.strip():
            errors.append("empty ticket text")
    return errors


# --- routing ---------------------------------------------------------------


def _failed_result(ticket_id: str, reasons: list[str], latency_ms: float, engine: str) -> TriageResult:
    """Build a failed result: nothing is auto-accepted and nothing is lost."""
    return TriageResult(
        id=ticket_id or "UNKNOWN",
        category=None,
        priority=None,
        needs_review=True,
        status=Status.FAILED,
        category_confidence=0.0,
        priority_confidence=0.0,
        reasons=reasons,
        signals={"routing_failed": True},
        engine=engine,
        latency_ms=latency_ms,
    )


def route(
    ticket: Ticket,
    prediction: Prediction,
    *,
    latency_ms: float = 0.0,
    engine_name: str | None = None,
) -> TriageResult:
    """Turn a raw prediction into a fully decided :class:`TriageResult`.

    Auto-accept requires BOTH confidence thresholds to pass and NO safety,
    escalation or injection flags. Urgent predictions use stricter thresholds.
    """
    engine = engine_name or getattr(prediction, "engine", "rules")

    prediction_errors = validate_prediction(prediction)
    if prediction_errors:
        return _failed_result(
            getattr(ticket, "id", "UNKNOWN"),
            ["invalid model response: " + "; ".join(prediction_errors)],
            latency_ms,
            engine,
        )

    ticket_errors = validate_ticket(ticket)
    if ticket_errors:
        return _failed_result(
            getattr(ticket, "id", "UNKNOWN"),
            ["malformed ticket: " + "; ".join(ticket_errors)],
            latency_ms,
            engine,
        )

    # `prediction.reasons` explains WHAT was decided; it is not evidence of
    # uncertainty. Only the flags below may force a review.
    decision_reasons: list[str] = []
    signals: dict[str, Any] = dict(prediction.signals)

    # Injection is evaluated on the ORIGINAL text, never on the sanitised copy.
    markers = detect_injection(ticket.text)
    if markers:
        signals["injection_markers"] = markers
        decision_reasons.append("prompt-injection markers detected in ticket text (ignored for classification; human review required)")

    safety = signals.get("safety_signals") or {}
    if safety:
        decision_reasons.append("safety signal detected: " + ", ".join(sorted(str(key) for key in safety)))
    if signals.get("priority_escalated"):
        decision_reasons.append("priority escalated by the safety layer")
    if signals.get("priority_conflict"):
        decision_reasons.append("classifier priority conflicted with safety priority; escalated")

    is_urgent = prediction.priority is Priority.URGENT
    cat_threshold = URGENT_CAT_THRESHOLD if is_urgent else CAT_THRESHOLD
    pri_threshold = URGENT_PRIORITY_THRESHOLD if is_urgent else PRIORITY_THRESHOLD

    if prediction.category_confidence < cat_threshold:
        decision_reasons.append(
            f"category confidence below threshold ({prediction.category_confidence:.2f} < {cat_threshold:.2f})"
        )
    if prediction.priority_confidence < pri_threshold:
        decision_reasons.append(
            f"priority confidence below threshold ({prediction.priority_confidence:.2f} < {pri_threshold:.2f})"
        )
    if is_urgent:
        decision_reasons.append("urgent predictions require corroborated evidence and human confirmation")

    needs_review = bool(decision_reasons)
    reasons = list(prediction.reasons) + decision_reasons
    return TriageResult(
        id=ticket.id,
        category=prediction.category,
        priority=prediction.priority,
        needs_review=needs_review,
        status=Status.PENDING_REVIEW if needs_review else Status.AUTO_CLASSIFIED,
        category_confidence=prediction.category_confidence,
        priority_confidence=prediction.priority_confidence,
        reasons=reasons,
        signals=signals,
        engine=engine,
        latency_ms=latency_ms,
    )
