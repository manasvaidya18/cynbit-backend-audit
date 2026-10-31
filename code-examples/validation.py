"""
Reusable Input Validation and Email Normalization Module.

Addresses audit finding:
- Absence of input normalization leading to duplicate records, spoofing,
  or header/CRLF injection attacks in email delivery workflows.
"""

import re
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, ValidationInfo

MAX_EMAIL_LENGTH = 254
DISALLOWED_CONTROL_CHARS = re.compile(r"[\r\n\t\x00-\x1f\x7f-\x9f]")


def normalize_email_address(email: str) -> str:
    """
    Perform RFC-compliant canonical normalization on an email address.
    
    Operations:
    1. Trims leading and trailing whitespace.
    2. Enforces maximum length of 254 characters (RFC 5321).
    3. Strips forbidden control and CRLF characters to prevent SMTP header injection.
    4. Lowercases the domain part (and optionally entire address for safe deduplication).
    """
    if not email or not isinstance(email, str):
        raise ValueError("Email must be a non-empty string.")

    cleaned = email.strip()

    if len(cleaned) > MAX_EMAIL_LENGTH:
        raise ValueError(f"Email length exceeds RFC 5321 maximum limit ({MAX_EMAIL_LENGTH} characters).")

    if DISALLOWED_CONTROL_CHARS.search(cleaned):
        raise ValueError("Email contains illegal control characters or line breaks (injection attempt detected).")

    if "@" not in cleaned:
        raise ValueError("Email must contain an '@' separator.")

    local_part, domain_part = cleaned.rsplit("@", 1)

    if not local_part or not domain_part:
        raise ValueError("Invalid email format: local-part and domain must be non-empty.")

    # Canonicalize domain and local part to lowercase for consistent database unique constraints
    return f"{local_part.lower()}@{domain_part.lower()}"


class NormalizedSubscriptionSchema(BaseModel):
    """
    Pydantic V2 Model enforcing strict email normalization and domain syntax validation.
    """
    email: EmailStr = Field(
        ...,
        description="Canonical subscriber email address",
        examples=["analyst@cynbit.in"]
    )

    @field_validator("email", mode="before")
    @classmethod
    def sanitize_and_normalize(cls, value: str, info: ValidationInfo) -> str:
        return normalize_email_address(value)


if __name__ == "__main__":
    # Demonstration of normalization & rejection
    test_cases = [
        "  User.Test@EXAMPLE.com  ",
        "valid.analyst@cynbit.in",
        "attacker@evil.com\r\nBcc:victim@cynbit.in",
    ]

    for test in test_cases:
        try:
            model = NormalizedSubscriptionSchema(email=test)
            print(f"[VALID] '{test}' -> '{model.email}'")
        except Exception as e:
            print(f"[REJECTED] '{test}' -> Error: {e}")
