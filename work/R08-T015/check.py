#!/usr/bin/env python3
"""
Automated verification check for Task R08-T015 (difference-of-squares).

Responsibilities:
1. Verify learner stub `exercises/practice/difference-of-squares/difference-of-squares.sql`
   remains untouched (SHA-256 integrity check before and after).
2. Run isolated tests using `tempfile.TemporaryDirectory` with refactored `.meta/example.sql`.
   Assert all 9 canonical cases execute and report "status": "pass".
3. Measure execution time and VDBE statement cost across 3 input sizes: n=1, n=5, n=100.
4. Export `work/R08-T015/evidence.json` and `work/R08-T015/versions.txt`.
"""

import datetime
import hashlib
import json
import os
import pathlib
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time


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


def measure_statement_cost(input_sizes: list[int]) -> dict:
    """
    Measure VDBE opcode count and benchmark execution time across input sizes.
    """
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()

    queries = {
        "squareOfSum": "SELECT {n} * {n} * ({n} + 1) * ({n} + 1) / 4;",
        "sumOfSquares": "SELECT {n} * ({n} + 1) * (2 * {n} + 1) / 6;",
        "differenceOfSquares": "SELECT {n} * ({n} + 1) * (3 * {n} + 2) * ({n} - 1) / 12;",
    }

    metrics = {}

    for n in input_sizes:
        metrics[f"n={n}"] = {}
        for prop, q_template in queries.items():
            query = q_template.format(n=n)
            
            # 1. Opcode count via EXPLAIN
            cursor.execute(f"EXPLAIN {query}")
            opcodes = cursor.fetchall()
            opcode_count = len(opcodes)

            # 2. Timing benchmark (averaged over 20,000 iterations for microsecond precision)
            iterations = 20000
            t0 = time.perf_counter_ns()
            for _ in range(iterations):
                cursor.execute(query)
                cursor.fetchone()
            t1 = time.perf_counter_ns()
            avg_duration_us = (t1 - t0) / (iterations * 1000)

            # 3. Calculate result value
            cursor.execute(query)
            result_val = cursor.fetchone()[0]

            metrics[f"n={n}"][prop] = {
                "n": n,
                "property": prop,
                "result": result_val,
                "vdbe_opcode_count": opcode_count,
                "complexity_class": "O(1)",
                "avg_execution_time_us": round(avg_duration_us, 4)
            }

    conn.close()
    return metrics


def main():
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    work_dir = repo_root / "work" / "R08-T015"
    work_dir.mkdir(parents=True, exist_ok=True)

    exercise_dir = repo_root / "exercises" / "practice" / "difference-of-squares"
    stub_file = exercise_dir / "difference-of-squares.sql"
    example_file = exercise_dir / ".meta" / "example.sql"

    print("=== Task R08-T015 Automated Verification ===")
    print(f"Repo Root: {repo_root}")
    print(f"Exercise Directory: {exercise_dir}")

    # Step 1: Verify learner stub exists and compute SHA256 before
    assert stub_file.exists(), f"Learner stub {stub_file} does not exist"
    sha256_before = compute_sha256(stub_file)
    print(f"Learner stub SHA256 (before): {sha256_before}")

    # Step 2: Isolated test execution in temporary directory
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = pathlib.Path(tmp_dir_str)
        temp_exercise = tmp_dir / "difference-of-squares"
        print(f"Cloning {exercise_dir} to temporary copy: {temp_exercise}")
        shutil.copytree(exercise_dir, temp_exercise)

        # Replace difference-of-squares.sql with .meta/example.sql in temporary copy only
        temp_stub = temp_exercise / "difference-of-squares.sql"
        temp_example = temp_exercise / ".meta" / "example.sql"
        shutil.copyfile(temp_example, temp_stub)

        # Run sqlite3 -bail < difference-of-squares_test.sql
        cmd = "sqlite3 -bail < difference-of-squares_test.sql"
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
        assert child_exit_code == 0, f"Command '{cmd}' failed with code {child_exit_code}.\nStderr: {stderr}"

        # Parse output.json and verify all 9 cases pass
        output_json_path = temp_exercise / "output.json"
        assert output_json_path.exists(), f"Expected {output_json_path} was not created"

        with open(output_json_path, "r", encoding="utf-8") as f:
            test_results = json.load(f)

        total_cases = len(test_results)
        print(f"Total test cases executed: {total_cases}")
        assert total_cases == 9, f"Expected 9 canonical test cases, found {total_cases}"

        passed_cases = []
        failed_cases = []
        for case in test_results:
            name = case.get("name", "unknown")
            status = case.get("status", "unknown")
            if status == "pass":
                passed_cases.append(name)
            else:
                failed_cases.append((name, case.get("message", "")))

        print(f"Passed cases: {len(passed_cases)}/9 (100%)")
        assert len(failed_cases) == 0, f"Found {len(failed_cases)} failures: {failed_cases}"

    # Step 3: Measure execution time and statement cost across 3 input sizes (n=1, n=5, n=100)
    print("\n--- Measuring Statement Cost & Execution Time (n=1, n=5, n=100) ---")
    cost_metrics = measure_statement_cost([1, 5, 100])
    for size_key, prop_dict in cost_metrics.items():
        print(f"\n{size_key}:")
        for prop, data in prop_dict.items():
            print(f"  {prop}: VDBE opcodes={data['vdbe_opcode_count']}, Result={data['result']}, AvgTime={data['avg_execution_time_us']} us")

    # Step 4: Verify learner solution hash integrity
    sha256_after = compute_sha256(stub_file)
    print(f"\nLearner stub SHA256 (after):  {sha256_after}")
    assert sha256_before == sha256_after, "Learner stub difference-of-squares.sql was modified!"
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
        f"Task: R08-T015\n"
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
        "task_id": "R08-T015",
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
            "command": "sqlite3 -bail < difference-of-squares_test.sql",
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
        "statement_cost_measurements": {
            "complexity": "O(1) time, O(1) space",
            "sizes": cost_metrics,
            "overflow_thresholds": {
                "sqlite_integer_type": "64-bit signed integer (INT64)",
                "int64_max": "9,223,372,036,854,775,807",
                "squareOfSum_max_n": 55108,
                "sumOfSquares_max_n": 1664510,
                "differenceOfSquares_max_n": 41876,
            }
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
