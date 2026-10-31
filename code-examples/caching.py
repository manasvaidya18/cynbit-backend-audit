"""
HTTP Caching, ETag Generation & Conditional GET Revalidation Architecture.

Demonstrates:
1. Cryptographic ETag generation based on response representation content.
2. Conditional GET evaluation handling 'If-None-Match' request headers.
3. Returning HTTP 304 Not Modified with empty payload on cache match.
4. Strategic Cache-Control policy selection (public, private, no-store, must-revalidate).
5. Defenses against caching sensitive/user-specific data publicly.

Independent reference implementation for Cynbit Backend Technical Audit.
"""

import hashlib
import json
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, Response as PlainResponse

app = FastAPI(
    title="Cynbit HTTP Caching & Conditional Revalidation Reference API",
    description="Demonstrates ETag generation, 304 Not Modified responses, and Cache-Control headers."
)


# --- Reusable ETag & Conditional Revalidation Helper ---
def generate_etag(data: Any) -> str:
    """
    Generate an RFC 9110 compliant Entity Tag (ETag).
    Computes a cryptographic SHA-256 digest over the canonical JSON serialization.
    """
    if isinstance(data, (dict, list)):
        canonical_str = json.dumps(data, sort_keys=True, separators=(",", ":"))
    else:
        canonical_str = str(data)
    digest = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()[:16]
    return f'"{digest}"'


def evaluate_conditional_get(
    request: Request,
    etag: str,
    cache_control: str = "public, max-age=0, must-revalidate"
) -> Optional[Response]:
    """
    Inspect incoming 'If-None-Match' header against current ETag.
    If match is detected, return HTTP 304 Not Modified with zero message body.
    Otherwise return None, allowing caller to return full HTTP 200 payload.
    """
    if_none_match = request.headers.get("if-none-match")
    if if_none_match:
        # Client may send multiple ETags or wildcards
        client_etags = [t.strip() for t in if_none_match.split(",")]
        if etag in client_etags or "*" in client_etags:
            # Resource is unmodified: return 304 with no body
            return PlainResponse(
                status_code=status.HTTP_304_NOT_MODIFIED,
                headers={
                    "ETag": etag,
                    "Cache-Control": cache_control
                }
            )
    return None


# --- Example Mock Resources ---
PUBLIC_REPORT_DATA = {
    "report_id": "CYN-INTEL-2026-Q4",
    "title": "Global Threat Intelligence Landscape",
    "version": "1.4.0",
    "updated_at": "2026-11-01T00:00:00Z",
    "summary": "Analysis of automated threat vectors and credential hygiene."
}


# --- Endpoints Demonstrating Cache-Control Strategies ---

@app.get("/api/public-report", summary="Public report with ETag and 304 revalidation")
def get_public_report(request: Request, response: Response):
    """
    Demonstrates public edge-cacheable content with ETag validation.
    
    Header Strategy:
    - Cache-Control: public, max-age=0, must-revalidate
      (CDN/Browser caches it, but must check origin before reusing)
    - Returns HTTP 304 when If-None-Match matches current content.
    """
    etag = generate_etag(PUBLIC_REPORT_DATA)
    cache_control = "public, max-age=0, must-revalidate"

    # Evaluate conditional GET
    revalidation_response = evaluate_conditional_get(request, etag, cache_control)
    if revalidation_response:
        return revalidation_response

    # First-time fetch: return full 200 OK with ETag
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = cache_control
    return PUBLIC_REPORT_DATA


@app.get("/api/user-profile", summary="Private user-specific data (Browser-only cache)")
def get_user_profile(request: Request, response: Response):
    """
    Demonstrates private, user-specific data caching.
    
    Header Strategy:
    - Cache-Control: private, no-cache
      (CRUCIAL: Prevents intermediate shared proxies or edge CDNs from storing User A's data
       and serving it to User B. Only the authenticated client's browser may cache it).
    """
    user_data = {
        "user_id": "usr_9918a",
        "username": "analyst@cynbit.in",
        "role": "Security Researcher"
    }
    etag = generate_etag(user_data)
    cache_control = "private, no-cache"

    reval = evaluate_conditional_get(request, etag, cache_control)
    if reval:
        return reval

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = cache_control
    return user_data


@app.get("/api/sensitive-token", summary="Sensitive data that must never be cached")
def get_sensitive_token(response: Response):
    """
    Demonstrates zero-cache policy for sensitive credentials or payment data.
    
    Header Strategy:
    - Cache-Control: no-store, no-cache, must-revalidate, max-age=0
    - Pragma: no-cache
      (Instructs browsers, CDNs, and proxies to never write the response to disk or memory).
    """
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return {
        "ephemeral_token": "one_time_token_xyz987",
        "expires_in": 60
    }


"""
===============================================================================
ARCHITECTURAL GUIDANCE: HTTP CACHE-CONTROL STRATEGY MATRIX
===============================================================================

1. public:
   - Response can be cached by ANY cache (Edge CDN, intermediate corporate proxies,
     ISP gateways, browser).
   - Only safe for truly public, unauthenticated resources.

2. private:
   - Response is intended for a single user and MUST NOT be cached by shared caches (CDNs).
   - The user's individual browser is permitted to cache it.
   - Mandatory for authenticated user dashboards and profiles.

3. no-cache vs. no-store:
   - no-cache: The cache MAY store the response, but MUST revalidate with the origin server
     (via ETag / If-None-Match) before serving it to the user.
   - no-store: The cache MUST NOT store any part of the request or response in any storage medium.
     Mandatory for credit card numbers, passwords, auth tokens, and session secrets.

4. max-age=0, must-revalidate:
   - Forces immediate expiration, compelling the client/CDN to send a conditional GET
     on every single access, enabling efficient 304 Not Modified bandwidth savings.
===============================================================================
"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8006)
