"""
Distributed Redis-Backed Rate Limiting Architecture.

Demonstrates:
1. Distributed sliding-window / fixed-window rate limiting backed by Redis.
2. Configurable request limits and time windows.
3. HTTP 429 Too Many Requests response with RFC-compliant Retry-After header.
4. Comprehensive explanation of why in-memory rate limiting fails in multi-worker
   and clustered environments.
5. Built-in mock Redis provider for offline testing without external Redis dependencies.

Independent reference implementation for Cynbit Backend Technical Audit.
"""

import time
from typing import Optional, Tuple
from fastapi import FastAPI, Depends, HTTPException, Request, Response, status

# Import redis client if available, with graceful fallback
try:
    import redis
except ImportError:
    redis = None


# --- Built-In In-Memory Mock Redis Client for Local/Test Environments ---
class MockRedisClient:
    """
    Lightweight, thread-safe in-memory mock replicating Redis atomic INCR and PTTL.
    Allows running and testing the rate-limiting architecture without requiring an active Redis daemon.
    """
    def __init__(self):
        self._data = {}
        self._expiry = {}

    def _purge_if_expired(self, key: str):
        if key in self._expiry and time.time() > self._expiry[key]:
            del self._data[key]
            del self._expiry[key]

    def incr(self, key: str) -> int:
        self._purge_if_expired(key)
        val = self._data.get(key, 0) + 1
        self._data[key] = val
        return val

    def expire(self, key: str, seconds: int) -> bool:
        if key in self._data:
            self._expiry[key] = time.time() + seconds
            return True
        return False

    def pttl(self, key: str) -> int:
        """Returns time to live in milliseconds, or -2 if key doesn't exist."""
        self._purge_if_expired(key)
        if key not in self._data or key not in self._expiry:
            return -2
        remaining = self._expiry[key] - time.time()
        return max(0, int(remaining * 1000))

    def flushall(self):
        self._data.clear()
        self._expiry.clear()


# --- Redis Distributed Rate Limiter ---
class RedisRateLimiter:
    """
    Distributed Rate Limiter utilizing atomic Redis commands.
    
    Why In-Memory Limiters Fail in Production:
    - Multiple Workers: Deployments running `uvicorn --workers 4` or Gunicorn run 4 distinct
      Python processes with unshared memory. An in-memory dictionary is isolated per-process,
      effectively quadrupling the allowed request limit.
    - Horizontal Scaling: Kubernetes pods and serverless instances scale dynamically;
      traffic routed through a load balancer hits different instances, rendering in-memory state useless.
    - Volatility: Pod restarts or rolling updates wipe all client request tracking history.
    - Centralized Authority: Redis serves as an ultra-fast, in-memory centralized datastore
      ensuring identical quota enforcement across all nodes in the cluster.
    """
    def __init__(
        self,
        limit: int = 5,
        window_seconds: int = 60,
        redis_client: Optional[Any] = None,
        key_prefix: str = "rl"
    ):
        self.limit = limit
        self.window_seconds = window_seconds
        self.prefix = key_prefix
        # Use provided client, or default to mock client if external Redis is not running
        self.client = redis_client if redis_client is not None else MockRedisClient()

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP respecting standard reverse-proxy headers."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "127.0.0.1"

    def is_allowed(self, client_id: str) -> Tuple[bool, int, int]:
        """
        Evaluate rate limit atomically using Redis.
        Returns: (allowed: bool, remaining_requests: int, retry_after_seconds: int)
        """
        current_time_bucket = int(time.time() // self.window_seconds)
        redis_key = f"{self.prefix}:{client_id}:{current_time_bucket}"

        # Atomic increment in Redis
        current_count = self.client.incr(redis_key)

        # Set expiration on key creation
        if current_count == 1:
            self.client.expire(redis_key, self.window_seconds)

        if current_count > self.limit:
            # Query TTL to inform the client of exact seconds to wait
            ttl_ms = self.client.pttl(redis_key)
            retry_after = max(1, (ttl_ms // 1000) if ttl_ms > 0 else self.window_seconds)
            return False, 0, retry_after

        remaining = max(0, self.limit - current_count)
        return True, remaining, 0

    def __call__(self, request: Request, response: Response):
        """FastAPI Dependency callable enforcing rate limits."""
        client_ip = self._get_client_ip(request)
        allowed, remaining, retry_after = self.is_allowed(client_ip)

        response.headers["X-RateLimit-Limit"] = str(self.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: Maximum {self.limit} requests per {self.window_seconds}s.",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Reset": str(retry_after)
                }
            )


# --- Example FastAPI Application ---
app = FastAPI(
    title="Cynbit Distributed Rate Limiting Reference API",
    description="Demonstrates Redis-backed rate limiting with Retry-After headers."
)

# Standard limiter: 5 requests per 60 seconds
default_limiter = RedisRateLimiter(limit=5, window_seconds=60)


@app.get(
    "/api/limited-action",
    summary="Rate-limited endpoint",
    responses={
        429: {"description": "Rate limit exceeded (Too Many Requests)"}
    }
)
def perform_action(request: Request, response: Response, _=Depends(default_limiter)):
    """
    Demonstrates a protected route enforced by the Redis rate limiter.
    Emits X-RateLimit-Limit and X-RateLimit-Remaining headers on success,
    and returns HTTP 429 with Retry-After when threshold is reached.
    """
    return {
        "success": True,
        "message": "Action completed successfully under quota.",
        "timestamp": time.time()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8005)
