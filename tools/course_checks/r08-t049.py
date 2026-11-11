#!/usr/bin/env python3
"""
Isolated test runner for exercises/practice/leap (Task R08-T049).

Runs the maintained reference implementation (or a specified solution)
in an isolated temporary directory to protect the unsolved learner stub
files while verifying exercise correctness.
"""

import argparse
import hashlib
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


def compute_file_hash(path: Path) -> str:
    """Compute SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_learner_hashes(exercise_dir: Path) -> dict:
    """Compute hashes of all learner-facing and fixture files in the exercise."""
    hashes = {}
    for entry in sorted(exercise_dir.iterdir()):
        if entry.is_file() and not entry.name.startswith("."):
            hashes[entry.name] = compute_file_hash(entry)
    return hashes


def run_isolated_leap_test(
    repo_root: Path,
    solution_override: Path = None,
    empty_tests: bool = False,
    quiet: bool = False,
) -> dict:
    """
    Execute leap tests in an isolated temporary directory.
    Returns a dictionary of execution results.
    """
    exercise_rel = Path("exercises/practice/leap")
    exercise_dir = repo_root / exercise_rel
    config_file = exercise_dir / ".meta" / "config.json"

    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")

    with open(config_file, "r", encoding="utf-8") as f:
        config = json.load(f)

    solution_rel = config["files"]["solution"][0]
    test_rel = config["files"]["test"][0]
    example_rel = config["files"]["example"][0]

    # Compute hashes of working tree files before execution
    hashes_before = compute_learner_hashes(exercise_dir)

    temp_dir_path = None
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir_path = Path(tmpdir)
            temp_exercise = temp_dir_path / "leap"

            # Copy exercise including dotfiles (.meta, .docs)
            shutil.copytree(exercise_dir, temp_exercise)

            # Substitute solution in the temporary directory ONLY
            target_solution = temp_exercise / solution_rel
            if solution_override is not None:
                if not solution_override.exists():
                    raise FileNotFoundError(f"Solution override file not found: {solution_override}")
                shutil.copyfile(solution_override, target_solution)
            else:
                source_example = temp_exercise / example_rel
                shutil.copyfile(source_example, target_solution)

            # If empty_tests requested, clear the tests INSERT in test_file
            if empty_tests:
                test_sql_path = temp_exercise / test_rel
                with open(test_sql_path, "r", encoding="utf-8") as f:
                    content = f.read()
                # Remove the entire INSERT INTO tests ...; statement
                import re
                cleared_content = re.sub(r"INSERT\s+INTO\s+tests\b.*?;", "-- no tests inserted", content, flags=re.DOTALL)
                with open(test_sql_path, "w", encoding="utf-8") as f:
                    f.write(cleared_content)

            # Execute sqlite3 -bail < leap_test.sql
            cmd = f"sqlite3 -bail < {test_rel}"
            proc = subprocess.run(
                cmd,
                cwd=temp_exercise,
                shell=True,
                capture_output=True,
                text=True
            )

            # Check child process return code
            child_returncode = proc.returncode
            if child_returncode != 0:
                return {
                    "status": "child_process_error",
                    "returncode": 3,
                    "child_returncode": child_returncode,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "test_count": 0,
                    "passed_count": 0,
                    "failed_count": 0,
                    "results": []
                }

            # Read output.json
            output_file = temp_exercise / "output.json"
            if not output_file.exists():
                return {
                    "status": "missing_output",
                    "returncode": 4,
                    "child_returncode": 0,
                    "stdout": proc.stdout,
                    "stderr": "output.json was not generated",
                    "test_count": 0,
                    "passed_count": 0,
                    "failed_count": 0,
                    "results": []
                }

            output_text = output_file.read_text(encoding="utf-8").strip()
            if not output_text:
                results = []
            else:
                results = json.loads(output_text)

            test_count = len(results)
            passed = [t for t in results if t.get("status") == "pass"]
            failed = [t for t in results if t.get("status") != "pass"]

            # Fail on zero-test run
            if test_count == 0:
                return {
                    "status": "zero_tests",
                    "returncode": 2,
                    "child_returncode": child_returncode,
                    "stdout": proc.stdout,
                    "stderr": "Zero test cases were executed.",
                    "test_count": 0,
                    "passed_count": 0,
                    "failed_count": 0,
                    "results": []
                }

            # Check for failed tests
            if failed:
                return {
                    "status": "assertion_failure",
                    "returncode": 1,
                    "child_returncode": child_returncode,
                    "stdout": proc.stdout,
                    "stderr": f"{len(failed)} test(s) failed.",
                    "test_count": test_count,
                    "passed_count": len(passed),
                    "failed_count": len(failed),
                    "results": results
                }

            return {
                "status": "success",
                "returncode": 0,
                "child_returncode": child_returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "test_count": test_count,
                "passed_count": len(passed),
                "failed_count": 0,
                "results": results
            }

    finally:
        # Check hashes of working tree files after execution
        hashes_after = compute_learner_hashes(exercise_dir)
        if hashes_before != hashes_after:
            raise RuntimeError(
                f"Learner files were modified during test execution!\n"
                f"Before: {hashes_before}\nAfter: {hashes_after}"
            )


def main():
    parser = argparse.ArgumentParser(
        description="Isolated test runner for exercises/practice/leap without altering learner starter files."
    )
    parser.add_argument(
        "--solution-file",
        type=Path,
        default=None,
        help="Path to an alternate SQL solution to test instead of the reference example.sql."
    )
    parser.add_argument(
        "--empty-tests",
        action="store_true",
        help="Simulate an empty test selection (zero-test run)."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format."
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress human-readable progress messages."
    )

    args = parser.parse_args()
    repo_root = find_repo_root()

    try:
        res = run_isolated_leap_test(
            repo_root=repo_root,
            solution_override=args.solution_file,
            empty_tests=args.empty_tests,
            quiet=args.quiet
        )
    except Exception as e:
        if args.json:
            print(json.dumps({"status": "error", "message": str(e), "returncode": 4}, indent=2))
        else:
            print(f"Error executing runner: {e}", file=sys.stderr)
        return 4

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        if res["status"] == "success":
            print(f"[SUCCESS] All {res['test_count']} test cases passed against reference.")
            for t in res["results"]:
                desc = t.get("name") or t.get("description")
                print(f"  ✓ {desc}")
        elif res["status"] == "assertion_failure":
            print(f"[FAILURE] Assertion failure: {res['failed_count']} of {res['test_count']} test(s) failed.", file=sys.stderr)
            for t in res["results"]:
                desc = t.get("name") or t.get("description")
                if t.get("status") != "pass":
                    print(f"  ✗ {desc}: {t.get('message', 'fail')}", file=sys.stderr)
        elif res["status"] == "zero_tests":
            print("[FAILURE] Zero-test run detected: no tests were executed.", file=sys.stderr)
        elif res["status"] == "child_process_error":
            print(f"[FAILURE] SQLite process failed with exit code {res['child_returncode']}.", file=sys.stderr)
            if res.get("stderr"):
                print(res["stderr"], file=sys.stderr)
        else:
            print(f"[FAILURE] Run ended with status '{res['status']}': {res.get('stderr')}", file=sys.stderr)

    return res["returncode"]


if __name__ == "__main__":
    sys.exit(main())
