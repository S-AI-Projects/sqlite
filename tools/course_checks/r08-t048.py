#!/usr/bin/env python3
"""
Reusable path and configuration checker for exercises/practice/resistor-color-duo (Task R08-T048).

Verifies:
1. Parses the files object in .meta/config.json directly without filename heuristics.
2. Resolves each path, rejects parent directory traversal, and checks file existence.
3. Tests deliberately invalid metadata fixtures (missing-reference, missing-test, outside-exercise).
4. Tests that the learner stub in the working tree remains unsolved.
5. Tests the reference implementation in an isolated temporary copy, asserting all 6 cases pass.
"""

import argparse
import copy
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


def validate_metadata_config(exercise_dir: Path, config: dict):
    """Validate declared file paths in exercise config metadata."""
    if "files" not in config or not isinstance(config["files"], dict):
        raise ValueError("Missing or invalid 'files' object in config.json")

    base_dir = exercise_dir.resolve()
    for role, file_list in config["files"].items():
        if not isinstance(file_list, list):
            raise ValueError(f"Role '{role}' must map to a list of file paths")
        for rel_path in file_list:
            if not isinstance(rel_path, str) or not rel_path.strip():
                raise ValueError(f"Invalid path in role '{role}': '{rel_path}'")
            target = (base_dir / rel_path).resolve()
            if not target.is_relative_to(base_dir):
                raise ValueError(f"Security violation: path '{rel_path}' in role '{role}' traverses outside exercise directory")
            if not target.is_file():
                raise FileNotFoundError(f"Declared file for role '{role}' not found: '{rel_path}'")


def test_invalid_fixtures(exercise_dir: Path, real_config: dict) -> list:
    """Test path validator against three deliberately invalid metadata fixtures."""
    fixtures = [
        {
            "fixture": "missing-reference",
            "mutation": {"role": "example", "path": ".meta/missing_example.sql"},
            "expected_exception": FileNotFoundError
        },
        {
            "fixture": "missing-test",
            "mutation": {"role": "test", "path": "missing_test.sql"},
            "expected_exception": FileNotFoundError
        },
        {
            "fixture": "outside-exercise",
            "mutation": {"role": "example", "path": "../outside.sql"},
            "expected_exception": ValueError
        }
    ]

    fixture_results = []
    for f in fixtures:
        cfg = copy.deepcopy(real_config)
        role = f["mutation"]["role"]
        path = f["mutation"]["path"]
        cfg["files"][role] = [path]

        try:
            validate_metadata_config(exercise_dir, cfg)
            raise AssertionError(f"Invalid fixture '{f['fixture']}' unexpectedly passed validation!")
        except Exception as e:
            if not isinstance(e, f["expected_exception"]):
                raise AssertionError(f"Fixture '{f['fixture']}' raised {type(e).__name__}, expected {f['expected_exception'].__name__}: {e}")
            fixture_results.append({
                "fixture": f["fixture"],
                "rejected": True,
                "exception": type(e).__name__,
                "message": str(e)
            })

    return fixture_results


def run_sqlite_test(exercise_dir: Path, sql_implementation: str) -> tuple[int, list]:
    """Execute resistor-color-duo_test.sql in a temporary copy of exercise_dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_exercise = Path(tmpdir) / "resistor-color-duo"
        shutil.copytree(exercise_dir, tmp_exercise)

        (tmp_exercise / "resistor-color-duo.sql").write_text(sql_implementation, encoding="utf-8")

        test_file = tmp_exercise / "resistor-color-duo_test.sql"
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
    """Execute all verification checks for R08-T048."""
    exercise_rel = Path("exercises/practice/resistor-color-duo")
    exercise_dir = repo_root / exercise_rel

    config_path = exercise_dir / ".meta" / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Missing config.json at {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        real_config = json.load(f)

    # 1. Validate real configuration
    validate_metadata_config(exercise_dir, real_config)

    # 2. Test deliberately invalid fixtures
    fixture_results = test_invalid_fixtures(exercise_dir, real_config)

    # 3. Verify learner stub is unsolved
    solution_rel = real_config["files"]["solution"][0]
    stub_code = (exercise_dir / solution_rel).read_text(encoding="utf-8")
    stub_rc, stub_results = run_sqlite_test(exercise_dir, stub_code)
    stub_passed = [t for t in stub_results if t.get("status") == "pass"]
    if len(stub_passed) > 0:
        raise AssertionError(f"Learner stub unexpectedly passed {len(stub_passed)} tests; expected 0.")

    # 4. Verify reference implementation passes all tests
    example_rel = real_config["files"]["example"][0]
    ref_code = (exercise_dir / example_rel).read_text(encoding="utf-8")
    ref_rc, ref_results = run_sqlite_test(exercise_dir, ref_code)
    if ref_rc != 0:
        raise AssertionError(f"Reference implementation failed with returncode {ref_rc}")

    if len(ref_results) == 0:
        raise AssertionError("Zero test cases executed for reference!")

    ref_passed = [t for t in ref_results if t.get("status") == "pass"]
    if len(ref_passed) != len(ref_results):
        failed_tests = [t for t in ref_results if t.get("status") != "pass"]
        raise AssertionError(f"{len(failed_tests)} test(s) failed against reference: {failed_tests}")

    # 5. Verify documentation exists
    doc_path = repo_root / "docs" / "maintenance" / "resistor-color-duo.md"
    if not doc_path.exists():
        raise AssertionError(f"Missing maintenance documentation at {doc_path}")

    return {
        "status": "success",
        "returncode": 0,
        "real_config_valid": True,
        "invalid_fixtures_tested": len(fixture_results),
        "total_cases": len(ref_results),
        "reference_passed": len(ref_passed),
        "stub_unsolved": True,
        "docs_verified": True
    }


def main():
    parser = argparse.ArgumentParser(description="Path and metadata configuration checker for resistor-color-duo.")
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
        print(f"[SUCCESS] resistor-color-duo configuration and paths verified successfully:")
        print(f"  - Real metadata config.json parsed and validated strictly inside exercise.")
        print(f"  - All {res['invalid_fixtures_tested']} deliberately invalid fixtures rejected for intended reasons.")
        print(f"  - Learner stub remains unsolved (0/{res['total_cases']} passed).")
        print(f"  - Reference implementation passed all {res['total_cases']}/{res['total_cases']} canonical test cases.")
        print(f"  - Maintenance documentation in docs/maintenance/resistor-color-duo.md verified.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

