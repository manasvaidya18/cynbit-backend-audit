"""
Application Configuration Settings.
Provides central configuration with environment variable overrides.
"""

import os


class Settings:
    """Application runtime settings."""
    PROJECT_NAME: str = "Cynbit Secure Newsletter Reference Implementation"
    PROJECT_VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./newsletter.db")

    # Security & Tokens
    TOKEN_EXPIRATION_HOURS: int = int(os.getenv("TOKEN_EXPIRATION_HOURS", "24"))
    SECRET_KEY: str = os.getenv("SECRET_KEY", "cynbit-audit-reference-secret-key-32-chars-min")

    # Application Base URL (for verification & unsubscribe links)
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")

    # Rate Limiting Settings (Requests per Window in seconds)
    RATE_LIMIT_SUBSCRIBE_MAX: int = int(os.getenv("RATE_LIMIT_SUBSCRIBE_MAX", "5"))
    RATE_LIMIT_SUBSCRIBE_WINDOW: int = int(os.getenv("RATE_LIMIT_SUBSCRIBE_WINDOW", "60"))

    RATE_LIMIT_VERIFY_MAX: int = int(os.getenv("RATE_LIMIT_VERIFY_MAX", "10"))
    RATE_LIMIT_VERIFY_WINDOW: int = int(os.getenv("RATE_LIMIT_VERIFY_WINDOW", "60"))

    RATE_LIMIT_UNSUBSCRIBE_MAX: int = int(os.getenv("RATE_LIMIT_UNSUBSCRIBE_MAX", "5"))
    RATE_LIMIT_UNSUBSCRIBE_WINDOW: int = int(os.getenv("RATE_LIMIT_UNSUBSCRIBE_WINDOW", "60"))


settings = Settings()
