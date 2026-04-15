from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


logger = logging.getLogger(__name__)


DEFAULT_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_SERVER_ERROR",
}


def build_error_payload(
    *, detail: str, code: str, errors: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"detail": detail, "code": code}
    if errors:
        payload["errors"] = errors
    return payload


class BridgewoodError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        detail: str,
        code: str,
        headers: Mapping[str, str] | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.code = code
        self.headers = dict(headers or {})
        self.errors = errors


def _default_code(status_code: int) -> str:
    return DEFAULT_ERROR_CODES.get(status_code, "ERROR")


def _coerce_http_exception(
    exc: HTTPException | StarletteHTTPException,
) -> tuple[str, str, list[dict[str, Any]] | None]:
    detail = exc.detail
    code = _default_code(exc.status_code)
    errors = None

    if isinstance(detail, dict):
        detail_value = detail.get("detail", "Request failed.")
        code = str(detail.get("code", code))
        raw_errors = detail.get("errors")
        errors = raw_errors if isinstance(raw_errors, list) else None
        return str(detail_value), code, errors

    if isinstance(detail, list):
        return (
            "Request validation failed.",
            "VALIDATION_ERROR",
            jsonable_encoder(detail),
        )

    if detail is None:
        return "Request failed.", code, None

    return str(detail), code, None


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BridgewoodError)
    async def handle_bridgewood_error(
        request: Request, exc: BridgewoodError
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_payload(
                detail=exc.detail, code=exc.code, errors=exc.errors
            ),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=422,
            content=build_error_payload(
                detail="Request validation failed.",
                code="VALIDATION_ERROR",
                errors=jsonable_encoder(exc.errors()),
            ),
        )

    @app.exception_handler(ValidationError)
    async def handle_validation_error(
        request: Request, exc: ValidationError
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=422,
            content=build_error_payload(
                detail="Validation failed.",
                code="VALIDATION_ERROR",
                errors=jsonable_encoder(exc.errors()),
            ),
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        del request
        detail, code, errors = _coerce_http_exception(exc)
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_payload(detail=detail, code=code, errors=errors),
            headers=exc.headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_starlette_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        del request
        detail, code, errors = _coerce_http_exception(exc)
        headers = getattr(exc, "headers", None)
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_payload(detail=detail, code=code, errors=errors),
            headers=headers,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception(
            "Unhandled application error on %s %s",
            request.method,
            request.url.path,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content=build_error_payload(
                detail="Internal server error.",
                code="INTERNAL_SERVER_ERROR",
            ),
        )
