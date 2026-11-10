"""
scripts/run_experiments.py
Master experiment runner. Executes all required benchmark scenarios,
retrieval setting evaluations, and failure amplification tests.
Generates results/results.csv and compiles final metric summaries.
"""

import os
import sys
import asyncio
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import CONFIG, ProviderLimits
from app.providers.standin_provider import StandinProvider
from app.providers.groq_provider import GroqProvider
from app.experiments.benchmark import BenchmarkSuite
from scripts.validate_results import main as run_validation

async def run_all():
    print("=" * 80)
    print("THE RELAY: EXECUTING FULL EXPERIMENTAL BENCHMARK BATTERY")
    print("=" * 80)

    # Clean existing results.csv if present for clean benchmark run
    csv_path = CONFIG.results_csv_path
    if os.path.exists(csv_path):
        os.remove(csv_path)

    # Initialize calibrated stand-in provider
    standin = StandinProvider()
    suite = BenchmarkSuite()

    # If GROQ_API_KEY is present in environment, run a real calibration run first
    if CONFIG.groq_api_key:
        print("\n[REAL GROQ CALIBRATION] GROQ_API_KEY detected. Running modest calibration requests...")
        real_provider = GroqProvider()
        try:
            await suite.run_scenario_steady(real_provider, total_requests=5, interval_s=2.5)
            print("[REAL GROQ CALIBRATION] Completed real provider sample run.")
        except Exception as e:
            print(f"[REAL GROQ CALIBRATION] Notice: Real provider encountered {e}, proceeding with calibrated stand-in.")
    else:
        print("\n[PROVIDER NOTICE] GROQ_API_KEY not set in environment. Running benchmark on calibrated StandinProvider.")

    # 1. Steady Scenario
    await suite.run_scenario_steady(standin, total_requests=15, interval_s=1.8)

    # 2. Burst Scenario
    await suite.run_scenario_burst(standin, total_requests=35)

    # 3. Sustained Overload Scenario
    await suite.run_scenario_overload(standin, total_requests=40, duration_s=25.0)

    # 4. Limit Halved Scenario
    await suite.run_scenario_limit_halved(standin, total_requests=25)

    # 5. Daily Budget Exhausted Scenario
    await suite.run_scenario_daily_budget_exhausted(standin, total_requests=15)

    # 6. Retrieval Setting Comparisons (Settings A, B, C, D on 15 questions)
    await suite.run_retrieval_experiments(lambda: StandinProvider(limits=ProviderLimits(rpm=100, tpm=100000), seed=42))

    # 7. Retry Storm & Failure Amplification Experiment
    await suite.run_retry_storm_experiment(standin)

    print("\n" + "=" * 80)
    print("ALL EXPERIMENTAL RUNS COMPLETE. RUNNING VALIDATION AND COMPILATION...")
    print("=" * 80)
    run_validation()

def main():
    asyncio.run(run_all())

if __name__ == "__main__":
    main()
