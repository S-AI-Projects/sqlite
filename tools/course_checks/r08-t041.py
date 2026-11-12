#!/usr/bin/env python3
"""
Reusable focused verification check for exercises/practice/rest-api (Task R08-T041).

Verifies:
1. Resolves solution, test, and example paths from .meta/config.json.
2. Asserts the learner stub in the working tree remains unsolved.
3. Tests the reference implementation in an isolated temporary copy and asserts all 9 cases pass.
4. Asserts rationales exist in tests.toml for UUIDs 5be01ffb-a814-47a8-a19f-490a5622ba07,
   382b70cc-9f6c-486d-9bee-fda2df81c803, d624e5e5-1abb-4f18-95b3-45d55c818dc3 and TOML parses.
5. Verifies documentation in docs/maintenance/rest-api.md.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


def find_repo_root() -> Path:
    """Locate the git repository root."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".git").exists() or (current / "exercises").exists():
            return current
        current = current.parent
    return Path.cwd()


def run_sqlite_test(exercise_dir: Path, sql_implementation: str) -> tuple[int, list]:
    """Execute rest-api_test.sql in a temporary copy of exercise_dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_exercise = Path(tmpdir) / "rest-api"
        shutil.copytree(exercise_dir, tmp_exercise)

        (tmp_exercise / "rest-api.sql").write_text(sql_implementation, encoding="utf-8")

        test_file = tmp_exercise / "rest-api_test.sql"
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
            return proc.returncode, []

        with open(output_file, "r", encoding="utf-8") as f_out:
            results = json.load(f_out)

        return proc.returncode, results


def run_checks(repo_root: Path, quiet: bool = False) -> dict:
    """Execute all verification checks for R08-T041."""
    exercise_rel = Path("exercises/practice/rest-api")
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
    stub_rc, stub_results = run_sqlite_test(exercise_dir, stub_code)
    stub_passed = [t for t in stub_results if t.get("status") == "pass"]
    if stub_rc == 0 and len(stub_passed) > 0:
        raise AssertionError(f"Learner stub unexpectedly passed {len(stub_passed)} tests; expected unsolved.")

    # 2. Verify reference implementation passes all canonical tests
    ref_rc, ref_results = run_sqlite_test(exercise_dir, ref_code)
    if ref_rc != 0:
        raise AssertionError(f"Reference implementation failed with returncode {ref_rc}")

    if len(ref_results) == 0:
        raise AssertionError("Zero test cases executed for reference!")

    ref_passed = [t for t in ref_results if t.get("status") == "pass"]
    if len(ref_passed) != len(ref_results):
        failed_tests = [t for t in ref_results if t.get("status") != "pass"]
        raise AssertionError(f"{len(failed_tests)} test(s) failed against reference: {failed_tests}")

    # 3. Verify tests.toml parsing and selected UUID rationales
    tests_toml_path = exercise_dir / ".meta" / "tests.toml"
    with open(tests_toml_path, "rb") as f:
        toml_data = tomllib.load(f)

    selected_uuids = [
        "5be01ffb-a814-47a8-a19f-490a5622ba07",
        "382b70cc-9f6c-486d-9bee-fda2df81c803",
        "d624e5e5-1abb-4f18-95b3-45d55c818dc3"
    ]
    for uuid in selected_uuids:
        if uuid not in toml_data:
            raise AssertionError(f"UUID {uuid} not found in tests.toml")
        entry = toml_data[uuid]
        if "comment" not in entry or len(entry["comment"].strip()) == 0:
            raise AssertionError(f"UUID {uuid} is missing a rationale comment in tests.toml")

    # 4. Verify docs/maintenance/rest-api.md
    doc_path = repo_root / "docs" / "maintenance" / "rest-api.md"
    if not doc_path.exists():
        raise AssertionError(f"Documentation file {doc_path} does not exist!")

    doc_text = doc_path.read_text(encoding="utf-8")
    for uuid in selected_uuids:
        if uuid not in doc_text:
            raise AssertionError(f"rest-api.md is missing rationale for UUID {uuid}")

    return {
        "status": "success",
        "returncode": 0,
        "total_cases": len(ref_results),
        "reference_passed": len(ref_passed),
        "stub_unsolved": True,
        "selected_uuids_verified": len(selected_uuids),
        "toml_parsed": True,
        "docs_verified": True
    }


def main():
    parser = argparse.ArgumentParser(description="Focused check for rest-api canonical case rationales.")
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
        print(f"[SUCCESS] rest-api canonical case rationales verified successfully:")
        print(f"  - Learner stub remains unsolved.")
        print(f"  - Reference implementation passed all {res['total_cases']}/{res['total_cases']} canonical test cases.")
        print(f"  - Rationales for all {res['selected_uuids_verified']} selected UUIDs verified in tests.toml and docs.")
        print(f"  - tests.toml parsed validly.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
