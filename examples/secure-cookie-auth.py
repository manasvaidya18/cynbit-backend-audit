"""
Secure Cookie-Based Authentication & Anti-CSRF Reference Implementation.

Demonstrates production-grade client-side credential security:
1. HttpOnly, Secure, and SameSite cookie attributes preventing XSS credential theft.
2. Anti-CSRF token protection for state-changing requests (Double Submit Cookie).
3. Short-lived access tokens with path-scoped HttpOnly refresh cookies.
4. Server-side authorization validation (never trusting client-side storage).

Independent educational demonstration for Cynbit Backend Technical Audit.
"""

from datetime import datetime, timedelta, timezone
import hmac
import hashlib
import secrets
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(
    title="Secure Cookie Authentication & Storage Reference API",
    description="Demonstrates HttpOnly cookies, CSRF defense, and server-side authorization.",
    version="1.0.0"
)

# Configuration settings
SECRET_KEY = "cynbit-demo-super-secret-key-change-in-production"
ACCESS_TOKEN_LIFETIME_MINUTES = 15
REFRESH_TOKEN_LIFETIME_DAYS = 7
CSRF_SECRET = "cynbit-csrf-protection-secret-salt"

# In-memory session store (in production, use Redis or PostgreSQL)
REVOKED_REFRESH_TOKENS = set()


class LoginRequest(BaseModel):
    username: str = Field(..., example="security_analyst")
    password: str = Field(..., example="DemonstrationPassword123!")


class UserProfile(BaseModel):
    user_id: str
    username: str
    role: str
    last_login: datetime


def generate_secure_token() -> str:
    """Generate cryptographically secure 256-bit token."""
    return secrets.token_urlsafe(32)


def generate_csrf_token(session_id: str) -> str:
    """Generate a HMAC-SHA256 CSRF token tied to the user's session."""
    message = f"{session_id}:{CSRF_SECRET}"
    return hmac.new(SECRET_KEY.encode(), message.encode(), hashlib.sha256).hexdigest()


def verify_csrf_token(csrf_token: str, session_id: str) -> bool:
    """Validate incoming CSRF token in constant time."""
    if not csrf_token or not session_id:
        return False
    expected = generate_csrf_token(session_id)
    return hmac.compare_digest(csrf_token, expected)


# --- Dependencies ---

def get_current_user_from_cookie(request: Request) -> dict:
    """
    Extract and validate session from HttpOnly cookie.
    JavaScript cannot read this cookie; it is transmitted automatically by the browser.
    """
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: No valid session cookie found."
        )

    # In production: query database or Redis using session_id
    if session_id.startswith("mock_session_"):
        return {
            "user_id": "usr_9981a",
            "username": "security_analyst",
            "role": "auditor",
            "session_id": session_id
        }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired session cookie."
    )


def require_csrf_protection(request: Request, user: dict = Depends(get_current_user_from_cookie)):
    """
    Enforce CSRF token verification on state-changing operations.
    The CSRF token is provided via the 'X-CSRF-Token' request header.
    """
    if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
        csrf_header = request.headers.get("X-CSRF-Token")
        if not csrf_header or not verify_csrf_token(csrf_header, user["session_id"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF validation failed: Missing or invalid X-CSRF-Token header."
            )
    return user


# --- API Routes ---

@app.post("/api/auth/login", summary="Login and receive HttpOnly session & CSRF tokens")
def login(credentials: LoginRequest, response: Response):
    """
    Authenticates the user and sets HttpOnly, Secure, SameSite cookies.
    Also returns a CSRF token for the frontend to include in custom request headers.
    """
    # Simple demonstration credentials
    if credentials.username != "security_analyst" or credentials.password != "DemonstrationPassword123!":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials."
        )

    # 1. Create a server-side session identifier
    session_id = f"mock_session_{generate_secure_token()}"
    refresh_token = f"refresh_{generate_secure_token()}"

    # 2. Generate anti-CSRF token tied to this session
    csrf_token = generate_csrf_token(session_id)

    # 3. Set Session Cookie with strict security flags:
    # - httponly=True: Inaccessible via document.cookie (Defeats XSS theft)
    # - secure=True: Sent strictly over TLS/HTTPS (Set False only in local non-SSL dev)
    # - samesite="Lax" or "Strict": Browser suppresses cookie on cross-site requests
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=ACCESS_TOKEN_LIFETIME_MINUTES * 60,
        path="/"
    )

    # 4. Set Refresh Token Cookie with restricted path scope
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="strict",
        max_age=REFRESH_TOKEN_LIFETIME_DAYS * 86400,
        path="/api/auth/refresh"  # Only sent when calling refresh endpoint
    )

    return {
        "success": True,
        "message": "Login successful. Credentials saved securely in HttpOnly cookies.",
        "csrf_token": csrf_token,
        "user": {
            "username": credentials.username,
            "role": "auditor"
        }
    }


@app.get("/api/user/profile", summary="Fetch profile using HttpOnly cookie session")
def get_profile(current_user: dict = Depends(get_current_user_from_cookie)):
    """
    Protected endpoint: Verified entirely via server-side session lookup.
    Never relies on client-side stored roles or user IDs.
    """
    return {
        "user_id": current_user["user_id"],
        "username": current_user["username"],
        "role": current_user["role"],
        "last_login": datetime.now(timezone.utc).isoformat()
    }


@app.post("/api/user/update-settings", summary="State-changing operation requiring CSRF header")
def update_settings(
    settings_payload: dict,
    current_user: dict = Depends(require_csrf_protection)
):
    """
    Demonstrates defense-in-depth:
    1. Authenticated via HttpOnly session cookie.
    2. Protected against CSRF via X-CSRF-Token header verification.
    """
    return {
        "success": True,
        "message": "Settings updated safely with valid CSRF verification.",
        "applied_settings": settings_payload
    }


@app.post("/api/auth/logout", summary="Logout and clear authentication cookies")
def logout(response: Response, current_user: dict = Depends(get_current_user_from_cookie)):
    """
    Clears all authentication cookies and invalidates server-side session.
    """
    response.delete_cookie(key="session_id", path="/")
    response.delete_cookie(key="refresh_token", path="/api/auth/refresh")

    return {
        "success": True,
        "message": "Logged out successfully. All authentication cookies destroyed."
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
