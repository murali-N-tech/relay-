# AI Assistant Conversation & Prompt History
**Project:** The Relay — ML Engineering Selection Assignment (Vaani Research)  
**Target:** 3 arXiv Papers Inference Pipeline with Groq & Stand-in Under Heavy Load

---

## 1. Master Architecture Formulation Prompt

```text
# MASTER PROMPT — THE RELAY
## Build a Selection-Winning, Production-Grade AI Inference System

You are my Principal AI Systems Architect, Senior Backend Engineer, Distributed Systems Specialist, Performance Engineer, Research Analyst, and Technical Selection Mentor.

I am completing a technical selection assignment called The Relay for Vaani Research. Your objective is to help me build an exceptional, fully working, experimentally validated submission that demonstrates real engineering ability rather than merely satisfying minimum requirements.

The system must:
- Answer engineering questions using exactly three specified arXiv papers:
  1. Attention Is All You Need — arXiv:1706.03762v7
  2. Moshi: A Speech-Text Foundation Model for Real-Time Dialogue — arXiv:2410.00037v1
  3. Dynamic Chunking for End-to-End Hierarchical Sequence Modeling — arXiv:2507.07955v2
- Use a real hosted model through Groq's free tier (llama-3.1-8b-instant).
- Implement a controllable stand-in model service.
- Handle bursts, concurrency, provider limits, timeouts and failures.
- Measure time to first token and total response time.
- Experiment with different retrieval configurations.
- Preserve raw experimental results in results.csv.
- Produce a maximum two-page engineering report.
- Include actual AI-assistant conversation history or prompts.
```

### Key Decisions Made:
- Identified 5 core engineering differentiators: Adaptive Admission Control via Little's Law, Dynamic Context Degradation under Token Pressure, Calibrated Stand-in with M/M/c queuing dynamics, Resilient Retry Policy with Full Jitter and Circuit Breaker, and Failure Amplification Quantification.
- Implemented pure Python 3.10 standard library text extraction and BM25Okapi index to eliminate multi-gigabyte PyTorch/CUDA container dependencies.

---

## 2. Empirical Stand-in & Queuing Dynamics Prompt

```text
Build a high-fidelity calibrated stand-in provider that accurately mirrors Groq LPU latency characteristics:
1. Log-normal TTFT distribution matching observed llama-3.1-8b-instant network and prefill times.
2. Contention-based M/M/c queuing penalty that slows down concurrent requests as active connections rise.
3. Realistic token streaming generator emitting tokens at ~220 tokens/sec.
4. Exact sliding 60-second request and token tracking returning authentic HTTP 429 payloads with retry-after headers.
5. Strict synthesis rules: Answer answerable questions with exact paper citations if evidence is in context; refuse explicitly if evidence is missing or if the question is an adversarial trap.
```

### Key Decisions Made:
- Avoided crude `asyncio.sleep()` mocks; implemented stateful concurrency counters and sliding timestamp logs.
- Engineered precise lexical verification in synthetic response generation to eliminate false answers on ungrounded inquiries.

---

## 3. Data Integrity & Independent Validation Prompt

```text
Write a strict, independent auditor (scripts/independent_audit_validator.py) that reads only results/results.csv:
1. Verify exact 12-column schema: request_id, scenario, source, start_time, first_token_ms, total_ms, status, retries, tokens_in, tokens_out, retrieval_setting, answer_grade.
2. Validate value domains (source in {'real', 'stand-in'}, status in {'ok', 'rate_limited', 'timeout', 'error'}, answer_grade in {'correct', 'wrong', 'refused_correctly', 'refused_wrongly'}).
3. Enforce request_id uniqueness across all recorded rows.
4. Verify non-negative latencies and token counts.
5. Provide a --test-corruption mode that synthetically injects invalid rows to prove the auditor fails on bad data.
```

### Key Decisions Made:
- Prevented circular validation: The validator parses raw CSV directly without importing benchmark state or pre-computed summaries.
- Proved auditor rigor with automated self-tests passing across all failure modes.

---

## 4. Retrieval Root-Cause Fix & Grading Calibration Prompt

```text
Audit the retrieval evaluation pipeline. In earlier iterations, Settings C and D had 0% correct answers.
Investigate:
1. Did rerank_passages return RRF scores (~0.03) instead of BM25 scores, causing the DecisionEngine threshold (2.5) to reject every chunk?
2. Did StandinProvider look across the entire prompt (which contained all retrieved chunks) instead of the user's isolated question?
3. Did the retrieval experiment saturate the 30 RPM limit by running 60 requests sequentially without a fresh provider?
Fix all three root causes and re-run the benchmark battery.
```

### Key Decisions Made:
- Fixed `rerank_passages` to re-order chunks by RRF rank while preserving true BM25 relevance scores for downstream sufficiency gating.
- Isolated user question parsing in `StandinProvider` to evaluate true context-evidence grounding.
- Allocated fresh dedicated provider instances per retrieval setting to isolate retrieval quality from load backpressure.
