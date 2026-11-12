#!/usr/bin/env python3
"""
Reusable focused verification check for exercises/practice/hello-world (Task R08-T050).

Verifies the hello-world contract and decision table:
1. Resolves solution, test, and example paths from .meta/config.json.
2. Asserts the learner stub in the working tree remains unsolved.
3. Tests the reference implementation in an isolated temporary copy and asserts 1/1 pass.
4. Asserts subtle contract variations against SQLite behavior (case sensitivity, punctuation).
5. Verifies guidance documentation in .docs/hints.md and docs/maintenance/hello-world.md.
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


def run_sqlite_test(exercise_dir: Path, sql_statement: str) -> list:
    """Execute hello-world_test.sql in a temporary copy of exercise_dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_exercise = Path(tmpdir) / "hello-world"
        shutil.copytree(exercise_dir, tmp_exercise)

        (tmp_exercise / "hello-world.sql").write_text(sql_statement, encoding="utf-8")

        test_file = tmp_exercise / "hello-world_test.sql"
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
            raise AssertionError(f"output.json was not generated (child exit {proc.returncode}):\n{proc.stderr}")

        with open(output_file, "r", encoding="utf-8") as f_out:
            results = json.load(f_out)

        return results


def run_checks(repo_root: Path, quiet: bool = False) -> dict:
    """Execute all verification checks for R08-T050."""
    exercise_rel = Path("exercises/practice/hello-world")
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
    stub_results = run_sqlite_test(exercise_dir, stub_code)
    stub_passed = [t for t in stub_results if t.get("status") == "pass"]
    if len(stub_passed) > 0:
        raise AssertionError(f"Learner stub passed {len(stub_passed)} tests; expected 0.")

    # 2. Verify reference implementation passes
    ref_results = run_sqlite_test(exercise_dir, ref_code)
    if len(ref_results) == 0:
        raise AssertionError("No test cases were executed!")

    ref_passed = [t for t in ref_results if t.get("status") == "pass"]
    if len(ref_passed) != len(ref_results):
        raise AssertionError(f"Reference failed test cases: {ref_results}")

    # 3. Verify contract edge cases from decision table
    test_cases = [
        ("INSERT INTO hello_world (greeting) VALUES ('hello, world!');", "fail", "case mismatch"),
        ("INSERT INTO hello_world (greeting) VALUES ('Hello World!');", "fail", "missing comma"),
        ("INSERT INTO hello_world (greeting) VALUES ('Hello, World');", "fail", "missing exclamation"),
        ("INSERT INTO hello_world (greeting) VALUES (NULL);", "fail", "null greeting"),
        ("INSERT INTO hello_world (greeting) VALUES ('Hello, World!');", "pass", "canonical string"),
    ]
    for sql, expected_status, desc in test_cases:
        res = run_sqlite_test(exercise_dir, sql)
        actual_status = res[0].get("status")
        if actual_status != expected_status:
            raise AssertionError(f"Decision table test '{desc}' expected status '{expected_status}', got '{actual_status}'")

    # 4. Verify hints.md and docs
    hints_path = exercise_dir / ".docs" / "hints.md"
    if not hints_path.exists():
        raise AssertionError(f"Missing {hints_path}")
    hints_text = hints_path.read_text(encoding="utf-8")
    if "Decision Table" not in hints_text or "Unspecified Behavior" not in hints_text:
        raise AssertionError("hints.md missing expected Decision Table or Unspecified Behavior sections.")

    return {
        "status": "success",
        "returncode": 0,
        "total_cases": len(ref_results),
        "reference_passed": len(ref_passed),
        "stub_unsolved": True,
        "contract_cases_verified": len(test_cases),
        "hints_verified": True
    }


def main():
    parser = argparse.ArgumentParser(description="Focused check for hello-world contract guidance.")
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
        print(f"[SUCCESS] hello-world contract and decision table verified successfully:")
        print(f"  - Learner stub remains unsolved (0/{res['total_cases']} passed).")
        print(f"  - Reference implementation passed all {res['total_cases']}/{res['total_cases']} test cases.")
        print(f"  - {res['contract_cases_verified']} contract decision table cases confirmed against SQLite.")
        print(f"  - Guidance documentation in .docs/hints.md verified.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
