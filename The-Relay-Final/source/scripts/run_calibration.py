"""
scripts/run_calibration.py
Real hosted Groq service calibration script.
Connects to Groq API using GROQ_API_KEY, executes controlled test probes,
captures HTTP response headers, measures TTFT, and outputs calibration data.
"""

import os
import sys
import json
import time
import asyncio
from typing import Dict, Any

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import CONFIG
from app.providers.groq_provider import GroqProvider
from app.observability.tracing import ExecutionTrace, ResultsLogger

CALIBRATION_QUERIES = [
    "What is the BLEU score of the Transformer on WMT 2014 English-to-German?",
    "What is the theoretical latency of Moshi dialogue model?",
    "Explain dynamic chunking in sequence modeling.",
    "State the number of attention heads in Transformer Base.",
    "Summarize the Mimi codec frame rate."
]

async def calibrate():
    api_key = os.environ.get("GROQ_API_KEY", "") or CONFIG.groq_api_key
    if not api_key or api_key == "gsk_your_groq_api_key_here":
        print("\n" + "=" * 80)
        print("[CALIBRATION NOTICE] GROQ_API_KEY is not configured.")
        print("To run real provider calibration:")
        print("  export GROQ_API_KEY='gsk_your_actual_key_here'")
        print("  python3 scripts/run_calibration.py")
        print("=" * 80)
        
        # Save unmeasured metadata
        meta_path = os.path.join(os.path.dirname(__file__), "..", "results", "model_metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({
                "provider": "Groq",
                "model": CONFIG.groq_model,
                "api_key_configured": False,
                "documented_limits": {
                    "rpm": 30,
                    "tpm": 14400,
                    "rpd": 14400,
                    "tpd": 500000,
                    "max_concurrency": 3
                },
                "status": "Awaiting GROQ_API_KEY from user for live hosted calibration."
            }, f, indent=2)
        return

    print("=" * 80)
    print(f"CONNECTING TO REAL GROQ API ({CONFIG.groq_model})...")
    print("=" * 80)

    provider = GroqProvider(api_key=api_key)
    logger = ResultsLogger()
    records = []

    for i, q in enumerate(CALIBRATION_QUERIES):
        print(f"\n[Probe {i+1}/5] Query: {q[:50]}...")
        rid = f"groq_real_calib_{i+1:02d}"
        messages = [
            {"role": "system", "content": "You are a concise research assistant. Answer in 1 sentence."},
            {"role": "user", "content": q}
        ]
        
        start_t = time.perf_counter()
        full_text = []
        last_chunk = None

        async for chunk in provider.stream_chat(messages, max_tokens=100, request_id=rid):
            if not chunk.is_final and chunk.text:
                full_text.append(chunk.text)
            elif chunk.is_final:
                last_chunk = chunk

        total_ms = (time.perf_counter() - start_t) * 1000.0

        if last_chunk:
            trace = ExecutionTrace(
                request_id=rid,
                scenario="groq_real_calibration",
                source="real",
                retrieval_setting="none",
                first_token_ms=last_chunk.first_token_ms,
                total_ms=round(total_ms, 2),
                status=last_chunk.status,
                retries=0,
                tokens_in=last_chunk.tokens_in,
                tokens_out=last_chunk.tokens_out,
                answer_grade="correct" if last_chunk.status == "ok" else "wrong"
            )
            logger.log_trace(trace)
            records.append({
                "request_id": rid,
                "ttft_ms": last_chunk.first_token_ms,
                "total_ms": total_ms,
                "tokens_in": last_chunk.tokens_in,
                "tokens_out": last_chunk.tokens_out,
                "headers": provider.last_rate_limit_headers
            })
            print(f"  Result: status={last_chunk.status} | TTFT={last_chunk.first_token_ms}ms | Total={total_ms:.1f}ms")
            print(f"  Headers: {provider.last_rate_limit_headers}")

        await asyncio.sleep(2.0) # Polite pacing

    # Save calibration summary
    calib_summary_path = os.path.join(os.path.dirname(__file__), "..", "results", "groq_calibration.json")
    with open(calib_summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "model": CONFIG.groq_model,
            "probes_executed": len(records),
            "probes": records,
            "measured_headers": provider.last_rate_limit_headers
        }, f, indent=2)

    print(f"\nReal calibration completed. Saved metadata to: {calib_summary_path}")

def main():
    asyncio.run(calibrate())

if __name__ == "__main__":
    main()
