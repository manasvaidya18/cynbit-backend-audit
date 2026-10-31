"""
Newsletter API Endpoints (v1).
Implements secure subscription, token verification, and unsubscription workflows.
"""

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import (
    get_db,
    subscribe_rate_limiter,
    verify_rate_limiter,
    unsubscribe_rate_limiter,
)
from app.schemas import (
    SubscribeRequest,
    SubscribeResponse,
    VerifyResponse,
    UnsubscribeRequest,
    UnsubscribeResponse,
    ErrorResponse,
)
from app.services.subscription_service import SubscriptionService

router = APIRouter(prefix="/newsletter", tags=["Newsletter"])


@router.post(
    "/subscribe",
    response_model=SubscribeResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(subscribe_rate_limiter)],
    summary="Subscribe to Newsletter with Double Opt-In",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        429: {"description": "Rate limit exceeded"},
    }
)
def subscribe(
    payload: SubscribeRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Initiate newsletter subscription.
    
    Security Workflow:
    1. Normalizes email (lowercase, stripped, length/RFC checks).
    2. Enforces unique constraint on database.
    3. Handles duplicate subscriptions idempotently without leaking sensitive info.
    4. Generates a cryptographically random verification token.
    5. Stores only the SHA-256 hash of the verification token with an expiration timestamp.
    6. Dispatches Double Opt-In confirmation email.
    """
    client_ip = request.headers.get("x-forwarded-for") or (
        request.client.host if request.client else None
    )
    user_agent = request.headers.get("user-agent")

    sub, raw_token, message = SubscriptionService.subscribe(
        email=str(payload.email),
        client_ip=client_ip,
        user_agent=user_agent,
        db=db
    )

    return SubscribeResponse(
        success=True,
        message=message,
        status=sub.status,
        token_preview=raw_token  # Provided for demonstration/testing
    )


@router.get(
    "/verify",
    response_model=VerifyResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_rate_limiter)],
    summary="Verify Email Subscription",
    responses={
        400: {"description": "Invalid or expired token"},
        429: {"description": "Rate limit exceeded"},
    }
)
def verify(
    token: str = Query(..., min_length=16, description="Cryptographic verification token"),
    db: Session = Depends(get_db)
):
    """
    Verify ownership of the email address using the one-time verification token.
    
    Security Workflow:
    1. Hashes incoming token with SHA-256 in constant time.
    2. Verifies token expiration timestamp.
    3. Transitions subscription from PENDING to ACTIVE.
    4. Generates and stores a distinct, hashed unsubscribe token.
    5. Invalidates the verification token to prevent replay attacks.
    6. Triggers a welcome email containing the unsubscribe link and RFC 8058 headers.
    """
    sub = SubscriptionService.verify(raw_token=token, db=db)
    return VerifyResponse(
        success=True,
        message="Email successfully verified! Welcome to the Cynbit Intelligence Network.",
        email=sub.email,
        verified_at=sub.verified_at
    )


@router.post(
    "/unsubscribe",
    response_model=UnsubscribeResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(unsubscribe_rate_limiter)],
    summary="Unsubscribe from Newsletter",
    responses={
        400: {"description": "Invalid unsubscribe token"},
        429: {"description": "Rate limit exceeded"},
    }
)
def unsubscribe(
    payload: UnsubscribeRequest,
    db: Session = Depends(get_db)
):
    """
    Unsubscribe from the newsletter using the subscriber's unique token.
    
    Security Workflow:
    1. Validates token format and computes SHA-256 hash.
    2. Locates matching subscriber record.
    3. Updates status to UNSUBSCRIBED and records cancellation timestamp.
    4. Rotates/clears unsubscribe token hash to prevent unauthorized reuse.
    """
    sub = SubscriptionService.unsubscribe(
        raw_token=payload.token,
        db=db,
        email_hint=str(payload.email) if payload.email else None
    )
    return UnsubscribeResponse(
        success=True,
        message="You have been successfully unsubscribed from the Cynbit Intelligence Network.",
        unsubscribed_at=sub.unsubscribed_at
    )
