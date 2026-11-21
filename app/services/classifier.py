"""Transparent, deterministic category classifier and rules engine.

There are NO ground-truth labels in the provided dataset. This is deliberately
NOT described as a trained/supervised model: it is a conservative, auditable
keyword/feature rules baseline that runs fully offline with the standard library.

Every decision records its matched signals and a human-readable reason.
Confidence is derived from (a) the absolute strength of the matched evidence and
(b) the margin between the top two category scores — weak or ambiguous evidence
produces low confidence, so uncertain tickets are routed to a human.

An optional TF-IDF exemplar-similarity signal can be added later, but the rules
below work on their own and remain the authoritative signal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Iterable

from app.services.confidence import detect_injection, strip_injection
from app.services.priority_engine import PrioritySafetyEngine
from app.triage.types import Category, Prediction, Priority, Ticket

# --- category signals -------------------------------------------------------
# (label, case-insensitive regex, weight). Weights reflect how diagnostic a
# term is. Subject matches are multiplied by SUBJECT_WEIGHT below.

SUBJECT_WEIGHT = 2.5
STRONG_EVIDENCE = 3.0  # score at which evidence strength saturates


@dataclass(frozen=True)
class _Signal:
    label: str
    pattern: re.Pattern[str]
    weight: float


def _signals(entries: Iterable[tuple[str, str, float]]) -> tuple[_Signal, ...]:
    return tuple(_Signal(label, re.compile(pattern, re.IGNORECASE), weight) for label, pattern, weight in entries)


CATEGORY_SIGNALS: dict[Category, tuple[_Signal, ...]] = {
    Category.BILLING: _signals(
        [
            ("invoice", r"\binvoic(?:e|es|ing)\b|\brechnung", 2.5),
            ("receipt", r"\breceipt\b|\bbeleg\b|\bquittung", 2.0),
            ("charge", r"\bcharg(?:e|ed|es|ing)\b|\bcharged twice\b|\bcobro", 2.5),
            ("double_payment", r"\bdouble[ -]charge|\bduplicate payment|\bdouble payment|\b charged twice", 2.5),
            ("payment", r"\bpayment\b|\bpay(?:ing|ment)?\b|\bpaid\b|\bpaypal\b", 1.5),
            ("refund", r"\brefund\b|\breimburse", 2.0),
            ("card", r"\bcard\b|\bcrédit\b|\bkarte\b", 1.5),
            ("subscription", r"\bsubscription\b|\brenewal\b|\brenewed\b|\babonnement\b", 2.0),
            ("promo_discount", r"\bpromo\b|\bdiscount\b|\bcoupon\b|\brabatt", 1.5),
            ("pricing", r"\bprice\b|\bpricing\b|\bcost\b|\bbilling\b|\bbill\b", 1.5),
            ("money_debited", r"\bपैसे\s*कट|\bmoney (?:going out|debited|taken)", 2.5),
        ]
    ),
    Category.TECHNICAL: _signals(
        [
            ("app", r"\bapp\b|\bapplication\b|\bアプリ", 1.5),
            ("crash", r"\bcrash(?:es|ed|ing)?\b|\bstürzt ab\b|\b抽象", 2.5),
            ("sync", r"\bsync(?:ing|hronis\w*)?\b|\bnot syncing\b", 2.5),
            ("lag_slow", r"\blag(?:ging|gy)?\b|\bslow\b|\b遅い\b|\blento\b", 2.0),
            ("error", r"\berror\b|\bfails?\b|\bfailure\b|\bfehler\b|\berrore", 2.0),
            ("export", r"\bexport\b|\bexporting\b", 2.0),
            ("login_technical", r"\blog[ -]?in\b|\bcan(?:not|'t) log\b|\bno puedo entrar\b|\bconnexion", 1.5),
            ("device", r"\bdevice\b|\bdevices\b|\bhub\b|\bunits?\b", 1.5),
            ("disconnect", r"\bdisconnect\w*\b|\boffline\b|\bunreachable\b", 2.0),
            ("update_technical", r"\bupdate\b|\bupdate[sd]?\b|\bnach dem update", 1.5),
            ("broken", r"\bbroken\b|\bnot working\b|\bwill not open\b|\bwon't open\b|\bfreeze", 2.0),
        ]
    ),
    Category.ACCOUNT: _signals(
        [
            ("account", r"\baccount\b|\bcompte\b|\bcuenta\b|\bkonto\b|\bखाता", 2.0),
            ("password", r"\bpassword\b|\bpasswort\b|\bcontraseña", 1.5),
            ("reset_link", r"\breset link\b|\breset email\b|\bpassword reset\b", 2.0),
            ("email_change", r"\bemail (?:address )?(?:was )?chang|\bchange (?:my )?email\b|\balterar e-?mail\b", 2.5),
            ("locked_out", r"\blocked out\b|\blocked\b|\bgesperrt\b", 2.0),
            ("two_factor", r"\btwo[ -]?factor\b|\b2fa\b|\blogin codes\b|\bverification code", 2.0),
            ("close_account", r"\bclose my account\b|\bdelete my account\b|\baccount deletion\b", 2.5),
            ("personal_data", r"\bdata privacy\b|\brequest for my data\b|\bpersonal data\b|\bdatos personales", 2.0),
            ("compromise", r"\bhack(?:ed|ing)?\b|\bfraud\b|\bunauthoris(?:ed|ed)\b|\bunauthorized\b|\bcompromis", 2.0),
        ]
    ),
    Category.SHIPPING: _signals(
        [
            ("delivery", r"\bdeliver(?:y|ies|ing|ed)?\b|\bship(?:ping|ped)?\b|\bversand|\blivraison", 2.5),
            ("tracking", r"\btrack(?:ing)?\b|\bnon aggiornato\b", 2.5),
            ("order", r"\border\b|\bbestellung\b|\bcommande", 1.5),
            ("arrival", r"\barriv(?:ed|al)\b|\barrived damaged\b|\bnot arrived\b|\bdoes not arrive", 2.0),
            ("package", r"\bpackage\b|\bparcel\b|\bbroken on arrival", 2.0),
            ("address", r"\baddress\b|\badresse\b", 1.5),
            ("wrong_item", r"\bwrong item\b|\bwrong product\b|\bगलत सामान|\bincorrect item", 2.5),
            ("damaged", r"\bdamaged\b|\bbroken on arrival", 2.0),
        ]
    ),
    Category.OTHER: _signals(
        [
            ("business_enquiry", r"\bbusiness enquiry\b|\breseller\b|\bpartnership\b|\bdistributor", 2.5),
            ("careers", r"\bcareers?\b|\bjob application\b|\brecruitment\b|\bCV\b", 2.5),
            ("suggestion", r"\bsuggestion\b|\bidea for the app\b|\bfeature request\b|\bwidgets?\b", 2.0),
            ("feedback", r"\bgreat product\b|\bthanks\b|\bthank you\b|\bjus saying thanks", 1.5),
            ("complaint", r"\bcomplaint\b|\bridiculous\b|\bunacceptable\b|\bterrible\b|\bworst\b|\bunbelievable", 2.0),
            ("question", r"\bquestion about a feature\b|\bhow do i\b|\bset up a routine\b|\bsecond user", 1.5),
            # NOTE: placeholder subjects ("(no subject)", "asdf", "???", ...)
            # are deliberately NOT a signal here. They carry zero evidence and
            # are removed by _sanitised() before any scoring takes place.
        ]
    ),
}

# Placeholder subjects and near-empty bodies carry no genuine lexical evidence.
# They are excluded from both scoring and the confidence numerator so that an
# empty ticket can never look confidently like "Other".
PLACEHOLDER_SUBJECT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*\(\s*no subject\s*\)\s*$", re.IGNORECASE),
    re.compile(r"^\s*asdf\s*$", re.IGNORECASE),
    re.compile(r"^\s*\?+\s*$"),
    re.compile(r"^\s*re:\s*re:\s*fwd:?\s*$", re.IGNORECASE),
)

NEAR_EMPTY_BODY_PATTERN = re.compile(
    r"^\s*(?:help|sent from my (?:phone|mobile|iphone|android|device)|hi|hello|test|\.+|\?+|-+)\s*$",
    re.IGNORECASE,
)

LOW_EVIDENCE_CONFIDENCE_CAP = 0.30

# --- base priority cues -----------------------------------------------------


@dataclass(frozen=True)
class _PriorityCue:
    label: str
    pattern: re.Pattern[str]
    weight: float


URGENCY_CUES: tuple[_PriorityCue, ...] = (
    _PriorityCue("explicit_urgency", re.compile(r"\burgent\b|\basap\b|\bimmediately\b|\bright now\b|\bcritical\b|\bemergency\b|\btुरंत|\bdringend|\burgente", re.I), 2.0),
    _PriorityCue("hard_deadline", re.compile(r"\bdeadline\b|\bby end of day\b|\btoday\b|\bwithin the hour\b|\bby friday\b|\btime[ -]sensitive|\bbefore more\b", re.I), 1.5),
    _PriorityCue("severe_impact", re.compile(r"\bcannot log in at all\b|\bno access to\b|\bnothing works\b|\bcannot use\b|\bblocked\b|\bcan't work\b|\bwhole office\b|\ball our devices", re.I), 2.0),
    _PriorityCue("frustration", re.compile(r"\bunacceptable\b|\bridiculous\b|\bterrible\b|\bworst\b|\bformal complaint\b|\bunbelievable\b|\bfrustrat", re.I), 1.0),
    _PriorityCue("escalation_request", re.compile(r"\bplease escalate\b|\bescalate this\b", re.I), 1.5),
)

LOW_URGENCY_CUES: tuple[_PriorityCue, ...] = (
    _PriorityCue("low_urgency", re.compile(r"\bwhen you can\b|\bno rush\b|\bwhenever\b|\bwhen you have a moment\b|\bjust a small thing\b|\bsmall question\b|\bquick question\b|\bno hurry\b|\bhope you are well", re.I), 1.0),
)


@dataclass
class CategoryAssessment:
    """Result of the deterministic category classifier."""

    category: Category
    confidence: float
    scores: dict[str, float] = field(default_factory=dict)
    matched_signals: dict[str, list[str]] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    low_evidence: bool = False


@dataclass
class PriorityAssessment:
    """Baseline priority from the classifier, before the safety layer runs."""

    priority: Priority
    confidence: float
    score: float = 0.0
    cues: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def _scan(text: str, signals: tuple[_Signal, ...], multiplier: float) -> tuple[float, list[str]]:
    """Return (score, matched labels) for one text field."""
    score = 0.0
    matched: list[str] = []
    for signal in signals:
        if signal.pattern.search(text):
            score += signal.weight * multiplier
            if signal.label not in matched:
                matched.append(signal.label)
    return score, matched


def _is_placeholder_subject(subject: str) -> bool:
    return any(pattern.match(subject or "") for pattern in PLACEHOLDER_SUBJECT_PATTERNS)


def _is_near_empty_body(body: str) -> bool:
    return bool(NEAR_EMPTY_BODY_PATTERN.match(body or ""))


def category_assessment(ticket: Ticket) -> CategoryAssessment:
    """Score every category over subject + body and return a defensible assessment.

    Subject matches count more than body matches. Confidence combines absolute
    evidence strength with the margin over the runner-up category. Placeholder
    subjects and near-empty bodies are stripped first, so they contribute no
    score and no confidence.
    """
    original_subject = ticket.subject or ""
    original_body = ticket.body or ""
    ticket = _sanitised(ticket)
    subject, body = ticket.subject or "", ticket.body or ""

    scores: dict[str, float] = {}
    matched_signals: dict[str, list[str]] = {}
    for category, signals in CATEGORY_SIGNALS.items():
        subject_score, subject_hits = _scan(subject, signals, SUBJECT_WEIGHT)
        body_score, body_hits = _scan(body, signals, 1.0)
        scores[category.value] = round(subject_score + body_score, 4)
        matched_signals[category.value] = sorted(set(subject_hits + body_hits))

    ranked = sorted(scores.items(), key=lambda item: (-item[1], list(Category).index(_category_from_value(item[0]))))
    top_name, top_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    category = _category_from_value(top_name)

    low_evidence = top_score <= 0 or (
        _is_near_empty_body(original_body) and not original_subject.strip()
    )

    if top_score <= 0:
        # No genuine evidence at all: the honest answer is Other with very low confidence.
        category = Category.OTHER
        confidence = 0.05
    else:
        strength = min(1.0, top_score / STRONG_EVIDENCE)
        margin_ratio = max(0.0, (top_score - runner_up) / top_score)
        confidence = round(0.05 + 0.90 * strength * (0.40 + 0.60 * margin_ratio), 4)

    if low_evidence:
        # Minimum-evidence gate: an empty/placeholder ticket must never clear a
        # confidence threshold, regardless of category.
        confidence = min(confidence, LOW_EVIDENCE_CONFIDENCE_CAP)

    reasons = [
        f"category {category.value}: top score {top_score:g}, runner-up {runner_up:g}",
        "matched signals: " + (", ".join(matched_signals[category.value]) or "none"),
    ]
    if low_evidence:
        reasons.append("low-evidence gate: placeholder/near-empty text excluded from scoring")

    return CategoryAssessment(
        category=category,
        confidence=min(1.0, max(0.0, confidence)),
        scores=scores,
        matched_signals=matched_signals,
        reasons=reasons,
        low_evidence=low_evidence,
    )


def _category_from_value(value: str) -> Category:
    for member in Category:
        if member.value == value:
            return member
    return Category.OTHER


def priority_assessment(ticket: Ticket, category_confidence: float) -> PriorityAssessment:
    """Baseline priority from explicit urgency cues.

    This is intentionally mild: it never emits Urgent. The dedicated safety
    layer in :mod:`priority_engine` owns critical escalation.
    """
    ticket = _sanitised(ticket)
    text = f"{ticket.subject or ''}\n{ticket.body or ''}"

    score = 0.0
    cues: list[str] = []
    for cue in URGENCY_CUES:
        if cue.pattern.search(text):
            score += cue.weight
            cues.append(cue.label)

    low_present = False
    for cue in LOW_URGENCY_CUES:
        if cue.pattern.search(text):
            score -= cue.weight
            low_present = True
            cues.append(cue.label)

    if score >= 3.0:
        priority = Priority.HIGH
    elif score >= 1.0:
        priority = Priority.MEDIUM
    else:
        priority = Priority.LOW

    confidence = 0.50
    if cues:
        confidence += min(0.30, 0.12 * len(cues))
    if score >= 2.0:
        confidence += 0.10
    if category_confidence >= 0.65:
        confidence += 0.10  # a clear, complete ticket makes 'routine' meaningful
    if low_present:
        confidence += 0.05
    if low_present and any(cue in ("explicit_urgency", "hard_deadline") for cue in cues):
        confidence -= 0.25  # contradictory urgency signals

    confidence = round(min(0.95, max(0.05, confidence)), 4)
    reasons = [f"base priority {priority.value} from urgency score {score:g} (cues: {', '.join(cues) or 'none'})"]
    return PriorityAssessment(priority=priority, confidence=confidence, score=score, cues=cues, reasons=reasons)


# --- public engine ----------------------------------------------------------


class RuleBasedClassifier:
    """Deterministic category + baseline priority classifier.

    Implements a small self-contained surface used by :class:`RulesEngine`.
    The full :class:`~app.triage.types.Prediction` returned by ``predict`` is
    still subject to the safety layer before any routing decision is made.
    """

    name = "rules"

    def predict_category(self, ticket: Ticket) -> CategoryAssessment:
        """Classify the category only (sanitising untrusted text first)."""
        return category_assessment(ticket)

    def predict_priority(self, ticket: Ticket, category_confidence: float = 0.0) -> PriorityAssessment:
        """Baseline priority only (no safety escalation)."""
        return priority_assessment(ticket, category_confidence)

    def predict(self, ticket: Ticket) -> Prediction:
        """Return a structured :class:`Prediction` for the ticket."""
        cat = self.predict_category(ticket)
        pri = self.predict_priority(ticket, cat.confidence)
        signals: dict[str, object] = {
            "category_scores": cat.scores,
            "category_signals": cat.matched_signals,
            "priority_cues": pri.cues,
            "priority_score": round(pri.score, 4),
        }
        if cat.low_evidence:
            signals["low_evidence"] = True
        return Prediction(
            category=cat.category,
            priority=pri.priority,
            category_confidence=cat.confidence,
            priority_confidence=pri.confidence,
            signals=signals,
            reasons=cat.reasons + pri.reasons,
            engine=self.name,
        )


class RulesEngine:
    """Top-level engine combining rules classification + safety + injection awareness.

    Satisfies the :class:`~app.triage.types.TriageEngine` protocol
    (``name`` and ``predict(ticket) -> Prediction``). The engine never treats
    ticket text as instructions: injected directives are stripped before
    analysis and recorded as a signal that forces human review downstream.
    """

    name = "rules-v1"

    def __init__(self) -> None:
        self.classifier = RuleBasedClassifier()
        self.safety = PrioritySafetyEngine()

    def predict(self, ticket: Ticket) -> Prediction:
        prediction = self.classifier.predict(ticket)
        prediction = self.safety.apply(ticket, prediction)
        prediction.engine = self.name

        markers = detect_injection(ticket.text)
        if markers:
            prediction.signals["injection_markers"] = markers
        return prediction


def _sanitised(ticket: Ticket) -> Ticket:
    """Return a copy with untrusted injection spans and zero-evidence text removed.

    Placeholder subjects and near-empty bodies are data hygiene, not evidence:
    keeping them would let an empty ticket score as a confident "Other".
    """
    subject = strip_injection(ticket.subject or "")
    body = strip_injection(ticket.body or "")
    if _is_placeholder_subject(subject):
        subject = ""
    if _is_near_empty_body(body):
        body = ""
    return replace(ticket, subject=subject, body=body)
