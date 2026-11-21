"""Aggregate report endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api import get_service
from app.schemas import ReportOut

router = APIRouter(prefix="/api", tags=["report"])


@router.get("/report", response_model=ReportOut)
def get_report(service=Depends(get_service)):
    """Return the full processing/accounting report as JSON."""
    return service.get_report()
