"""
Standardized Domain Exception Hierarchy.

Provides custom domain exceptions mapped to HTTP semantics, supporting
predictable error envelopes, correlation IDs, and clear operational codes.

Part of Cynbit Backend Technical Audit Reference Suite.
"""

from typing import Any, Dict, List, Optional
from fastapi import status


class AppException(Exception):
    """
    Base domain exception for all expected application errors.
    All custom domain exceptions should inherit from this class.
    """
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_SERVER_ERROR"

    def __init__(
        self,
        message: str,
        details: Optional[List[Dict[str, Any]]] = None,
        headers: Optional[Dict[str, str]] = None
    ):
        super().__init__(message)
        self.message = message
        self.details = details or []
        self.headers = headers or {}


class ResourceNotFoundException(AppException):
    """Raised when a requested resource is absent."""
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "RESOURCE_NOT_FOUND"


class DuplicateResourceException(AppException):
    """Raised when a unique constraint or conflict occurs."""
    status_code = status.HTTP_409_CONFLICT
    error_code = "DUPLICATE_RESOURCE"


class ValidationException(AppException):
    """Raised when business validation rules fail."""
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "VALIDATION_ERROR"


class AuthenticationException(AppException):
    """Raised when authentication credentials are missing or invalid."""
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "AUTHENTICATION_REQUIRED"

    def __init__(self, message: str = "Authentication required."):
        super().__init__(
            message=message,
            headers={"WWW-Authenticate": "Bearer"}
        )


class AuthorizationException(AppException):
    """Raised when caller lacks required privileges."""
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "PERMISSION_DENIED"


class RateLimitExceededException(AppException):
    """Raised when request volume exceeds defined quota."""
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "RATE_LIMIT_EXCEEDED"

    def __init__(self, message: str = "Too many requests. Please try again later.", retry_after: int = 60):
        super().__init__(
            message=message,
            details=[{"retry_after_seconds": retry_after}],
            headers={"Retry-After": str(retry_after)}
        )
        self.retry_after = retry_after


class ServiceUnavailableException(AppException):
    """Raised when upstream dependencies or databases are unreachable."""
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "SERVICE_UNAVAILABLE"


# Backwards-compatibility aliases for earlier demonstration scripts
DomainException = AppException
InvalidEmailException = ValidationException
DuplicateSubscriptionException = DuplicateResourceException
InvalidTokenException = ValidationException
TokenExpiredException = ValidationException
RateLimitException = RateLimitExceededException
