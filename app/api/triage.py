"""Batch triage endpoints: POST /api/triage/batch and GET /api/triage/seed."""

from __future__ import annotations

import csv
import io
from typing import List

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from app.api import ApiError, get_service
from app.config import get_settings, resolve_project_path
from app.schemas import BatchResultOut, BatchTicketsIn, NewTicketIn, TicketDecisionOut, TicketIn
from app.triage.types import Ticket

router = APIRouter(prefix="/api/triage", tags=["triage"])

_BATCH_REQUEST_BODY = {
    "required": True,
    "content": {
        "application/json": {"schema": BatchTicketsIn.model_json_schema()},
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "properties": {"file": {"type": "string", "format": "binary"}},
                "required": ["file"],
            }
        },
    },
}


def _validation_details(exc: ValidationError) -> list[dict]:
    details = []
    for err in exc.errors():
        details.append(
            {
                "loc": [str(part) for part in err.get("loc", ())],
                "msg": str(err.get("msg", "")),
                "type": str(err.get("type", "")),
            }
        )
    return details


def _rows_to_tickets(rows: list[dict]) -> List[Ticket]:
    """Validate raw mapping rows and turn them into shared Ticket objects."""
    try:
        validated = [TicketIn.model_validate(row) for row in rows]
    except ValidationError as exc:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "One or more tickets are invalid.",
            _validation_details(exc),
        ) from None
    return [
        Ticket(
            id=t.id,
            received_at=t.received_at,
            customer=t.customer,
            subject=t.subject,
            body=t.body,
        )
        for t in validated
    ]


async def _parse_csv_upload(request: Request) -> List[Ticket]:
    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        raise ApiError(
            400,
            "BAD_REQUEST",
            "multipart/form-data requests must include a 'file' field.",
        )
    raw = await upload.read()
    if isinstance(raw, str):
        text = raw
    else:
        text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = [dict(row) for row in reader]
    return _rows_to_tickets(rows)


async def _parse_json_body(request: Request) -> List[Ticket]:
    try:
        payload = await request.json()
    except Exception:
        raise ApiError(400, "BAD_REQUEST", "Request body must be valid JSON.") from None
    try:
        body = BatchTicketsIn.model_validate(payload)
    except ValidationError as exc:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Request body is invalid.",
            _validation_details(exc),
        ) from None
    return _rows_to_tickets([t.model_dump() for t in body.tickets])


async def _parse_tickets(request: Request) -> List[Ticket]:
    content_type = request.headers.get("content-type", "").lower()
    if "multipart/form-data" in content_type:
        tickets = await _parse_csv_upload(request)
    else:
        tickets = await _parse_json_body(request)
    if not tickets:
        raise ApiError(400, "EMPTY_BATCH", "No tickets were supplied.", None)
    return tickets


@router.post("/batch", response_model=BatchResultOut, openapi_extra={"requestBody": _BATCH_REQUEST_BODY})
async def batch_triage(request: Request, service=Depends(get_service)):
    """Process a batch supplied as JSON ``{"tickets": [...]}`` or a CSV upload."""
    tickets = await _parse_tickets(request)
    return service.process_batch(tickets)


@router.post("/ticket", response_model=TicketDecisionOut)
async def create_triage_ticket(payload: NewTicketIn, service=Depends(get_service)):
    """Create ONE ticket and return its full triage decision.

    Uses the same pipeline and safety rules as batch processing. The id is
    generated when omitted. New tickets are additive to the benchmark dataset.
    """
    ticket = Ticket(
        id=(payload.id or "").strip(),
        received_at=payload.received_at or "",
        customer=payload.customer or "",
        subject=payload.subject or "",
        body=payload.body or "",
    )
    return service.triage_one(ticket)


@router.get("/seed", response_model=BatchResultOut)
@router.post("/seed", response_model=BatchResultOut)
async def seed_triage(service=Depends(get_service)):
    """Convenience endpoint: triage all 300 tickets in ``data/tickets.csv``.

    Available as both GET and POST so dashboard clients using either verb work.
    Idempotent — reprocessing known ids is handled by the service layer.
    """
    path = resolve_project_path(get_settings().data_path)
    if not path.is_file():
        raise ApiError(404, "DATA_NOT_FOUND", "The configured dataset file was not found.")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = [dict(row) for row in csv.DictReader(handle)]
    except OSError:
        raise ApiError(500, "DATA_READ_ERROR", "The dataset file could not be read.") from None
    tickets = _rows_to_tickets(rows)
    if not tickets:
        raise ApiError(400, "EMPTY_BATCH", "The dataset contains no tickets.", None)
    return service.process_batch(tickets)
