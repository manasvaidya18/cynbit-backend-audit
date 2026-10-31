"""
FastAPI Dependencies: Database sessions and endpoint rate limiters.
"""

from fastapi import Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.config import settings
from app.middleware.rate_limiter import SlidingWindowRateLimiter

# Endpoint-specific rate limiter dependencies
subscribe_rate_limiter = SlidingWindowRateLimiter(
    times=settings.RATE_LIMIT_SUBSCRIBE_MAX,
    seconds=settings.RATE_LIMIT_SUBSCRIBE_WINDOW,
    name="subscribe"
)

verify_rate_limiter = SlidingWindowRateLimiter(
    times=settings.RATE_LIMIT_VERIFY_MAX,
    seconds=settings.RATE_LIMIT_VERIFY_WINDOW,
    name="verify"
)

unsubscribe_rate_limiter = SlidingWindowRateLimiter(
    times=settings.RATE_LIMIT_UNSUBSCRIBE_MAX,
    seconds=settings.RATE_LIMIT_UNSUBSCRIBE_WINDOW,
    name="unsubscribe"
)
