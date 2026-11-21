"""Request/response models for ticket listing and retrieval."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class TicketIn(BaseModel):
    """A single inbound ticket (JSON batch item or one CSV row)."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., min_length=1, description="Stable ticket identifier, e.g. T-0001")
    subject: str = Field(default="", description="Ticket subject line")
    body: str = Field(default="", description="Full ticket body")
    received_at: str = Field(default="", description="Timestamp as provided in the dataset")
    customer: str = Field(default="", description="Customer name")


class BatchTicketsIn(BaseModel):
    """JSON body accepted by POST /api/triage/batch."""

    model_config = ConfigDict(extra="ignore")

    tickets: List[TicketIn] = Field(default_factory=list)


class PaginationOut(BaseModel):
    """Pagination metadata. Extra keys from the service are preserved."""

    model_config = ConfigDict(extra="allow")

    page: int = 1
    page_size: int = 50
    total: int = 0
    total_pages: int = 0


class TicketListOut(BaseModel):
    """Standard paginated list envelope: {"data": [...], "pagination": {...}}."""

    model_config = ConfigDict(extra="allow")

    data: List[Dict[str, Any]] = Field(default_factory=list)
    pagination: PaginationOut = Field(default_factory=PaginationOut)
