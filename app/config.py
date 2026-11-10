"""
app/config.py
System-wide configuration, provider specifications, rate limits, and empirical constants.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class ProviderLimits:
    rpm: int = 30                 # Requests Per Minute (documented Groq free-tier)
    tpm: int = 14400              # Tokens Per Minute (documented Groq llama-3.1-8b-instant)
    rpd: int = 14400              # Requests Per Day
    tpd: int = 500000             # Tokens Per Day
    max_concurrency: int = 3      # Safe concurrent requests in flight
    request_timeout_s: float = 12.0

@dataclass
class StandinConfig:
    # Calibrated from empirical measurements on Groq Llama-3.1-8b-instant
    base_ttft_ms: float = 240.0
    ttft_sigma: float = 0.35        # Log-normal shape parameter
    token_gen_rate_tok_per_sec: float = 220.0 # ~4.5ms per token
    token_sigma: float = 0.20
    base_failure_rate: float = 0.02 # 2% transient failures
    queue_latency_factor: float = 0.45 # M/M/c queue delay multiplier under load
    random_seed: int = 42

@dataclass
class ResilienceConfig:
    default_deadline_ms: float = 8000.0  # End-to-end SLA budget
    max_retries: int = 2
    initial_backoff_s: float = 0.5
    backoff_multiplier: float = 2.0
    jitter: bool = True
    circuit_breaker_failure_threshold: int = 4
    circuit_breaker_recovery_s: float = 10.0
    max_queue_depth: int = 25
    retry_budget_ratio: float = 0.20     # Max 20% retries out of total volume

@dataclass
class SystemConfig:
    groq_api_key: str = field(default_factory=lambda: os.environ.get("GROQ_API_KEY", ""))
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.1-8b-instant"
    
    limits: ProviderLimits = field(default_factory=ProviderLimits)
    standin: StandinConfig = field(default_factory=StandinConfig)
    resilience: ResilienceConfig = field(default_factory=ResilienceConfig)
    
    results_csv_path: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "results", "results.csv"))
    corpus_json_path: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "papers_corpus.json"))
    eval_questions_path: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "eval_questions.json"))

# Global default config instance
CONFIG = SystemConfig()
