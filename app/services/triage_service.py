"""Application service: orchestrates ingestion, prediction, routing and storage.

The service is the single entry point used by the API layer. It is tolerant of
bad input, idempotent for repeated ticket ids, and preserves the original engine
prediction even after a human correction.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.database import Database
from app.services.classifier import RulesEngine
from app.services.confidence import route, validate_prediction, validate_ticket
from app.services.reporting import build_report, export_csvs, save_report
from app.triage.types import (
    Category,
    Prediction,
    Priority,
    Status,
    Ticket,
    TriageEngine,
    TriageResult,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return value.value if isinstance(value, Enum) else str(value)


class TriageService:
    """End-to-end triage service backed by SQLite."""

    def __init__(self, db_path: str = "artifacts/triage.db", engine: TriageEngine | None = None) -> None:
        self.db = Database(db_path)
        # Generated artefacts live beside the database. Tests use a temp DB, so their
        # reports/CSVs stay in the temp dir and never overwrite the committed 300-ticket run.
        self.artifacts_dir = os.path.dirname(os.path.abspath(db_path)) or os.getcwd()
        # An engine may be injected (e.g. a failing engine in resilience tests).
        self.engine: TriageEngine = engine if engine is not None else RulesEngine()

    # ------------------------------------------------------------------
    # ingestion
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce_ticket(item: Any, index: int) -> Ticket:
        """Best-effort conversion of incoming data into a Ticket dataclass."""
        if isinstance(item, Ticket):
            return item
        if isinstance(item, dict):
            return Ticket(
                id=str(item.get("id") or ""),
                received_at=str(item.get("received_at") or ""),
                customer=str(item.get("customer") or ""),
                subject=str(item.get("subject") or ""),
                body=str(item.get("body") or ""),
            )
        # Unknown objects become a detectable, empty ticket rather than crashing.
        return Ticket(id=f"INVALID-{index}", received_at="", customer="", subject="", body="")

    @staticmethod
    def _sentinel_prediction(ticket_id: str, reasons: list[str], engine: str) -> Prediction:
        """A no-evidence prediction stored when the engine fails or is invalid."""
        return Prediction(
            category=Category.OTHER,
            priority=Priority.LOW,
            category_confidence=0.0,
            priority_confidence=0.0,
            signals={"model_failure": True},
            reasons=list(reasons),
            engine=engine,
        )

    @staticmethod
    def _failure_result(ticket_id: str, reasons: list[str], latency_ms: float, engine: str) -> TriageResult:
        """A failed decision — never loses the ticket, never auto-accepts it."""
        return TriageResult(
            id=ticket_id or "UNKNOWN",
            category=None,
            priority=None,
            needs_review=True,
            status=Status.FAILED,
            category_confidence=0.0,
            priority_confidence=0.0,
            reasons=list(reasons),
            signals={"routing_failed": True},
            engine=engine,
            latency_ms=latency_ms,
        )

    def process_batch(self, tickets: list[Ticket]) -> dict[str, Any]:
        """Process a list of tickets idempotently and return batch statistics.

        Re-processing an already-seen id is counted as a duplicate and does not
        overwrite its original prediction or status.
        """
        started_at = _now()
        wall_start = time.perf_counter()
        submitted = len(tickets) if isinstance(tickets, (list, tuple)) else 0
        new_count = 0
        duplicate_count = 0

        for index, item in enumerate(tickets or []):
            ticket = self._coerce_ticket(item, index)
            ticket_id = getattr(ticket, "id", "") or f"INVALID-{index}"

            if not self.db.insert_ticket(ticket, id_override=ticket_id):
                duplicate_count += 1
                continue

            new_count += 1
            started = time.perf_counter()
            engine_name = getattr(self.engine, "name", "unknown")
            errors = validate_ticket(ticket)

            prediction: Prediction
            result: TriageResult
            if errors:
                reasons = ["malformed ticket: " + "; ".join(errors)]
                prediction = self._sentinel_prediction(ticket_id, reasons, engine_name)
                latency = (time.perf_counter() - started) * 1000
                result = self._failure_result(ticket_id, reasons, latency, engine_name)
            else:
                try:
                    prediction = self.engine.predict(ticket)
                    model_errors = validate_prediction(prediction)
                    if model_errors:
                        raise ValueError("invalid model response: " + "; ".join(model_errors))
                except Exception as exc:  # noqa: BLE001 - engine failures must never abort a batch
                    reasons = [f"model failure: {type(exc).__name__}: {exc}"]
                    prediction = self._sentinel_prediction(ticket_id, reasons, engine_name)
                    latency = (time.perf_counter() - started) * 1000
                    result = self._failure_result(ticket_id, reasons, latency, engine_name)
                else:
                    latency = (time.perf_counter() - started) * 1000
                    result = route(ticket, prediction, latency_ms=latency, engine_name=engine_name)

            self.db.insert_prediction(ticket_id, prediction)
            self.db.upsert_result(result)

        duration_ms = (time.perf_counter() - wall_start) * 1000
        self.db.record_run(
            started_at=started_at,
            finished_at=_now(),
            submitted=submitted,
            new_tickets=new_count,
            duplicates=duplicate_count,
            duration_ms=duration_ms,
        )
        report = self._build_report()
        self.save_report()
        self.export_csvs()
        return report

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------

    def list_tickets(
        self,
        category: Category | str | None = None,
        priority: Priority | str | None = None,
        status: Status | str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """List tickets with optional filters and pagination."""
        return self.db.list_results(
            category=_enum_value(category),
            priority=_enum_value(priority),
            status=_enum_value(status),
            page=page,
            page_size=page_size,
        )

    def get_ticket(self, ticket_id: str) -> dict[str, Any] | None:
        """Return one ticket with its current decision, or None if absent."""
        return self.db.get_result(ticket_id)

    def get_original_prediction(self, ticket_id: str) -> dict[str, Any] | None:
        """Return the immutable original engine prediction for a ticket."""
        return self.db.get_original_prediction(ticket_id)

    def get_review_queue(self, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        """Return tickets that still need a person: pending review or failed."""
        return self.db.list_results(needs_review=True, page=page, page_size=page_size)

    def submit_review(
        self,
        ticket_id: str,
        category: Category,
        priority: Priority,
        reviewer: str = "human",
    ) -> dict[str, Any]:
        """Apply a human correction and transition the ticket to human_reviewed."""
        cat = category if isinstance(category, Category) else Category(str(category))
        pri = priority if isinstance(priority, Priority) else Priority(str(priority))
        if not self.db.apply_review(ticket_id, cat.value, pri.value, reviewer):
            raise KeyError(f"unknown ticket: {ticket_id}")
        self._build_report()  # keep the persisted report in sync with the transition
        result = self.get_ticket(ticket_id)
        assert result is not None
        return result

    # ------------------------------------------------------------------
    # reporting / exports
    # ------------------------------------------------------------------

    def _build_report(self) -> dict[str, Any]:
        latest = self.db.latest_run() or {}
        return build_report(
            results=self.db.all_results(),
            predictions=self.db.all_predictions(),
            reviews=self.db.all_reviews(),
            latest_run=latest,
            submitted=int(latest.get("submitted") or 0),
            duplicates=int(latest.get("duplicates") or 0),
        )

    def get_report(self) -> dict[str, Any]:
        """Build the current report. Pure read — no filesystem side effects."""
        return self._build_report()

    def save_report(self, path: str | None = None) -> str:
        """Persist the current report as JSON next to this service's database."""
        target = path or os.path.join(self.artifacts_dir, "report.json")
        return save_report(self._build_report(), target)

    def export_csvs(self, out_dir: str | None = None) -> dict[str, Any]:
        """Write results.csv, review_queue.csv and all_predictions.csv."""
        return export_csvs(
            results=self.db.all_results(),
            predictions=self.db.all_predictions(),
            out_dir=out_dir or self.artifacts_dir,
        )
