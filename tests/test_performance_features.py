"""
Unit and Integration Tests for Performance, Caching, Pagination & Rate-Limiting Features.

Covers:
- Pagination default parameters and maximum page size enforcement
- Invalid limit and offset handling (422)
- Stable, deterministic ordering across sequential pages
- Redis-backed rate limiter allowed requests
- Rate limit exceeded response (HTTP 429)
- Retry-After header presence and value
- Cryptographic ETag header emission on initial request
- Conditional GET handling returning HTTP 304 Not Modified
"""

import sys
import os
import pytest
from fastapi.testclient import TestClient

# Ensure code-examples directory is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "code-examples"))

from pagination import app as pagination_app
from rate_limiting import app as rate_limiting_app, RedisRateLimiter, MockRedisClient
from caching import app as caching_app, generate_etag


@pytest.fixture
def page_client():
    return TestClient(pagination_app)


@pytest.fixture
def cache_client():
    return TestClient(caching_app)


@pytest.fixture
def rate_client():
    # Use isolated mock Redis client for tests
    mock_redis = MockRedisClient()
    test_limiter = RedisRateLimiter(limit=3, window_seconds=10, redis_client=mock_redis)

    # Override default limiter in app dependencies
    from rate_limiting import default_limiter
    rate_limiting_app.dependency_overrides[default_limiter] = test_limiter
    client = TestClient(rate_limiting_app)
    yield client
    rate_limiting_app.dependency_overrides.clear()


# ============================================================================
# 1. PAGINATION TESTS
# ============================================================================

def test_pagination_defaults_and_max_limit(page_client):
    """Test 1: Default pagination uses limit=20, offset=0, and respects max page size."""
    # Default parameters
    resp = page_client.get("/api/items")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 20
    assert data["pagination"]["limit"] == 20
    assert data["pagination"]["offset"] == 0
    assert data["pagination"]["total_count"] == 150
    assert data["pagination"]["has_next"] is True
    assert data["pagination"]["has_previous"] is False

    # Maximum allowed page size (100)
    resp_max = page_client.get("/api/items?limit=100")
    assert resp_max.status_code == 200
    assert len(resp_max.json()["items"]) == 100


def test_invalid_limit_and_offset_rejected(page_client):
    """Test 2: Invalid limit (<1 or >100) and negative offset are rejected with 422."""
    # Negative offset
    resp_neg_offset = page_client.get("/api/items?offset=-5")
    assert resp_neg_offset.status_code == 422

    # Limit = 0 (< 1)
    resp_zero_limit = page_client.get("/api/items?limit=0")
    assert resp_zero_limit.status_code == 422

    # Limit > 100 (> max)
    resp_over_limit = page_client.get("/api/items?limit=101")
    assert resp_over_limit.status_code == 422


def test_stable_deterministic_ordering(page_client):
    """Test 3: Sequential pages maintain stable, disjoint ordering without gaps or duplicates."""
    # Fetch page 1 (items 1 to 20)
    resp1 = page_client.get("/api/items?offset=0&limit=20")
    page1_items = resp1.json()["items"]
    page1_ids = [item["id"] for item in page1_items]

    # Fetch page 2 (items 21 to 40)
    next_offset = resp1.json()["pagination"]["next_offset"]
    assert next_offset == 20
    resp2 = page_client.get(f"/api/items?offset={next_offset}&limit=20")
    page2_items = resp2.json()["items"]
    page2_ids = [item["id"] for item in page2_items]

    # Verify strict disjointness (no duplicate items across pages)
    assert set(page1_ids).isdisjoint(set(page2_ids))

    # Verify strict monotonic ordering
    assert page1_ids == list(range(1, 21))
    assert page2_ids == list(range(21, 41))


# ============================================================================
# 2. RATE LIMITING TESTS
# ============================================================================

def test_rate_limiting_allowed_under_quota(rate_client):
    """Test 4: Requests within quota succeed (HTTP 200) with quota tracking headers."""
    # Limit is 3 requests per 10s window
    for i in range(3):
        resp = rate_client.get("/api/limited-action", headers={"X-Forwarded-For": "198.51.100.1"})
        assert resp.status_code == 200
        assert resp.headers["X-RateLimit-Limit"] == "3"
        assert int(resp.headers["X-RateLimit-Remaining"]) == (2 - i)


def test_rate_limiting_exceeded_and_retry_after(rate_client):
    """Test 5: Exceeding rate limit triggers HTTP 429 with Retry-After header."""
    client_ip = "198.51.100.2"

    # Exhaust quota (3 requests)
    for _ in range(3):
        res = rate_client.get("/api/limited-action", headers={"X-Forwarded-For": client_ip})
        assert res.status_code == 200

    # 4th request must be rejected with 429
    blocked_resp = rate_client.get("/api/limited-action", headers={"X-Forwarded-For": client_ip})
    assert blocked_resp.status_code == 429
    data = blocked_resp.json()
    assert "rate limit exceeded" in data["detail"].lower()

    # Verify Retry-After header
    assert "Retry-After" in blocked_resp.headers
    retry_after = int(blocked_resp.headers["Retry-After"])
    assert retry_after > 0
    assert retry_after <= 10


# ============================================================================
# 3. HTTP CACHING & ETAG REVALIDATION TESTS
# ============================================================================

def test_etag_returned_on_first_request(cache_client):
    """Test 6: Initial GET returns full 200 OK, payload, and ETag header."""
    resp = cache_client.get("/api/public-report")
    assert resp.status_code == 200
    assert "ETag" in resp.headers
    assert resp.headers["ETag"].startswith('"') and resp.headers["ETag"].endswith('"')
    assert "Cache-Control" in resp.headers
    assert "public" in resp.headers["Cache-Control"]
    assert resp.json()["report_id"] == "CYN-INTEL-2026-Q4"


def test_conditional_request_returns_304_not_modified(cache_client):
    """Test 7: Conditional GET with matching If-None-Match returns HTTP 304 with no body."""
    # Step 1: Initial request to get current ETag
    init_resp = cache_client.get("/api/public-report")
    etag = init_resp.headers["ETag"]

    # Step 2: Conditional request sending the obtained ETag
    reval_resp = cache_client.get("/api/public-report", headers={"If-None-Match": etag})
    assert reval_resp.status_code == 304
    assert reval_resp.headers["ETag"] == etag
    assert reval_resp.content == b""  # Zero message body payload


def test_private_and_no_store_caching_policies(cache_client):
    """Test 8: User profile uses private caching; sensitive token uses no-store."""
    # Private profile
    user_resp = cache_client.get("/api/user-profile")
    assert user_resp.status_code == 200
    assert "private" in user_resp.headers["Cache-Control"]
    assert "public" not in user_resp.headers["Cache-Control"]

    # No-store sensitive token
    token_resp = cache_client.get("/api/sensitive-token")
    assert token_resp.status_code == 200
    assert "no-store" in token_resp.headers["Cache-Control"]
