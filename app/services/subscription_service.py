"""
Subscription Business Logic Service.
Coordinates atomic database operations, cryptographic token lifecycle,
and transactional email dispatch.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.config import settings
from app.models import Subscription, SubscriptionStatus
from app.security import generate_secure_token, hash_token, hash_ip
from app.services.email_service import email_service


class SubscriptionService:
    """Manages secure subscription lifecycle, token validation, and state transitions."""

    @staticmethod
    def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
        """Ensure datetime object is timezone-aware in UTC for safe comparisons."""
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @classmethod
    def subscribe(
        cls,
        email: str,
        client_ip: Optional[str],
        user_agent: Optional[str],
        db: Session
    ) -> Tuple[Subscription, Optional[str], str]:
        """
        Initiate or update a subscription with Double Opt-In.
        Returns: (subscription, raw_token_preview_if_sent, message)
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=settings.TOKEN_EXPIRATION_HOURS)

        # 1. Check for existing subscription
        existing = db.query(Subscription).filter(Subscription.email == email).first()

        if existing:
            # Case A: Already active subscriber (Duplicate Handling)
            if existing.status == SubscriptionStatus.ACTIVE:
                return existing, None, "You're already in our intelligence network!"

            # Case B: Pending verification (Resend verification token)
            elif existing.status == SubscriptionStatus.PENDING:
                raw_token = generate_secure_token(32)
                existing.verification_token_hash = hash_token(raw_token)
                existing.verification_token_expires_at = expires_at
                existing.consent_ip_hash = hash_ip(client_ip)
                existing.consent_user_agent = user_agent[:255] if user_agent else None
                db.commit()
                db.refresh(existing)

                # Send fresh verification email
                email_service.send_verification_email(recipient=email, raw_token=raw_token)
                return existing, raw_token, "A fresh verification link has been sent to your email."

            # Case C: Previously unsubscribed (Re-subscription workflow)
            elif existing.status == SubscriptionStatus.UNSUBSCRIBED:
                raw_token = generate_secure_token(32)
                existing.status = SubscriptionStatus.PENDING
                existing.verification_token_hash = hash_token(raw_token)
                existing.verification_token_expires_at = expires_at
                existing.unsubscribed_at = None
                existing.consent_ip_hash = hash_ip(client_ip)
                existing.consent_user_agent = user_agent[:255] if user_agent else None
                db.commit()
                db.refresh(existing)

                email_service.send_verification_email(recipient=email, raw_token=raw_token)
                return existing, raw_token, "Welcome back! Please verify your email to reactivate your subscription."

        # 2. Brand new subscriber
        raw_token = generate_secure_token(32)
        token_hash = hash_token(raw_token)
        new_sub = Subscription(
            email=email,
            status=SubscriptionStatus.PENDING,
            verification_token_hash=token_hash,
            verification_token_expires_at=expires_at,
            consent_ip_hash=hash_ip(client_ip),
            consent_user_agent=user_agent[:255] if user_agent else None,
        )

        try:
            db.add(new_sub)
            db.commit()
            db.refresh(new_sub)
        except IntegrityError:
            # Handle concurrent race condition gracefully
            db.rollback()
            existing = db.query(Subscription).filter(Subscription.email == email).first()
            if existing and existing.status == SubscriptionStatus.ACTIVE:
                return existing, None, "You're already in our intelligence network!"
            return existing, None, "A verification request is already being processed for this address."

        # Send verification email for the new subscription
        email_service.send_verification_email(recipient=email, raw_token=raw_token)
        return new_sub, raw_token, "Please check your inbox to confirm your subscription."

    @classmethod
    def verify(cls, raw_token: str, db: Session) -> Subscription:
        """
        Verify a pending subscription using the cryptographically hashed token.
        Transitions state from PENDING to ACTIVE upon success.
        """
        if not raw_token or len(raw_token.strip()) < 16:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification token format."
            )

        token_hash = hash_token(raw_token.strip())
        subscription = db.query(Subscription).filter(
            Subscription.verification_token_hash == token_hash
        ).first()

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or unrecognized verification token."
            )

        now = datetime.now(timezone.utc)
        expires_at = cls._ensure_utc(subscription.verification_token_expires_at)

        # Check expiration
        if expires_at and expires_at < now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification token has expired. Please subscribe again to receive a fresh verification link."
            )

        # Idempotent response if already verified
        if subscription.status == SubscriptionStatus.ACTIVE:
            return subscription

        # Generate a unique unsubscribe token for future use
        raw_unsubscribe_token = generate_secure_token(32)
        unsubscribe_hash = hash_token(raw_unsubscribe_token)

        # State transition to ACTIVE
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.verified_at = now
        subscription.unsubscribe_token_hash = unsubscribe_hash
        
        # Single-use security: invalidate the verification token immediately
        subscription.verification_token_hash = None
        subscription.verification_token_expires_at = None

        db.commit()
        db.refresh(subscription)

        # Send welcome email containing the unsubscribe link & headers
        email_service.send_welcome_email(
            recipient=subscription.email,
            unsubscribe_token=raw_unsubscribe_token
        )

        return subscription

    @classmethod
    def unsubscribe(
        cls,
        raw_token: str,
        db: Session,
        email_hint: Optional[str] = None
    ) -> Subscription:
        """
        Unsubscribe a user using their unique unsubscribe token hash.
        Safe against enumeration and unauthorized unsubscriptions.
        """
        if not raw_token or len(raw_token.strip()) < 16:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid unsubscribe token format."
            )

        token_hash = hash_token(raw_token.strip())
        query = db.query(Subscription).filter(
            Subscription.unsubscribe_token_hash == token_hash
        )

        if email_hint:
            query = query.filter(Subscription.email == email_hint.strip().lower())

        subscription = query.first()

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or unrecognized unsubscribe token."
            )

        # Idempotent unsubscription
        if subscription.status == SubscriptionStatus.UNSUBSCRIBED:
            return subscription

        now = datetime.now(timezone.utc)
        subscription.status = SubscriptionStatus.UNSUBSCRIBED
        subscription.unsubscribed_at = now
        # Rotate token hash on unsubscribe to prevent replay
        subscription.unsubscribe_token_hash = None

        db.commit()
        db.refresh(subscription)
        return subscription
