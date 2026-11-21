"""Request/response models for batch triage operations."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class BatchResultOut(BaseModel):
    """Statistics returned by the service after processing a batch.

    The exact keys are owned by the service layer; ``extra="allow"`` keeps the
    response contract stable while forwarding all of them unchanged.
    """

    model_config = ConfigDict(extra="allow")


class TicketDecisionOut(BaseModel):
    """The persisted decision for a single ticket.

    Extra keys are allowed so service additions remain backward compatible.
    """

    model_config = ConfigDict(extra="allow")
