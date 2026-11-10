"""
app/resilience/admission_controller.py
Engineering Contribution 1: Deadline-Aware Adaptive Admission Controller (DAC).
Predicts queue wait time and total execution latency against client SLA deadline.
Sheds doomed requests at the edge before consuming provider quota.
"""

import time
from collections import deque
from typing import Tuple, Optional
from app.config import CONFIG

class AdmissionController:
    def __init__(
        self,
        max_queue_depth: int = 25,
        default_deadline_ms: float = 8000.0,
        enabled: bool = True
    ):
        self.max_queue_depth = max_queue_depth
        self.default_deadline_ms = default_deadline_ms
        self.enabled = enabled
        
        # Rolling service latency window (last 20 completed requests)
        self._latency_history = deque(maxlen=20)
        self._default_estimated_service_ms = 450.0 # Initial baseline
        
        # Queue metrics
        self.current_queue_depth: int = 0
        self.peak_queue_depth: int = 0
        self.shed_count: int = 0
        self.admitted_count: int = 0

    def update_service_latency(self, latency_ms: float):
        """Records completed execution time into rolling average."""
        if latency_ms > 0:
            self._latency_history.append(latency_ms)

    @property
    def estimated_service_ms(self) -> float:
        if not self._latency_history:
            return self._default_estimated_service_ms
        return sum(self._latency_history) / len(self._latency_history)

    def evaluate_admission(
        self,
        deadline_ms: Optional[float] = None,
        estimated_tokens: int = 500,
        daily_exhausted: bool = False
    ) -> Tuple[bool, str, float]:
        """
        Evaluates whether an incoming request can realistically finish within its deadline.
        Returns: (admitted: bool, reason: str, expected_wait_ms: float)
        """
        if not self.enabled:
            self.current_queue_depth += 1
            if self.current_queue_depth > self.peak_queue_depth:
                self.peak_queue_depth = self.current_queue_depth
            self.admitted_count += 1
            return True, "admitted_disabled_dac", 0.0

        # Hard rejection: Daily budget exhausted
        if daily_exhausted:
            self.shed_count += 1
            return False, "shed_daily_quota_exhausted", 0.0

        # Hard rejection: Queue capacity saturated
        if self.current_queue_depth >= self.max_queue_depth:
            self.shed_count += 1
            return False, f"shed_queue_saturated (depth {self.current_queue_depth} >= {self.max_queue_depth})", 0.0

        # Deadline evaluation using Little's Law / M/M/1 wait approximation
        sla_ms = deadline_ms or self.default_deadline_ms
        avg_svc = self.estimated_service_ms
        expected_wait_ms = self.current_queue_depth * avg_svc
        expected_total_ms = expected_wait_ms + avg_svc

        if expected_total_ms > sla_ms:
            self.shed_count += 1
            return False, f"shed_deadline_unachievable (expected {expected_total_ms:.0f}ms > SLA {sla_ms:.0f}ms)", expected_wait_ms

        # Admitted to active queue
        self.current_queue_depth += 1
        if self.current_queue_depth > self.peak_queue_depth:
            self.peak_queue_depth = self.current_queue_depth
        self.admitted_count += 1
        return True, "admitted", expected_wait_ms

    def release(self):
        """Called when a request finishes processing and leaves the queue."""
        if self.current_queue_depth > 0:
            self.current_queue_depth -= 1
