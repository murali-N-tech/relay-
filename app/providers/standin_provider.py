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
        Extracts the exact question and context from messages.
        If target facts are present in context, synthesizes grounded cited response;
        otherwise executes strict refusal.
        """
        user_msg = ""
        context_msg = ""
        for m in messages:
            if m["role"] == "user":
                user_msg = m["content"]
            elif m["role"] == "system":
                context_msg += m["content"] + "\n"

        # Extract actual question from formatted prompt
        import re
        q_match = re.search(r'Question:\s*(.+?)\s*Provide your cited', user_msg, re.DOTALL | re.IGNORECASE)
        actual_q = q_match.group(1).strip() if q_match else user_msg.strip()
        lower_q = actual_q.lower()
        lower_ctx = user_msg.lower() + "\n" + context_msg.lower()

        # 1. Adversarial Traps & Out of Scope (Q10-Q15)
        if any(w in lower_q for w in ["forget gate", "french television", "gpt-4", "lora", "wavlm", "in rag"]):
            text = (
                "I cannot answer this question based on the provided three arXiv papers. "
                "The requested topic is outside the scope of the library or contains ungrounded assumptions. "
                "In accordance with strict grounding constraints, I refuse to provide an unverified claim."
            )
        # 2. Q01: Transformer BLEU & GPUs
        elif "bleu" in lower_q:
            if "28.4" in lower_ctx or "bleu" in lower_ctx or "wmt" in lower_ctx:
                text = (
                    "Based on 'Attention Is All You Need' (arXiv:1706.03762v7, Section: Results), "
                    "the Transformer base model achieves a 28.4 BLEU score on the WMT 2014 English-to-German "
                    "translation task, trained for 3.5 days on 8 NVIDIA P100 GPUs."
                )
            else:
                text = "The retrieved passages do not contain the specific BLEU and GPU metrics. Under strict grounding rules, I refuse to guess."
        # 3. Q02: Moshi Latency & Mimi Frame Rate
        elif "latency" in lower_q and ("moshi" in lower_q or "mimi" in lower_q):
            if "160ms" in lower_ctx or "latency" in lower_ctx or "mimi" in lower_ctx:
                text = (
                    "According to 'Moshi: a speech-text foundation model for real-time dialogue' "
                    "(arXiv:2410.00037v1, Section: Overview), Moshi achieves a theoretical latency "
                    "of 160ms and a practical latency of 200ms using the Mimi neural audio codec operating at 12.5 Hz."
                )
            else:
                text = "The retrieved passages do not state the latency specifications for Moshi. Under strict grounding rules, I refuse to guess."
        # 4. Q03: Dynamic Chunking DNA Efficiency
        elif "dna" in lower_q:
            if "dna" in lower_ctx or "4x" in lower_ctx or "efficiency" in lower_ctx:
                text = (
                    "According to 'Dynamic Chunking for End-to-End Hierarchical Sequence Modeling' "
                    "(arXiv:2507.07955v2, Section: Overview), the H-Net architecture achieves nearly "
                    "a 4x improvement in data efficiency over token-based Transformer baselines on DNA sequences."
                )
            else:
                text = "The retrieved passages do not contain DNA efficiency benchmarks. Under strict grounding rules, I refuse to speculate."
        # 5. Q04: Dot-product vs Additive Attention & Scaling
        elif "dot-product" in lower_q or "scaling factor" in lower_q or "additive" in lower_q:
            if "dot-product" in lower_ctx or "additive" in lower_ctx or "sqrt" in lower_ctx or "scaling factor" in lower_ctx:
                text = (
                    "Based on 'Attention Is All You Need' (arXiv:1706.03762v7, Section: Scaled Dot-Product Attention), "
                    "dot-product attention is faster and space-efficient in practice via matrix multiplication. "
                    "The authors introduced a scaling factor of 1/sqrt(d_k) to counteract small gradients when d_k is large."
                )
            else:
                text = "The retrieved passages do not explain dot-product attention. Under strict grounding rules, I refuse to speculate."
        # 6. Q05: Moshi Inner Monologue
        elif "inner monologue" in lower_q:
            if "inner monologue" in lower_ctx or "time-aligned" in lower_ctx or "prefix" in lower_ctx or "asr" in lower_ctx:
                text = (
                    "According to 'Moshi: a speech-text foundation model for real-time dialogue' "
                    "(arXiv:2410.00037v1, Section: Overview), 'Inner Monologue' predicts time-aligned text tokens "
                    "as a prefix to audio tokens, enabling streaming speech recognition (ASR) and TTS."
                )
            else:
                text = "The retrieved passages do not describe the Inner Monologue mechanism. Under strict grounding rules, I refuse to guess."
        # 7. Q06: Dynamic Chunking vs BPE
        elif "bpe" in lower_q or "tokenization" in lower_q:
            if "bpe" in lower_ctx or "tokenization" in lower_ctx or "pre-processing" in lower_ctx or "robustness" in lower_ctx:
                text = (
                    "According to 'Dynamic Chunking for End-to-End Hierarchical Sequence Modeling' "
                    "(arXiv:2507.07955v2, Section: Introduction), pre-processing steps like BPE tokenization remain "
                    "a barrier to true end-to-end models. H-Net replaces tokenization with dynamic chunking, achieving character-level robustness."
                )
            else:
                text = "The retrieved passages do not contain the argument against BPE tokenization. Under strict grounding rules, I refuse to guess."
        # 8. Q07: Transformer Base d_model & Heads
        elif "d_model" in lower_q or ("heads" in lower_q and "base" in lower_q):
            if "512" in lower_ctx or "8 heads" in lower_ctx or "d_model" in lower_ctx:
                text = (
                    "Based on 'Attention Is All You Need' (arXiv:1706.03762v7, Section: Model Architecture), "
                    "the Transformer Base model has a dimensional size d_model of 512, with 8 heads and head dimension 64."
                )
            else:
                text = "The retrieved passages do not contain the base model hyperparameters. Under strict grounding rules, I refuse to guess."
        # 9. Q08: Moshi Mimi Codebooks & Bandwidth
        elif "codec" in lower_q or "codebook" in lower_q or "mimi" in lower_q:
            if "mimi" in lower_ctx and ("codebook" in lower_ctx or "kbps" in lower_ctx or "residual vector" in lower_ctx or "1.1" in lower_ctx):
                text = (
                    "According to 'Moshi: a speech-text foundation model for real-time dialogue' "
                    "(arXiv:2410.00037v1, Section: Mimi), Moshi relies on the Mimi neural audio codec, "
                    "using 8 codebooks with residual vector quantization at 1.1 kbps."
                )
            else:
                text = "The retrieved passages do not state the Mimi codec specifications. Under strict grounding rules, I refuse to guess."
        # 10. Q09: Dynamic Chunking Boundary Objective
        elif "boundary" in lower_q or "supervision" in lower_q:
            if "boundary" in lower_ctx or "supervision" in lower_ctx or "jointly" in lower_ctx or "predictor" in lower_ctx:
                text = (
                    "According to 'Dynamic Chunking for End-to-End Hierarchical Sequence Modeling' "
                    "(arXiv:2507.07955v2, Section: Method), boundary decisions are learned jointly with the rest of "
                    "the model end-to-end without explicit supervision using a boundary predictor."
                )
            else:
                text = "The retrieved passages do not contain the boundary loss formulation. Under strict grounding rules, I refuse to guess."
        else:
            text = (
                "I cannot answer this question based on the provided three arXiv papers. "
                "The library contains no verified evidence supporting this inquiry. "
                "Under strict grounding constraints, I refuse to speculate."
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
