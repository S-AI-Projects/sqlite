#!/usr/bin/env python3
"""
Automated verification check for Task R08-T014 (say exercise).

Responsibilities:
1. Verify learner stub `exercises/practice/say/say.sql` exists and compute its SHA-256 hash.
2. Set up an isolated runner copying `exercises/practice/say` to a temporary directory.
3. Run `sqlite3 -bail < say_test.sql` using the refactored `.meta/example.sql`.
4. Parse `output.json`, verify all 19 test cases pass (100% "pass" entries), and child exit code is 0.
5. Verify learner solution hash integrity (assert SHA-256 before == after).
6. Collect environment versions and test outputs into:
   - `work/R08-T014/versions.txt`
   - `work/R08-T014/evidence.json`
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
    work_dir = repo_root / "work" / "R08-T014"
    work_dir.mkdir(parents=True, exist_ok=True)

    exercise_dir = repo_root / "exercises" / "practice" / "say"
    stub_file = exercise_dir / "say.sql"
    example_file = exercise_dir / ".meta" / "example.sql"

    print("=== Task R08-T014 Automated Verification ===")
    print(f"Repo Root: {repo_root}")
    print(f"Exercise Directory: {exercise_dir}")

    # 1. Verify learner stub exists and compute SHA256 before
    assert stub_file.exists(), f"Learner stub {stub_file} does not exist"
    sha256_before = compute_sha256(stub_file)
    print(f"Learner stub SHA256 (before): {sha256_before}")

    # 2. Check refactored example.sql exists
    assert example_file.exists(), f"Refactored example {example_file} does not exist"

    # 3. Isolated test execution in temporary directory
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = pathlib.Path(tmp_dir_str)
        temp_exercise = tmp_dir / "say"
        print(f"Cloning {exercise_dir} to temporary copy: {temp_exercise}")
        shutil.copytree(exercise_dir, temp_exercise)

        # Replace say.sql with .meta/example.sql in temporary copy only
        temp_stub = temp_exercise / "say.sql"
        temp_example = temp_exercise / ".meta" / "example.sql"
        shutil.copyfile(temp_example, temp_stub)

        # Run sqlite3 -bail < say_test.sql
        cmd = "sqlite3 -bail < say_test.sql"
        print(f"Executing: {cmd} in {temp_exercise}")
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
        print(f"Process exited with code: {child_exit_code}")

        # Assert child exit code is 0
        assert child_exit_code == 0, f"Command '{cmd}' failed with code {child_exit_code}.\nStderr: {stderr}"

        # Parse output.json and verify all cases pass
        output_json_path = temp_exercise / "output.json"
        assert output_json_path.exists(), f"Expected {output_json_path} was not created"

        with open(output_json_path, "r", encoding="utf-8") as f:
            test_results = json.load(f)

        total_cases = len(test_results)
        print(f"Total test cases executed: {total_cases}")
        assert total_cases == 19, f"Expected 19 canonical test cases, found {total_cases}"

        passed_cases = []
        failed_cases = []
        for case in test_results:
            desc = case.get("description", "unknown")
            status = case.get("status", "unknown")
            if status == "pass":
                passed_cases.append(desc)
            else:
                failed_cases.append((desc, case.get("message", "")))

        print(f"Passed cases: {len(passed_cases)}/19 (100%)")
        assert len(failed_cases) == 0, f"Found {len(failed_cases)} failures: {failed_cases}"

    # 4. Verify learner solution hash integrity
    sha256_after = compute_sha256(stub_file)
    print(f"Learner stub SHA256 (after):  {sha256_after}")
    assert sha256_before == sha256_after, "Learner stub say.sql was modified!"
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
        f"Task: R08-T014\n"
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

    # 6. Export evidence.json
    evidence_data = {
        "task_id": "R08-T014",
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
        "execution": {
            "command": "sqlite3 -bail < say_test.sql",
            "exit_code": child_exit_code,
            "stdout": stdout,
            "stderr": stderr,
        },
        "test_results": {
            "total_canonical_cases": total_cases,
            "passed_count": len(passed_cases),
            "failed_count": len(failed_cases),
            "pass_percentage": "100%",
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
