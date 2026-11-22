#!/usr/bin/env python3
"""
Automated verification check for Task R08-T020 (sublist).

Responsibilities:
1. Verify learner starter stub `exercises/practice/sublist/sublist.sql` remains untouched.
2. Run isolated tests copying sublist into `tempfile.TemporaryDirectory`.
3. Execute `sqlite3 -bail` with `.meta/example.sql` and assert 100% pass status in `output.json`.
4. Export `work/R08-T020/evidence.json` and `work/R08-T020/versions.txt`.
5. Exit with status code 0 on complete success.
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


def run_isolated_test(repo_root: pathlib.Path) -> dict:
    """
    Run sublist test suite in an isolated temporary directory using .meta/example.sql.
    """
    exercise_dir = repo_root / "exercises" / "practice" / "sublist"
    example_sql = exercise_dir / ".meta" / "example.sql"
    if not example_sql.exists():
        raise FileNotFoundError(f"Missing reference implementation at {example_sql}")

    required_assets = [
        "create_fixture.sql",
        "create_test_table.sql",
        "sublist_test.sql",
        "data.csv",
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = pathlib.Path(tmp_dir)

        # Copy harness files
        for fname in required_assets:
            src = exercise_dir / fname
            if not src.exists():
                raise FileNotFoundError(f"Missing required harness file: {src}")
            shutil.copy(src, tmp_path / fname)

        # Copy reference implementation as sublist.sql
        shutil.copy(example_sql, tmp_path / "sublist.sql")

        # Execute sqlite3 -bail
        proc = subprocess.run(
            ["sqlite3", "-bail"],
            input=".read sublist_test.sql\n",
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )

        output_json_path = tmp_path / "output.json"
        if not output_json_path.exists():
            raise RuntimeError(
                f"output.json was not generated.\n"
                f"Exit code: {proc.returncode}\n"
                f"Stdout: {proc.stdout}\n"
                f"Stderr: {proc.stderr}"
            )

        with open(output_json_path, "r", encoding="utf-8") as f:
            test_results = json.load(f)

        total_cases = len(test_results)
        passed_cases = sum(1 for item in test_results if item.get("status") == "pass")
        failed_cases = total_cases - passed_cases

        return {
            "command": "sqlite3 -bail < sublist_test.sql",
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "total_canonical_cases": total_cases,
            "passed_count": passed_cases,
            "failed_count": failed_cases,
            "pass_percentage": f"{(passed_cases / total_cases * 100):.1f}%" if total_cases > 0 else "0.0%",
            "cases": test_results,
        }


def main():
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    os.chdir(repo_root)

    print("=" * 70)
    print("Task R08-T020: Sublist Contract & Decision Table Verification")
    print("=" * 70)

    # 1. Environment & Git details
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    git_branch = get_cmd_output(["git", "branch", "--show-current"])
    git_commit = get_cmd_output(["git", "rev-parse", "HEAD"])
    sqlite_version = get_cmd_output(["sqlite3", "--version"])
    py_version = sys.version.replace("\n", " ")
    os_platform = platform.platform()
    machine_arch = platform.machine()

    print(f"Timestamp (UTC): {timestamp}")
    print(f"Git Branch:      {git_branch}")
    print(f"Git Commit:      {git_commit}")
    print(f"Python:          {py_version}")
    print(f"SQLite3 CLI:     {sqlite_version}")
    print(f"OS Platform:     {os_platform} ({machine_arch})")
    print("-" * 70)

    # 2. Stub integrity verification before running tests
    stub_path = repo_root / "exercises" / "practice" / "sublist" / "sublist.sql"
    if not stub_path.exists():
        sys.exit(f"Error: Learner stub missing at {stub_path}")
    stub_sha_initial = compute_sha256(stub_path)
    print(f"Learner stub initial SHA-256: {stub_sha_initial}")

    # 3. Direct isolated test execution against .meta/example.sql
    print(f"\nTesting Reference Implementation (.meta/example.sql)...")
    test_result = run_isolated_test(repo_root)
    print(f"  Total Cases:  {test_result['total_canonical_cases']}")
    print(f"  Passed:       {test_result['passed_count']}")
    print(f"  Failed:       {test_result['failed_count']}")
    print(f"  Success Rate: {test_result['pass_percentage']}")

    if test_result["failed_count"] > 0 or test_result["exit_code"] != 0:
        print("[FAIL] Reference implementation failed test cases!")
        sys.exit(1)

    # 4. Stub integrity verification after tests
    stub_sha_final = compute_sha256(stub_path)
    print(f"\nLearner stub post-test SHA-256: {stub_sha_final}")
    stub_untouched = (stub_sha_initial == stub_sha_final)
    if not stub_untouched:
        print("[FAIL] Learner stub was modified during testing!")
        sys.exit(1)
    print("[PASS] Learner stub hash integrity confirmed untouched.")

    # 5. Generate evidence.json
    work_dir = repo_root / "work" / "R08-T020"
    work_dir.mkdir(parents=True, exist_ok=True)

    evidence_data = {
        "task_id": "R08-T020",
        "timestamp": timestamp,
        "environment": {
            "platform": os_platform,
            "architecture": machine_arch,
            "python_version": py_version,
            "sqlite3_version": sqlite_version,
        },
        "git": {
            "branch": git_branch,
            "commit": git_commit,
        },
        "stub_verification": {
            "file": str(stub_path.relative_to(repo_root)),
            "sha256_before": stub_sha_initial,
            "sha256_after": stub_sha_final,
            "untouched": stub_untouched,
        },
        "reference_implementation": test_result,
        "all_checks_passed": True,
    }

    evidence_file = work_dir / "evidence.json"
    with open(evidence_file, "w", encoding="utf-8") as f:
        json.dump(evidence_data, f, indent=2)
    print(f"Generated evidence artifact: {evidence_file.relative_to(repo_root)}")

    # 6. Generate versions.txt
    versions_file = work_dir / "versions.txt"
    with open(versions_file, "w", encoding="utf-8") as f:
        f.write(f"Task: R08-T020\n")
        f.write(f"Timestamp (UTC): {timestamp}\n")
        f.write(f"Git Branch: {git_branch}\n")
        f.write(f"Git Commit: {git_commit}\n")
        f.write(f"OS Platform: {os_platform}\n")
        f.write(f"Architecture: {machine_arch}\n")
        f.write(f"Python Version: {py_version}\n")
        f.write(f"SQLite CLI Version: {sqlite_version}\n")
    print(f"Generated versions artifact: {versions_file.relative_to(repo_root)}")

    print("\n" + "=" * 70)
    print("ALL VERIFICATION CHECKS PASSED SUCCESSFULLY (Exit 0)")
    print("=" * 70)


if __name__ == "__main__":
    main()
