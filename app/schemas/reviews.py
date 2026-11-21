"""Request/response models for the human review workflow."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.triage.types import Category, Priority


class ReviewIn(BaseModel):
    """Corrected category/priority supplied by a human reviewer.

    ``Category``/``Priority`` are the shared enums from ``app.triage.types``;
    Pydantic therefore rejects unknown values with a 422 at the boundary.
    """

    model_config = ConfigDict(extra="ignore")

    category: Category
    priority: Priority
    reviewer: str = Field(default="human", min_length=1)


class ReviewOut(BaseModel):
    """Result of a submitted review (service-owned shape, forwarded as-is)."""

    model_config = ConfigDict(extra="allow")
