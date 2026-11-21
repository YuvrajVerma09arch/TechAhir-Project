"""Application configuration.

All settings are read from environment variables with sensible, offline-friendly
defaults. No secrets or third-party credentials are required by this project.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Repository root (this file lives at <root>/app/config.py).
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of runtime configuration."""

    app_title: str
    app_description: str
    version: str
    db_path: str
    data_path: str
    category_confidence_threshold: float
    priority_confidence_threshold: float
    default_page_size: int
    max_page_size: int


def get_settings() -> Settings:
    """Build settings from the current environment (cheap; called at startup)."""
    return Settings(
        app_title=os.getenv("APP_TITLE", "Support Ticket Triage API"),
        app_description=os.getenv(
            "APP_DESCRIPTION",
            "Offline, confidence-aware support ticket triage with human review.",
        ),
        version=os.getenv("VERSION", "1.0.0"),
        db_path=os.getenv("DB_PATH", "artifacts/triage.db"),
        data_path=os.getenv("DATA_PATH", "data/tickets.csv"),
        category_confidence_threshold=_env_float("CATEGORY_CONFIDENCE_THRESHOLD", 0.55),
        priority_confidence_threshold=_env_float("PRIORITY_CONFIDENCE_THRESHOLD", 0.55),
        default_page_size=_env_int("DEFAULT_PAGE_SIZE", 50),
        max_page_size=_env_int("MAX_PAGE_SIZE", 200),
    )


def resolve_project_path(path: str | Path) -> Path:
    """Resolve a possibly-relative configured path against the repository root."""
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


# Convenience snapshot for modules that do not need per-request freshness.
settings = get_settings()
