"""
Comprehensive Test Suite for Newsletter Subscription System.
Covers:
- Valid subscription
- Invalid email handling
- Duplicate subscription handling
- Verification with valid token
- Verification with expired token
- Verification with invalid token
- Unsubscribe workflow
- Repeated subscription attempts (Pending & Unsubscribed states)
- Rate limiting enforcement
"""

import re
from datetime import datetime, timedelta, timezone
import pytest
from app.models import Subscription, SubscriptionStatus
from app.services.email_service import email_service
from app.security import hash_token


def extract_token_from_url(url: str) -> str:
    """Extract token parameter from a URL string."""
    match = re.search(r"token=([A-Za-z0-9_\-]+)", url)
    assert match is not None, f"Failed to extract token from URL: {url}"
    return match.group(1)


def test_valid_subscription(client, db_session):
    """Test 1: Valid email subscription initiates double opt-in."""
    email = "security.analyst@example.com"
    response = client.post(
        "/api/v1/newsletter/subscribe",
        json={"email": email}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "PENDING"
    assert "inbox" in data["message"].lower()

    # Verify database state
    sub = db_session.query(Subscription).filter(Subscription.email == email).first()
    assert sub is not None
    assert sub.status == SubscriptionStatus.PENDING
    assert sub.verification_token_hash is not None
    assert sub.verification_token_expires_at is not None
    assert sub.verified_at is None

    # Verify email dispatch
    last_email = email_service.get_last_email_for(email)
    assert last_email is not None
    assert "Confirm Your Subscription" in last_email.subject
    assert "/api/v1/newsletter/verify?token=" in last_email.text_body


@pytest.mark.parametrize("invalid_email", [
    "not-an-email",
    "missingdomain@",
    "@domain.com",
    "spaces in@email.com",
    "attacker@domain.com\r\nBcc:victim@spam.com",
    "a" * 250 + "@example.com",
])
def test_invalid_email(client, invalid_email):
    """Test 2: Malformed, illegal, and injection emails are rejected with 422."""
    response = client.post(
        "/api/v1/newsletter/subscribe",
        json={"email": invalid_email}
    )
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert data["error_code"] == "VALIDATION_ERROR"


def test_duplicate_subscription_active(client, db_session):
    """Test 3: Duplicate submission of an active email returns idempotent confirmation."""
    email = "active.member@example.com"

    # Step 1: Initial subscription
    sub_resp = client.post("/api/v1/newsletter/subscribe", json={"email": email})
    assert sub_resp.status_code == 200
    raw_token = sub_resp.json()["token_preview"]

    # Step 2: Verify and activate
    verify_resp = client.get(f"/api/v1/newsletter/verify?token={raw_token}")
    assert verify_resp.status_code == 200
    email_service.clear()

    # Step 3: Attempt duplicate subscription
    dup_resp = client.post("/api/v1/newsletter/subscribe", json={"email": email})
    assert dup_resp.status_code == 200
    dup_data = dup_resp.json()
    assert dup_data["success"] is True
    assert dup_data["status"] == "ACTIVE"
    assert "already in our intelligence network" in dup_data["message"]

    # Ensure no spam email was generated
    assert email_service.get_last_email_for(email) is None


def test_verification_with_valid_token(client, db_session):
    """Test 4: Verification transitions subscription to ACTIVE and issues unsubscribe token."""
    email = "new.user@example.com"
    sub_resp = client.post("/api/v1/newsletter/subscribe", json={"email": email})
    raw_token = sub_resp.json()["token_preview"]

    # Perform verification
    verify_resp = client.get(f"/api/v1/newsletter/verify?token={raw_token}")
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["success"] is True
    assert verify_data["email"] == email

    # Check database state: Single-use verification token is cleared
    sub = db_session.query(Subscription).filter(Subscription.email == email).first()
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.verification_token_hash is None
    assert sub.verification_token_expires_at is None
    assert sub.verified_at is not None
    assert sub.unsubscribe_token_hash is not None

    # Check welcome email with unsubscribe mechanism
    welcome_email = email_service.get_last_email_for(email)
    assert welcome_email is not None
    assert "Welcome to Cynbit" in welcome_email.subject
    assert "List-Unsubscribe" in welcome_email.headers


def test_verification_with_expired_token(client, db_session):
    """Test 5: Verification fails gracefully when the token is past expiration."""
    email = "expired.token@example.com"
    sub_resp = client.post("/api/v1/newsletter/subscribe", json={"email": email})
    raw_token = sub_resp.json()["token_preview"]

    # Manually expire the token in the database
    sub = db_session.query(Subscription).filter(Subscription.email == email).first()
    past_time = datetime.now(timezone.utc) - timedelta(hours=2)
    sub.verification_token_expires_at = past_time
    db_session.commit()

    # Attempt verification
    verify_resp = client.get(f"/api/v1/newsletter/verify?token={raw_token}")
    assert verify_resp.status_code == 400
    assert "expired" in verify_resp.json()["detail"].lower()

    # Verify status remained PENDING
    db_session.refresh(sub)
    assert sub.status == SubscriptionStatus.PENDING


def test_verification_with_invalid_token(client):
    """Test 6: Verification fails when token is forged or does not exist."""
    invalid_token = "completely_bogus_token_random_string_12345"
    response = client.get(f"/api/v1/newsletter/verify?token={invalid_token}")
    assert response.status_code == 400
    assert "invalid" in response.json()["detail"].lower()


def test_unsubscribe(client, db_session):
    """Test 7: Unsubscribe transitions active subscriber to UNSUBSCRIBED."""
    email = "retiring.subscriber@example.com"
    client.post("/api/v1/newsletter/subscribe", json={"email": email})
    
    # Extract token from welcome email
    welcome_email = email_service.get_last_email_for(email)
    assert welcome_email is not None
    # Verify first
    verify_token = extract_token_from_url(welcome_email.text_body)
    client.get(f"/api/v1/newsletter/verify?token={verify_token}")

    welcome_email = email_service.get_last_email_for(email)
    unsub_token = extract_token_from_url(welcome_email.text_body)

    # Execute unsubscribe
    unsub_resp = client.post(
        "/api/v1/newsletter/unsubscribe",
        json={"token": unsub_token, "email": email}
    )
    assert unsub_resp.status_code == 200
    data = unsub_resp.json()
    assert data["success"] is True
    assert "unsubscribed" in data["message"].lower()

    # Check database
    sub = db_session.query(Subscription).filter(Subscription.email == email).first()
    assert sub.status == SubscriptionStatus.UNSUBSCRIBED
    assert sub.unsubscribed_at is not None

    # Idempotent re-attempt or forged token
    fake_token = "nonexistent_unsub_token_6789012345"
    bad_resp = client.post("/api/v1/newsletter/unsubscribe", json={"token": fake_token})
    assert bad_resp.status_code == 400


def test_repeated_subscription_attempts(client, db_session):
    """Test 8: Repeated subscriptions handle pending re-send and unsubscribed re-activation."""
    email = "resubscriber@example.com"

    # Step 1: Subscribe (Pending)
    client.post("/api/v1/newsletter/subscribe", json={"email": email})
    email_service.clear()

    # Step 2: Subscribe again while pending -> Resends fresh verification link
    repeat_resp = client.post("/api/v1/newsletter/subscribe", json={"email": email})
    assert repeat_resp.status_code == 200
    assert "fresh verification link" in repeat_resp.json()["message"]
    assert email_service.get_last_email_for(email) is not None

    # Step 3: Verify and then unsubscribe
    token = repeat_resp.json()["token_preview"]
    client.get(f"/api/v1/newsletter/verify?token={token}")

    welcome_email = email_service.get_last_email_for(email)
    unsub_token = extract_token_from_url(welcome_email.text_body)
    client.post("/api/v1/newsletter/unsubscribe", json={"token": unsub_token})

    # Step 4: Re-subscribe after unsubscribing -> Transitions back to PENDING with new verification token
    resub_resp = client.post("/api/v1/newsletter/subscribe", json={"email": email})
    assert resub_resp.status_code == 200
    assert "welcome back" in resub_resp.json()["message"].lower()

    sub = db_session.query(Subscription).filter(Subscription.email == email).first()
    assert sub.status == SubscriptionStatus.PENDING
    assert sub.unsubscribed_at is None


def test_rate_limiting(client):
    """Test 9: Rate limiting triggers HTTP 429 when threshold is exceeded."""
    # Threshold for subscribe is 5 per 60 seconds
    responses = []
    for i in range(6):
        resp = client.post(
            "/api/v1/newsletter/subscribe",
            json={"email": f"ratelimit.test{i}@example.com"},
            headers={"X-Forwarded-For": "198.51.100.42"}
        )
        responses.append(resp)

    # First 5 should succeed (200 OK)
    for resp in responses[:5]:
        assert resp.status_code == 200

    # 6th should be throttled (429 Too Many Requests)
    assert responses[5].status_code == 429
    assert "rate limit exceeded" in responses[5].json()["detail"].lower()
    assert "Retry-After" in responses[5].headers
