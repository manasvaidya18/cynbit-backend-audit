"""
Pytest Fixtures and Test Configuration.
Provides isolated in-memory test database, clean rate limiters, and mock email state.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, get_db
from app.services.email_service import email_service
from app.api.deps import (
    subscribe_rate_limiter,
    verify_rate_limiter,
    unsubscribe_rate_limiter,
)

# In-memory SQLite database isolated for tests
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db_session():
    """Create fresh tables for every test function, yielding an isolated session."""
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function", autouse=True)
def reset_state():
    """Reset rate limiters and outbox before every test execution."""
    subscribe_rate_limiter.reset()
    verify_rate_limiter.reset()
    unsubscribe_rate_limiter.reset()
    email_service.clear()
    yield
    subscribe_rate_limiter.reset()
    verify_rate_limiter.reset()
    unsubscribe_rate_limiter.reset()
    email_service.clear()


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI TestClient with overridden database session."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
