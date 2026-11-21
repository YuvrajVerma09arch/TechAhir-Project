"""Dedicated priority SAFETY layer.

This layer is deliberately separate from the category classifier. Its job is to
catch security breaches, account compromise, financial loss, service-wide
outages, severe impact, explicit urgency and hard deadlines, and to make sure a
potentially critical ticket is NEVER auto-downgraded because some other signal
looked 'low'.

Urgency requires corroborated evidence: a single loud keyword (or an injected
instruction) is not enough. When safety evidence conflicts with the classifier's
priority, safety wins and the conflict is recorded so routing forces a review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from app.services.confidence import strip_injection
from app.triage.types import Prediction, Priority, Ticket

_PRIORITY_ORDER: tuple[Priority, ...] = (Priority.LOW, Priority.MEDIUM, Priority.HIGH, Priority.URGENT)


@dataclass(frozen=True)
class _SafetyPattern:
    label: str
    pattern: re.Pattern[str]


def _patterns(entries: Iterable[tuple[str, str]]) -> tuple[_SafetyPattern, ...]:
    return tuple(_SafetyPattern(label, re.compile(expr, re.IGNORECASE)) for label, expr in entries)


# Specific, corroborating phrases. Broad words like "urgent" are only a mild
# signal and can never alone produce an Urgent decision.
SAFETY_PATTERNS: dict[str, tuple[_SafetyPattern, ...]] = {
    "security_breach": _patterns(
        [
            ("hacked", r"\bhack(?:ed|ing|er)\b|\bgehackt\b"),
            ("account_compromise", r"\baccount (?:was |has been )?compromis"),
            ("unauthorised_activity", r"\bunauthoris(?:ed|z?ed)\b|\bunauthori[sz]ed\b|\bsomeone is using my\b"),
            ("fraud", r"\bfraud\b|\bbetrug\b"),
            ("change_not_mine", r"\b(?:was |were )?changed.{0,40}\bnot me\b|\bwhich was not me\b|\bi did not do it\b|\bi didn't do it\b"),
            ("email_changed", r"\bemail (?:on my account |address )?(?:was |has been )?changed\b"),
            ("takeover_attempt", r"\baccount takeover\b|\bsomeone else (?:is |was )?(?:on|using|logged)"),
            ("khata_block", r"\bखाता\s*ब्लॉक|\bखाता.*ब्लॉक"),
        ]
    ),
    "financial_loss": _patterns(
        [
            ("unauthorised_payment", r"\bunauthoris(?:ed|z?ed) payments?\b|\bunauthori[sz]ed payments?\b"),
            ("charges_not_mine", r"\bcharges? i did not make\b|\b charges? (?:that )?(?:i|we) did not (?:make|authorise|authorize)\b"),
            ("money_out", r"\bmoney (?:going out|debited|taken|gone)\b|\bपैसे\s*कट|\bmoney.*कट"),
            ("fraudulent_order", r"\bnew orders being placed\b|\borders? (?:being|are) placed.{0,30}\bnot mine\b|\bnot mine\b.{0,30}\borders?\b"),
            ("duplicate_charge", r"\bdouble[ -]charge|\bcharged twice\b|\bduplicate payment|\bcobro duplicado\b"),
        ]
    ),
    "service_outage": _patterns(
        [
            ("whole_office_offline", r"\bwhole office offline\b|\b 모두\s*오프라인"),
            ("all_devices_down", r"\ball (?:of )?(?:our |the )?devices?\b|\bevery device\b|\ball \d+ of our\b"),
            ("unreachable", r"\bunreachable\b|\bnone will reconnect\b|\bwent offline at the same time\b|\boffline at the same time\b"),
            ("service_down", r"\bservice down\b|\ball our sites\b|\baffecting all our sites\b|\bproduction (?:is )?down\b"),
        ]
    ),
    "severe_impact": _patterns(
        [
            ("cannot_work", r"\bnobody here can work\b|\bcannot work\b|\bcan't work\b|\bunable to work\b"),
            ("business_critical", r"\bwhole office depends\b|\bbusiness account\b|\baffecting all our sites\b|\bproduction down\b"),
            ("no_access", r"\bno access to (?:anything|everything|our)\b|\blocked out of my account\b"),
            ("escalation_request", r"\bplease escalate\b|\bescalate this\b|\bneeds? escalation\b"),
        ]
    ),
    "explicit_urgency": _patterns(
        [
            ("urgent", r"\burgent\b|\bcritical\b|\bemergency\b|\bdringend\b|\burgente\b|\btुरंत"),
            ("asap", r"\basap\b|\bimmediately\b|\bright now\b|\bstraight away\b"),
        ]
    ),
    "hard_deadline": _patterns(
        [
            ("deadline", r"\bdeadline\b|\btime[ -]sensitive\b|\bby end of day\b"),
            ("imminent", r"\bwithin the hour\b|\bbefore more\b|\bby friday\b|\btoday\b"),
        ]
    ),
}

# A compromise plus a lock-out is a single, strongly corroborated critical case
# (the polite T-0259 ticket). We treat it as its own high-strength signal.
_LOCKOUT_PATTERN = re.compile(
    r"\bpassword is not accepted\b|\bcan(?:not|'t) log ?in\b|\bcan no longer log ?in\b|\blocked out\b|\bno longer have access\b",
    re.IGNORECASE,
)

_PRIMARY_SIGNALS = ("security_breach", "financial_loss", "service_outage")


@dataclass
class SafetyAssessment:
    """Outcome of the dedicated safety analysis."""

    priority: Priority
    confidence: float
    safety_signals: dict[str, list[str]] = field(default_factory=dict)
    escalated: bool = False
    conflict: bool = False
    reasons: list[str] = field(default_factory=list)


def _safety_signals(text: str) -> dict[str, list[str]]:
    """Detect corroborating safety signals in sanitised ticket text."""
    found: dict[str, list[str]] = {}
    for name, patterns in SAFETY_PATTERNS.items():
        hits: list[str] = []
        for item in patterns:
            if item.pattern.search(text):
                hits.append(item.label)
        if hits:
            found[name] = hits

    if "security_breach" in found and _LOCKOUT_PATTERN.search(text):
        found["account_takeover"] = ["compromise_with_lockout"]
    return found


def _rank(priority: Priority) -> int:
    """Numeric severity rank used to enforce the never-downgrade invariant."""
    return _PRIORITY_ORDER.index(priority)


def _decide(baseline: Priority, signals: dict[str, list[str]]) -> Priority:
    """Return the safety-proposed priority (never lower than the baseline)."""
    proposed = baseline
    primary_present = [name for name in _PRIMARY_SIGNALS if name in signals]

    # Urgent requires strong, corroborated evidence.
    urgent = (
        "account_takeover" in signals
        or len(primary_present) >= 2
        or ("service_outage" in signals and "severe_impact" in signals)
        or (
            bool(primary_present)
            and "explicit_urgency" in signals
            and "hard_deadline" in signals
        )
    )

    if urgent:
        proposed = Priority.URGENT
    elif primary_present or "severe_impact" in signals or "hard_deadline" in signals:
        proposed = Priority.HIGH
    elif "explicit_urgency" in signals:
        # One loud word alone is only a mild escalation, never Urgent.
        proposed = Priority.HIGH
    else:
        proposed = baseline

    # Absolute safety invariant: never downgrade a potentially critical ticket.
    if _rank(proposed) < _rank(baseline):
        proposed = baseline
    return proposed


class PrioritySafetyEngine:
    """Safety-first priority engine operating on a raw :class:`Prediction`."""

    name = "priority-safety"

    def assess(self, ticket: Ticket, prediction: Prediction) -> SafetyAssessment:
        """Analyse safety signals and decide the appropriate priority."""
        text = f"{ticket.subject or ''}\n{ticket.body or ''}"
        # Injection text is untrusted and must never create urgency.
        text = strip_injection(text)

        signals = _safety_signals(text)
        proposed = _decide(prediction.priority, signals)
        escalated = proposed is not prediction.priority
        conflict = escalated

        if not signals:
            confidence = prediction.priority_confidence
        else:
            confidence = min(0.95, 0.75 + 0.06 * max(0, len(signals) - 1))
            if "account_takeover" in signals:
                confidence = max(confidence, 0.92)
            confidence = max(confidence, prediction.priority_confidence)

        reasons: list[str] = []
        if signals:
            reasons.append("safety signals detected: " + ", ".join(sorted(signals)))
        if escalated:
            reasons.append(
                f"priority escalated from {prediction.priority.value} to {proposed.value} by safety layer"
            )
        if conflict:
            reasons.append(
                "classifier priority conflicted with safety priority; escalated and flagged for review"
            )

        return SafetyAssessment(
            priority=proposed,
            confidence=round(confidence, 4),
            safety_signals=signals,
            escalated=escalated,
            conflict=conflict,
            reasons=reasons,
        )

    def apply(self, ticket: Ticket, prediction: Prediction) -> Prediction:
        """Return a NEW prediction with safety adjustments merged in."""
        assessment = self.assess(ticket, prediction)
        signals = dict(prediction.signals)
        reasons = list(prediction.reasons)

        if assessment.safety_signals:
            signals["safety_signals"] = assessment.safety_signals
            signals["safety_signal_count"] = len(assessment.safety_signals)
        if assessment.escalated:
            signals["priority_escalated"] = True
            signals["priority_escalation_from"] = prediction.priority.value
        if assessment.conflict:
            signals["priority_conflict"] = True
        reasons.extend(assessment.reasons)

        return Prediction(
            category=prediction.category,
            priority=assessment.priority,
            category_confidence=prediction.category_confidence,
            priority_confidence=assessment.confidence,
            signals=signals,
            reasons=reasons,
            engine=prediction.engine,
        )
