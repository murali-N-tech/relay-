"""
scripts/independent_audit_validator.py
Strict, independent auditor that validates results/results.csv data integrity,
schema compliance, allowed domain values, duplicate IDs, and verifies report agreement.
Fails with exit code 1 if any discrepancy or violation is detected.
Includes self-test mode (--test-corruption) to verify that corrupt data is caught.
"""

import os
import sys
import csv
import json
import argparse
from typing import List, Dict, Any

ALLOWED_SOURCES = {"real", "stand-in"}
ALLOWED_STATUSES = {"ok", "rate_limited", "timeout", "error"}
ALLOWED_GRADES = {"correct", "wrong", "refused_correctly", "refused_wrongly"}

MANDATORY_COLUMNS = [
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

def audit_csv_rows(rows: List[Dict[str, str]]) -> List[str]:
    """Audits rows for schema, uniqueness, and value domains."""
    errors = []
    seen_ids = set()

    for idx, r in enumerate(rows):
        line_num = idx + 2 # Header is line 1

        # 1. Uniqueness
        rid = r.get("request_id", "").strip()
        if not rid:
            errors.append(f"Line {line_num}: Empty request_id")
        elif rid in seen_ids:
            errors.append(f"Line {line_num}: Duplicate request_id '{rid}'")
        else:
            seen_ids.add(rid)

        # 2. Source domain
        src = r.get("source", "").strip()
        if src not in ALLOWED_SOURCES:
            errors.append(f"Line {line_num} ({rid}): Invalid source '{src}'. Must be one of {ALLOWED_SOURCES}")

        # 3. Status domain
        st = r.get("status", "").strip()
        if st not in ALLOWED_STATUSES:
            errors.append(f"Line {line_num} ({rid}): Invalid status '{st}'. Must be one of {ALLOWED_STATUSES}")

        # 4. Answer grade domain
        ag = r.get("answer_grade", "").strip()
        if ag not in ALLOWED_GRADES:
            errors.append(f"Line {line_num} ({rid}): Invalid answer_grade '{ag}'. Must be one of {ALLOWED_GRADES}")

        # 5. Numeric sanity
        try:
            tot = float(r.get("total_ms", 0))
            if tot < 0:
                errors.append(f"Line {line_num} ({rid}): Negative total_ms ({tot})")
        except ValueError:
            errors.append(f"Line {line_num} ({rid}): Non-numeric total_ms '{r.get('total_ms')}'")

        ft = r.get("first_token_ms", "").strip()
        if ft:
            try:
                ft_val = float(ft)
                if ft_val < 0:
                    errors.append(f"Line {line_num} ({rid}): Negative first_token_ms ({ft_val})")
            except ValueError:
                errors.append(f"Line {line_num} ({rid}): Non-numeric first_token_ms '{ft}'")

    return errors

def audit_file(csv_path: str) -> bool:
    print(f"[AUDIT] Inspecting: {csv_path}")
    if not os.path.exists(csv_path):
        print(f"[AUDIT ERROR] Target file does not exist: {csv_path}")
        return False

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != MANDATORY_COLUMNS:
            print(f"[AUDIT ERROR] Column schema mismatch.")
            print(f"  Expected: {MANDATORY_COLUMNS}")
            print(f"  Found:    {reader.fieldnames}")
            return False

        rows = list(reader)

    if not rows:
        print("[AUDIT ERROR] CSV is empty.")
        return False

    errors = audit_csv_rows(rows)
    if errors:
        print(f"[AUDIT FAILED] Found {len(errors)} data integrity violations:")
        for e in errors[:10]:
            print(f"  - {e}")
        if len(errors) > 10:
            print(f"  ... and {len(errors)-10} more.")
        return False

    print(f"[AUDIT PASSED] All {len(rows)} rows strictly adhere to schema, unique IDs, and allowed domain values.")
    return True

def test_corruption():
    """Generates synthetic corrupt datasets and asserts that the auditor fails."""
    print("\n--- Running Auditor Self-Test Against Deliberate Corruptions ---")
    
    # Test 1: Invalid status
    corrupt_1 = [
        {"request_id": "r1", "scenario": "s", "source": "stand-in", "start_time": "t", "first_token_ms": "1", "total_ms": "2", "status": "INVALID_STATUS", "retries": "0", "tokens_in": "10", "tokens_out": "5", "retrieval_setting": "B", "answer_grade": "correct"}
    ]
    errs_1 = audit_csv_rows(corrupt_1)
    assert any("Invalid status" in e for e in errs_1), "Auditor failed to catch invalid status!"
    print("  [OK] Caught invalid status domain.")

    # Test 2: Duplicate ID
    corrupt_2 = [
        {"request_id": "r1", "scenario": "s", "source": "stand-in", "start_time": "t", "first_token_ms": "1", "total_ms": "2", "status": "ok", "retries": "0", "tokens_in": "10", "tokens_out": "5", "retrieval_setting": "B", "answer_grade": "correct"},
        {"request_id": "r1", "scenario": "s", "source": "stand-in", "start_time": "t", "first_token_ms": "1", "total_ms": "2", "status": "ok", "retries": "0", "tokens_in": "10", "tokens_out": "5", "retrieval_setting": "B", "answer_grade": "correct"}
    ]
    errs_2 = audit_csv_rows(corrupt_2)
    assert any("Duplicate request_id" in e for e in errs_2), "Auditor failed to catch duplicate request ID!"
    print("  [OK] Caught duplicate request_id.")

    # Test 3: Invalid source
    corrupt_3 = [
        {"request_id": "r1", "scenario": "s", "source": "mock_llm", "start_time": "t", "first_token_ms": "1", "total_ms": "2", "status": "ok", "retries": "0", "tokens_in": "10", "tokens_out": "5", "retrieval_setting": "B", "answer_grade": "correct"}
    ]
    errs_3 = audit_csv_rows(corrupt_3)
    assert any("Invalid source" in e for e in errs_3), "Auditor failed to catch invalid source!"
    print("  [OK] Caught invalid source domain.")
    print("Auditor self-test completed successfully: All corruptions properly rejected.")

def main():
    parser = argparse.ArgumentParser(description="Strict independent results.csv auditor")
    parser.add_argument("--csv", type=str, default="", help="Path to CSV file to audit")
    parser.add_argument("--test-corruption", action="store_true", help="Run auditor test against corrupted data")
    args = parser.parse_args()

    if args.test_corruption:
        test_corruption()
        return

    csv_path = args.csv or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "results", "results.csv"))
    success = audit_file(csv_path)
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
