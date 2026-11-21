"""Tests for the optional caution-only LLM judge.

No network is used: the transport is either stubbed or a fake judge is injected.
"""

from __future__ import annotations

from pathlib import Path

from app.services.llm_judge import JudgeVerdict, LlmJudge
from app.services.triage_service import TriageService
from app.triage.types import Category, Priority, Status, Ticket


def _ticket() -> Ticket:
    return Ticket(
        id="T-JUDGE-1",
        received_at="2026-11-16 09:00",
        customer="Test",
        subject="Invoice copy",
        body="Please send my invoice for expenses.",
    )


class FakeJudge:
    """Injected judge that returns a fixed verdict and counts calls."""

    def __init__(self, verdict: JudgeVerdict) -> None:
        self.enabled = True
        self.verdict = verdict
        self.calls = 0

    def judge(self, ticket: Ticket, result):  # noqa: ANN001 - duck-typed verdict receiver
        self.calls += 1
        return self.verdict


class InertJudge:
    enabled = False

    def judge(self, ticket, result):  # pragma: no cover - must never be called
        raise AssertionError("a disabled judge must not be called")


# --- strict verdict parsing -------------------------------------------------
def test_parse_valid_escalate_verdict_with_summary():
    verdict = LlmJudge._parse(
        '{"escalate": true, "reason": "possible account takeover", '
        '"summary": "Customer cannot log in after changing their phone number."}'
    )
    assert verdict.escalate is True
    assert verdict.reason == "possible account takeover"
    assert verdict.summary == "Customer cannot log in after changing their phone number."
    assert verdict.ok is True


def test_parse_valid_no_escalate_verdict():
    verdict = LlmJudge._parse('{"escalate": false, "reason": "routine invoice request"}')
    assert verdict.escalate is False
    assert verdict.ok is True


def test_parse_invalid_json_fails_closed():
    verdict = LlmJudge._parse("this is not json")
    assert verdict.escalate is True
    assert verdict.ok is False


def test_parse_wrong_types_fails_closed():
    verdict = LlmJudge._parse('{"escalate": "yes", "reason": "still text"}')
    assert verdict.escalate is True
    assert verdict.ok is False


def test_parse_missing_reason_fails_closed():
    verdict = LlmJudge._parse('{"escalate": false}')
    assert verdict.escalate is True
    assert verdict.ok is False


def test_malformed_summary_is_dropped_without_changing_routing():
    verdict = LlmJudge._parse(
        '{"escalate": false, "reason": "routine", "summary": {"bad": "type"}}'
    )
    assert verdict.escalate is False
    assert verdict.ok is True
    assert verdict.summary == ""


def test_missing_key_means_disabled(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_JUDGE_ENABLED", raising=False)
    judge = LlmJudge()
    assert judge.enabled is False
    assert judge.judge(_ticket(), object()).escalate is False  # type: ignore[arg-type]


def test_api_timeout_fails_closed(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_JUDGE_ENABLED", "true")
    judge = LlmJudge()

    def boom(_prompt: str) -> str:
        raise TimeoutError("simulated timeout")

    judge._call_api = boom  # type: ignore[method-assign]
    verdict = judge.judge(_ticket(), _decision_result())
    assert verdict.escalate is True
    assert verdict.ok is False
    assert "unavailable" in verdict.reason


# --- service integration ----------------------------------------------------
def _service(tmp_path: Path, judge: object) -> TriageService:
    return TriageService(db_path=str(tmp_path / "judge.db"), judge=judge)  # type: ignore[arg-type]


def _decision_result():
    from app.services.confidence import route
    from app.services.classifier import RulesEngine

    prediction = RulesEngine().predict(_ticket())
    return route(_ticket(), prediction)


def test_judge_escalation_adds_review_without_changing_prediction(tmp_path):
    base = _decision_result()
    judge = FakeJudge(JudgeVerdict(True, "customer distress detected"))
    service = _service(tmp_path, judge)

    service.process_batch([_ticket()])
    result = service.get_ticket("T-JUDGE-1")

    assert judge.calls == 1
    assert result["needs_review"] is True
    assert result["status"] == Status.PENDING_REVIEW.value
    # The judge must NEVER replace the classifier's labels.
    assert result["category"] == (base.category.value if base.category else None)
    assert result["priority"] == (base.priority.value if base.priority else None)
    assert any("LLM judge" in reason for reason in result["reasons"])
    assert result["signals"]["llm_judge"]["escalate"] is True


def test_judge_no_escalation_leaves_decision_untouched_but_keeps_summary(tmp_path):
    base = _decision_result()
    judge = FakeJudge(JudgeVerdict(False, "routine request", "Customer asked for an invoice copy."))
    service = _service(tmp_path, judge)

    service.process_batch([_ticket()])
    result = service.get_ticket("T-JUDGE-1")

    assert result["needs_review"] == base.needs_review
    assert result["status"] == base.status.value
    assert result["signals"]["llm_judge"]["summary"] == "Customer asked for an invoice copy."
    assert result["signals"]["llm_judge"]["escalate"] is False


def test_disabled_judge_is_never_called(tmp_path):
    service = _service(tmp_path, InertJudge())
    service.process_batch([_ticket()])
    assert service.get_ticket("T-JUDGE-1") is not None
