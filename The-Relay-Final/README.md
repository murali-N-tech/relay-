# The Relay — Production-Grade AI Inference & RAG System

A resilient, mathematically calibrated AI inference and document-grounded question-answering pipeline designed for strict arXiv research paper libraries under real provider rate limits, traffic bursts, and concurrency constraints.

Built for **The Relay** technical selection challenge.

---

## 1. System Architecture

```text
Incoming Request
      │
      ▼
[ Stage 0: Deadline-Aware Admission Controller (DAC) ] ── (Expected Latency > SLA?) ──► HTTP 503 Shed
      │ (Admitted)
      ▼
[ Stage 1: Query Understanding & Routing ]
      │
      ▼
[ Stage 2: Tool Call: retrieve_passages ] ── (Token Pressure < 25%?) ──► Dynamic Degradation (Setting A)
      │
      ▼
[ Stage 3: Evidence Sufficiency Decision Gate ] ── (Ungrounded / Trap?) ──► Direct Refusal Branch
      │ (Sufficient)
      ▼
[ Stage 4: Inference Drafting & Stream Generation ] ◄──► [ Inference Provider (Groq / Stand-in) ]
      │                                                         ▲
      │ (Rate Limit 429 / 503 Fault?)                           │
      └──► [ Resilient Retry Policy ] ──────────────────────────┘
             • Exponential Backoff with Full Jitter
             • Circuit Breaker (Trips at 4 failures)
             • Global Retry Budget (Max 20% traffic)
      │ (OK)
      ▼
[ Stage 5: Citation Validation & Grounding Loop ] ── (Uncited Claim?) ──► Re-ground / Refusal Loop
      │
      ▼
[ Stage 6: Incremental Stream Delivery & results.csv Logging ]
```

---

## 2. The Three Core Engineering Contributions

1. **Deadline-Aware Adaptive Admission Controller (DAC):**
   * Employs Little's Law ($W_q = Q \cdot \bar{T}_s$) to compute expected queue wait plus service time against the client SLA deadline.
   * Drops doomed requests at the edge before consuming precious provider token quotas, maximizing goodput under sudden traffic bursts.

2. **Evidence-Preserving Retrieval Degradation (EPRD):**
   * Monitors real-time token bucket capacity in sliding 60-second windows.
   * When remaining tokens fall below 25%, automatically shifts from broad multi-chunk context (Setting B/C, ~1,800 tokens) to compact precision slices (Setting A, ~450 tokens), preventing 429 exhaustion while maintaining strict citation grounding.

3. **Failure Amplification & Retry Storm Quantification:**
   * Demonstrates empirically how naive retries (immediate fixed backoff without circuit breaking) transform transient 5-second provider dips into 2-minute system-wide outages.
   * Mitigates this using Full Jitter backoff, a 3-state Circuit Breaker, and an explicit global retry budget.

---

## 3. Mandatory arXiv Paper Library

This system exclusively answers questions from the exact versions specified in the brief:
1. **Attention Is All You Need** — `arXiv:1706.03762v7` (Vaswani et al.)
2. **Moshi: a speech-text foundation model for real-time dialogue** — `arXiv:2410.00037v1` (Défossez et al.)
3. **Dynamic Chunking for End-to-End Hierarchical Sequence Modeling** — `arXiv:2507.07955v2` (Medjkoune et al.)

All 3 official PDFs are stored in `papers/`, and 105 structured sections are extracted into `data/papers_corpus.json`.

---

## 4. Quickstart & Reproducibility

### A. Environment Setup
```bash
# Clone and enter workspace
git clone <repo-url>
cd The-Relay

# Optional: set Groq API key (system uses calibrated Stand-in if unset)
cp .env.example .env
export GROQ_API_KEY="your_groq_api_key_here"
```

### B. Fetch Papers & Verify Checksums
```bash
python3 scripts/fetch_papers.py
```

### C. Run Unit Test Suite (100% Pass)
```bash
python3 -m unittest discover -s tests -v
```

### D. Run Full Experimental Benchmark Battery
```bash
python3 scripts/run_experiments.py
```
This runs the 5 mandatory load scenarios (Steady, Burst, Overload, Halved Limit, Budget Exhausted), tests all 4 retrieval settings across the 15 evaluation questions, executes the retry storm experiment, and outputs verified tables.

### E. Recompute and Verify Results
```bash
python3 scripts/validate_results.py
```

### F. Interactive CLI Query
```bash
python3 -m app.main --query "What is the theoretical latency of Moshi?" --setting B
```

---

## 5. Repository File Structure

```text
├── app/
│   ├── main.py                     # CLI and HTTP server runner
│   ├── config.py                   # System config, empirical constants, limits
│   ├── pipeline/
│   │   ├── orchestrator.py         # 6-stage async state machine
│   │   ├── query_analyzer.py       # Stage 1: Intent & complexity analyzer
│   │   ├── retriever.py            # Stage 2: Tool call with adaptive degradation
│   │   ├── decision_engine.py      # Stage 3: Sufficiency gate & refusal branch
│   │   ├── answer_generator.py     # Stage 4: Citation prompt synthesizer
│   │   └── citation_validator.py   # Stage 5: Provenance & grounding validator
│   ├── providers/
│   │   ├── base.py                 # Abstract InferenceProvider & StreamChunk
│   │   ├── groq_provider.py        # Real Groq API client with SSE & header parsing
│   │   └── standin_provider.py     # Calibrated stand-in with M/M/c load queueing
│   ├── resilience/
│   │   ├── rate_limiter.py         # Leaky token bucket rate limiter
│   │   ├── admission_controller.py # Little's Law deadline-aware shedding
│   │   ├── circuit_breaker.py      # 3-state circuit breaker
│   │   └── retry_policy.py         # Full jitter & retry budget policy
│   ├── retrieval/
│   │   ├── chunking.py             # Multi-strategy chunking (A, B, C, D)
│   │   ├── indexing.py             # BM25Okapi inverted index
│   │   └── reranking.py            # Reciprocal rank fusion (RRF) & density reranking
│   ├── experiments/
│   │   └── benchmark.py            # Automated multi-scenario load runner
│   └── observability/
│       └── tracing.py              # Nanosecond execution tracing & results.csv logger
├── papers/                         # Downloaded PDFs and source archives
├── data/
│   ├── papers_corpus.json          # 105 indexed sections with paper provenance
│   └── eval_questions.json         # 15 ground-truth evaluation questions
├── results/
│   ├── results.csv                 # Raw experiment logs (exact schema)
│   └── experiment_summary.json     # Recomputed tables & metrics
├── tests/                          # 12 automated unit tests
├── scripts/
│   ├── fetch_papers.py             # Paper fetcher and SHA256 verifier
│   ├── run_experiments.py          # Master benchmark execution script
│   └── validate_results.py         # Independent CSV validator & table compiler
├── docs/
│   └── REPORT.md                   # Complete 2-page engineering report
├── requirements.txt
├── .env.example
└── README.md
```
