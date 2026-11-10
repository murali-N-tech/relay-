"""
app/experiments/benchmark.py
Automated benchmark runner executing the 5 required load scenarios,
retrieval setting comparisons across the 15 evaluation questions,
and failure amplification retry experiments.
"""

import os
import json
import time
import asyncio
import random
from typing import List, Dict, Any, Optional

from app.config import CONFIG, ProviderLimits, StandinConfig
from app.providers.standin_provider import StandinProvider
from app.providers.groq_provider import GroqProvider
from app.resilience.admission_controller import AdmissionController
from app.resilience.retry_policy import RetryPolicy
from app.resilience.circuit_breaker import CircuitBreaker
from app.pipeline.retriever import RetrieverTool
from app.pipeline.orchestrator import PipelineOrchestrator
from app.observability.tracing import ResultsLogger

class BenchmarkSuite:
    def __init__(self, logger: Optional[ResultsLogger] = None):
        self.logger = logger or ResultsLogger()
        self.eval_questions = self._load_eval_questions()
        self.retriever = RetrieverTool()

    def _load_eval_questions(self) -> List[Dict[str, Any]]:
        with open(CONFIG.eval_questions_path, "r", encoding="utf-8") as f:
            return json.load(f)

    async def run_scenario_steady(self, provider, total_requests: int = 15, interval_s: float = 2.0):
        """Scenario 1: Steady Traffic (within safe limits, offered rate ~30 req/min)."""
        print(f"\n--- Running Scenario: Steady Traffic ({total_requests} requests, interval {interval_s}s) ---")
        orchestrator = PipelineOrchestrator(
            provider=provider,
            retriever=self.retriever,
            admission_controller=AdmissionController(enabled=True),
            retry_policy=RetryPolicy(max_retries=2, jitter=True),
            logger=self.logger
        )

        for i in range(total_requests):
            q_data = self.eval_questions[i % len(self.eval_questions)]
            rid = f"steady_{i+1:03d}"
            async for _ in orchestrator.execute_request(
                query=q_data["question"],
                scenario="steady",
                retrieval_setting="B",
                must_refuse=q_data["must_refuse"],
                expected_keywords=q_data["expected_answer_keywords"],
                request_id=rid
            ):
                pass
            await asyncio.sleep(interval_s)

    async def run_scenario_burst(self, provider, total_requests: int = 35):
        """Scenario 2: Traffic Burst (35 concurrent requests fired at once)."""
        print(f"\n--- Running Scenario: Sudden Traffic Burst ({total_requests} concurrent requests) ---")
        orchestrator = PipelineOrchestrator(
            provider=provider,
            retriever=self.retriever,
            admission_controller=AdmissionController(enabled=True, max_queue_depth=20),
            retry_policy=RetryPolicy(max_retries=2, jitter=True),
            logger=self.logger
        )

        tasks = []
        for i in range(total_requests):
            q_data = self.eval_questions[i % len(self.eval_questions)]
            rid = f"burst_{i+1:03d}"
            
            async def run_one(q, r_id, must_ref, kws):
                async for _ in orchestrator.execute_request(
                    query=q,
                    scenario="burst",
                    retrieval_setting="B",
                    must_refuse=must_ref,
                    expected_keywords=kws,
                    request_id=r_id
                ):
                    pass

            tasks.append(run_one(q_data["question"], rid, q_data["must_refuse"], q_data["expected_answer_keywords"]))

        await asyncio.gather(*tasks)

    async def run_scenario_overload(self, provider, total_requests: int = 40, duration_s: float = 30.0):
        """Scenario 3: Sustained Overload (offered rate 80 req/min, provider capacity 30 RPM)."""
        print(f"\n--- Running Scenario: Sustained Overload ({total_requests} requests over {duration_s}s) ---")
        orchestrator = PipelineOrchestrator(
            provider=provider,
            retriever=self.retriever,
            admission_controller=AdmissionController(enabled=True, max_queue_depth=25),
            retry_policy=RetryPolicy(max_retries=2, jitter=True),
            logger=self.logger
        )

        interval = duration_s / total_requests
        tasks = []
        for i in range(total_requests):
            q_data = self.eval_questions[i % len(self.eval_questions)]
            rid = f"overload_{i+1:03d}"

            async def dispatch(q, r_id, must_ref, kws, delay):
                await asyncio.sleep(delay)
                async for _ in orchestrator.execute_request(
                    query=q,
                    scenario="sustained_overload",
                    retrieval_setting="B",
                    must_refuse=must_ref,
                    expected_keywords=kws,
                    request_id=r_id
                ):
                    pass

            tasks.append(dispatch(q_data["question"], rid, q_data["must_refuse"], q_data["expected_answer_keywords"], i * interval))

        await asyncio.gather(*tasks)

    async def run_scenario_limit_halved(self, provider, total_requests: int = 25):
        """Scenario 4: Per-Minute Limit Halved (15 RPM / 7,200 TPM)."""
        print(f"\n--- Running Scenario: Limit Halved (15 RPM limit, {total_requests} requests) ---")
        if hasattr(provider, "halve_minute_limits"):
            provider.halve_minute_limits = True

        orchestrator = PipelineOrchestrator(
            provider=provider,
            retriever=self.retriever,
            admission_controller=AdmissionController(enabled=True),
            retry_policy=RetryPolicy(max_retries=2, jitter=True),
            logger=self.logger
        )

        tasks = []
        interval = 2.0
        for i in range(total_requests):
            q_data = self.eval_questions[i % len(self.eval_questions)]
            rid = f"halved_{i+1:03d}"

            async def dispatch(q, r_id, must_ref, kws, delay):
                await asyncio.sleep(delay)
                async for _ in orchestrator.execute_request(
                    query=q,
                    scenario="limit_halved",
                    retrieval_setting="B",
                    must_refuse=must_ref,
                    expected_keywords=kws,
                    request_id=r_id
                ):
                    pass

            tasks.append(dispatch(q_data["question"], rid, q_data["must_refuse"], q_data["expected_answer_keywords"], i * interval))

        await asyncio.gather(*tasks)
        if hasattr(provider, "halve_minute_limits"):
            provider.halve_minute_limits = False

    async def run_scenario_daily_budget_exhausted(self, provider, total_requests: int = 15):
        """Scenario 5: Daily Budget Exhausted (3pm quota exhaustion)."""
        print(f"\n--- Running Scenario: Daily Budget Exhausted ({total_requests} requests) ---")
        if hasattr(provider, "daily_budget_exhausted"):
            provider.daily_budget_exhausted = True

        orchestrator = PipelineOrchestrator(
            provider=provider,
            retriever=self.retriever,
            admission_controller=AdmissionController(enabled=True),
            retry_policy=RetryPolicy(max_retries=1, jitter=False),
            logger=self.logger
        )

        for i in range(total_requests):
            q_data = self.eval_questions[i % len(self.eval_questions)]
            rid = f"quota_{i+1:03d}"
            async for _ in orchestrator.execute_request(
                query=q_data["question"],
                scenario="daily_budget_exhausted",
                retrieval_setting="B",
                must_refuse=q_data["must_refuse"],
                expected_keywords=q_data["expected_answer_keywords"],
                request_id=rid
            ):
                pass

        if hasattr(provider, "daily_budget_exhausted"):
            provider.daily_budget_exhausted = False

    async def run_retrieval_experiments(self, base_provider_factory=None):
        """
        Runs the 15 evaluation questions across Setting A, Setting B, Setting C, and Setting D.
        Uses a fresh provider instance per setting to isolate retrieval quality from load backpressure.
        """
        print(f"\n--- Running Retrieval Experiments (Settings A, B, C, D across 15 questions) ---")
        settings = ["A", "B", "C", "D"]

        for setting in settings:
            provider = base_provider_factory() if base_provider_factory else StandinProvider(limits=ProviderLimits(rpm=100, tpm=100000), seed=42)
            orchestrator = PipelineOrchestrator(
                provider=provider,
                retriever=self.retriever,
                admission_controller=AdmissionController(enabled=False),
                retry_policy=RetryPolicy(max_retries=1),
                logger=self.logger
            )
            for idx, q_data in enumerate(self.eval_questions):
                rid = f"ret_{setting}_{idx+1:02d}"
                async for _ in orchestrator.execute_request(
                    query=q_data["question"],
                    scenario=f"retrieval_eval_{setting}",
                    retrieval_setting=setting,
                    must_refuse=q_data["must_refuse"],
                    expected_keywords=q_data["expected_answer_keywords"],
                    request_id=rid
                ):
                    pass
                await asyncio.sleep(0.02)

    async def run_retry_storm_experiment(self, provider):
        """
        Engineering Contribution 3: Compares Naive Retries vs Jittered Resilient Retries
        under a transient 5-second provider throttling spike.
        """
        print(f"\n--- Running Failure Amplification & Retry Storm Experiment ---")
        # 1. Naive Retry: max_retries=3, fixed 0.2s backoff, NO jitter, NO circuit breaker
        cb = CircuitBreaker(failure_threshold=4, recovery_timeout_s=5.0)
        naive_policy = RetryPolicy(max_retries=3, base_backoff_s=0.2, jitter=False, circuit_breaker=None, retry_budget_ratio=1.0)
        resilient_policy = RetryPolicy(max_retries=2, base_backoff_s=0.5, jitter=True, circuit_breaker=cb, retry_budget_ratio=0.20)

        # Run 20 requests with naive policy
        orch_naive = PipelineOrchestrator(
            provider=provider,
            retriever=self.retriever,
            admission_controller=AdmissionController(enabled=False),
            retry_policy=naive_policy,
            logger=self.logger
        )
        for i in range(12):
            q_data = self.eval_questions[i % len(self.eval_questions)]
            rid = f"naive_retry_{i+1:02d}"
            async for _ in orch_naive.execute_request(
                query=q_data["question"],
                scenario="retry_storm_naive",
                retrieval_setting="B",
                must_refuse=q_data["must_refuse"],
                expected_keywords=q_data["expected_answer_keywords"],
                request_id=rid
            ):
                pass
            await asyncio.sleep(0.05)

        # Run 20 requests with resilient policy
        orch_resilient = PipelineOrchestrator(
            provider=provider,
            retriever=self.retriever,
            admission_controller=AdmissionController(enabled=True),
            retry_policy=resilient_policy,
            logger=self.logger
        )
        for i in range(12):
            q_data = self.eval_questions[i % len(self.eval_questions)]
            rid = f"resilient_retry_{i+1:02d}"
            async for _ in orch_resilient.execute_request(
                query=q_data["question"],
                scenario="retry_storm_resilient",
                retrieval_setting="B",
                must_refuse=q_data["must_refuse"],
                expected_keywords=q_data["expected_answer_keywords"],
                request_id=rid
            ):
                pass
            await asyncio.sleep(0.05)
