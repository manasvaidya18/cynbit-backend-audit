"""
Sliding-Window Rate Limiter Dependency.
Protects sensitive public endpoints against abuse, denial-of-service, and brute-force enumeration.
"""

import time
import threading
from typing import Dict, List, Optional
from fastapi import HTTPException, Request, status


class SlidingWindowRateLimiter:
    """
    Thread-safe in-memory sliding-window rate limiter.
    Limits the number of requests per unique client IP within a sliding time window.
    """
    def __init__(self, times: int = 5, seconds: int = 60, name: str = "default"):
        self.times = times
        self.seconds = seconds
        self.name = name
        self._history: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def _get_client_identifier(self, request: Request) -> str:
        """Extract client identifier from proxy headers or direct client IP."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown_client"
        return f"{self.name}:{client_ip}"

    def __call__(self, request: Request) -> None:
        client_key = self._get_client_identifier(request)
        current_time = time.time()
        window_start = current_time - self.seconds

        with self._lock:
            timestamps = self._history.get(client_key, [])
            # Filter timestamps outside the sliding window
            valid_timestamps = [ts for ts in timestamps if ts > window_start]

            if len(valid_timestamps) >= self.times:
                oldest_timestamp = valid_timestamps[0]
                retry_after = int(self.seconds - (current_time - oldest_timestamp)) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded for {self.name}. Maximum {self.times} requests allowed per {self.seconds} seconds.",
                    headers={"Retry-After": str(max(retry_after, 1))}
                )

            valid_timestamps.append(current_time)
            self._history[client_key] = valid_timestamps

    def reset(self) -> None:
        """Reset limiter state (primarily for test isolation)."""
        with self._lock:
            self._history.clear()
