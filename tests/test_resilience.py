"""
tests/test_resilience.py
Unit tests for resilience primitives:
- AdmissionController (Contribution 1: Little's Law deadline-aware shedding)
- TokenBucketRateLimiter
- CircuitBreaker
- RetryPolicy (Contribution 3: Jitter & retry budget)
"""

import unittest
import asyncio
from app.resilience.admission_controller import AdmissionController
from app.resilience.rate_limiter import TokenBucketRateLimiter
from app.resilience.circuit_breaker import CircuitBreaker
from app.resilience.retry_policy import RetryPolicy

class TestResilience(unittest.TestCase):
    def test_admission_controller_shedding_under_deadline(self):
        # Admission controller with tight SLA of 300ms and average service time 200ms
        ac = AdmissionController(max_queue_depth=10, default_deadline_ms=300.0, enabled=True)
        ac.update_service_latency(200.0)

        # First request admitted (0 wait + 200 service = 200ms <= 300ms SLA)
        admitted, reason, wait = ac.evaluate_admission(deadline_ms=300.0)
        self.assertTrue(admitted)
        self.assertEqual(ac.current_queue_depth, 1)

        # Second request: queue depth is 1. Expected wait: 1 * 200 = 200ms. Expected total: 400ms > 300ms SLA
        # Controller MUST shed to avoid wasting token quota
        admitted_2, reason_2, _ = ac.evaluate_admission(deadline_ms=300.0)
        self.assertFalse(admitted_2)
        self.assertIn("shed_deadline_unachievable", reason_2)

    def test_admission_controller_daily_exhaustion(self):
        ac = AdmissionController(enabled=True)
        admitted, reason, _ = ac.evaluate_admission(daily_exhausted=True)
        self.assertFalse(admitted)
        self.assertIn("daily_quota_exhausted", reason)

    def test_circuit_breaker_transitions(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout_s=0.5)
        self.assertEqual(cb.state, CircuitBreaker.STATE_CLOSED)

        # 3 failures trip circuit
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitBreaker.STATE_CLOSED)
        cb.record_failure()
        self.assertEqual(cb.state, CircuitBreaker.STATE_OPEN)

        # In open state, execution rejected
        can_exec, reason = cb.can_execute()
        self.assertFalse(can_exec)
        self.assertIn("circuit_open", reason)

    def test_retry_budget_enforcement(self):
        rp = RetryPolicy(max_retries=3, retry_budget_ratio=0.20)
        # Register 10 total requests -> allowed 2 retries
        for _ in range(10):
            rp.total_requests += 1

        can_retry_1, reason_1, _ = rp.can_retry(0, "rate_limited", "error")
        self.assertTrue(can_retry_1)

        can_retry_2, reason_2, _ = rp.can_retry(1, "rate_limited", "error")
        self.assertTrue(can_retry_2)

        # 3rd retry exceeds 20% budget (2/10)
        can_retry_3, reason_3, _ = rp.can_retry(0, "rate_limited", "error")
        self.assertFalse(can_retry_3)
        self.assertIn("retry_budget_depleted", reason_3)

if __name__ == "__main__":
    unittest.main()
