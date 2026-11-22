#!/usr/bin/env python3
"""
Automated check script for Task R08-T012 (secret-handshake verification).

Steps performed:
1. Verifies the learner stub `exercises/practice/secret-handshake/secret-handshake.sql`
   and computes its SHA-256 before running any checks.
2. Invokes `tools/course_checks/r08-t012.py` as a child process and asserts exit code 0.
3. Runs the test suite against the reference implementation in an isolated temporary copy
   to verify child exit code, test counts, and pass status for all cases in output.json.
4. Asserts that the original learner stub remains completely untouched (SHA-256 before == after).
5. Gathers environment versions and test outputs into:
   - `work/R08-T012/versions.txt`
   - `work/R08-T012/evidence.json`
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


def main():
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    work_dir = repo_root / "work" / "R08-T012"
    work_dir.mkdir(parents=True, exist_ok=True)

    exercise_dir = repo_root / "exercises" / "practice" / "secret-handshake"
    stub_file = exercise_dir / "secret-handshake.sql"
    runner_script = repo_root / "tools" / "course_checks" / "r08-t012.py"

    print("=== Task R08-T012 Automated Verification ===")
    print(f"Repo Root: {repo_root}")
    print(f"Runner Script: {runner_script}")

    # 1. Verify original learner stub existence and compute SHA256 before
    assert stub_file.exists(), f"Learner stub {stub_file} does not exist"
    sha256_before = compute_sha256(stub_file)
    print(f"Learner stub SHA256 (before): {sha256_before}")

    # 2. Check that tools/course_checks/r08-t012.py successfully runs and passes
    assert runner_script.exists(), f"Runner script {runner_script} does not exist"
    print(f"Executing course check runner: {runner_script}")
    runner_proc = subprocess.run(
        [sys.executable, str(runner_script), "--json"],
        capture_output=True,
        text=True
    )
    print(f"Course check runner exited with code: {runner_proc.returncode}")
    assert runner_proc.returncode == 0, (
        f"tools/course_checks/r08-t012.py failed with code {runner_proc.returncode}.\n"
        f"Stdout: {runner_proc.stdout}\nStderr: {runner_proc.stderr}"
    )

    runner_data = json.loads(runner_proc.stdout)
    assert runner_data.get("status") == "PASS", "Runner did not report status PASS"

    # 3. Verify isolated execution against example.sql and examine output.json
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = pathlib.Path(tmp_dir_str)
        temp_exercise = tmp_dir / "secret-handshake"
        shutil.copytree(exercise_dir, temp_exercise)

        temp_stub = temp_exercise / "secret-handshake.sql"
        temp_example = temp_exercise / ".meta" / "example.sql"
        assert temp_example.exists(), f"Example file {temp_example} missing"
        shutil.copyfile(temp_example, temp_stub)

        cmd = "sqlite3 -bail < secret-handshake_test.sql"
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=temp_exercise,
            capture_output=True,
            text=True
        )

        child_exit_code = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
        print(f"Test suite process exited with code: {child_exit_code}")
        assert child_exit_code == 0, f"Test suite failed with code {child_exit_code}.\nStderr: {stderr}"

        output_json_path = temp_exercise / "output.json"
        assert output_json_path.exists(), f"Expected {output_json_path} to exist"

        with open(output_json_path, "r", encoding="utf-8") as f:
            test_results = json.load(f)

        total_cases = len(test_results)
        print(f"Total test cases executed: {total_cases}")
        assert total_cases == 11, f"Expected 11 canonical test cases, found {total_cases}"

        passed_cases = []
        failed_cases = []
        for case in test_results:
            desc = case.get("description", "unknown")
            status = case.get("status", "unknown")
            if status == "pass":
                passed_cases.append(desc)
            else:
                failed_cases.append((desc, case.get("message", "")))

        print(f"Passed cases: {len(passed_cases)}/11")
        assert len(failed_cases) == 0, f"Found {len(failed_cases)} failing cases: {failed_cases}"

    # 4. Verify learner stub secret-handshake.sql is untouched
    sha256_after = compute_sha256(stub_file)
    print(f"Learner stub SHA256 (after):  {sha256_after}")
    assert sha256_before == sha256_after, "Learner stub secret-handshake.sql was modified!"
    print("Assertion verified: Original learner stub is completely untouched.")

    # 5. Collect environment versions
    python_ver = sys.version
    sqlite_cli_ver = get_cmd_output(["sqlite3", "--version"])
    git_branch = get_cmd_output(["git", "branch", "--show-current"])
    git_commit = get_cmd_output(["git", "rev-parse", "HEAD"])
    platform_info = platform.platform()
    machine_arch = platform.machine()
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    versions_content = (
        f"Task: R08-T012\n"
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

    # 6. Write evidence.json
    evidence_data = {
        "task_id": "R08-T012",
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
        "runner_check": {
            "script": "tools/course_checks/r08-t012.py",
            "exit_code": runner_proc.returncode,
            "status": runner_data.get("status"),
            "consistency_active_cases": runner_data.get("consistency", {}).get("active_cases_count"),
        },
        "stub_verification": {
            "file": str(stub_file.relative_to(repo_root)),
            "sha256_before": sha256_before,
            "sha256_after": sha256_after,
            "untouched": sha256_before == sha256_after,
        },
        "execution": {
            "command": cmd,
            "exit_code": child_exit_code,
            "stdout": stdout,
            "stderr": stderr,
        },
        "test_results": {
            "total_canonical_cases": total_cases,
            "passed_count": len(passed_cases),
            "failed_count": len(failed_cases),
            "cases": test_results,
        },
        "status": "PASS"
    }

    evidence_file = work_dir / "evidence.json"
    with open(evidence_file, "w", encoding="utf-8") as f:
        json.dump(evidence_data, f, indent=2)
    print(f"Wrote verification evidence to {evidence_file}")

    print("=== All checks completed successfully ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
