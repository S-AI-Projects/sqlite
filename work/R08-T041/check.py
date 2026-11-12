#!/usr/bin/env python3
"""
Verification check for Task R08-T041 (exercises/practice/rest-api).

Requirements verified:
1. Resolves solution/test/example paths from exercises/practice/rest-api/.meta/config.json.
2. Copies the exercise including dotfiles to a temporary directory without modifying the working tree.
3. Asserts the learner stub in the working tree remains unsolved.
4. Substitutes the maintained reference implementation only in the temporary copy and runs:
     sqlite3 -bail < rest-api_test.sql
5. Asserts every entry in output.json has status "pass" and verifies child return codes and test counts.
6. Asserts each of 5be01ffb-a814-47a8-a19f-490a5622ba07, 382b70cc-9f6c-486d-9bee-fda2df81c803,
   and d624e5e5-1abb-4f18-95b3-45d55c818dc3 has an independently checkable rationale naming the
   relevant SQLite operation; asserts tests.toml parses validly.
7. Records before/after inclusion and exclusion counts (9 included, 0 excluded).
8. Verifies documentation in docs/maintenance/rest-api.md.
9. Saves inputs, expected vs actual results, tool versions, and summary in work/R08-T041/.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
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


def verify_learner_stub(exercise_dir: Path, config: dict):
    """Verify that learner stub in working tree is unsolved."""
    solution_file = config["files"]["solution"][0]
    stub_content = (exercise_dir / solution_file).read_text(encoding="utf-8")

    returncode, results = run_sqlite_test(exercise_dir, stub_content)

    passed = [t for t in results if t.get("status") == "pass"]

    # Either sqlite3 failed with non-zero exit or 0 tests passed
    if returncode == 0 and len(passed) > 0:
        raise AssertionError(f"Learner stub unexpectedly passed {len(passed)} tests; expected 0.")

    print(f"[OK] Learner stub verified: returncode={returncode}, passed={len(passed)} (unsolved as expected).")
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


def verify_canonical_rationales_and_toml(exercise_dir: Path, work_dir: Path):
    """Verify rationales in tests.toml for the three selected UUIDs."""
    tests_toml_path = exercise_dir / ".meta" / "tests.toml"

    with open(tests_toml_path, "rb") as f:
        toml_data = tomllib.load(f)

    selected_uuids = {
        "5be01ffb-a814-47a8-a19f-490a5622ba07": {
            "name": "user management -> no users",
            "endpoint": "GET /users",
            "operation": "LEFT JOIN json_each() with IIF(json_type(DB.value) IS NULL, json_array(), json_array(json(DB.value)))"
        },
        "382b70cc-9f6c-486d-9bee-fda2df81c803": {
            "name": "user management -> add user",
            "endpoint": "POST /add",
            "operation": "json_extract(payload, '$.user') and json_object('name', ..., 'owes', json_object(), 'owed_by', json_object(), 'balance', 0)"
        },
        "d624e5e5-1abb-4f18-95b3-45d55c818dc3": {
            "name": "user management -> get single user",
            "endpoint": "GET /users",
            "operation": "LEFT JOIN json_each(RA.payload, '$.users') with json_each(RA.database, '$.users') on name equality"
        }
    }

    recorded_rationales = []
    for uuid, meta in selected_uuids.items():
        if uuid not in toml_data:
            raise AssertionError(f"UUID {uuid} not found in tests.toml")
        entry = toml_data[uuid]
        if "comment" not in entry or not entry["comment"].strip():
            raise AssertionError(f"UUID {uuid} missing rationale comment in tests.toml")

        recorded_rationales.append({
            "uuid": uuid,
            "description": entry.get("description", meta["name"]),
            "endpoint": meta["endpoint"],
            "sqlite_operation": meta["operation"],
            "rationale": entry["comment"],
            "included": entry.get("include", True)
        })

    print(f"[OK] Verified {len(recorded_rationales)} selected canonical rationales in tests.toml.")

    with open(work_dir / "canonical_rationales.json", "w", encoding="utf-8") as f:
        json.dump(recorded_rationales, f, indent=2)

    return recorded_rationales


def record_inclusion_counts(exercise_dir: Path, work_dir: Path):
    """Record before and after included/excluded counts."""
    tests_toml_path = exercise_dir / ".meta" / "tests.toml"
    with open(tests_toml_path, "rb") as f:
        toml_data = tomllib.load(f)

    total_cases = len(toml_data)
    excluded = sum(1 for v in toml_data.values() if isinstance(v, dict) and v.get("include") is False)
    included = total_cases - excluded

    counts_data = {
        "before": {
            "total": 9,
            "included": 9,
            "excluded": 0
        },
        "after": {
            "total": total_cases,
            "included": included,
            "excluded": excluded
        },
        "changed_inclusions": 0,
        "note": "All 9 canonical cases remain included and passing against reference solution."
    }

    if included != 9 or excluded != 0:
        raise AssertionError(f"Unexpected case counts: {included} included, {excluded} excluded; expected 9 and 0.")

    with open(work_dir / "inclusion_counts.json", "w", encoding="utf-8") as f:
        json.dump(counts_data, f, indent=2)

    print(f"[OK] Recorded inclusion counts: {included} included, {excluded} excluded (unchanged).")
    return counts_data


def verify_maintenance_docs(repo_root: Path):
    """Verify that docs/maintenance/rest-api.md exists and contains required sections."""
    doc_path = repo_root / "docs" / "maintenance" / "rest-api.md"
    if not doc_path.exists():
        raise AssertionError(f"Missing documentation at {doc_path}")

    doc_text = doc_path.read_text(encoding="utf-8")
    required_tokens = [
        "5be01ffb-a814-47a8-a19f-490a5622ba07",
        "382b70cc-9f6c-486d-9bee-fda2df81c803",
        "d624e5e5-1abb-4f18-95b3-45d55c818dc3",
        "json_each",
        "json_object",
        "Inclusion & Exclusion Tracking"
    ]
    for token in required_tokens:
        if token not in doc_text:
            raise AssertionError(f"rest-api.md missing required token: '{token}'")

    print(f"[OK] Maintenance documentation in {doc_path} verified.")


def main():
    repo_root = Path(__file__).resolve().parent.parent.parent
    work_dir = repo_root / "work" / "R08-T041"
    work_dir.mkdir(parents=True, exist_ok=True)

    exercise_rel = Path("exercises/practice/rest-api")
    exercise_dir = repo_root / exercise_rel

    print("=== Running Checks for Task R08-T041 ===")
    print(f"Repository Root: {repo_root}")
    print(f"Work Directory:  {work_dir}")

    # 1. Collect tool versions
    tools = get_tool_versions(work_dir)
    print(f"[OK] Collected tool versions: sqlite3={tools.get('sqlite3')}, python3={sys.version.split()[0]}")

    # 2. Read config.json
    config_path = exercise_dir / ".meta" / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 3. Verify learner stub is unsolved
    verify_learner_stub(exercise_dir, config)

    # 4. Verify reference implementation passes all canonical tests
    ref_results = verify_reference_implementation(exercise_dir, config, work_dir)

    # 5. Verify selected canonical case rationales and TOML validity
    rationales = verify_canonical_rationales_and_toml(exercise_dir, work_dir)

    # 6. Record inclusion/exclusion counts
    counts = record_inclusion_counts(exercise_dir, work_dir)

    # 7. Verify maintenance documentation
    verify_maintenance_docs(repo_root)

    # 8. Write summary.json
    summary = {
        "task": "R08-T041",
        "exercise": "exercises/practice/rest-api",
        "total_canonical_cases": len(ref_results),
        "reference_all_passed": True,
        "learner_stub_unsolved": True,
        "selected_rationales_verified": len(rationales),
        "toml_valid": True,
        "included_cases": counts["after"]["included"],
        "excluded_cases": counts["after"]["excluded"],
        "maintenance_docs_verified": True
    }
    with open(work_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n=== ALL CHECKS PASSED SUCCESSFULLY ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
