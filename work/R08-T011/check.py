#!/usr/bin/env python3
"""
Automated check script for Task R08-T011 (Transpose exercise).

Steps performed:
1. Verifies the learner stub `exercises/practice/transpose/transpose.sql` and computes its SHA256 before testing.
2. Clones `exercises/practice/transpose` into a temporary directory using `tempfile.TemporaryDirectory`.
3. Replaces `transpose.sql` with `.meta/example.sql` in the temporary copy only.
4. Executes: `sqlite3 -bail < transpose_test.sql`.
5. Parses `output.json` from the temporary copy and asserts that all 12 canonical test cases pass.
6. Asserts child process exit code is 0.
7. Verifies that the original learner stub `exercises/practice/transpose/transpose.sql` is completely untouched (SHA256 match).
8. Documents rationales for the three UUIDs in `work/R08-T011/rationales.md`.
9. Gathers environment versions and test outputs into `work/R08-T011/evidence.json` and `work/R08-T011/versions.txt`.
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


RATIONALES_MD = """# Rationales for Transpose Canonical Test UUIDs

This document details the rationales and SQLite operational behaviors for three foundational canonical test cases in `exercises/practice/transpose`.

---

## 1. UUID: `404b7262-c050-4df0-a2a2-0cb06cd6a821`
- **Description**: `empty string`
- **Input**: `""`
- **Expected Output**: `""`
- **Explanatory Rationale**:
  * Input text is empty.
  * SQLite CTE recursion terminates at length 0, producing an empty result set.
  * In the reference implementation (`example.sql`), an explicit `UPDATE transpose SET result = '' WHERE lines = '';` or recursive base termination condition ensures that no `NULL` value or empty line artifact is generated.
  * Verifying this case ensures that recursive SQL statements do not enter infinite loops when scanning zero-length strings.

---

## 2. UUID: `a89ce8a3-c940-4703-a688-3ea39412fbcb`
- **Description**: `two characters in a row`
- **Input**: `"A1"`
- **Expected Output**: `"A\n1"`
- **Explanatory Rationale**:
  * 1 row with 2 columns transposes into 2 rows of 1 column each.
  * SQLite character extraction uses `SUBSTR()` (specifically `SUBSTR(string, 1, 1)` to extract the current character and `SUBSTR(string, 2)` to step the recursive remainder).
  * This case confirms that single-line horizontal string decomposition works properly in SQLite before multi-line aggregation.

---

## 3. UUID: `855bb6ae-4180-457c-abd0-ce489803ce98`
- **Description**: `two characters in a column`
- **Input**: `"A\n1"`
- **Expected Output**: `"A1"`
- **Explanatory Rationale**:
  * 2 rows with 1 column each transpose into 1 row of 2 columns.
  * String aggregation in SQLite uses `GROUP_CONCAT()` (with an empty separator `GROUP_CONCAT(..., '')`) or the string concatenation operator `||`.
  * This validates that character tokens extracted from separate vertical rows can be aggregated horizontally into a single transposed output row.
"""


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
    work_dir = repo_root / "work" / "R08-T011"
    work_dir.mkdir(parents=True, exist_ok=True)

    exercise_dir = repo_root / "exercises" / "practice" / "transpose"
    stub_file = exercise_dir / "transpose.sql"
    example_file = exercise_dir / ".meta" / "example.sql"

    print("=== Task R08-T011 Automated Verification ===")
    print(f"Repo Root: {repo_root}")
    print(f"Exercise Directory: {exercise_dir}")

    # 1. Check stub SHA256 before execution
    assert stub_file.exists(), f"Learner stub {stub_file} does not exist"
    sha256_before = compute_sha256(stub_file)
    print(f"Original stub SHA256 (before): {sha256_before}")

    # 2. Use tempfile.TemporaryDirectory to clone exercises/practice/transpose
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = pathlib.Path(tmp_dir_str)
        temp_exercise = tmp_dir / "transpose"
        print(f"Cloning {exercise_dir} to temporary copy: {temp_exercise}")
        shutil.copytree(exercise_dir, temp_exercise)

        # 3. Replace transpose.sql with .meta/example.sql in temporary copy only
        temp_stub = temp_exercise / "transpose.sql"
        temp_example = temp_exercise / ".meta" / "example.sql"
        assert temp_example.exists(), f"Example solution {temp_example} does not exist"

        print(f"Replacing temporary {temp_stub} with {temp_example}")
        shutil.copyfile(temp_example, temp_stub)

        # 4. Run: sqlite3 -bail < transpose_test.sql
        cmd = "sqlite3 -bail < transpose_test.sql"
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

        # 5. Verify child exit code is 0
        assert child_exit_code == 0, f"Command '{cmd}' failed with code {child_exit_code}.\nStderr: {stderr}"

        # 6. Parse output.json and verify all 12 canonical cases pass
        output_json_path = temp_exercise / "output.json"
        assert output_json_path.exists(), f"Expected output file {output_json_path} was not created"

        with open(output_json_path, "r", encoding="utf-8") as f:
            test_results = json.load(f)

        total_cases = len(test_results)
        print(f"Total test cases executed: {total_cases}")
        assert total_cases == 12, f"Expected 12 canonical test cases, found {total_cases}"

        passed_cases = []
        failed_cases = []
        for case in test_results:
            desc = case.get("description", "unknown")
            status = case.get("status", "unknown")
            if status == "pass":
                passed_cases.append(desc)
            else:
                failed_cases.append((desc, case.get("message", "")))

        print(f"Passed cases: {len(passed_cases)}/12")
        if failed_cases:
            for desc, msg in failed_cases:
                print(f"  FAILED: {desc} -> {msg}")
            raise AssertionError(f"Not all test cases passed: {len(failed_cases)} failures")

    # 7. Ensure the learner stub exercises/practice/transpose/transpose.sql remains completely untouched
    sha256_after = compute_sha256(stub_file)
    print(f"Original stub SHA256 (after):  {sha256_after}")
    assert sha256_before == sha256_after, "Learner stub transpose.sql was modified!"
    print("Assertion verified: Original learner stub is completely untouched.")

    # 8. Create work/R08-T011/rationales.md documenting the three UUIDs
    rationales_file = work_dir / "rationales.md"
    with open(rationales_file, "w", encoding="utf-8") as f:
        f.write(RATIONALES_MD)
    print(f"Wrote rationales documentation to {rationales_file}")

    # 9. Collect environment versions
    python_ver = sys.version
    sqlite_cli_ver = get_cmd_output(["sqlite3", "--version"])
    git_branch = get_cmd_output(["git", "branch", "--show-current"])
    git_commit = get_cmd_output(["git", "rev-parse", "HEAD"])
    platform_info = platform.platform()
    machine_arch = platform.machine()
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    versions_content = (
        f"Task: R08-T011\n"
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

    # 10. Collect evidence.json
    evidence_data = {
        "task_id": "R08-T011",
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
            "command": "sqlite3 -bail < transpose_test.sql",
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
