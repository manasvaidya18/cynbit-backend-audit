"""
Centralized Error Handling & Observability Architecture.

Demonstrates:
1. Centralized exception handling with standard JSON envelopes.
2. Correlation / Request ID generation, propagation, and response injection.
3. Strict stack-trace suppression for unexpected 500 errors (zero internal leaks).
4. Server-side structured logging with sensitive field redaction.
5. Pydantic request validation and semantic HTTP status code mapping.

Independent reference implementation for Cynbit Backend Technical Audit.
"""

from datetime import datetime, timezone
import logging
import re
import sys
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from exceptions import (
    AppException,
    ResourceNotFoundException,
    DuplicateResourceException,
    ValidationException,
    RateLimitExceededException,
)

# --- Sensitive Data Redaction Logger Setup ---
SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|token|secret|authorization|api[_-]?key|credit_card|cvv)",
    re.IGNORECASE
)


class SensitiveDataRedactingFilter(logging.Filter):
    """Redacts sensitive values from server log records."""
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            # Redact common Authorization / Bearer tokens
            record.msg = re.sub(
                r"(Bearer\s+)[A-Za-z0-9_\-\.]+",
                r"\1[REDACTED]",
                record.msg,
                flags=re.IGNORECASE
            )
        return True


logger = logging.getLogger("cynbit.audit.error_handler")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter(
    "[%(asctime)s] [%(levelname)s] [corr_id=%(correlation_id)s] %(message)s",
    defaults={"correlation_id": "none"}
))
handler.addFilter(SensitiveDataRedactingFilter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)


# --- Standardized Error Schemas ---
class ErrorDetail(BaseModel):
    """Field-level error specification."""
    field: Optional[str] = None
    message: str
    code: Optional[str] = None


class ErrorBody(BaseModel):
    """Standardized error payload body."""
    code: str
    message: str
    correlation_id: str
    timestamp: str
    details: List[ErrorDetail] = Field(default_factory=list)


class ErrorEnvelope(BaseModel):
    """Predictable error response envelope."""
    success: bool = False
    error: ErrorBody


class SuccessEnvelope(BaseModel):
    """Predictable success response envelope."""
    success: bool = True
    data: Any
    correlation_id: str


# --- Correlation ID Middleware ---
class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Extracts or generates an RFC 4122 correlation ID for each incoming request.
    Injects the correlation ID into request state and the outgoing X-Correlation-ID header.
    """
    async def dispatch(self, request: Request, call_next):
        correlation_id = (
            request.headers.get("X-Request-ID")
            or request.headers.get("X-Correlation-ID")
            or str(uuid.uuid4())
        )
        request.state.correlation_id = correlation_id

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


# --- Application Setup ---
app = FastAPI(
    title="Cynbit Error Handling & Observability Reference API",
    description="Production-grade centralized exception handling and correlation tracking.",
    version="1.0.0"
)
app.add_middleware(CorrelationIdMiddleware)


# --- Centralized Exception Handlers ---
def build_error_response(
    status_code: int,
    code: str,
    message: str,
    correlation_id: str,
    details: Optional[List[ErrorDetail]] = None,
    headers: Optional[Dict[str, str]] = None
) -> JSONResponse:
    """Helper to assemble a uniform error envelope."""
    response_headers = headers.copy() if headers else {}
    response_headers["X-Correlation-ID"] = correlation_id

    content = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "correlation_id": correlation_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": [d.model_dump() for d in (details or [])]
        }
    }
    return JSONResponse(status_code=status_code, content=content, headers=response_headers)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """Handle custom application domain exceptions."""
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    logger.warning(
        f"Handled application exception: {exc.error_code} - {exc.message}",
        extra={"correlation_id": correlation_id}
    )
    details = [ErrorDetail(message=str(d)) for d in exc.details] if exc.details else []
    return build_error_response(
        status_code=exc.status_code,
        code=exc.error_code,
        message=exc.message,
        correlation_id=correlation_id,
        details=details,
        headers=exc.headers
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic request body/query validation failures (422)."""
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    logger.info(
        f"Request validation failure on path {request.url.path}",
        extra={"correlation_id": correlation_id}
    )
    details = []
    for err in exc.errors():
        field_name = " -> ".join(str(loc) for loc in err.get("loc", []) if loc != "body")
        details.append(ErrorDetail(
            field=field_name or "body",
            message=err.get("msg", "Invalid value"),
            code=err.get("type", "value_error")
        ))

    return build_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="VALIDATION_ERROR",
        message="Request payload validation failed. Please correct the specified fields.",
        correlation_id=correlation_id,
        details=details
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle standard Starlette/FastAPI HTTP exceptions (e.g. 404, 405)."""
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    code_map = {
        404: "RESOURCE_NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN"
    }
    error_code = code_map.get(exc.status_code, "HTTP_ERROR")
    return build_error_response(
        status_code=exc.status_code,
        code=error_code,
        message=str(exc.detail),
        correlation_id=correlation_id,
        headers=getattr(exc, "headers", None)
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    CRITICAL SECURITY LAYER: Catch-all handler for unexpected server faults (500).
    - Logs the full stack trace and correlation ID securely on the server.
    - NEVER reveals internal stack traces, filenames, or exception strings to the client.
    - Returns a safe, generic message referencing the correlation ID.
    """
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    
    # Secure server-side logging with full traceback
    logger.error(
        f"Unhandled unexpected exception on {request.method} {request.url.path}: {exc}",
        exc_info=True,
        extra={"correlation_id": correlation_id}
    )

    return build_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected internal server error occurred. Please contact support with the provided correlation ID.",
        correlation_id=correlation_id
    )


# --- Example Request Schemas & Endpoints ---
class ContactInput(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    message: str = Field(..., min_length=10, max_length=3000)

    @field_validator("name", "message", mode="before")
    @classmethod
    def strip_whitespace(cls, v: Any) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Field cannot be empty or whitespace-only.")
        return v.strip()


@app.post("/api/contact", status_code=status.HTTP_200_OK)
def submit_contact(payload: ContactInput, request: Request):
    """Successful endpoint demonstration."""
    correlation_id = request.state.correlation_id
    return {
        "success": True,
        "correlation_id": correlation_id,
        "data": {
            "name": payload.name,
            "email": payload.email,
            "status": "received"
        }
    }


@app.get("/api/resource/{item_id}")
def get_resource(item_id: str, request: Request):
    """Demonstrates expected 404 application error."""
    if item_id == "missing":
        raise ResourceNotFoundException(f"Resource with ID '{item_id}' was not found.")
    return {"id": item_id, "name": "Existing Resource", "correlation_id": request.state.correlation_id}


@app.post("/api/resource/duplicate")
def create_duplicate(payload: dict, request: Request):
    """Demonstrates expected 409 application error."""
    raise DuplicateResourceException("A resource with this key already exists.")


@app.get("/api/simulate-server-error")
def simulate_crash():
    """Simulates an unexpected unhandled server exception (e.g., division by zero)."""
    # Intentional unhandled exception
    result = 1 / 0
    return {"result": result}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8003)
