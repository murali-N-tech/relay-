"""
app/observability/tracing.py
Request-level execution tracing and strict results.csv logging.
Guarantees schema compliance and preserves raw experimental data.
"""

import os
import csv
import time
import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from app.config import CONFIG

CSV_HEADER = [
    "request_id",
    "scenario",
    "source",
    "start_time",
    "first_token_ms",
    "total_ms",
    "status",
    "retries",
    "tokens_in",
    "tokens_out",
    "retrieval_setting",
    "answer_grade"
]

@dataclass
class StageSpan:
    stage_name: str
    start_time: float
    end_time: float = 0.0

    @property
    def duration_ms(self) -> float:
        if self.end_time == 0.0:
            return 0.0
        return (self.end_time - self.start_time) * 1000.0

@dataclass
class ExecutionTrace:
    request_id: str
    scenario: str
    source: str # "real" or "stand-in"
    retrieval_setting: str
    start_wall_time: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat() + "Z")
    
    first_token_ms: Optional[float] = None
    total_ms: float = 0.0
    status: str = "ok" # "ok", "rate_limited", "timeout", "error"
    retries: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    answer_grade: str = "correct" # "correct", "wrong", "refused_correctly", "refused_wrongly"

    # Deep breakdown spans for Heading 4 ("Where the time goes")
    queue_wait_ms: float = 0.0
    query_analysis_ms: float = 0.0
    retrieval_ms: float = 0.0
    decision_ms: float = 0.0
    inference_ms: float = 0.0
    retry_delay_ms: float = 0.0
    validation_ms: float = 0.0

    error_message: Optional[str] = None
    generated_text: str = ""

class ResultsLogger:
    def __init__(self, csv_path: Optional[str] = None):
        self.csv_path = csv_path or CONFIG.results_csv_path
        self._ensure_header()

    def _ensure_header(self):
        os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
        if not os.path.exists(self.csv_path) or os.path.getsize(self.csv_path) == 0:
            with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(CSV_HEADER)

    def log_trace(self, trace: ExecutionTrace):
        """Appends one raw record adhering strictly to the assignment CSV schema."""
        row = [
            trace.request_id,
            trace.scenario,
            trace.source,
            trace.start_wall_time,
            f"{trace.first_token_ms:.1f}" if trace.first_token_ms is not None else "",
            f"{trace.total_ms:.1f}",
            trace.status,
            str(trace.retries),
            str(trace.tokens_in),
            str(trace.tokens_out),
            trace.retrieval_setting,
            trace.answer_grade
        ]
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(row)

# Global results logger
LOGGER = ResultsLogger()
