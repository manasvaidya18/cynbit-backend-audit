"""
Security and Cryptography Utilities.
Provides cryptographically secure token generation, hashing, and validation.
"""

import hashlib
import hmac
import secrets
from typing import Optional
from app.config import settings


def generate_secure_token(nbytes: int = 32) -> str:
    """
    Generate a cryptographically secure, URL-safe random string token.
    Uses Python's secrets module (backed by os.urandom).
    """
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """
    Compute SHA-256 cryptographic hash of a raw token.
    This hash is what gets stored in the database, ensuring that a database compromise
    never exposes usable verification or unsubscribe tokens.
    """
    if not token:
        raise ValueError("Token cannot be empty")
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def verify_token_hash(raw_token: str, stored_hash: Optional[str]) -> bool:
    """
    Verify whether the hash of a raw token matches the stored token hash.
    Uses hmac.compare_digest to prevent side-channel timing attacks.
    """
    if not raw_token or not stored_hash:
        return False
    computed_hash = hash_token(raw_token)
    return hmac.compare_digest(computed_hash, stored_hash)


def hash_ip(ip_address: Optional[str]) -> Optional[str]:
    """
    Hash client IP with a salt for privacy-preserving audit logging (GDPR / DPDP compliance).
    Allows fraud detection without persisting raw Personally Identifiable Information (PII).
    """
    if not ip_address:
        return None
    salt = settings.SECRET_KEY[:16]
    payload = f"{salt}:{ip_address.strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
