"""Response model for the aggregate triage report."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ReportOut(BaseModel):
    """Full report produced by the service. Keys are service-owned."""

    model_config = ConfigDict(extra="allow")
