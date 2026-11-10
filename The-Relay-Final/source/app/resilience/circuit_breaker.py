"""
app/resilience/circuit_breaker.py
Circuit Breaker implementation protecting downstream inference providers from cascading failures.
"""

import time
from typing import Tuple

class CircuitBreaker:
    STATE_CLOSED = "CLOSED"       # Normal operation
    STATE_OPEN = "OPEN"           # Failing fast, requests rejected
    STATE_HALF_OPEN = "HALF_OPEN" # Testing single canary request

    def __init__(
        self,
        failure_threshold: int = 4,
        recovery_timeout_s: float = 10.0
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        
        self.state = self.STATE_CLOSED
        self.consecutive_failures = 0
        self.last_failure_time = 0.0
        self.open_count = 0

    def can_execute(self) -> Tuple[bool, str]:
        now = time.perf_counter()

        if self.state == self.STATE_CLOSED:
            return True, "closed"

        if self.state == self.STATE_OPEN:
            if now - self.last_failure_time > self.recovery_timeout_s:
                self.state = self.STATE_HALF_OPEN
                return True, "half_open_probe"
            return False, f"circuit_open (cooldown {self.recovery_timeout_s - (now - self.last_failure_time):.1f}s remaining)"

        if self.state == self.STATE_HALF_OPEN:
            return True, "half_open_probe"

        return True, "ok"

    def record_success(self):
        if self.state in (self.STATE_HALF_OPEN, self.STATE_OPEN):
            self.state = self.STATE_CLOSED
            self.consecutive_failures = 0

    def record_failure(self):
        self.consecutive_failures += 1
        self.last_failure_time = time.perf_counter()

        if self.consecutive_failures >= self.failure_threshold:
            if self.state != self.STATE_OPEN:
                self.open_count += 1
            self.state = self.STATE_OPEN
