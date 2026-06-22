"""Global error handling for the API."""
from typing import Any, Dict
import uuid
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from logger import logger


def create_error_response(
    error_code: str,
    message: str,
    details: Any = None,
    request_id: str = None
) -> Dict:
    """Create a structured error response."""
    if request_id is None:
        request_id = str(uuid.uuid4())

    response = {
        "error": error_code,
        "message": message,
        "request_id": request_id,
    }

    if details is not None:
        response["details"] = details

    return response


def register_error_handlers(app: FastAPI) -> None:
    """Register global error handlers."""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle Pydantic validation errors."""
        request_id = str(uuid.uuid4())

        # Extract field-level error details
        errors = []
        for error in exc.errors():
            errors.append({
                "field": ".".join(str(x) for x in error["loc"][1:]),  # Skip 'body'
                "type": error["type"],
                "message": error["msg"],
            })

        logger.warning(
            "validation_error",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "errors": errors,
            }
        )

        return JSONResponse(
            status_code=422,
            content=create_error_response(
                error_code="validation_error",
                message="Input validation failed",
                details=errors,
                request_id=request_id,
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle HTTP exceptions."""
        request_id = str(uuid.uuid4())

        logger.warning(
            "http_exception",
            extra={
                "request_id": request_id,
                "status_code": exc.status_code,
                "detail": exc.detail,
                "path": request.url.path,
            }
        )

        return JSONResponse(
            status_code=exc.status_code,
            content=create_error_response(
                error_code="http_error",
                message=exc.detail,
                request_id=request_id,
            ),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle unexpected exceptions."""
        request_id = str(uuid.uuid4())

        logger.error(
            "unhandled_exception",
            extra={
                "request_id": request_id,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "path": request.url.path,
            },
            exc_info=True,
        )

        # In production, don't expose internal error details
        from config import settings
        if settings.is_production():
            message = "Internal server error"
        else:
            message = str(exc)

        return JSONResponse(
            status_code=500,
            content=create_error_response(
                error_code="internal_error",
                message=message,
                request_id=request_id,
            ),
        )


# Add type hints at the top
from typing import Any, Dict
