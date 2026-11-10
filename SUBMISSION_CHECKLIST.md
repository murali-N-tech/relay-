# The Relay — Technical Submission Checklist

| Item | Requirement | Verification Method | Status |
|---|---|---|---|
| **1. Mandatory Papers** | Exactly 3 arXiv papers: 1706.03762v7, 2410.00037v1, 2507.07955v2 | `python3 scripts/fetch_papers.py --verify-only` (SHA-256 match) | **VERIFIED** |
| **2. Provider Integration** | Real Groq provider + calibrated stand-in provider with M/M/c queuing | Unit tests in `tests/test_standin.py` and `scripts/run_calibration.py` | **VERIFIED** |
| **3. Multi-Stage Pipeline** | 6 async stages with genuine tool call `retrieve_passages` and branching | Unit tests in `tests/test_pipeline.py` | **VERIFIED** |
| **4. Raw Dataset** | `results/results.csv` with all 12 mandatory columns and 200+ runs | `python3 scripts/independent_audit_validator.py` (214 rows pass) | **VERIFIED** |
| **5. Audit Validator** | Independent validation script catching schema and corruptions | `python3 scripts/independent_audit_validator.py --test-corruption` | **VERIFIED** |
| **6. Verified Metrics** | Tables 1, 2a, 2b, 3 computed strictly from CSV | `python3 scripts/validate_results.py` | **VERIFIED** |
| **7. Engineering Report** | Exactly 12 sequential numbered sections adhering to 2-page limit | `docs/REPORT.md` | **VERIFIED** |
| **8. Assistant History** | Actual conversation prompts and engineering trade-offs | `assistant_history/actual_prompts.md` | **VERIFIED** |
| **9. Unit Tests** | 100% test pass rate across retrieval, resilience, pipeline, stand-in | `python3 -m unittest discover -s tests -v` (12/12 pass) | **VERIFIED** |
| **10. Web Dashboard** | Full-stack interactive interface running on port 3000 | `compile_applet` & `lint_applet` clean | **VERIFIED** |
| **11. Clean Workspace** | No secrets (`GROQ_API_KEY`), no `.env` credentials, no `__pycache__` | `find . -name "*.pyc" -o -name "__pycache__"` clean | **VERIFIED** |
