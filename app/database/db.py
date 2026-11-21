"""SQLite storage with a permanent audit trail.

Design notes
------------
* ``tickets``       — one row per unique ticket id (idempotent ingestion).
* ``predictions``   — the ORIGINAL engine output, written once and never overwritten.
* ``results``       — current routing state (may be updated by a human review).
* ``reviews``       — append-only log of human corrections.
* ``runs``          — batch run statistics used by the report.

A fresh connection is opened per operation, which keeps the layer safe when the
FastAPI layer calls the service from multiple worker threads.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.triage.types import Prediction, TriageResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _dumps(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


class Database:
    """Thin, dependency-free SQLite wrapper used by :class:`TriageService`."""

    def __init__(self, db_path: str = "artifacts/triage.db") -> None:
        self.db_path = os.path.abspath(db_path)
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._init_schema()

    # --- connection / schema ------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tickets (
                    id          TEXT PRIMARY KEY,
                    received_at TEXT,
                    customer    TEXT,
                    subject     TEXT,
                    body        TEXT,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS predictions (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id           TEXT NOT NULL UNIQUE,
                    category            TEXT,
                    priority            TEXT,
                    category_confidence REAL NOT NULL DEFAULT 0,
                    priority_confidence REAL NOT NULL DEFAULT 0,
                    signals_json        TEXT NOT NULL DEFAULT '{}',
                    reasons_json        TEXT NOT NULL DEFAULT '[]',
                    engine              TEXT,
                    created_at          TEXT NOT NULL,
                    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
                );

                CREATE TABLE IF NOT EXISTS results (
                    ticket_id           TEXT PRIMARY KEY,
                    category            TEXT,
                    priority            TEXT,
                    needs_review        INTEGER NOT NULL,
                    status              TEXT NOT NULL,
                    category_confidence REAL NOT NULL DEFAULT 0,
                    priority_confidence REAL NOT NULL DEFAULT 0,
                    reasons_json        TEXT NOT NULL DEFAULT '[]',
                    signals_json        TEXT NOT NULL DEFAULT '{}',
                    engine              TEXT,
                    latency_ms          REAL NOT NULL DEFAULT 0,
                    updated_at          TEXT NOT NULL,
                    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
                );

                CREATE TABLE IF NOT EXISTS reviews (
                    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id          TEXT NOT NULL,
                    original_category  TEXT,
                    original_priority  TEXT,
                    corrected_category TEXT NOT NULL,
                    corrected_priority TEXT NOT NULL,
                    reviewer           TEXT NOT NULL,
                    note               TEXT,
                    reviewed_at        TEXT NOT NULL,
                    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
                );

                CREATE TABLE IF NOT EXISTS runs (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at    TEXT NOT NULL,
                    finished_at   TEXT NOT NULL,
                    submitted     INTEGER NOT NULL,
                    new_tickets   INTEGER NOT NULL,
                    duplicates    INTEGER NOT NULL,
                    duration_ms   REAL NOT NULL
                );
                """
            )

    def close(self) -> None:
        """No persistent connection is held; provided for API symmetry."""
        return None

    # --- writes -------------------------------------------------------------

    def insert_ticket(self, ticket: Any, id_override: str | None = None) -> bool:
        """Insert a ticket if new. Returns True only for a newly inserted row.

        ``id_override`` lets the service persist malformed tickets under a
        synthetic id while still validating the original (missing) id.
        """
        stamp = _now()
        stored_id = id_override if id_override is not None else str(getattr(ticket, "id", "") or "")
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO tickets
                   (id, received_at, customer, subject, body, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    stored_id,
                    str(getattr(ticket, "received_at", "") or ""),
                    str(getattr(ticket, "customer", "") or ""),
                    str(getattr(ticket, "subject", "") or ""),
                    str(getattr(ticket, "body", "") or ""),
                    stamp,
                    stamp,
                ),
            )
            return cursor.rowcount > 0

    def insert_prediction(self, ticket_id: str, prediction: Prediction) -> bool:
        """Store the ORIGINAL prediction once; never overwrite it."""
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO predictions
                   (ticket_id, category, priority, category_confidence, priority_confidence,
                    signals_json, reasons_json, engine, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ticket_id,
                    prediction.category.value if prediction.category else None,
                    prediction.priority.value if prediction.priority else None,
                    float(prediction.category_confidence),
                    float(prediction.priority_confidence),
                    _dumps(prediction.signals),
                    _dumps(prediction.reasons),
                    getattr(prediction, "engine", "rules"),
                    _now(),
                ),
            )
            return cursor.rowcount > 0

    def upsert_result(self, result: TriageResult) -> None:
        """Persist the current routing/decision state for a ticket."""
        stamp = _now()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO results
                   (ticket_id, category, priority, needs_review, status,
                    category_confidence, priority_confidence, reasons_json, signals_json,
                    engine, latency_ms, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(ticket_id) DO UPDATE SET
                    category=excluded.category,
                    priority=excluded.priority,
                    needs_review=excluded.needs_review,
                    status=excluded.status,
                    category_confidence=excluded.category_confidence,
                    priority_confidence=excluded.priority_confidence,
                    reasons_json=excluded.reasons_json,
                    signals_json=excluded.signals_json,
                    engine=excluded.engine,
                    latency_ms=excluded.latency_ms,
                    updated_at=excluded.updated_at""",
                (
                    result.id,
                    result.category.value if result.category else None,
                    result.priority.value if result.priority else None,
                    int(result.needs_review),
                    result.status.value,
                    float(result.category_confidence),
                    float(result.priority_confidence),
                    _dumps(result.reasons),
                    _dumps(result.signals),
                    getattr(result, "engine", "rules"),
                    float(result.latency_ms),
                    stamp,
                ),
            )

    def apply_review(
        self,
        ticket_id: str,
        category: str,
        priority: str,
        reviewer: str,
        note: str | None = None,
    ) -> bool:
        """Append a review record and transition the ticket to human_reviewed."""
        with self._connect() as connection:
            row = connection.execute(
                """SELECT r.category, r.priority
                   FROM results r WHERE r.ticket_id = ?""",
                (ticket_id,),
            ).fetchone()
            if row is None:
                return False

            original_category = row["category"]
            original_priority = row["priority"]
            connection.execute(
                """INSERT INTO reviews
                   (ticket_id, original_category, original_priority, corrected_category,
                    corrected_priority, reviewer, note, reviewed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (ticket_id, original_category, original_priority, category, priority, reviewer, note, _now()),
            )

            current = connection.execute(
                "SELECT reasons_json FROM results WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
            reason_list = _loads(current["reasons_json"] if current else None, [])
            reason_list.append(f"human review by {reviewer}: {original_category}->{category}, {original_priority}->{priority}")

            connection.execute(
                """UPDATE results SET
                     category=?, priority=?, needs_review=0, status='human_reviewed',
                     reasons_json=?, updated_at=?
                   WHERE ticket_id=?""",
                (category, priority, _dumps(reason_list), _now(), ticket_id),
            )
            return True

    def record_run(
        self,
        *,
        started_at: str,
        finished_at: str,
        submitted: int,
        new_tickets: int,
        duplicates: int,
        duration_ms: float,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO runs (started_at, finished_at, submitted, new_tickets, duplicates, duration_ms)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (started_at, finished_at, submitted, new_tickets, duplicates, duration_ms),
            )

    # --- reads --------------------------------------------------------------

    _SELECT = """
        SELECT t.id, t.received_at, t.customer, t.subject, t.body,
               r.category, r.priority, r.needs_review, r.status,
               r.category_confidence, r.priority_confidence, r.reasons_json, r.signals_json,
               r.engine, r.latency_ms, r.updated_at,
               rv.reviewer, rv.reviewed_at, rv.corrected_category, rv.corrected_priority,
               p.category AS original_category, p.priority AS original_priority,
               p.category_confidence AS original_category_confidence,
               p.priority_confidence AS original_priority_confidence,
               p.engine AS original_engine
        FROM tickets t
        LEFT JOIN results r ON r.ticket_id = t.id
        LEFT JOIN predictions p ON p.ticket_id = t.id
        LEFT JOIN reviews rv ON rv.id = (
            SELECT id FROM reviews WHERE ticket_id = t.id ORDER BY id DESC LIMIT 1
        )
    """

    @staticmethod
    def _record(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["reasons"] = _loads(record.pop("reasons_json", None), [])
        record["signals"] = _loads(record.pop("signals_json", None), {})
        record["needs_review"] = bool(record.get("needs_review"))
        return record

    def list_results(
        self,
        *,
        category: str | None = None,
        priority: str | None = None,
        status: str | None = None,
        needs_review: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """Return a paginated, filtered view of tickets with their current results."""
        clauses: list[str] = []
        params: list[Any] = []
        if category:
            clauses.append("r.category = ?")
            params.append(category)
        if priority:
            clauses.append("r.priority = ?")
            params.append(priority)
        if status:
            clauses.append("r.status = ?")
            params.append(status)
        if needs_review is not None:
            clauses.append("r.needs_review = ?")
            params.append(int(needs_review))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""

        safe_page = max(1, int(page or 1))
        safe_size = max(1, min(500, int(page_size or 50)))
        offset = (safe_page - 1) * safe_size

        with self._connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM tickets t LEFT JOIN results r ON r.ticket_id=t.id" + where,
                params,
            ).fetchone()[0]
            rows = connection.execute(
                self._SELECT + where + " ORDER BY t.id LIMIT ? OFFSET ?",
                [*params, safe_size, offset],
            ).fetchall()

        return {
            "items": [self._record(row) for row in rows],
            "total": total,
            "page": safe_page,
            "page_size": safe_size,
            "total_pages": (total + safe_size - 1) // safe_size,
        }

    def get_result(self, ticket_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(self._SELECT + " WHERE t.id = ?", (ticket_id,)).fetchone()
        return self._record(row) if row else None

    def get_original_prediction(self, ticket_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM predictions WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
        if not row:
            return None
        record = dict(row)
        record["signals"] = _loads(record.pop("signals_json", None), {})
        record["reasons"] = _loads(record.pop("reasons_json", None), [])
        return record

    def all_results(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(self._SELECT + " ORDER BY t.id").fetchall()
        return [self._record(row) for row in rows]

    def all_predictions(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT p.*, t.customer, t.subject FROM predictions p
                   LEFT JOIN tickets t ON t.id = p.ticket_id ORDER BY p.ticket_id"""
            ).fetchall()
        records = []
        for row in rows:
            record = dict(row)
            record["signals"] = _loads(record.pop("signals_json", None), {})
            record["reasons"] = _loads(record.pop("reasons_json", None), [])
            records.append(record)
        return records

    def all_reviews(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM reviews ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def latest_run(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def status_counts(self) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute("SELECT status, COUNT(*) AS n FROM results GROUP BY status").fetchall()
        return {row["status"]: row["n"] for row in rows}
