"""
SQLAlchemy ORM Models for Newsletter Subscriptions.
PostgreSQL and SQLite compatible with security-first schema design.
"""

import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    DateTime,
    Enum as SQLEnum,
    Index,
    text,
)
from app.database import Base


class SubscriptionStatus(str, enum.Enum):
    """Lifecycle states of a newsletter subscription."""
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    UNSUBSCRIBED = "UNSUBSCRIBED"


def get_utc_now():
    """Helper to return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class Subscription(Base):
    """
    Newsletter subscriber record.
    
    Security & Architecture features:
    - Unique index on normalized email for strict deduplication.
    - Token values are stored exclusively as cryptographic SHA-256 hashes.
    - Explicit token expiration timestamps enforce time-limited activation.
    - Privacy-preserving IP hash for consent verification audit trails.
    """
    __tablename__ = "newsletter_subscriptions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, index=True, nullable=False)
    status = Column(
        SQLEnum(SubscriptionStatus, name="subscription_status_enum"),
        default=SubscriptionStatus.PENDING,
        nullable=False,
        index=True
    )

    # Cryptographic hashes of tokens (raw tokens are never persisted)
    verification_token_hash = Column(String(64), index=True, nullable=True)
    verification_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    unsubscribe_token_hash = Column(String(64), index=True, nullable=True)

    # Privacy & Consent Tracking (Anonymized metadata compliant with GDPR / DPDP)
    consent_ip_hash = Column(String(64), nullable=True)
    consent_user_agent = Column(String(255), nullable=True)

    # Audit Timestamps
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    unsubscribed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_subscriptions_email_status", "email", "status"),
    )

    def __repr__(self) -> str:
        return f"<Subscription(id={self.id}, email={self.email}, status={self.status})>"
