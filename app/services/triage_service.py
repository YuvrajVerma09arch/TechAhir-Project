"""Application service: orchestrates ingestion, prediction, routing and storage.

The service is the single entry point used by the API layer. It is tolerant of
bad input, idempotent for repeated ticket ids, and preserves the original engine
prediction even after a human correction.
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.database import Database
from app.services.classifier import RulesEngine
from app.services.confidence import route, validate_prediction, validate_ticket
from app.services.llm_judge import LlmJudge
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


def _retry_db_write(operation, *, attempts: int = 3, base_delay: float = 0.01):
    """Run a DB write with bounded retries on transient SQLite locking errors.

    ``sqlite3.OperationalError`` (typically "database is locked") is the one
    failure mode where a short retry is safe and useful. Other exceptions are
    raised immediately so they can be converted into a FAILED TriageResult by
    the caller. After the last attempt the original exception is re-raised.
    """
    last_exc: sqlite3.OperationalError | None = None
    for attempt in range(max(1, attempts)):
        try:
            return operation()
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if attempt + 1 < attempts:
                time.sleep(base_delay * (attempt + 1))
    assert last_exc is not None  # loop always runs at least once
    raise last_exc


class TriageService:
    """End-to-end triage service backed by SQLite."""

    def __init__(
        self,
        db_path: str = "artifacts/triage.db",
        engine: TriageEngine | None = None,
        judge: Any | None = None,
    ) -> None:
        self.db = Database(db_path)
        # Generated artefacts live beside the database. Tests use a temp DB, so their
        # reports/CSVs stay in the temp dir and never overwrite the committed 300-ticket run.
        self.artifacts_dir = os.path.dirname(os.path.abspath(db_path)) or os.getcwd()
        # An engine may be injected (e.g. a failing engine in resilience tests).
        self.engine: TriageEngine = engine if engine is not None else RulesEngine()
        # Optional caution-only LLM judge. Inert unless explicitly enabled with a key.
        self.judge = judge if judge is not None else LlmJudge()

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
            started = time.perf_counter()
            engine_name = getattr(self.engine, "name", "unknown")

            # Ingest idempotently. A transient lock is retried; if the DB stays
            # unavailable we cannot persist anything (FK), but the batch must
            # still continue so one bad write never aborts the remaining tickets.
            try:
                inserted = _retry_db_write(
                    lambda: self.db.insert_ticket(ticket, id_override=ticket_id)
                )
            except sqlite3.Error:
                continue

            if not inserted:
                duplicate_count += 1
                continue

            new_count += 1
            prediction: Prediction | None = None
            result: TriageResult

            try:
                errors = validate_ticket(ticket)
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
                    except Exception as exc:  # noqa: BLE001 - engine failures contained
                        reasons = [f"model failure: {type(exc).__name__}: {exc}"]
                        prediction = self._sentinel_prediction(ticket_id, reasons, engine_name)
                        latency = (time.perf_counter() - started) * 1000
                        result = self._failure_result(ticket_id, reasons, latency, engine_name)
                    else:
                        latency = (time.perf_counter() - started) * 1000
                        result = route(ticket, prediction, latency_ms=latency, engine_name=engine_name)

                # Optional LLM caution judge: it may only ADD human review. It can
                # never change category/priority or turn a review into an auto-accept.
                if result.status is not Status.FAILED and getattr(self.judge, "enabled", False):
                    verdict = self.judge.judge(ticket, result)
                    if verdict.escalate:
                        result.needs_review = True
                        result.status = Status.PENDING_REVIEW
                        result.reasons.append(f"LLM judge: {verdict.reason}")
                        result.signals["llm_judge"] = {
                            "escalate": True,
                            "ok": verdict.ok,
                            "error": verdict.error,
                        }
            except Exception as exc:  # noqa: BLE001 - any post-insert failure must not orphan a ticket
                reasons = [f"processing failure: {type(exc).__name__}: {exc}"]
                if prediction is None:
                    prediction = self._sentinel_prediction(ticket_id, reasons, engine_name)
                latency = (time.perf_counter() - started) * 1000
                result = self._failure_result(ticket_id, reasons, latency, engine_name)

            # Persist the original prediction and the decision. Both writes are
            # retried on transient locks; if they still fail we fall back to a
            # FAILED result so the ticket is never silently left as an orphan.
            try:
                _retry_db_write(lambda: self.db.insert_prediction(ticket_id, prediction))
                _retry_db_write(lambda: self.db.upsert_result(result))
            except Exception as exc:  # noqa: BLE001 - degraded DB, keep the batch alive
                reasons = [f"persistence failure: {type(exc).__name__}: {exc}"]
                failed_result = self._failure_result(
                    ticket_id, reasons, (time.perf_counter() - started) * 1000, engine_name
                )
                try:
                    _retry_db_write(lambda: self.db.upsert_result(failed_result))
                except Exception:  # pragma: no cover - build_report's fallback covers this
                    pass

        duration_ms = (time.perf_counter() - wall_start) * 1000
        try:
            _retry_db_write(
                lambda: self.db.record_run(
                    started_at=started_at,
                    finished_at=_now(),
                    submitted=submitted,
                    new_tickets=new_count,
                    duplicates=duplicate_count,
                    duration_ms=duration_ms,
                )
            )
        except sqlite3.Error:
            # A failed run-log write must not abort reporting; last-run counters
            # simply reflect the most recently persisted run (see run_metrics_note).
            pass
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

    def triage_one(self, ticket: Ticket) -> dict[str, Any]:
        """Triage a single newly-created ticket, generating an id when absent.

        Reuses the exact batch pipeline (so storage, reporting and safety rules are
        identical) and returns the persisted decision. New tickets are additive to
        the benchmark run; the committed 300-ticket artifacts remain the reference.
        """
        ticket_id = (ticket.id or "").strip()
        if not ticket_id:
            next_number = self.db.ticket_count() + 1
            ticket_id = f"T-{next_number:04d}"
            while self.db.get_result(ticket_id) is not None:
                next_number += 1
                ticket_id = f"T-{next_number:04d}"
            ticket = replace(ticket, id=ticket_id)
        self.process_batch([ticket])
        result = self.get_ticket(ticket.id)
        if result is None:  # pragma: no cover - defensive; process_batch persists a result
            raise RuntimeError("ticket was triaged but no result was persisted")
        return result

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
        # Keep every on-disk deliverable in sync with the review transition:
        # report.json, results.csv and review_queue.csv must never still show a
        # reviewed ticket as pending. Both writers default to the artifacts dir
        # beside this service's DB, so tests stay isolated in their temp dir.
        self.save_report()
        self.export_csvs()
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
            total_tickets=self.db.ticket_count(),
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
