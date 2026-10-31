"""
Pydantic Schemas for Request & Response Data Validation.
Enforces email normalization, length limits, and strict typing.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.models import SubscriptionStatus
import re

# RFC 5321 specifies maximum email length of 254 characters
MAX_EMAIL_LENGTH = 254


class SubscribeRequest(BaseModel):
    """Payload for newsletter subscription."""
    email: EmailStr = Field(
        ...,
        description="Subscriber email address",
        examples=["researcher@example.com"]
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_and_validate_email(cls, v: str) -> str:
        """
        Normalize email address by trimming surrounding whitespace,
        lowercasing domain/local part, and enforcing length restrictions.
        """
        if not isinstance(v, str):
            raise ValueError("Email must be a valid string")
        
        normalized = v.strip().lower()
        
        if len(normalized) > MAX_EMAIL_LENGTH:
            raise ValueError(f"Email exceeds maximum length of {MAX_EMAIL_LENGTH} characters")
        
        # Guard against CRLF injection or control characters in emails
        if any(c in normalized for c in ["\r", "\n", "\0"]):
            raise ValueError("Email contains forbidden control characters")
            
        return normalized


class SubscribeResponse(BaseModel):
    """Standardized response for subscription requests."""
    success: bool = True
    message: str
    status: SubscriptionStatus
    # Token preview is included strictly in development/test demonstration modes
    token_preview: Optional[str] = Field(
        default=None,
        description="Verification token preview (demonstration/testing only)"
    )


class VerifyResponse(BaseModel):
    """Response returned when an email is successfully verified."""
    success: bool = True
    message: str
    email: str
    verified_at: datetime


class UnsubscribeRequest(BaseModel):
    """Payload to unsubscribe from the newsletter using a secure token."""
    token: str = Field(..., min_length=16, description="Cryptographic unsubscribe token")
    email: Optional[EmailStr] = Field(default=None, description="Optional email for validation")

    @field_validator("token")
    @classmethod
    def validate_token(cls, v: str) -> str:
        token = v.strip()
        if not re.match(r"^[A-Za-z0-9_\-]+$", token):
            raise ValueError("Token must be a valid URL-safe string")
        return token


class UnsubscribeResponse(BaseModel):
    """Response returned upon successful unsubscription."""
    success: bool = True
    message: str
    unsubscribed_at: datetime


class ErrorResponse(BaseModel):
    """Consistent error payload."""
    success: bool = False
    error_code: str
    message: str
