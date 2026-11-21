"""Ticket listing and detail endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api import ApiError, get_service
from app.config import get_settings
from app.schemas import TicketListOut
from app.triage.types import Category, Priority, Status

router = APIRouter(prefix="/api/tickets", tags=["tickets"])

_settings = get_settings()


@router.get("", response_model=TicketListOut)
def list_tickets(
    category: Optional[Category] = Query(default=None, description="Filter by category"),
    priority: Optional[Priority] = Query(default=None, description="Filter by priority"),
    status: Optional[Status] = Query(default=None, description="Filter by lifecycle status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(
        default=_settings.default_page_size,
        ge=1,
        le=_settings.max_page_size,
    ),
    service=Depends(get_service),
):
    """Return a paginated, optionally filtered list of stored tickets."""
    return service.list_tickets(
        category=category.value if category else None,
        priority=priority.value if priority else None,
        status=status.value if status else None,
        page=page,
        page_size=page_size,
    )


@router.get("/{ticket_id}")
def get_ticket(ticket_id: str, service=Depends(get_service)):
    """Return one ticket by id, or a 404 error envelope."""
    ticket = service.get_ticket(ticket_id)
    if ticket is None:
        raise ApiError(404, "NOT_FOUND", f"Ticket '{ticket_id}' was not found.")
    return ticket
