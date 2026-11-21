"""Tests for TriageService: persistence, idempotency, reviews, reporting and exports."""

from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.services.triage_service import TriageService
from app.triage.types import Category, Prediction, Priority, Status, Ticket, TriageEngine


def make_ticket(ticket_id: str, subject: str = "Invoice copy", body: str = "Please send my invoice.") -> Ticket:
    """Arrange helper."""
    return Ticket(
        id=ticket_id,
        received_at="2026-11-16 09:00",
        customer="Test Customer",
        subject=subject,
        body=body,
    )


class FailingEngine:
    """Injected engine that always fails — used to test resilience."""

    name = "failing-engine"

    def predict(self, ticket: Ticket) -> Prediction:  # noqa: D102
        raise RuntimeError("simulated model failure")


class InvalidResponseEngine:
    """Injected engine that returns malformed output."""

    name = "invalid-engine"

    def predict(self, ticket: Ticket) -> Prediction:  # noqa: D102
        return Prediction(
            category=Category.BILLING,
            priority=Priority.LOW,
            category_confidence=99.0,  # impossible confidence
            priority_confidence=0.5,
        )


@pytest.fixture()
def service(tmp_path: Path) -> TriageService:
    return TriageService(db_path=str(tmp_path / "triage.db"))


# ---------------------------------------------------------------------------
# Batch processing & accounting
# ---------------------------------------------------------------------------


def test_process_batch_persists_every_ticket(service: TriageService) -> None:
    # Arrange
    tickets = [make_ticket("T-1"), make_ticket("T-2", "App crashes", "It crashes on start."), make_ticket("T-3", "help", "help")]

    # Act
    stats = service.process_batch(tickets)

    # Assert
    assert stats["total_input"] == 3
    assert stats["new_tickets"] == 3
    assert stats["duplicates"] == 0
    assert stats["auto_classified"] + stats["pending_review"] + stats["human_reviewed"] + stats["failed"] == 3
    assert service.get_ticket("T-1") is not None
    assert service.get_ticket("T-2") is not None
    assert service.get_ticket("T-3") is not None


def test_batch_accounting_invariant_holds(service: TriageService) -> None:
    # Arrange — mix of auto, review and failed
    tickets = [
        make_ticket("T-A", "Invoice copy", "Please send me a copy of the invoice for order LM-1."),
        make_ticket("T-B", "help", "help"),
        make_ticket("T-C", "", ""),
    ]

    # Act
    stats = service.process_batch(tickets)
    report = service.get_report()

    # Assert
    total = stats["total_input"]
    assert total == stats["auto_classified"] + stats["pending_review"] + stats["human_reviewed"] + stats["failed"]
    assert total == report["total_input"]
    assert total == report["auto_classified"] + report["pending_review"] + report["human_reviewed"] + report["failed"]
    assert report["invariant_holds"] is True
    assert report["processed"] == total - report["failed"]


def test_duplicate_processing_is_idempotent(service: TriageService) -> None:
    # Arrange
    tickets = [make_ticket("T-DUP", "Invoice copy", "Please send my invoice.")]

    # Act
    first = service.process_batch(tickets)
    second = service.process_batch(tickets)

    # Assert
    assert first["new_tickets"] == 1
    assert second["new_tickets"] == 0
    assert second["duplicates"] == 1
    assert second["total_input"] == first["total_input"]
    assert service.get_report()["total_input"] == 1


def test_all_four_statuses_are_mutually_exclusive(service: TriageService) -> None:
    # Arrange
    tickets = [
        make_ticket("T-AUTO", "Invoice copy", "Please send a copy of the invoice for my records, order LM-1."),
        make_ticket("T-REVIEW", "help", "help"),
        make_ticket("T-FAIL", "", ""),
    ]
    service.process_batch(tickets)

    # Act
    service.submit_review("T-REVIEW", Category.BILLING, Priority.MEDIUM, reviewer="alice")
    statuses = {t["status"] for t in [service.get_ticket(ticket.id) for ticket in tickets]}

    # Assert
    assert Status.HUMAN_REVIEWED.value in statuses
    assert Status.FAILED.value in statuses
    assert service.get_ticket("T-AUTO")["status"] == Status.AUTO_CLASSIFIED.value


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


def test_empty_ticket_is_marked_failed_not_lost(service: TriageService) -> None:
    # Act
    service.process_batch([make_ticket("T-EMPTY", "", "   ")])

    # Act
    record = service.get_ticket("T-EMPTY")

    # Assert
    assert record is not None
    assert record["status"] == Status.FAILED.value
    assert record["needs_review"] is True
    assert any("empty" in reason.lower() or "missing" in reason.lower() for reason in record["reasons"])


def test_missing_ticket_id_is_marked_failed(service: TriageService) -> None:
    # Arrange
    broken = make_ticket("", "Invoice copy", "Please send my invoice.")
    # Act
    service.process_batch([broken])
    # Assert
    # An empty id is still persisted so the ticket is never silently dropped.
    assert service.get_report()["total_input"] == 1
    assert service.get_report()["failed"] == 1


def test_model_exception_is_contained_and_marked_failed(tmp_path: Path) -> None:
    # Arrange
    service = TriageService(db_path=str(tmp_path / "failing.db"), engine=FailingEngine())
    # Act
    stats = service.process_batch([make_ticket("T-1"), make_ticket("T-2")])
    # Assert
    assert stats["failed"] == 2
    assert stats["auto_classified"] == 0
    assert all(service.get_ticket(tid)["status"] == Status.FAILED.value for tid in ("T-1", "T-2"))


def test_invalid_model_response_is_marked_failed(tmp_path: Path) -> None:
    # Arrange
    service = TriageService(db_path=str(tmp_path / "invalid.db"), engine=InvalidResponseEngine())
    # Act
    stats = service.process_batch([make_ticket("T-1")])
    # Assert
    assert stats["failed"] == 1
    assert service.get_ticket("T-1")["status"] == Status.FAILED.value


# ---------------------------------------------------------------------------
# Human review
# ---------------------------------------------------------------------------


def test_human_review_corrects_labels_without_overwriting_original_prediction(service: TriageService) -> None:
    # Arrange
    ticket = make_ticket("T-REVIEW", "help", "help")
    service.process_batch([ticket])
    before = service.get_ticket("T-REVIEW")
    assert before["status"] == Status.PENDING_REVIEW.value

    # Act
    updated = service.submit_review("T-REVIEW", Category.TECHNICAL, Priority.HIGH, reviewer="alice")

    # Assert — current result reflects correction
    assert updated["status"] == Status.HUMAN_REVIEWED.value
    assert updated["category"] == Category.TECHNICAL.value
    assert updated["priority"] == Priority.HIGH.value
    assert updated["needs_review"] is False
    assert updated["reviewer"] == "alice"
    # Assert — original prediction immutable
    original = service.get_original_prediction("T-REVIEW")
    assert original["category"] == before["category"]
    assert original["priority"] == before["priority"]


def test_report_reflects_review_transition(service: TriageService) -> None:
    # Arrange
    service.process_batch([make_ticket("T-REVIEW", "help", "help")])
    before = service.get_report()
    assert before["pending_review"] == 1

    # Act
    service.submit_review("T-REVIEW", Category.OTHER, Priority.LOW)
    after = service.get_report()

    # Assert
    assert after["pending_review"] == 0
    assert after["human_reviewed"] == 1
    assert after["total_input"] == after["auto_classified"] + after["pending_review"] + after["human_reviewed"] + after["failed"]


# ---------------------------------------------------------------------------
# Queries & exports
# ---------------------------------------------------------------------------


def test_list_tickets_filters_and_paginates(service: TriageService) -> None:
    # Arrange
    service.process_batch([make_ticket(f"T-{i}", "Invoice copy", "Please send my invoice.") for i in range(5)])

    # Act
    page1 = service.list_tickets(page=1, page_size=2)
    page3 = service.list_tickets(page=3, page_size=2)
    filtered = service.list_tickets(status=Status.AUTO_CLASSIFIED.value)

    # Assert
    assert page1["total"] == 5
    assert len(page1["items"]) == 2
    assert page1["total_pages"] == 3
    assert len(page3["items"]) == 1
    assert filtered["total"] == 5


def test_get_review_queue_contains_uncertain_tickets(service: TriageService) -> None:
    # Arrange
    service.process_batch(
        [
            make_ticket("T-AUTO", "Invoice copy", "Please send a copy of the invoice for my records."),
            make_ticket("T-REVIEW", "help", "help"),
            make_ticket("T-FAIL", "", ""),
        ]
    )

    # Act
    queue = service.get_review_queue()

    # Assert
    ids = {item["id"] for item in queue["items"]}
    assert "T-REVIEW" in ids
    assert "T-FAIL" in ids
    assert "T-AUTO" not in ids


def test_export_csvs_writes_exact_results_schema_and_all_rows(service: TriageService, tmp_path: Path) -> None:
    # Arrange
    service.process_batch([make_ticket(f"T-{i}", "Invoice copy", "Please send my invoice.") for i in range(3)])
    out_dir = tmp_path / "artifacts"

    # Act
    paths = service.export_csvs(out_dir=str(out_dir))

    # Assert — exact columns on results.csv
    with open(paths["results"], newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == ["id", "category", "priority", "needs_review"]
        rows = list(reader)
    assert len(rows) == 3
    assert {row["id"] for row in rows} == {"T-0", "T-1", "T-2"}
    assert all(row["needs_review"] in ("yes", "no") for row in rows)
    assert Path(paths["review_queue"]).exists()
    assert Path(paths["all_predictions"]).exists()


def test_get_report_saves_json(service: TriageService, tmp_path: Path) -> None:
    # Arrange
    service.process_batch([make_ticket("T-1")])
    report_path = tmp_path / "report.json"

    # Act
    report = service.get_report()
    service.save_report(path=str(report_path))

    # Assert
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["total_input"] == report["total_input"] == 1
    assert "automation_coverage" in saved
    assert "processing_duration_ms" in saved
