"""Human review queue and review submission endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api import ApiError, get_service
from app.config import get_settings
from app.schemas import ReviewIn, ReviewOut, TicketListOut

router = APIRouter(prefix="/api", tags=["reviews"])
_settings = get_settings()


@router.get("/review-queue", response_model=TicketListOut)
def get_review_queue(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(
        default=_settings.default_page_size,
        ge=1,
        le=_settings.max_page_size,
    ),
    service=Depends(get_service),
):
    """List tickets awaiting human review, paginated."""
    return service.get_review_queue(page=page, page_size=page_size)


@router.post("/review/{ticket_id}", response_model=ReviewOut)
def submit_review(
    ticket_id: str,
    payload: ReviewIn,
    service=Depends(get_service),
):
    """Record a human correction. Original predictions are never overwritten."""
    try:
        result = service.submit_review(
            ticket_id,
            payload.category,
            payload.priority,
            payload.reviewer,
        )
    except KeyError:
        raise ApiError(404, "NOT_FOUND", f"Ticket '{ticket_id}' was not found.") from None
    if result is None:
        raise ApiError(404, "NOT_FOUND", f"Ticket '{ticket_id}' was not found.")
    return result
