"""
Unit and Integration Tests for Centralized Error Handling & Observability.

Covers:
- Successful request with correlation ID (200 OK)
- Invalid request body with structured field errors (422 Unprocessable Content)
- Expected application domain errors (404 Resource Not Found, 409 Duplicate)
- Unexpected internal server error (500 Internal Server Error)
- Stack trace suppression (zero internal stack traces leaked in 500 response)
- Correlation ID propagation and generation (custom X-Request-ID vs generated UUID)
"""

import sys
import os
import pytest
from fastapi.testclient import TestClient

# Ensure code-examples is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "code-examples"))
from error_responses import app


@pytest.fixture
def client():
    """TestClient fixture for error handling API."""
    return TestClient(app, raise_server_exceptions=False)


def test_successful_request_with_correlation_id(client):
    """Test 1: Successful request returns 200 and preserves correlation ID."""
    payload = {
        "name": "Manas Vaidya",
        "email": "manas.vaidya@example.com",
        "message": "Valid inquiry message exceeding 10 characters."
    }
    custom_trace_id = "trace-client-req-001"
    response = client.post(
        "/api/contact",
        json=payload,
        headers={"X-Request-ID": custom_trace_id}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["name"] == "Manas Vaidya"
    assert data["correlation_id"] == custom_trace_id
    assert response.headers["X-Correlation-ID"] == custom_trace_id


def test_invalid_request_body_422(client):
    """Test 2: Validation failure returns 422 with structured field details and correlation ID."""
    invalid_payload = {
        "name": "M",  # Too short (< 2 chars)
        "email": "not-an-email",  # Malformed email
        "message": "   "  # Whitespace-only
    }
    response = client.post("/api/contact", json=invalid_payload)

    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "correlation_id" in data["error"]
    assert len(data["error"]["details"]) >= 2
    assert response.headers["X-Correlation-ID"] == data["error"]["correlation_id"]


def test_expected_application_error_404(client):
    """Test 3: Expected 404 domain exception returns structured error envelope."""
    response = client.get("/api/resource/missing")

    assert response.status_code == 404
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert "not found" in data["error"]["message"].lower()
    assert "correlation_id" in data["error"]
    assert response.headers["X-Correlation-ID"] == data["error"]["correlation_id"]


def test_expected_application_error_409(client):
    """Test 4: Expected 409 conflict exception returns structured error envelope."""
    response = client.post("/api/resource/duplicate", json={"key": "existing_value"})

    assert response.status_code == 409
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "DUPLICATE_RESOURCE"
    assert "already exists" in data["error"]["message"].lower()
    assert response.headers["X-Correlation-ID"] == data["error"]["correlation_id"]


def test_unexpected_server_error_500_suppresses_stack_trace(client):
    """
    Test 5: Unexpected 500 error logs internally and returns a safe generic message.
    Crucial Security Check: The response MUST NOT leak Python stack traces, file paths,
    or internal exception names (e.g. ZeroDivisionError).
    """
    response = client.get("/api/simulate-server-error")

    assert response.status_code == 500
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "unexpected internal server error" in data["error"]["message"].lower()
    assert "correlation_id" in data["error"]
    assert response.headers["X-Correlation-ID"] == data["error"]["correlation_id"]

    # Security check: Zero information disclosure
    raw_response_text = response.text
    assert "ZeroDivisionError" not in raw_response_text
    assert "Traceback" not in raw_response_text
    assert "line " not in raw_response_text
    assert ".py" not in raw_response_text


def test_correlation_id_propagation_and_generation(client):
    """Test 6: Custom correlation IDs are propagated; missing IDs are auto-generated."""
    # Case A: Client supplies custom X-Correlation-ID
    client_corr_id = "custom-audit-correlation-uuid-987"
    resp_custom = client.get(
        "/api/resource/missing",
        headers={"X-Correlation-ID": client_corr_id}
    )
    assert resp_custom.headers["X-Correlation-ID"] == client_corr_id
    assert resp_custom.json()["error"]["correlation_id"] == client_corr_id

    # Case B: Client provides no header -> Auto-generated UUID present
    resp_auto = client.get("/api/resource/missing")
    auto_id = resp_auto.headers.get("X-Correlation-ID")
    assert auto_id is not None
    assert len(auto_id) >= 16
    assert resp_auto.json()["error"]["correlation_id"] == auto_id
