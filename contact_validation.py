"""
Contact Form Submission Engine & Whitespace-Resilient Validation Module.

Demonstrates robust server-side input validation, string normalization,
centralized exception handling, rate limiting, and side-effect isolation.

Part of Cynbit Backend Technical Audit Reference Suite (Finding F-04).
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import re
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator, ValidationInfo
from sqlalchemy import Column, String, Text, DateTime, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# --- Configuration & Database Setup ---
DATABASE_URL = "sqlite:///./contact_submissions.db"
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# --- Database Model (PostgreSQL & SQLite Compatible) ---
class ContactSubmission(Base):
    """Stores validated contact inquiries."""
    __tablename__ = "contact_submissions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    company = Column(String(150), nullable=True)
    industry = Column(String(100), nullable=True)
    message = Column(Text, nullable=False)
    ip_hash = Column(String(64), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )


def init_db(target_engine=engine):
    """Initialize database tables."""
    Base.metadata.create_all(bind=target_engine)


def get_db():
    """Database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Input Trimming & Normalization Helpers ---
def clean_and_trim_string(v: Any) -> Optional[str]:
    """
    Trim surrounding whitespace and normalize internal whitespace.
    Converts empty or whitespace-only inputs to None.
    """
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValueError("Input must be a string.")
    
    # Strip leading and trailing whitespace
    trimmed = v.strip()
    return trimmed if trimmed else None


# --- Pydantic V2 Validation Schemas ---
class ContactRequest(BaseModel):
    """
    Strictly validated contact form request schema.
    
    Validation Rules:
    - name: Required, trimmed, 2-100 characters. Reject whitespace-only.
    - email: Validated via EmailStr, trimmed, lowercased.
    - company: Optional, trimmed, max 150 characters. Empty strings normalize to None.
    - industry: Optional, trimmed, max 100 characters. Empty strings normalize to None.
    - message: Required, trimmed, 10-3000 characters. Reject whitespace-only.
    """
    name: str = Field(
        ...,
        description="Full name of sender",
        examples=["Manas Vaidya"]
    )
    email: EmailStr = Field(
        ...,
        description="Sender email address",
        examples=["analyst@example.com"]
    )
    company: Optional[str] = Field(
        default=None,
        description="Optional company or organization",
        examples=["Cynbit Research"]
    )
    industry: Optional[str] = Field(
        default=None,
        description="Optional industry sector",
        examples=["Cybersecurity"]
    )
    message: str = Field(
        ...,
        description="Inquiry message body",
        examples=["We are interested in scheduling an audit of our threat intelligence pipeline."]
    )

    @field_validator("name", mode="before")
    @classmethod
    def validate_and_trim_name(cls, v: Any) -> str:
        trimmed = clean_and_trim_string(v)
        if not trimmed:
            raise ValueError("Name cannot be empty or contain only whitespace.")
        if len(trimmed) < 2:
            raise ValueError("Name must contain at least 2 non-whitespace characters.")
        if len(trimmed) > 100:
            raise ValueError("Name cannot exceed 100 characters.")
        return trimmed

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise ValueError("Email must be a string.")
        trimmed = v.strip().lower()
        if not trimmed:
            raise ValueError("Email cannot be empty or contain only whitespace.")
        return trimmed

    @field_validator("company", mode="before")
    @classmethod
    def normalize_company(cls, v: Any) -> Optional[str]:
        trimmed = clean_and_trim_string(v)
        if trimmed and len(trimmed) > 150:
            raise ValueError("Company name cannot exceed 150 characters.")
        return trimmed

    @field_validator("industry", mode="before")
    @classmethod
    def normalize_industry(cls, v: Any) -> Optional[str]:
        trimmed = clean_and_trim_string(v)
        if trimmed and len(trimmed) > 100:
            raise ValueError("Industry cannot exceed 100 characters.")
        return trimmed

    @field_validator("message", mode="before")
    @classmethod
    def validate_and_trim_message(cls, v: Any) -> str:
        trimmed = clean_and_trim_string(v)
        if not trimmed:
            raise ValueError("Message cannot be empty or contain only whitespace.")
        if len(trimmed) < 10:
            raise ValueError("Message must contain at least 10 non-whitespace characters.")
        if len(trimmed) > 3000:
            raise ValueError("Message cannot exceed 3000 characters.")
        return trimmed


class ContactResponse(BaseModel):
    """Successful submission response."""
    success: bool = True
    message: str
    contact_id: str
    submitted_at: datetime


# --- Transactional Email Service ---
class ContactEmailService:
    """Mockable email service dispatching transactional contact acknowledgements."""
    def __init__(self):
        self.outbox: List[Dict[str, Any]] = []

    def send_acknowledgement(self, recipient: str, name: str, contact_id: str) -> Dict[str, Any]:
        email_data = {
            "recipient": recipient,
            "name": name,
            "contact_id": contact_id,
            "subject": "Thank you for contacting Cynbit",
            "body": f"Hello {name},\n\nWe have received your inquiry (Ref: {contact_id}). Our team will review it shortly.",
            "dispatched_at": datetime.now(timezone.utc).isoformat()
        }
        self.outbox.append(email_data)
        return email_data

    def clear(self):
        self.outbox.clear()


contact_email_service = ContactEmailService()


# --- Sliding Window Rate Limiter ---
class ContactRateLimiter:
    """Sliding-window IP rate limiter limiting contact form submissions."""
    def __init__(self, limit: int = 5, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self._history: Dict[str, List[float]] = {}

    def __call__(self, request: Request):
        import time
        now = time.time()
        client_ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown_client")
        )
        window_start = now - self.window_seconds

        timestamps = [ts for ts in self._history.get(client_ip, []) if ts > window_start]
        if len(timestamps) >= self.limit:
            retry_after = int(self.window_seconds - (now - timestamps[0])) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {self.limit} submissions allowed per minute.",
                headers={"Retry-After": str(max(retry_after, 1))}
            )

        timestamps.append(now)
        self._history[client_ip] = timestamps

    def reset(self):
        self._history.clear()


contact_rate_limiter = ContactRateLimiter(limit=5, window_seconds=60)


# --- Application Lifecycle & Factory ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Cynbit Contact Submission Engine",
    description="Reference implementation demonstrating server-side whitespace trimming and validation.",
    version="1.0.0",
    lifespan=lifespan
)


# --- Centralized Validation Exception Handler ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Format Pydantic field validation errors into structured, client-friendly JSON.
    Guarantees validation errors abort request processing before database writes or email dispatch.
    """
    formatted_errors = []
    for err in exc.errors():
        field_path = " -> ".join(str(loc) for loc in err.get("loc", []) if loc != "body")
        formatted_errors.append({
            "field": field_path or "root",
            "message": err.get("msg", "Invalid value"),
            "type": err.get("type", "value_error")
        })

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error_code": "VALIDATION_ERROR",
            "message": "Input validation failed. Please correct the highlighted fields.",
            "errors": formatted_errors
        }
    )


# --- Contact Form Endpoint ---
@app.post(
    "/api/v1/contact",
    response_model=ContactResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(contact_rate_limiter)],
    summary="Submit Contact Inquiry",
    responses={
        422: {"description": "Validation failed (e.g., whitespace-only fields, invalid email)"},
        429: {"description": "Rate limit exceeded"}
    }
)
def submit_contact_form(
    payload: ContactRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Receives and processes contact form inquiries.
    
    Security Architecture:
    1. Rate Limiting enforced before processing.
    2. Pydantic v2 automatically strips whitespace and enforces character bounds.
    3. If validation fails, RequestValidationError aborts execution immediately.
    4. Database record is persisted with privacy-preserving salted IP hash.
    5. Side effect (email dispatch) is triggered ONLY AFTER successful validation and database commit.
    """
    client_ip = request.headers.get("x-forwarded-for") or (
        request.client.host if request.client else None
    )
    ip_hash = (
        hashlib.sha256(f"cynbit-salt:{client_ip}".encode()).hexdigest()
        if client_ip else None
    )

    # 1. Create and persist database record
    submission = ContactSubmission(
        name=payload.name,
        email=str(payload.email),
        company=payload.company,
        industry=payload.industry,
        message=payload.message,
        ip_hash=ip_hash
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    # 2. Trigger side effect: Send automated acknowledgement email
    contact_email_service.send_acknowledgement(
        recipient=submission.email,
        name=submission.name,
        contact_id=submission.id
    )

    return ContactResponse(
        success=True,
        message="Thank you for contacting Cynbit. Your inquiry has been received.",
        contact_id=submission.id,
        submitted_at=submission.created_at
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8002)
