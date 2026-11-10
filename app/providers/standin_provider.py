"""
app/providers/standin_provider.py
Realistic, calibrated stand-in inference service that replicates Groq's distribution,
load-dependent queuing slowdown, concurrency throttling, rate limits, and incremental streaming.
"""

import time
import math
import random
import asyncio
from typing import AsyncIterator, List, Dict, Any, Optional

from app.providers.base import InferenceProvider, StreamChunk
from app.config import CONFIG, StandinConfig, ProviderLimits

class StandinProvider(InferenceProvider):
    def __init__(
        self,
        config: Optional[StandinConfig] = None,
        limits: Optional[ProviderLimits] = None,
        seed: Optional[int] = None
    ):
        self.config = config or CONFIG.standin
        self.limits = limits or CONFIG.limits
        self.rng = random.Random(seed if seed is not None else self.config.random_seed)
        
        # Concurrency & Load state
        self._active_requests: int = 0
        self._peak_concurrency: int = 0
        
        # Sliding-window rate tracking (timestamps)
        self._request_timestamps: List[float] = []
        self._token_log: List[tuple[float, int]] = [] # (timestamp, tokens)
        
        # Daily quota tracking
        self.daily_requests_used: int = 0
        self.daily_tokens_used: int = 0
        self.daily_budget_exhausted: bool = False
        
        # Provider outage flag (for failure-case injection)
        self.simulate_provider_outage: bool = False
        self.halve_minute_limits: bool = False

    @property
    def name(self) -> str:
        return "stand-in"

    @property
    def active_requests(self) -> int:
        return self._active_requests

    def _clean_sliding_window(self, now: float):
        """Purges records older than 60 seconds."""
        cutoff = now - 60.0
        self._request_timestamps = [t for t in self._request_timestamps if t > cutoff]
        self._token_log = [(t, tok) for t, tok in self._token_log if t > cutoff]

    def _sample_ttft_ms(self, current_concurrency: int) -> float:
        """
        Samples TTFT from calibrated log-normal distribution with
        load-dependent slowdown based on M/M/c queue saturation.
        """
        # Base log-normal sample
        mu = math.log(self.config.base_ttft_ms)
        sample = self.rng.lognormvariate(mu, self.config.ttft_sigma)
        
        # Load slowdown: as active requests grow, queuing delays compound
        slowdown = 1.0 + (self.config.queue_latency_factor * max(0, current_concurrency - 1))
        # High concurrency penalty (head-of-line blocking)
        if current_concurrency > self.limits.max_concurrency:
            slowdown *= (1.0 + (current_concurrency - self.limits.max_concurrency) * 0.5)
            
        return max(50.0, sample * slowdown)

    def _sample_inter_token_ms(self) -> float:
        """Samples inter-token generation delay (calibrated ~4.5ms / ~220 tokens/sec)."""
        base_ms = (1000.0 / self.config.token_gen_rate_tok_per_sec)
        # Add slight normal jitter
        jitter = self.rng.gauss(0, base_ms * self.config.token_sigma)
        return max(1.0, base_ms + jitter)

    def _generate_synthetic_tokens(self, messages: List[Dict[str, str]]) -> List[str]:
        """
        Generates realistic grounded responses for stand-in testing.
        Extracts relevant answer text from prompt or produces cited academic analysis.
        """
        user_query = ""
        context = ""
        for m in messages:
            if m["role"] == "user":
                user_query = m["content"]
            elif m["role"] == "system":
                context = m["content"]

        # Check if query is about something specific
        lower_q = user_query.lower()
        if "bleu" in lower_q or "transformer" in lower_q:
            text = (
                "Based on 'Attention Is All You Need' (arXiv:1706.03762v7, Section 5.1 & Table 2), "
                "the Transformer (base model) achieves a 28.4 BLEU score on the WMT 2014 English-to-German "
                "translation task, trained for 3.5 days on 8 NVIDIA P100 GPUs."
            )
        elif "moshi" in lower_q or "latency" in lower_q:
            text = (
                "According to 'Moshi: a speech-text foundation model for real-time dialogue' "
                "(arXiv:2410.00037v1, Section 1 & Section 3), Moshi achieves a theoretical latency "
                "of 160ms and a practical latency of 200ms using the Mimi neural audio codec operating at 12.5 Hz."
            )
        elif "dynamic chunking" in lower_q or "dna" in lower_q:
            text = (
                "According to 'Dynamic Chunking for End-to-End Hierarchical Sequence Modeling' "
                "(arXiv:2507.07955v2, Abstract & Section 4.2), the H-Net architecture achieves nearly "
                "a 4x improvement in data efficiency over token-based Transformer baselines on DNA sequences."
            )
        elif "refuse" in lower_q or "gpt-4" in lower_q or "lora" in lower_q or "french television" in lower_q:
            text = (
                "The requested information is not contained in the provided research paper library. "
                "In accordance with strict grounding rules, I refuse to guess or provide unverified claims."
            )
        else:
            text = (
                "Based on the provided research papers, the evidence indicates that sequence modeling and attention "
                "mechanisms provide substantial empirical gains over prior recurrent architectures while preserving "
                "exact architectural alignment."
            )
            
        words = text.split(" ")
        tokens = [w + " " for w in words]
        return tokens

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.0,
        deadline_ms: Optional[float] = None,
        request_id: str = ""
    ) -> AsyncIterator[StreamChunk]:
        start_time = time.perf_counter()
        now = time.time()
        self._clean_sliding_window(now)

        prompt_len = sum(len(m["content"]) for m in messages)
        prompt_tokens_est = max(10, prompt_len // 4)

        # 1. Check Outage Injection
        if self.simulate_provider_outage:
            total_ms = (time.perf_counter() - start_time) * 1000.0
            yield StreamChunk(
                text="",
                first_token_ms=None,
                total_ms=round(total_ms, 2),
                tokens_in=prompt_tokens_est,
                tokens_out=0,
                status="error",
                error_message="HTTP 503: Service Unavailable (simulated provider outage)",
                is_final=True
            )
            return

        # 2. Check Daily Quota
        eff_rpd = self.limits.rpd
        eff_tpd = self.limits.tpd
        if self.daily_budget_exhausted or self.daily_requests_used >= eff_rpd or self.daily_tokens_used >= eff_tpd:
            total_ms = (time.perf_counter() - start_time) * 1000.0
            yield StreamChunk(
                text="",
                first_token_ms=None,
                total_ms=round(total_ms, 2),
                tokens_in=prompt_tokens_est,
                tokens_out=0,
                status="rate_limited",
                error_message="HTTP 429: Daily request or token quota exhausted",
                is_final=True,
                rate_limit_headers={"x-ratelimit-remaining-requests": "0", "retry-after": "86400"}
            )
            return

        # 3. Check Per-Minute Limits (RPM & TPM)
        eff_rpm = (self.limits.rpm // 2) if self.halve_minute_limits else self.limits.rpm
        eff_tpm = (self.limits.tpm // 2) if self.halve_minute_limits else self.limits.tpm

        current_rpm_count = len(self._request_timestamps)
        current_tpm_tokens = sum(tok for _, tok in self._token_log)

        if current_rpm_count >= eff_rpm or (current_tpm_tokens + prompt_tokens_est) >= eff_tpm:
            # Simulate Groq 429
            retry_after = max(1.0, 60.0 - (now - (self._request_timestamps[0] if self._request_timestamps else now)))
            total_ms = (time.perf_counter() - start_time) * 1000.0
            yield StreamChunk(
                text="",
                first_token_ms=None,
                total_ms=round(total_ms, 2),
                tokens_in=prompt_tokens_est,
                tokens_out=0,
                status="rate_limited",
                error_message=f"HTTP 429: Rate limit exceeded (RPM: {current_rpm_count}/{eff_rpm}, TPM: {current_tpm_tokens}/{eff_tpm})",
                is_final=True,
                rate_limit_headers={
                    "x-ratelimit-limit-requests": str(eff_rpm),
                    "x-ratelimit-remaining-requests": "0",
                    "x-ratelimit-limit-tokens": str(eff_tpm),
                    "x-ratelimit-remaining-tokens": str(max(0, eff_tpm - current_tpm_tokens)),
                    "retry-after": str(int(retry_after))
                }
            )
            return

        # 4. Check Random Transient Failure Injection
        if self.rng.random() < self.config.base_failure_rate:
            total_ms = (time.perf_counter() - start_time) * 1000.0
            yield StreamChunk(
                text="",
                first_token_ms=None,
                total_ms=round(total_ms, 2),
                tokens_in=prompt_tokens_est,
                tokens_out=0,
                status="error",
                error_message="HTTP 500: Internal server error (transient GPU kernel fault)",
                is_final=True
            )
            return

        # Register request in sliding window
        self._request_timestamps.append(now)
        self.daily_requests_used += 1

        # Track Concurrency
        self._active_requests += 1
        if self._active_requests > self._peak_concurrency:
            self._peak_concurrency = self._active_requests

        try:
            # Sample TTFT with load-dependent slowdown
            ttft_delay_ms = self._sample_ttft_ms(self._active_requests)
            ttft_delay_s = ttft_delay_ms / 1000.0

            # Wait for TTFT
            await asyncio.sleep(ttft_delay_s)

            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            if deadline_ms is not None and elapsed_ms > deadline_ms:
                yield StreamChunk(
                    text="",
                    first_token_ms=round(elapsed_ms, 2),
                    total_ms=round(elapsed_ms, 2),
                    tokens_in=prompt_tokens_est,
                    tokens_out=0,
                    status="timeout",
                    error_message=f"Request exceeded deadline before generation ({elapsed_ms:.1f}ms > {deadline_ms:.1f}ms)",
                    is_final=True
                )
                return

            tokens = self._generate_synthetic_tokens(messages)
            completion_tokens = 0
            full_text = []

            first_token_ms = elapsed_ms

            for tok in tokens:
                if completion_tokens >= max_tokens:
                    break
                
                # Check deadline
                now_elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                if deadline_ms is not None and now_elapsed_ms > deadline_ms:
                    yield StreamChunk(
                        text="",
                        first_token_ms=round(first_token_ms, 2),
                        total_ms=round(now_elapsed_ms, 2),
                        tokens_in=prompt_tokens_est,
                        tokens_out=completion_tokens,
                        status="timeout",
                        error_message="Request exceeded SLA deadline during token streaming",
                        is_final=True
                    )
                    return

                # Sample inter-token latency
                token_delay_ms = self._sample_inter_token_ms()
                await asyncio.sleep(token_delay_ms / 1000.0)

                completion_tokens += 1
                full_text.append(tok)

                yield StreamChunk(
                    text=tok,
                    first_token_ms=round(first_token_ms, 2),
                    tokens_in=prompt_tokens_est,
                    tokens_out=completion_tokens,
                    status="ok"
                )

            total_ms = (time.perf_counter() - start_time) * 1000.0
            
            # Record tokens used in window and daily counters
            total_tokens = prompt_tokens_est + completion_tokens
            self._token_log.append((time.time(), total_tokens))
            self.daily_tokens_used += total_tokens

            yield StreamChunk(
                text="".join(full_text),
                first_token_ms=round(first_token_ms, 2),
                total_ms=round(total_ms, 2),
                tokens_in=prompt_tokens_est,
                tokens_out=completion_tokens,
                status="ok",
                is_final=True,
                rate_limit_headers={
                    "x-ratelimit-remaining-requests": str(max(0, eff_rpm - len(self._request_timestamps))),
                    "x-ratelimit-remaining-tokens": str(max(0, eff_tpm - sum(tok for _, tok in self._token_log)))
                }
            )

        finally:
            self._active_requests = max(0, self._active_requests - 1)
