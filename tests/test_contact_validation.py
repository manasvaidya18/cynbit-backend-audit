"""
Comprehensive Unit & Integration Test Suite for Contact Submission Validation.

Covers:
- Valid contact request processing
- Empty name rejection
- Whitespace-only name rejection
- Whitespace-only message rejection
- Invalid email rejection
- Missing required fields
- Minimum name length enforcement (min 2 chars)
- Minimum message length enforcement (min 10 chars)
- Maximum field length enforcement
- Optional empty/whitespace company and industry normalization to None
- Leading and trailing whitespace trimming
- Verification that invalid requests NEVER trigger email dispatch
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from contact_validation import (
    app,
    get_db,
    Base,
    ContactSubmission,
    contact_email_service,
    contact_rate_limiter,
)

# In-memory isolated database for contact validation tests
TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def contact_db():
    """Create fresh isolated tables for each test."""
    Base.metadata.create_all(bind=test_engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def contact_client(contact_db):
    """TestClient with overridden database session and reset state."""
    contact_rate_limiter.reset()
    contact_email_service.clear()

    def override_get_db():
        try:
            yield contact_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    contact_rate_limiter.reset()
    contact_email_service.clear()


def test_valid_contact_request(contact_client, contact_db):
    """Test 1: Valid contact submission succeeds, persists to DB, and sends email."""
    payload = {
        "name": "Manas Vaidya",
        "email": "manas.vaidya@example.com",
        "company": "Cynbit Technologies",
        "industry": "Cybersecurity",
        "message": "We would like to request a technical audit of our API infrastructure."
    }

    response = contact_client.post("/api/v1/contact", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert "received" in data["message"].lower()
    assert data["contact_id"] is not None

    # Verify DB persistence
    record = contact_db.query(ContactSubmission).filter_by(id=data["contact_id"]).first()
    assert record is not None
    assert record.name == "Manas Vaidya"
    assert record.email == "manas.vaidya@example.com"
    assert record.company == "Cynbit Technologies"
    assert record.industry == "Cybersecurity"

    # Verify email delivery
    assert len(contact_email_service.outbox) == 1
    dispatched = contact_email_service.outbox[0]
    assert dispatched["recipient"] == "manas.vaidya@example.com"
    assert dispatched["name"] == "Manas Vaidya"


def test_empty_name(contact_client):
    """Test 2: Empty string for name is rejected with 422."""
    payload = {
        "name": "",
        "email": "tester@example.com",
        "message": "This is a valid inquiry message."
    }
    response = contact_client.post("/api/v1/contact", json=payload)
    assert response.status_code == 422
    assert response.json()["success"] is False
    assert len(contact_email_service.outbox) == 0


def test_whitespace_only_name(contact_client):
    """Test 3: Whitespace-only name ('   ') is rejected with 422."""
    payload = {
        "name": "     \t   \n   ",
        "email": "tester@example.com",
        "message": "Valid inquiry message exceeding 10 characters."
    }
    response = contact_client.post("/api/v1/contact", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert any("Name cannot be empty or contain only whitespace" in str(err) for err in data["errors"])
    # Crucial: Email delivery must NOT have been triggered
    assert len(contact_email_service.outbox) == 0


def test_whitespace_only_message(contact_client):
    """Test 4: Whitespace-only message is rejected with 422."""
    payload = {
        "name": "Legitimate Sender",
        "email": "tester@example.com",
        "message": "                      \n\t       "
    }
    response = contact_client.post("/api/v1/contact", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert any("Message cannot be empty or contain only whitespace" in str(err) for err in data["errors"])
    assert len(contact_email_service.outbox) == 0


def test_invalid_email(contact_client):
    """Test 5: Malformed email format (e.g., abc123) is rejected with 422."""
    payload = {
        "name": "Jane Doe",
        "email": "abc123",
        "message": "This is an inquiry from an invalid address."
    }
    response = contact_client.post("/api/v1/contact", json=payload)
    assert response.status_code == 422
    assert response.json()["success"] is False
    assert len(contact_email_service.outbox) == 0


def test_missing_required_fields(contact_client):
    """Test 6: Missing required fields (name, email, message) are caught."""
    # Omitted name
    resp1 = contact_client.post("/api/v1/contact", json={
        "email": "test@example.com",
        "message": "Valid message exceeding 10 chars."
    })
    assert resp1.status_code == 422

    # Omitted message
    resp2 = contact_client.post("/api/v1/contact", json={
        "name": "Test User",
        "email": "test@example.com"
    })
    assert resp2.status_code == 422

    assert len(contact_email_service.outbox) == 0


def test_minimum_name_length(contact_client):
    """Test 7: Name with fewer than 2 non-whitespace characters is rejected."""
    # 1 char rejected
    resp_too_short = contact_client.post("/api/v1/contact", json={
        "name": "   M   ",
        "email": "tester@example.com",
        "message": "Valid message with sufficient length."
    })
    assert resp_too_short.status_code == 422
    assert any("at least 2 non-whitespace characters" in str(e) for e in resp_too_short.json()["errors"])

    # 2 chars accepted
    resp_valid = contact_client.post("/api/v1/contact", json={
        "name": "   Mo   ",
        "email": "tester@example.com",
        "message": "Valid message with sufficient length."
    })
    assert resp_valid.status_code == 201


def test_minimum_message_length(contact_client):
    """Test 8: Message with fewer than 10 non-whitespace characters is rejected."""
    # 9 characters trimmed -> rejected
    resp_short = contact_client.post("/api/v1/contact", json={
        "name": "Sender Name",
        "email": "tester@example.com",
        "message": "  123456789  "
    })
    assert resp_short.status_code == 422
    assert any("at least 10 non-whitespace characters" in str(e) for e in resp_short.json()["errors"])

    # 10 characters trimmed -> accepted
    resp_exact = contact_client.post("/api/v1/contact", json={
        "name": "Sender Name",
        "email": "tester@example.com",
        "message": "  1234567890  "
    })
    assert resp_exact.status_code == 201


def test_maximum_field_lengths(contact_client):
    """Test 9: Inputs exceeding maximum length limits are rejected with 422."""
    # Name > 100 characters
    resp_name = contact_client.post("/api/v1/contact", json={
        "name": "A" * 101,
        "email": "tester@example.com",
        "message": "Valid message body text."
    })
    assert resp_name.status_code == 422

    # Company > 150 characters
    resp_company = contact_client.post("/api/v1/contact", json={
        "name": "Sender Name",
        "email": "tester@example.com",
        "company": "C" * 151,
        "message": "Valid message body text."
    })
    assert resp_company.status_code == 422

    # Message > 3000 characters
    resp_msg = contact_client.post("/api/v1/contact", json={
        "name": "Sender Name",
        "email": "tester@example.com",
        "message": "M" * 3001
    })
    assert resp_msg.status_code == 422


def test_optional_empty_company_and_industry(contact_client, contact_db):
    """Test 10: Empty or whitespace-only optional fields normalize to None."""
    payload = {
        "name": "Independent Researcher",
        "email": "researcher@cynbit.org",
        "company": "    ",      # Whitespace-only optional
        "industry": "",          # Empty string optional
        "message": "Inquiry regarding security architecture consultation."
    }
    response = contact_client.post("/api/v1/contact", json=payload)
    assert response.status_code == 201
    contact_id = response.json()["contact_id"]

    # Verify in DB that company and industry were stored as None (NULL), not blank strings
    record = contact_db.query(ContactSubmission).filter_by(id=contact_id).first()
    assert record.company is None
    assert record.industry is None


def test_leading_and_trailing_whitespace_trimmed(contact_client, contact_db):
    """Test 11: Leading and trailing whitespace is automatically trimmed before persistence."""
    payload = {
        "name": "   Dr. Manas Vaidya   ",
        "email": "   AUDIT@EXAMPLE.COM   ",
        "company": "   Cynbit Labs   ",
        "industry": "   Threat Intel   ",
        "message": "   This message has significant outer padding on both ends.   "
    }
    response = contact_client.post("/api/v1/contact", json=payload)
    assert response.status_code == 201
    contact_id = response.json()["contact_id"]

    record = contact_db.query(ContactSubmission).filter_by(id=contact_id).first()
    assert record.name == "Dr. Manas Vaidya"
    assert record.email == "audit@example.com"
    assert record.company == "Cynbit Labs"
    assert record.industry == "Threat Intel"
    assert record.message == "This message has significant outer padding on both ends."


def test_invalid_requests_never_trigger_email(contact_client):
    """Test 12: Verify that invalid submissions abort before any external side effects occur."""
    invalid_payloads = [
        {"name": "   ", "email": "valid@email.com", "message": "Valid message text."},
        {"name": "Valid Name", "email": "not-an-email", "message": "Valid message text."},
        {"name": "Valid Name", "email": "valid@email.com", "message": "short"},
        {"name": "V", "email": "valid@email.com", "message": "Valid message text."}
    ]

    for p in invalid_payloads:
        resp = contact_client.post("/api/v1/contact", json=p)
        assert resp.status_code == 422

    # Across all 4 failed submissions, zero emails were dispatched
    assert len(contact_email_service.outbox) == 0
