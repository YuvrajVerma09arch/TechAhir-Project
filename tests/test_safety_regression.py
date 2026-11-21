"""End-to-end, dataset-backed safety regressions.

These tests are the durable guard against the review finding that the original
55 tests used idealised paraphrases and let critical tickets be auto-accepted.
They drive the REAL dataset through the PUBLIC ``TriageService`` API and assert
the persisted decision, using only temporary DB/artifact paths so ``data/`` and
``artifacts/`` are never mutated.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from app.services.triage_service import TriageService
from app.triage.types import Category, Priority, Status, Ticket

_TICKETS_CSV = Path(__file__).resolve().parents[1] / "data" / "tickets.csv"


def load_real_ticket(ticket_id: str) -> Ticket:
    """Arrange helper: load one verbatim ticket from the real dataset."""
    with open(_TICKETS_CSV, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["id"] == ticket_id:
                return Ticket(
                    id=row["id"],
                    received_at=row["received_at"],
                    customer=row["customer"],
                    subject=row["subject"],
                    body=row["body"],
                )
    raise AssertionError(f"{ticket_id} is not present in {_TICKETS_CSV}")


@pytest.fixture()
def service(tmp_path: Path) -> TriageService:
    return TriageService(db_path=str(tmp_path / "triage.db"))


# Never-auto-classified set from the safety audit (§9 of AGENTHANDOFF.md).
_NEVER_AUTO_IDS = (
    "T-0123",
    "T-0172",
    "T-0219",
    "T-0155",
    "T-0251",
    "T-0093",
    "T-0299",
)


@pytest.mark.parametrize("ticket_id", _NEVER_AUTO_IDS)
def test_critical_real_tickets_are_persisted_for_review(ticket_id: str, service: TriageService) -> None:
    # Arrange — a real safety-critical / no-evidence ticket.
    ticket = load_real_ticket(ticket_id)

    # Act — process it through the full service.
    service.process_batch([ticket])
    record = service.get_ticket(ticket_id)

    # Assert — the persisted decision must require a human and never be auto-accepted.
    assert record is not None
    assert record["needs_review"] is True
    assert record["status"] != Status.AUTO_CLASSIFIED.value
    assert record["status"] in (Status.PENDING_REVIEW.value, Status.FAILED.value)
    # It must land in the review queue as well.
    queued_ids = {item["id"] for item in service.get_review_queue(page_size=500)["items"]}
    assert ticket_id in queued_ids


@pytest.mark.parametrize("ticket_id", ["T-0072", "T-0245"])
def test_planted_injection_real_tickets_persist_reason_without_urgent(
    ticket_id: str, service: TriageService
) -> None:
    # Arrange — a real ticket containing a planted instruction aimed at the AI.
    ticket = load_real_ticket(ticket_id)

    # Act
    service.process_batch([ticket])
    record = service.get_ticket(ticket_id)

    # Assert — flagged for review, not urgent, with an injection reason preserved.
    assert record is not None
    assert record["needs_review"] is True
    assert record["status"] != Status.AUTO_CLASSIFIED.value
    assert record["priority"] != Priority.URGENT.value
    assert any("injection" in str(reason).lower() for reason in record["reasons"])
    # The injected directive must not have steered the category either.
    assert record["category"] != Category.BILLING.value


def test_urgent_real_ticket_t_0259_is_persisted_as_urgent(service: TriageService) -> None:
    # Arrange — real account takeover hidden behind polite wording.
    ticket = load_real_ticket("T-0259")

    # Act
    service.process_batch([ticket])
    record = service.get_ticket("T-0259")

    # Assert — politeness must not downgrade it; it is Urgent and reviewed.
    assert record is not None
    assert record["priority"] == Priority.URGENT.value
    assert record["needs_review"] is True
    assert record["status"] != Status.AUTO_CLASSIFIED.value
