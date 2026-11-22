#!/usr/bin/env python3
"""
Automated verification check for Task R08-T013 (Yacht exercise).

Steps:
1. Verify learner stub `exercises/practice/yacht/yacht.sql` and record SHA-256 before testing.
2. Pass 1: Run isolated test with `.meta/example.sql` -> must pass 100% of tests (29/29).
3. Pass 2: Run isolated test with mutant SQL -> must fail on the designated test case:
   UUID: 32a3f4ee-9142-4edf-ba70-6c0f96eb4b0c ("Yacht is not a full house").
4. Verify original learner files remain completely untouched (SHA-256 check).
5. Export `work/R08-T013/evidence.json` and `work/R08-T013/versions.txt`.
"""

import datetime
import hashlib
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import tempfile


# Mutant SQL allowing 5-of-a-kind (Yacht) as a Full House
MUTANT_REPLACEMENT_TARGET = """        WHEN 'full house' THEN CASE
          WHEN MAX(ones, twos, threes, fours, fives, sixes) == 3
          AND (
            ones == 3
            OR twos == 3
            OR threes == 3
            OR fours == 3
            OR fives == 3
            OR sixes == 3
          ) THEN total
          ELSE 0
        END"""

MUTANT_REPLACEMENT_CODE = """        WHEN 'full house' THEN CASE
          WHEN MAX(ones, twos, threes, fours, fives, sixes) IN (3, 5)
          AND (
            ones IN (3, 5)
            OR twos IN (3, 5)
            OR threes IN (3, 5)
            OR fours IN (3, 5)
            OR fives IN (3, 5)
            OR sixes IN (3, 5)
          ) THEN total
          ELSE 0
        END"""


def compute_sha256(file_path: pathlib.Path) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_cmd_output(cmd: list[str]) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception as e:
        return f"Error retrieving {cmd}: {e}"


def run_yacht_tests(exercise_dir: pathlib.Path, solution_content: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = pathlib.Path(tmp_dir_str)
        temp_exercise = tmp_dir / "yacht"
        shutil.copytree(exercise_dir, temp_exercise)

        # Write solution content to yacht.sql in temp copy
        (temp_exercise / "yacht.sql").write_text(solution_content, encoding="utf-8")

        # Run sqlite3 -bail < yacht_test.sql
        cmd = "sqlite3 -bail < yacht_test.sql"
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=temp_exercise,
            capture_output=True,
            text=True
        )

        output_json_path = temp_exercise / "output.json"
        if not output_json_path.exists():
            raise FileNotFoundError(f"output.json not found at {output_json_path}")

        with open(output_json_path, "r", encoding="utf-8") as f:
            test_results = json.load(f)

        passed = [t for t in test_results if t.get("status") == "pass"]
        failed = [t for t in test_results if t.get("status") != "pass"]

        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "total_count": len(test_results),
            "passed_count": len(passed),
            "failed_count": len(failed),
            "failed_cases": failed,
            "all_cases": test_results
        }


def main():
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    work_dir = repo_root / "work" / "R08-T013"
    work_dir.mkdir(parents=True, exist_ok=True)

    exercise_dir = repo_root / "exercises" / "practice" / "yacht"
    stub_file = exercise_dir / "yacht.sql"
    example_file = exercise_dir / ".meta" / "example.sql"

    print("=== Task R08-T013 Automated Verification ===")
    print(f"Repo Root: {repo_root}")
    print(f"Exercise Directory: {exercise_dir}")

    # Step 1: Verify learner stub exists and compute SHA256 before
    assert stub_file.exists(), f"Learner stub {stub_file} does not exist"
    sha256_before = compute_sha256(stub_file)
    print(f"Learner stub SHA256 (before): {sha256_before}")

    # Read reference solution
    assert example_file.exists(), f"Example file {example_file} does not exist"
    example_sql = example_file.read_text(encoding="utf-8")

    # Step 2: Pass 1 - Run reference solution (must pass 100% of tests)
    print("\n--- Pass 1: Running Reference Implementation (.meta/example.sql) ---")
    pass1_result = run_yacht_tests(exercise_dir, example_sql)
    print(f"Pass 1 Total: {pass1_result['total_count']}, Passed: {pass1_result['passed_count']}, Failed: {pass1_result['failed_count']}")
    assert pass1_result["total_count"] == 29, f"Expected 29 tests, found {pass1_result['total_count']}"
    assert pass1_result["passed_count"] == 29, f"Reference solution had failures: {pass1_result['failed_cases']}"
    assert pass1_result["failed_count"] == 0, "Reference solution should have 0 failures"
    print("Pass 1: PASSED (100% test success).")

    # Step 3: Pass 2 - Construct and run mutant SQL
    print("\n--- Pass 2: Running Mutant SQL (Full House allows 5-of-a-kind) ---")
    assert MUTANT_REPLACEMENT_TARGET in example_sql, "Could not find target block in example.sql to create mutant"
    mutant_sql = example_sql.replace(MUTANT_REPLACEMENT_TARGET, MUTANT_REPLACEMENT_CODE)

    pass2_result = run_yacht_tests(exercise_dir, mutant_sql)
    print(f"Pass 2 Total: {pass2_result['total_count']}, Passed: {pass2_result['passed_count']}, Failed: {pass2_result['failed_count']}")
    
    # Assert mutant fails on the designated test case
    assert pass2_result["failed_count"] == 1, (
        f"Expected exactly 1 failure for mutant, got {pass2_result['failed_count']}: {pass2_result['failed_cases']}"
    )

    failed_case = pass2_result["failed_cases"][0]
    failed_name = failed_case.get("name")
    failed_msg = failed_case.get("message", "")
    print(f"Mutant caught by test: '{failed_name}'")
    print(f"Failure message: {failed_msg}")

    # Designate target case: "Yacht is not a full house"
    assert failed_name == "Yacht is not a full house", f"Expected failure in 'Yacht is not a full house', got '{failed_name}'"
    assert "<10>" in failed_msg and "<0>" in failed_msg, f"Unexpected message: {failed_msg}"
    print("Pass 2: PASSED (Mutant correctly caught and rejected).")

    # Step 4: Verify learner files remain completely untouched
    sha256_after = compute_sha256(stub_file)
    print(f"\nLearner stub SHA256 (after):  {sha256_after}")
    assert sha256_before == sha256_after, "Learner stub yacht.sql was modified!"
    print("Assertion verified: Original learner stub is completely untouched.")

    # Step 5: Collect environment versions
    python_ver = sys.version
    sqlite_cli_ver = get_cmd_output(["sqlite3", "--version"])
    git_branch = get_cmd_output(["git", "branch", "--show-current"])
    git_commit = get_cmd_output(["git", "rev-parse", "HEAD"])
    platform_info = platform.platform()
    machine_arch = platform.machine()
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    versions_content = (
        f"Task: R08-T013\n"
        f"Timestamp (UTC): {timestamp}\n"
        f"Git Branch: {git_branch}\n"
        f"Git Commit: {git_commit}\n"
        f"OS Platform: {platform_info}\n"
        f"Architecture: {machine_arch}\n"
        f"Python Version: {python_ver}\n"
        f"SQLite CLI Version: {sqlite_cli_ver}\n"
    )

    versions_file = work_dir / "versions.txt"
    with open(versions_file, "w", encoding="utf-8") as f:
        f.write(versions_content)
    print(f"Wrote environment versions to {versions_file}")

    # Step 6: Export evidence.json
    evidence_data = {
        "task_id": "R08-T013",
        "timestamp": timestamp,
        "environment": {
            "platform": platform_info,
            "architecture": machine_arch,
            "python_version": python_ver,
            "sqlite3_version": sqlite_cli_ver,
        },
        "git": {
            "branch": git_branch,
            "commit": git_commit,
        },
        "stub_verification": {
            "file": str(stub_file.relative_to(repo_root)),
            "sha256_before": sha256_before,
            "sha256_after": sha256_after,
            "untouched": sha256_before == sha256_after,
        },
        "pass_1_reference": {
            "description": "Reference solution execution (.meta/example.sql)",
            "total_tests": pass1_result["total_count"],
            "passed_tests": pass1_result["passed_count"],
            "failed_tests": pass1_result["failed_count"],
            "status": "PASS",
        },
        "pass_2_mutant": {
            "description": "Mutant solution (Full House allows 5-of-a-kind / Yacht)",
            "total_tests": pass2_result["total_count"],
            "passed_tests": pass2_result["passed_count"],
            "failed_tests": pass2_result["failed_count"],
            "designated_rejection": {
                "uuid": "32a3f4ee-9142-4edf-ba70-6c0f96eb4b0c",
                "test_name": failed_name,
                "dice_results": "2, 2, 2, 2, 2",
                "category": "full house",
                "expected_score": 0,
                "mutant_score": 10,
                "error_message": failed_msg,
                "rejected": True,
            },
            "status": "PASS",
        },
        "status": "PASS"
    }

    evidence_file = work_dir / "evidence.json"
    with open(evidence_file, "w", encoding="utf-8") as f:
        json.dump(evidence_data, f, indent=2)
    print(f"Wrote verification evidence to {evidence_file}")

    print("\n=== All checks completed successfully ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
