"""FastAPI application entry point for the Support Ticket Triage API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import register_exception_handlers
from app.api.report import router as report_router
from app.api.reviews import router as reviews_router
from app.api.tickets import router as tickets_router
from app.api.triage import router as triage_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_title,
    description=settings.app_description,
    version=settings.version,
)

# The React dashboard is deployed separately (Vercel) and calls this API directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(triage_router)
app.include_router(tickets_router)
app.include_router(reviews_router)
app.include_router(report_router)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_title,
        "version": settings.version,
    }
