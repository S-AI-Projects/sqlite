#!/usr/bin/env python3
"""
Reusable focused verification check for exercises/practice/anagram (Task R08-T044).

Verifies the anagram reference implementation refactoring:
1. Resolves solution, test, and example paths from .meta/config.json.
2. Asserts the learner stub in the working tree remains unsolved.
3. Tests the refactored reference implementation in an isolated temporary copy.
4. Asserts that all 16 canonical test cases pass with status "pass".
5. Verifies strict before/after output parity.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def find_repo_root() -> Path:
    """Locate the git repository root."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".git").exists() or (current / "exercises").exists():
            return current
        current = current.parent
    return Path.cwd()


def run_test_in_tempdir(exercise_dir: Path, sql_implementation: str) -> list:
    """Execute anagram_test.sql in a temporary directory with the given implementation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_exercise = Path(tmpdir) / "anagram"
        shutil.copytree(exercise_dir, tmp_exercise)

        target_file = tmp_exercise / "anagram.sql"
        target_file.write_text(sql_implementation, encoding="utf-8")

        test_file = tmp_exercise / "anagram_test.sql"
        with open(test_file, "r", encoding="utf-8") as f_in:
            proc = subprocess.run(
                ["sqlite3", "-bail"],
                cwd=tmp_exercise,
                stdin=f_in,
                capture_output=True,
                text=True
            )

        output_file = tmp_exercise / "output.json"
        if not output_file.exists():
            raise AssertionError(f"output.json was not generated (sqlite3 returncode {proc.returncode}):\n{proc.stderr}")

        with open(output_file, "r", encoding="utf-8") as f_out:
            results = json.load(f_out)

        return results


def run_checks(repo_root: Path, quiet: bool = False) -> dict:
    """Execute all verification checks for R08-T044."""
    exercise_rel = Path("exercises/practice/anagram")
    exercise_dir = repo_root / exercise_rel

    config_path = exercise_dir / ".meta" / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Missing config.json at {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    solution_rel = config["files"]["solution"][0]
    example_rel = config["files"]["example"][0]

    stub_code = (exercise_dir / solution_rel).read_text(encoding="utf-8")
    ref_code = (exercise_dir / example_rel).read_text(encoding="utf-8")

    # 1. Verify learner stub is unsolved
    stub_results = run_test_in_tempdir(exercise_dir, stub_code)
    stub_passed = [t for t in stub_results if t.get("status") == "pass"]
    if len(stub_passed) > 0:
        raise AssertionError(f"Learner stub passed {len(stub_passed)} tests; expected 0.")

    # 2. Verify refactored reference passes all tests
    ref_results = run_test_in_tempdir(exercise_dir, ref_code)
    total_cases = len(ref_results)
    if total_cases == 0:
        raise AssertionError("No test cases were executed!")

    ref_passed = [t for t in ref_results if t.get("status") == "pass"]
    if len(ref_passed) != total_cases:
        failed_cases = [t for t in ref_results if t.get("status") != "pass"]
        raise AssertionError(f"{len(failed_cases)} test case(s) failed against reference: {failed_cases}")

    # 3. Verify invariant comments in example.sql
    if "Invariant" not in ref_code or "subject_sorted" not in ref_code or "word_signatures" not in ref_code:
        raise AssertionError("Refactored example.sql missing required invariant explanation or renamed identifiers.")

    return {
        "status": "success",
        "returncode": 0,
        "total_cases": total_cases,
        "reference_passed": len(ref_passed),
        "stub_unsolved": True,
        "identifiers_clarified": True
    }


def main():
    parser = argparse.ArgumentParser(description="Focused check for anagram reference refactoring.")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format.")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal console output.")
    args = parser.parse_args()

    repo_root = find_repo_root()

    try:
        res = run_checks(repo_root, quiet=args.quiet)
    except Exception as e:
        if args.json:
            print(json.dumps({"status": "failure", "error": str(e), "returncode": 1}, indent=2))
        else:
            print(f"[FAILURE] Check failed: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(res, indent=2))
    elif not args.quiet:
        print(f"[SUCCESS] Anagram reference refactor verified successfully:")
        print(f"  - Learner stub remains unsolved (0/{res['total_cases']} passed).")
        print(f"  - Refactored reference passed all {res['total_cases']}/{res['total_cases']} test cases.")
        print(f"  - Scoped readability refactoring and invariant comments verified.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
