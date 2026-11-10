"""
app/resilience/rate_limiter.py
Token Bucket and Sliding-Window rate limiter for local concurrency and quota governance.
"""

import time
import asyncio
from typing import Tuple

class TokenBucketRateLimiter:
    def __init__(self, rpm: int, tpm: int):
        self.rpm = rpm
        self.tpm = tpm
        
        # Leaky bucket rates per second
        self.request_leak_rate = rpm / 60.0
        self.token_leak_rate = tpm / 60.0

        # Current bucket levels
        self.request_tokens = float(rpm)
        self.capacity_requests = float(rpm)

        self.payload_tokens = float(tpm)
        self.capacity_tokens = float(tpm)

        self.last_update = time.perf_counter()
        self._lock = asyncio.Lock()

    def _replenish(self):
        now = time.perf_counter()
        elapsed = now - self.last_update
        self.last_update = now

        self.request_tokens = min(self.capacity_requests, self.request_tokens + elapsed * self.request_leak_rate)
        self.payload_tokens = min(self.capacity_tokens, self.payload_tokens + elapsed * self.token_leak_rate)

    async def acquire(self, estimated_tokens: int = 500) -> Tuple[bool, float]:
        """
        Attempts to acquire 1 request and estimated_tokens from the bucket.
        Returns (success, wait_time_seconds_if_failed).
        """
        async with self._lock:
            self._replenish()

            if self.request_tokens >= 1.0 and self.payload_tokens >= estimated_tokens:
                self.request_tokens -= 1.0
                self.payload_tokens -= estimated_tokens
                return True, 0.0

            # Compute wait time until tokens replenish
            req_wait = max(0.0, (1.0 - self.request_tokens) / self.request_leak_rate) if self.request_tokens < 1.0 else 0.0
            tok_wait = max(0.0, (estimated_tokens - self.payload_tokens) / self.token_leak_rate) if self.payload_tokens < estimated_tokens else 0.0
            wait_time = max(req_wait, tok_wait)

            return False, wait_time
