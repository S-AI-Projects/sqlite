#!/usr/bin/env python3
"""
Reusable isolated test runner and configuration validator for atbash-cipher.

Responsibilities:
1. Validate `config.json` schema and verify all referenced files exist.
2. Check learner starter file SHA-256 hashes before and after test execution.
3. Execute test suite in an isolated `tempfile.TemporaryDirectory`.
4. Replace student solution with `.meta/example.sql` (or custom `--solution`).
5. Execute `sqlite3 -bail` with timeout protection.
6. Verify `output.json` validity and test pass/fail counts.
"""

import argparse
import hashlib
import json
import os
import pathlib
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


def validate_config(exercise_dir: pathlib.Path) -> dict:
    """
    Validate config.json schema and assert all referenced files exist on disk.
    """
    config_path = exercise_dir / ".meta" / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Missing config.json at {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config_data = json.load(f)

    if "files" not in config_data:
        raise KeyError("config.json missing required 'files' key")

    files_section = config_data["files"]
    for role in ["solution", "test", "example"]:
        if role not in files_section:
            raise KeyError(f"config.json missing required files role: '{role}'")
        file_list = files_section[role]
        if not isinstance(file_list, list) or len(file_list) == 0:
            raise ValueError(f"Role '{role}' must be a non-empty list of paths")
        for rel_path in file_list:
            full_path = exercise_dir / rel_path
            if not full_path.exists():
                raise FileNotFoundError(f"File for role '{role}' not found: {full_path}")

    return config_data


def run_isolated_test(
    exercise_dir: pathlib.Path,
    solution_path: pathlib.Path | None = None,
    timeout: float = 15.0,
) -> dict:
    """
    Execute atbash-cipher test suite in an isolated temporary directory.
    """
    learner_stub = exercise_dir / "atbash-cipher.sql"
    if not learner_stub.exists():
        raise FileNotFoundError(f"Learner stub missing at {learner_stub}")

    # Compute pre-execution SHA-256
    sha_pre = compute_sha256(learner_stub)

    if solution_path is None:
        solution_path = exercise_dir / ".meta" / "example.sql"
    if not solution_path.exists():
        raise FileNotFoundError(f"Target solution file not found: {solution_path}")

    required_assets = [
        "create_fixture.sql",
        "create_test_table.sql",
        "atbash-cipher_test.sql",
        "data.csv",
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = pathlib.Path(tmp_dir)

        # Copy test harness files
        for asset in required_assets:
            src = exercise_dir / asset
            if not src.exists():
                raise FileNotFoundError(f"Missing required harness asset: {src}")
            shutil.copy(src, tmp_path / asset)

        # Copy the solution under test as atbash-cipher.sql
        shutil.copy(solution_path, tmp_path / "atbash-cipher.sql")

        try:
            proc = subprocess.run(
                ["sqlite3", "-bail"],
                input=".read atbash-cipher_test.sql\n",
                capture_output=True,
                text=True,
                cwd=tmp_path,
                timeout=timeout,
            )
            timed_out = False
            exit_code = proc.returncode
            stdout = proc.stdout
            stderr = proc.stderr
        except subprocess.TimeoutExpired as e:
            timed_out = True
            exit_code = -1
            stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")

        output_json_path = tmp_path / "output.json"
        has_output_json = output_json_path.exists()
        cases = []
        parse_error = None

        if has_output_json:
            try:
                with open(output_json_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        cases = json.loads(content)
                    else:
                        parse_error = "output.json is empty"
            except Exception as ex:
                parse_error = f"Failed to parse output.json: {ex}"
        else:
            parse_error = "output.json was not generated"

    # Compute post-execution SHA-256
    sha_post = compute_sha256(learner_stub)
    stub_untouched = (sha_pre == sha_post)

    total_cases = len(cases)
    passed_cases = sum(1 for c in cases if c.get("status") == "pass") if isinstance(cases, list) else 0
    failed_cases = total_cases - passed_cases if isinstance(cases, list) else 0

    success = (
        not timed_out
        and exit_code == 0
        and parse_error is None
        and total_cases > 0
        and failed_cases == 0
        and stub_untouched
    )

    return {
        "status": "pass" if success else "fail",
        "solution_tested": str(solution_path),
        "timed_out": timed_out,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "parse_error": parse_error,
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
        "pass_percentage": f"{(passed_cases / total_cases * 100):.1f}%" if total_cases > 0 else "0.0%",
        "stub_verification": {
            "file": str(learner_stub),
            "sha256_before": sha_pre,
            "sha256_after": sha_post,
            "untouched": stub_untouched,
        },
        "cases": cases if isinstance(cases, list) else [],
    }


def main():
    parser = argparse.ArgumentParser(description="Isolated test runner for atbash-cipher")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--solution", type=str, default=None, help="Custom solution SQL path")
    parser.add_argument("--timeout", type=float, default=15.0, help="Subprocess timeout in seconds")
    parser.add_argument("--exercise-dir", type=str, default=None, help="Path to atbash-cipher directory")

    args = parser.parse_args()

    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    if args.exercise_dir:
        exercise_dir = pathlib.Path(args.exercise_dir).resolve()
    else:
        exercise_dir = repo_root / "exercises" / "practice" / "atbash-cipher"

    try:
        config_data = validate_config(exercise_dir)
        sol_path = pathlib.Path(args.solution).resolve() if args.solution else None
        report = run_isolated_test(exercise_dir, solution_path=sol_path, timeout=args.timeout)
        report["config"] = {
            "blurb": config_data.get("blurb"),
            "authors": config_data.get("authors"),
        }

        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print("=" * 65)
            print("Atbash-Cipher Isolated Test Runner")
            print("=" * 65)
            print(f"Status:       {report['status'].upper()}")
            print(f"Solution:     {report['solution_tested']}")
            print(f"Exit Code:    {report['exit_code']}")
            print(f"Test Cases:   {report['total_cases']} total, {report['passed_cases']} passed, {report['failed_cases']} failed")
            print(f"Success Rate: {report['pass_percentage']}")
            print(f"Stub Status:  {'UNTOUCHED' if report['stub_verification']['untouched'] else 'MODIFIED'}")
            if report.get("parse_error"):
                print(f"Output Note:  {report['parse_error']}")
            if report.get("timed_out"):
                print("Output Note:  Execution timed out!")
            print("=" * 65)

        if report["status"] != "pass":
            sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Runner failed: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
