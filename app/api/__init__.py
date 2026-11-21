"""Shared API infrastructure: error envelope, handlers, and dependencies."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings


class ApiError(Exception):
    """Domain-level API error rendered through the standard error envelope."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
) -> JSONResponse:
    """Build the one consistent error shape used by every endpoint."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details}},
    )


def _safe(value: Any) -> Any:
    """Coerce arbitrary validation input into something JSON-serialisable."""
    try:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, (list, tuple)):
            return [_safe(v) for v in value]
        if isinstance(value, dict):
            return {str(k): _safe(v) for k, v in value.items()}
        return str(value)
    except Exception:  # pragma: no cover - defensive only
        return "<unserialisable>"


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, exc.details)


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = []
    for err in exc.errors():
        item = {
            "loc": [_safe(part) for part in err.get("loc", ())],
            "msg": str(err.get("msg", "")),
            "type": str(err.get("type", "")),
        }
        if "input" in err:
            item["input"] = _safe(err["input"])
        details.append(item)
    return error_response(422, "VALIDATION_ERROR", "Request validation failed", details)


_HTTP_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
}


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    status = int(exc.status_code)
    code = _HTTP_CODES.get(status, "HTTP_ERROR")
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        code = str(detail.get("code", code))
        message = str(detail.get("message", "Request failed"))
        extra = detail.get("details")
    else:
        try:
            message = str(detail) if detail else HTTPStatus(status).phrase
        except ValueError:
            message = "Request failed"
        extra = None
    return error_response(status, code, message, extra)


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler: never leak exception internals to clients."""
    return error_response(
        500,
        "INTERNAL_ERROR",
        "An unexpected error occurred. Please try again later.",
        None,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)


def normalize_list(result: Any) -> dict:
    """Adapt a service list payload to the documented {data, pagination} shape.

    The service currently returns ``{items, total, page, page_size, total_pages}``.
    Keeping the adaptation here means the public API contract stays stable even
    if the persistence layer changes its internal envelope.
    """
    if result is None:
        result = {}
    if not isinstance(result, dict):
        raise ApiError(500, "INTERNAL_ERROR", "Unexpected list result from the service.")
    payload = dict(result)
    if "data" not in payload:
        payload["data"] = result.get("items", result.get("data", [])) or []
    if "pagination" not in payload:
        payload["pagination"] = {
            "page": result.get("page", 1),
            "page_size": result.get("page_size", get_settings().default_page_size),
            "total": result.get("total", 0),
            "total_pages": result.get("total_pages", 0),
        }
    return payload


def get_service():
    """FastAPI dependency providing a TriageService bound to configured DB.

    Imported lazily so the API module graph stays importable while the service
    layer is being built in parallel. Tests override this dependency with a
    service pointed at a temporary database.
    """
    from app.services.triage_service import TriageService

    return TriageService(db_path=get_settings().db_path)
