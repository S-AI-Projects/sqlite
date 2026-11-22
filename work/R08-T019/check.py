#!/usr/bin/env python3
"""
Automated verification check for Task R08-T019 (atbash-cipher).

Responsibilities:
1. Verify learner starter stub `exercises/practice/atbash-cipher/atbash-cipher.sql` remains untouched.
2. Verify pass path: runner with reference `.meta/example.sql` succeeds with 100% pass status.
3. Verify negative failure path: runner with deliberately broken SQL reports failure.
4. Verify empty / missing output path: runner detects syntax error or absent output and fails gracefully.
5. Verify process timeout path: runner catches runaway loops via timeout guard and terminates cleanly.
6. Assert learner stub SHA-256 integrity remains intact across all scenarios.
7. Export `work/R08-T019/evidence.json` and `work/R08-T019/versions.txt`.
8. Exit with status code 0 on complete success.
"""

import datetime
import hashlib
import json
import os
import pathlib
import platform
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


def main():
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    os.chdir(repo_root)

    print("=" * 75)
    print("Task R08-T019: Atbash-Cipher Multi-Scenario Runner Verification")
    print("=" * 75)

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
    print("-" * 75)

    exercise_dir = repo_root / "exercises" / "practice" / "atbash-cipher"
    stub_path = exercise_dir / "atbash-cipher.sql"
    if not stub_path.exists():
        sys.exit(f"Error: Learner stub missing at {stub_path}")

    stub_sha_initial = compute_sha256(stub_path)
    print(f"Learner stub initial SHA-256: {stub_sha_initial}\n")

    runner_script = repo_root / "tools" / "course_checks" / "r08-t019.py"
    if not runner_script.exists():
        sys.exit(f"Error: Course check runner missing at {runner_script}")

    scenario_results = {}

    # ---------------------------------------------------------
    # Scenario 1: Pass Path (Reference Solution)
    # ---------------------------------------------------------
    print("[Scenario 1] Testing Pass Path (.meta/example.sql)...")
    proc_pass = subprocess.run(
        [sys.executable, str(runner_script), "--json"],
        capture_output=True,
        text=True,
    )
    pass_report = json.loads(proc_pass.stdout)
    print(f"  Status:       {pass_report['status'].upper()}")
    print(f"  Exit Code:    {pass_report['exit_code']}")
    print(f"  Test Cases:   {pass_report['total_cases']} total, {pass_report['passed_cases']} passed")
    print(f"  Success Rate: {pass_report['pass_percentage']}")

    if pass_report["status"] != "pass" or pass_report["failed_cases"] != 0:
        print("[FAIL] Pass path did not achieve 100% pass status!")
        sys.exit(1)
    scenario_results["pass_path"] = {
        "status": pass_report["status"],
        "exit_code": pass_report["exit_code"],
        "total_cases": pass_report["total_cases"],
        "passed_cases": pass_report["passed_cases"],
        "verified": True,
    }
    print("  -> Pass path verified successfully.\n")

    # ---------------------------------------------------------
    # Scenario 2: Negative Failure Path (Broken SQL)
    # ---------------------------------------------------------
    print("[Scenario 2] Testing Negative Failure Path (Deliberately Broken SQL)...")
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as f_broken:
        f_broken.write("UPDATE \"atbash-cipher\" SET result = 'broken_incorrect_answer';\n")
        broken_sql_path = f_broken.name

    try:
        proc_fail = subprocess.run(
            [sys.executable, str(runner_script), "--solution", broken_sql_path, "--json"],
            capture_output=True,
            text=True,
        )
        fail_report = json.loads(proc_fail.stdout)
        print(f"  Status:       {fail_report['status'].upper()}")
        print(f"  Exit Code:    {fail_report['exit_code']}")
        print(f"  Failed Cases: {fail_report['failed_cases']} (Expected > 0)")

        if fail_report["status"] != "fail" or fail_report["failed_cases"] == 0:
            print("[FAIL] Broken SQL was not flagged as failure!")
            sys.exit(1)
        scenario_results["negative_failure_path"] = {
            "status": fail_report["status"],
            "failed_cases": fail_report["failed_cases"],
            "total_cases": fail_report["total_cases"],
            "verified": True,
        }
        print("  -> Negative failure path verified successfully.\n")
    finally:
        if os.path.exists(broken_sql_path):
            os.remove(broken_sql_path)

    # ---------------------------------------------------------
    # Scenario 3: Empty / Missing Test Output Path (Syntax Error)
    # ---------------------------------------------------------
    print("[Scenario 3] Testing Missing/Empty Output Path (Syntax Error Crash)...")
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as f_syntax:
        f_syntax.write("SYNTAX ERROR INVALID SQL STATEMENTS HERE;\n")
        syntax_sql_path = f_syntax.name

    try:
        proc_syntax = subprocess.run(
            [sys.executable, str(runner_script), "--solution", syntax_sql_path, "--json"],
            capture_output=True,
            text=True,
        )
        syntax_report = json.loads(proc_syntax.stdout)
        print(f"  Status:       {syntax_report['status'].upper()}")
        print(f"  Exit Code:    {syntax_report['exit_code']} (Expected non-zero)")
        print(f"  Parse Error:  {syntax_report.get('parse_error')}")

        if syntax_report["status"] != "fail" or syntax_report["exit_code"] == 0:
            print("[FAIL] Syntax error crash was not flagged as failure!")
            sys.exit(1)
        scenario_results["empty_or_missing_output_path"] = {
            "status": syntax_report["status"],
            "exit_code": syntax_report["exit_code"],
            "parse_error": syntax_report.get("parse_error"),
            "verified": True,
        }
        print("  -> Missing/empty output path verified successfully.\n")
    finally:
        if os.path.exists(syntax_sql_path):
            os.remove(syntax_sql_path)

    # ---------------------------------------------------------
    # Scenario 4: Process Timeout Path (Infinite Recursion)
    # ---------------------------------------------------------
    print("[Scenario 4] Testing Process Timeout Path (Infinite Recursion CTE)...")
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as f_timeout:
        # Recursive CTE that runs indefinitely
        f_timeout.write(
            "WITH RECURSIVE inf(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM inf) "
            "UPDATE \"atbash-cipher\" SET result = (SELECT count(*) FROM inf);\n"
        )
        timeout_sql_path = f_timeout.name

    try:
        # Run with short timeout of 1.5 seconds
        proc_timeout = subprocess.run(
            [sys.executable, str(runner_script), "--solution", timeout_sql_path, "--timeout", "1.5", "--json"],
            capture_output=True,
            text=True,
        )
        timeout_report = json.loads(proc_timeout.stdout)
        print(f"  Status:       {timeout_report['status'].upper()}")
        print(f"  Timed Out:    {timeout_report.get('timed_out')} (Expected True)")

        if timeout_report["status"] != "fail" or not timeout_report.get("timed_out"):
            print("[FAIL] Process timeout was not detected!")
            sys.exit(1)
        scenario_results["process_timeout_path"] = {
            "status": timeout_report["status"],
            "timed_out": timeout_report.get("timed_out"),
            "verified": True,
        }
        print("  -> Process timeout path verified successfully.\n")
    finally:
        if os.path.exists(timeout_sql_path):
            os.remove(timeout_sql_path)

    # ---------------------------------------------------------
    # Final Integrity Check of Learner Starter Stub
    # ---------------------------------------------------------
    stub_sha_final = compute_sha256(stub_path)
    print(f"Learner stub post-test SHA-256: {stub_sha_final}")
    stub_untouched = (stub_sha_initial == stub_sha_final)
    if not stub_untouched:
        print("[FAIL] Learner stub was modified during testing!")
        sys.exit(1)
    print("[PASS] Learner stub hash integrity confirmed untouched.")

    # ---------------------------------------------------------
    # Generate Audit Artifacts
    # ---------------------------------------------------------
    work_dir = repo_root / "work" / "R08-T019"
    work_dir.mkdir(parents=True, exist_ok=True)

    evidence_data = {
        "task_id": "R08-T019",
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
        "scenarios": scenario_results,
        "all_checks_passed": True,
    }

    evidence_file = work_dir / "evidence.json"
    with open(evidence_file, "w", encoding="utf-8") as f:
        json.dump(evidence_data, f, indent=2)
    print(f"\nGenerated evidence artifact: {evidence_file.relative_to(repo_root)}")

    versions_file = work_dir / "versions.txt"
    with open(versions_file, "w", encoding="utf-8") as f:
        f.write(f"Task: R08-T019\n")
        f.write(f"Timestamp (UTC): {timestamp}\n")
        f.write(f"Git Branch: {git_branch}\n")
        f.write(f"Git Commit: {git_commit}\n")
        f.write(f"OS Platform: {os_platform}\n")
        f.write(f"Architecture: {machine_arch}\n")
        f.write(f"Python Version: {py_version}\n")
        f.write(f"SQLite CLI Version: {sqlite_version}\n")
    print(f"Generated versions artifact: {versions_file.relative_to(repo_root)}")

    print("\n" + "=" * 75)
    print("ALL 4 SCENARIOS PASSED VERIFICATION (Exit 0)")
    print("=" * 75)


if __name__ == "__main__":
    main()
