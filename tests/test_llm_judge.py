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


# --- Gemini provider --------------------------------------------------------
def test_gemini_key_is_auto_detected(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "AIza" + "x" * 35)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    judge = LlmJudge()
    assert judge.provider == "gemini"
    assert judge.model == "gemini-3.8-flash"


def test_explicit_openai_provider_overrides_detection(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "AIza" + "x" * 35)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "")
    judge = LlmJudge()
    assert judge.provider == "openai"
    assert judge.model == "gpt-4o-mini"


def test_gemini_request_shape_and_response(monkeypatch):
    import json as _json
    import urllib.request as _urllib

    monkeypatch.setenv("LLM_API_KEY", "AIza" + "x" * 35)
    monkeypatch.setenv("LLM_JUDGE_ENABLED", "true")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    judge = LlmJudge()

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            text = _json.dumps(
                {
                    "escalate": True,
                    "reason": "possible account takeover",
                    "summary": "Customer lost access to their account.",
                }
            )
            return _json.dumps(
                {"candidates": [{"content": {"parts": [{"text": text}]}}]}
            ).encode("utf-8")

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["key_header"] = request.headers.get("X-goog-api-key")
        captured["body"] = _json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(_urllib, "urlopen", fake_urlopen)
    verdict = judge.judge(_ticket(), _decision_result())

    assert "models/gemini-3.8-flash:generateContent" in captured["url"]
    assert captured["key_header"] == judge.api_key
    assert captured["body"]["generationConfig"]["temperature"] == 0
    assert captured["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert verdict.escalate is True
    assert verdict.summary == "Customer lost access to their account."


def test_parse_accepts_fenced_json():
    verdict = LlmJudge._parse(
        '```json\n{"escalate": false, "reason": "routine", "summary": "Invoice request."}\n```'
    )
    assert verdict.escalate is False
    assert verdict.summary == "Invoice request."


# --- Groq provider ----------------------------------------------------------
def test_groq_key_is_auto_detected(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "gsk_" + "x" * 40)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_BASE", raising=False)
    judge = LlmJudge()
    assert judge.provider == "groq"
    assert judge.model == "openai/gpt-oss-20b"
    assert judge.base_url == "https://api.groq.com/openai/v1"


def test_groq_provider_uses_openai_compatible_call(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "gsk_" + "x" * 40)
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_JUDGE_ENABLED", "true")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    judge = LlmJudge()

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return __import__("json").dumps({
                "choices": [{"message": {"content":
                    '{"escalate": false, "reason": "routine", "summary": "Invoice request."}'}}]
            }).encode("utf-8")

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["ua"] = request.headers.get("User-agent")
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    verdict = judge.judge(_ticket(), _decision_result())

    assert "/chat/completions" in captured["url"]
    assert captured["ua"] == "support-ticket-triage/1.0"
    assert verdict.escalate is False
    assert verdict.summary == "Invoice request."
