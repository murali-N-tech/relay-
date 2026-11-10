"""
app/resilience/retry_policy.py
Retry policies demonstrating failure amplification dynamics:
- NaiveRetryPolicy: Unbounded immediate/fixed retries (amplifies outages).
- ResilientRetryPolicy: Exponential backoff with Full Jitter, Retry Budget, and Circuit Breaker.
"""

import random
import time
import asyncio
from typing import Tuple, Optional
from app.resilience.circuit_breaker import CircuitBreaker

class RetryPolicy:
    def __init__(
        self,
        max_retries: int = 2,
        base_backoff_s: float = 0.5,
        backoff_multiplier: float = 2.0,
        jitter: bool = True,
        circuit_breaker: Optional[CircuitBreaker] = None,
        retry_budget_ratio: float = 0.20 # Max 20% retries out of total traffic
    ):
        self.max_retries = max_retries
        self.base_backoff_s = base_backoff_s
        self.backoff_multiplier = backoff_multiplier
        self.jitter = jitter
        self.circuit_breaker = circuit_breaker
        self.retry_budget_ratio = retry_budget_ratio

        # Global budget accounting
        self.total_requests = 0
        self.retries_executed = 0

    def can_retry(self, attempt: int, status: str, error_message: str) -> Tuple[bool, str, float]:
        """
        Determines whether a retry should be executed, and calculates backoff.
        Only retries transient faults: rate_limited, 503, 500, or socket timeouts.
        Does NOT retry permanent errors or client cancellations.
        """
        self.total_requests += 1

        if attempt >= self.max_retries:
            return False, "max_retries_exhausted", 0.0

        if status not in ("rate_limited", "timeout", "error"):
            return False, "status_not_retryable", 0.0

        # Check circuit breaker
        if self.circuit_breaker:
            can_exec, reason = self.circuit_breaker.can_execute()
            if not can_exec:
                return False, f"retry_aborted_by_circuit_breaker ({reason})", 0.0

        # Check global retry budget
        max_allowed_retries = max(2, int(self.total_requests * self.retry_budget_ratio))
        if self.retries_executed >= max_allowed_retries:
            return False, f"retry_budget_depleted ({self.retries_executed}/{max_allowed_retries})", 0.0

        # Calculate backoff delay
        calc_backoff = self.base_backoff_s * (self.backoff_multiplier ** attempt)
        if self.jitter:
            # Full Jitter: Uniform(0, calc_backoff)
            delay = random.uniform(0.1, calc_backoff)
        else:
            delay = calc_backoff

        self.retries_executed += 1
        return True, "retry_approved", delay
