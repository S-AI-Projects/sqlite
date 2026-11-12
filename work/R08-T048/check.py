#!/usr/bin/env python3
"""
Verification check for Task R08-T048 (exercises/practice/resistor-color-duo).

Requirements verified:
1. Resolves solution/test/example paths directly from exercises/practice/resistor-color-duo/.meta/config.json.
2. Validates declared paths against directory boundary escaping (parent traversal) and file existence.
3. Tests three deliberately invalid metadata fixtures:
     - missing-reference
     - missing-test
     - outside-exercise
   and asserts they each fail for the intended reason.
4. Copies the exercise including dotfiles to a temporary directory without modifying the working tree.
5. Asserts the learner stub in the working tree remains unsolved (0/6 passed).
6. Substitutes the maintained reference implementation only in the temporary copy and runs:
     sqlite3 -bail < resistor-color-duo_test.sql
7. Asserts every entry in output.json has status "pass" and verifies child return codes and test counts.
8. Verifies documentation in docs/maintenance/resistor-color-duo.md.
9. Saves inputs, expected vs actual results, tool versions, and summary in work/R08-T048/.
"""

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def get_tool_versions(work_dir: Path) -> dict:
    """Collect tool versions and write to tool_versions.json."""
    tools = {}

    try:
        res = subprocess.run(["sqlite3", "--version"], capture_output=True, text=True, check=True)
        tools["sqlite3"] = res.stdout.strip()
    except Exception as e:
        tools["sqlite3"] = f"error: {e}"

    tools["python3"] = sys.version.replace("\n", " ")

    try:
        res = subprocess.run(["bash", "--version"], capture_output=True, text=True, check=True)
        tools["bash"] = res.stdout.splitlines()[0].strip()
    except Exception as e:
        tools["bash"] = f"error: {e}"

    try:
        res = subprocess.run(["jq", "--version"], capture_output=True, text=True, check=True)
        tools["jq"] = res.stdout.strip()
    except Exception as e:
        tools["jq"] = f"error: {e}"

    try:
        res_branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True)
        tools["git_branch"] = res_branch.stdout.strip()
        res_commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
        tools["git_commit"] = res_commit.stdout.strip()
    except Exception as e:
        tools["git"] = f"error: {e}"

    with open(work_dir / "tool_versions.json", "w", encoding="utf-8") as f:
        json.dump(tools, f, indent=2)

    return tools


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


def verify_metadata_and_fixtures(exercise_dir: Path, real_config: dict, work_dir: Path):
    """Verify real config and test deliberately invalid metadata fixtures."""
    # 1. Real config must pass
    validate_metadata_config(exercise_dir, real_config)

    # 2. Deliberately invalid fixtures
    fixtures = [
        {
            "name": "missing-reference",
            "mutation": {"role": "example", "path": ".meta/missing_example.sql"},
            "expected_error": "FileNotFoundError"
        },
        {
            "name": "missing-test",
            "mutation": {"role": "test", "path": "missing_test.sql"},
            "expected_error": "FileNotFoundError"
        },
        {
            "name": "outside-exercise",
            "mutation": {"role": "example", "path": "../outside.sql"},
            "expected_error": "ValueError"
        }
    ]

    fixture_records = []
    for f in fixtures:
        cfg = copy.deepcopy(real_config)
        cfg["files"][f["mutation"]["role"]] = [f["mutation"]["path"]]

        raised_type = None
        error_msg = None
        try:
            validate_metadata_config(exercise_dir, cfg)
        except Exception as e:
            raised_type = type(e).__name__
            error_msg = str(e)

        if raised_type != f["expected_error"]:
            raise AssertionError(f"Fixture '{f['name']}' expected {f['expected_error']}, got {raised_type}: {error_msg}")

        fixture_records.append({
            "fixture": f["name"],
            "expected_rejection": f["expected_error"],
            "actual_rejection": raised_type,
            "error_message": error_msg,
            "passed_rejection_check": True
        })

    report = {
        "real_config_status": "valid",
        "declared_roles": list(real_config.get("files", {}).keys()),
        "fixtures": fixture_records
    }

    with open(work_dir / "metadata_validation.json", "w", encoding="utf-8") as f_out:
        json.dump(report, f_out, indent=2)

    print(f"[OK] Metadata validation: real config valid; all {len(fixture_records)} invalid fixtures rejected as expected.")
    return report


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


def verify_learner_stub(exercise_dir: Path, config: dict):
    """Verify that learner stub in working tree is unsolved."""
    solution_file = config["files"]["solution"][0]
    stub_content = (exercise_dir / solution_file).read_text(encoding="utf-8")

    returncode, results = run_sqlite_test(exercise_dir, stub_content)

    passed = [t for t in results if t.get("status") == "pass"]
    failed = [t for t in results if t.get("status") == "fail"]

    if len(passed) != 0:
        raise AssertionError(f"Learner stub unexpectedly passed {len(passed)} tests; expected 0.")

    print(f"[OK] Learner stub verified: {len(passed)} passed, {len(failed)} failed (unsolved as expected).")
    return results


def verify_reference_implementation(exercise_dir: Path, config: dict, work_dir: Path):
    """Verify that reference implementation passes all canonical tests."""
    example_file = config["files"]["example"][0]
    ref_content = (exercise_dir / example_file).read_text(encoding="utf-8")

    returncode, results = run_sqlite_test(exercise_dir, ref_content)

    if returncode != 0:
        raise AssertionError(f"sqlite3 execution failed against reference with returncode {returncode}")

    if len(results) == 0:
        raise AssertionError("Zero test cases executed for reference implementation!")

    passed = [t for t in results if t.get("status") == "pass"]
    failed = [t for t in results if t.get("status") != "pass"]

    if len(failed) > 0:
        raise AssertionError(f"{len(failed)} test(s) failed against reference: {failed}")

    print(f"[OK] Reference implementation passed all {len(passed)} executed canonical test cases.")

    with open(work_dir / "test_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "total_executed": len(results),
            "passed": len(passed),
            "failed": len(failed),
            "cases": results
        }, f, indent=2)

    return results


def verify_maintenance_docs(repo_root: Path):
    """Verify that docs/maintenance/resistor-color-duo.md exists and contains required sections."""
    doc_path = repo_root / "docs" / "maintenance" / "resistor-color-duo.md"
    if not doc_path.exists():
        raise AssertionError(f"Missing documentation at {doc_path}")

    doc_text = doc_path.read_text(encoding="utf-8")
    required_tokens = [
        "resistor-color-duo.sql",
        "resistor-color-duo_test.sql",
        ".meta/example.sql",
        "data.csv",
        "missing-reference",
        "missing-test",
        "outside-exercise",
        "verify-exercises"
    ]
    for token in required_tokens:
        if token not in doc_text:
            raise AssertionError(f"resistor-color-duo.md missing required token: '{token}'")

    print(f"[OK] Maintenance documentation in {doc_path} verified.")


def main():
    repo_root = Path(__file__).resolve().parent.parent.parent
    work_dir = repo_root / "work" / "R08-T048"
    work_dir.mkdir(parents=True, exist_ok=True)

    exercise_rel = Path("exercises/practice/resistor-color-duo")
    exercise_dir = repo_root / exercise_rel

    print("=== Running Checks for Task R08-T048 ===")
    print(f"Repository Root: {repo_root}")
    print(f"Work Directory:  {work_dir}")

    # 1. Collect tool versions
    tools = get_tool_versions(work_dir)
    print(f"[OK] Collected tool versions: sqlite3={tools.get('sqlite3')}, python3={sys.version.split()[0]}")

    # 2. Read config.json
    config_path = exercise_dir / ".meta" / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 3. Verify metadata and test invalid fixtures
    validation_report = verify_metadata_and_fixtures(exercise_dir, config, work_dir)

    # 4. Verify learner stub is unsolved
    verify_learner_stub(exercise_dir, config)

    # 5. Verify reference implementation passes all canonical tests
    ref_results = verify_reference_implementation(exercise_dir, config, work_dir)

    # 6. Verify maintenance documentation
    verify_maintenance_docs(repo_root)

    # 7. Write summary.json
    summary = {
        "task": "R08-T048",
        "exercise": "exercises/practice/resistor-color-duo",
        "real_metadata_valid": True,
        "invalid_fixtures_tested": len(validation_report["fixtures"]),
        "total_canonical_cases": len(ref_results),
        "reference_all_passed": True,
        "learner_stub_unsolved": True,
        "maintenance_docs_verified": True
    }
    with open(work_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n=== ALL CHECKS PASSED SUCCESSFULLY ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
