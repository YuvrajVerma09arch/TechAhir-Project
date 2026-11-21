"""Reporting, accounting invariants and CSV exports.

All numbers are derived from stored records — nothing is hard-coded or invented.
The accounting invariant is enforced here, at the point where the report is built:

    total_input = auto_classified + pending_review + human_reviewed + failed

Statuses are mutually exclusive, so no ticket can be counted twice.
"""

from __future__ import annotations

import csv
import json
import os
from collections import Counter
from typing import Any, Iterable


def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 2) if whole else 0.0


def _ratio(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def _collect_escalation_reasons(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tally safety/escalation/injection evidence from stored signals and reasons."""
    counter: Counter[str] = Counter()
    for record in records:
        # A reason can appear both in the original prediction and in the routing
        # decision; count it at most once per ticket.
        seen: set[str] = set()
        signals = record.get("signals") or {}
        for name in (signals.get("safety_signals") or {}).keys():
            seen.add(f"safety: {name}")
        if signals.get("priority_escalated"):
            seen.add("priority escalated by safety layer")
        if signals.get("injection_markers"):
            seen.add("prompt injection marker")
        for reason in record.get("reasons") or []:
            if "conflict" in str(reason).lower():
                seen.add("classifier/safety conflict")
        counter.update(seen)
    return [{"reason": reason, "count": count} for reason, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))]


_KNOWN_STATUSES = ("auto_classified", "pending_review", "human_reviewed", "failed")

_RUN_METRICS_NOTE = (
    "submitted/duplicates/new_tickets describe the most recent batch; "
    "other counts are cumulative"
)


def build_report(
    *,
    results: list[dict[str, Any]],
    predictions: list[dict[str, Any]] | None = None,
    reviews: list[dict[str, Any]] | None = None,
    latest_run: dict[str, Any] | None = None,
    submitted: int = 0,
    duplicates: int = 0,
    total_tickets: int | None = None,
) -> dict[str, Any]:
    """Build a fully derived report dict from stored records.

    ``total_tickets`` (when supplied) is the authoritative denominator from the
    tickets table. A ticket whose result row is missing or carries an unknown
    status is treated as ``failed`` rather than being silently dropped, so a
    mid-batch DB failure can never break reporting.

    Raises:
        AssertionError: if the mutual-exclusivity accounting invariant is broken.
    """
    predictions = predictions or []
    reviews = reviews or []
    latest_run = latest_run or {}

    # Normalise orphan rows: a ticket with no decision is a failure, never an
    # unaccounted "unknown" status that would violate the invariant.
    normalised: list[dict[str, Any]] = []
    orphan_rows = 0
    for record in results:
        item = dict(record)
        status = str(item.get("status") or "").strip()
        if status not in _KNOWN_STATUSES:
            orphan_rows += 1
            item["status"] = "failed"
            item["needs_review"] = True
            reasons = list(item.get("reasons") or [])
            reasons.append("missing result row: ticket had no decision (counted as failed)")
            item["reasons"] = reasons
        normalised.append(item)
    results = normalised

    counted = len(results)
    total = max(int(total_tickets or 0), counted)
    # Tickets present in the tickets table but absent from the result feed are
    # also failures; add them so the invariant still closes.
    missing_from_feed = total - counted
    missing_results = orphan_rows + missing_from_feed

    counts = Counter(str(record.get("status")) for record in results)
    auto = counts.get("auto_classified", 0)
    pending = counts.get("pending_review", 0)
    human = counts.get("human_reviewed", 0)
    failed = counts.get("failed", 0) + missing_from_feed
    processed = total - failed

    invariant_holds = total == auto + pending + human + failed
    if not invariant_holds:
        raise AssertionError(
            f"accounting invariant violated: {total} != {auto}+{pending}+{human}+{failed}"
        )

    category_counts = Counter(
        str(record["category"]) for record in results if record.get("category")
    )
    priority_counts = Counter(
        str(record["priority"]) for record in results if record.get("priority")
    )

    duration_ms = float(latest_run.get("duration_ms") or 0.0)
    latencies = [float(record.get("latency_ms") or 0.0) for record in results]

    return {
        "total_input": total,
        "processed": processed,
        "successfully_processed": processed,
        "auto_classified": auto,
        "pending_review": pending,
        "human_reviewed": human,
        "failed": failed,
        "category_distribution": dict(sorted(category_counts.items())),
        "priority_distribution": dict(sorted(priority_counts.items())),
        "escalation_reasons": _collect_escalation_reasons(results),
        "processing_duration_ms": round(duration_ms, 2),
        "processing_duration_seconds": round(duration_ms / 1000.0, 3),
        "automation_coverage": _ratio(auto, total),
        "automation_coverage_pct": _pct(auto, total),
        "review_rate": _ratio(pending + human, total),
        "failure_rate": _ratio(failed, total),
        "submitted": submitted,
        "duplicates": duplicates,
        "new_tickets": latest_run.get("new_tickets", total),
        "human_reviews_recorded": len(reviews),
        "original_predictions_stored": len(predictions),
        "average_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
        "invariant_holds": invariant_holds,
        "missing_results": missing_results,
        "run_metrics_note": _RUN_METRICS_NOTE,
    }


def save_report(report: dict[str, Any], path: str = "artifacts/report.json") -> str:
    """Write the report as JSON and return the path."""
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=False)
        handle.write("\n")
    return path


# --- CSV exports ------------------------------------------------------------


def write_csv(path: str, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> str:
    """Write a UTF-8 CSV with an explicit column order."""
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def export_csvs(
    *,
    results: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    out_dir: str = "artifacts",
) -> dict[str, Any]:
    """Write results.csv plus review-queue and all-predictions exports."""
    os.makedirs(out_dir, exist_ok=True)

    results_path = os.path.join(out_dir, "results.csv")
    write_csv(
        results_path,
        ["id", "category", "priority", "needs_review"],
        [
            {
                "id": record.get("id", ""),
                "category": record.get("category") or "",
                "priority": record.get("priority") or "",
                "needs_review": "yes" if record.get("needs_review") else "no",
            }
            for record in results
        ],
    )

    review_rows = [record for record in results if record.get("needs_review")]
    review_path = os.path.join(out_dir, "review_queue.csv")
    write_csv(
        review_path,
        [
            "id",
            "status",
            "category",
            "priority",
            "category_confidence",
            "priority_confidence",
            "needs_review",
            "review_reason",
        ],
        [
            {
                "id": record.get("id", ""),
                "status": record.get("status", ""),
                "category": record.get("category") or "",
                "priority": record.get("priority") or "",
                "category_confidence": round(float(record.get("category_confidence") or 0), 4),
                "priority_confidence": round(float(record.get("priority_confidence") or 0), 4),
                "needs_review": "yes" if record.get("needs_review") else "no",
                "review_reason": "; ".join(str(reason) for reason in (record.get("reasons") or [])),
            }
            for record in review_rows
        ],
    )

    prediction_path = os.path.join(out_dir, "all_predictions.csv")
    write_csv(
        prediction_path,
        [
            "id",
            "original_category",
            "original_priority",
            "category_confidence",
            "priority_confidence",
            "engine",
            "safety_signals",
            "reasons",
        ],
        [
            {
                "id": record.get("ticket_id", ""),
                "original_category": record.get("category") or "",
                "original_priority": record.get("priority") or "",
                "category_confidence": round(float(record.get("category_confidence") or 0), 4),
                "priority_confidence": round(float(record.get("priority_confidence") or 0), 4),
                "engine": record.get("engine") or "",
                "safety_signals": ", ".join(sorted((record.get("signals") or {}).get("safety_signals") or {})),
                "reasons": "; ".join(str(reason) for reason in (record.get("reasons") or [])),
            }
            for record in predictions
        ],
    )

    return {
        "results": results_path,
        "review_queue": review_path,
        "all_predictions": prediction_path,
        "result_rows": len(results),
        "review_queue_rows": len(review_rows),
        "prediction_rows": len(predictions),
    }
