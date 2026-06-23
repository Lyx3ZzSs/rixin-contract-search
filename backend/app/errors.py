from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, code: str, message: str, status_code: int, details: dict[str, Any] | None = None) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def error_envelope(error: ApiError) -> dict[str, Any]:
    return {"error": {"code": error.code, "message": error.message, "details": error.details}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError):
        return JSONResponse(error_envelope(exc), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError):
        return JSONResponse(error_envelope(ApiError("invalid_request", "Invalid request", 422)), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            err = ApiError("not_found", "Not found", 404)
        elif exc.status_code == 405:
            err = ApiError("invalid_request", "Invalid request", 422)
        else:
            err = ApiError("invalid_request", "Invalid request", exc.status_code)
        return JSONResponse(error_envelope(err), status_code=err.status_code)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        err = ApiError("internal_error", "Internal server error", 500)
        return JSONResponse(error_envelope(err), status_code=500)

