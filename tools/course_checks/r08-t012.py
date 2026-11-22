#!/usr/bin/env python3
"""
Automated verification runner for Task R08-T012 (secret-handshake exercise).

Responsibilities:
1. Verify consistency between `exercises/practice/secret-handshake/.meta/tests.toml`
   and `exercises/practice/secret-handshake/create_test_table.sql`.
2. Execute the test suite against `.meta/example.sql` in an isolated temporary copy.
3. Assert that all canonical test cases execute and report "status": "pass".
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib


def verify_tests_toml_consistency(exercise_dir: pathlib.Path, verbose: bool = True) -> dict:
    """
    Verify that tests.toml and create_test_table.sql are completely consistent.
    Returns parsed metadata dict.
    """
    toml_path = exercise_dir / ".meta" / "tests.toml"
    sql_path = exercise_dir / "create_test_table.sql"

    if not toml_path.exists():
        raise FileNotFoundError(f"Missing tests.toml at {toml_path}")
    if not sql_path.exists():
        raise FileNotFoundError(f"Missing create_test_table.sql at {sql_path}")

    with open(toml_path, "rb") as f:
        toml_data = tomllib.load(f)

    # Active test cases in tests.toml
    active_toml = {
        uuid: data["description"]
        for uuid, data in toml_data.items()
        if data.get("include", True)
    }

    # Parse create_test_table.sql VALUES rows: ('<uuid>', '<description>', <number>, '<expected>')
    sql_content = sql_path.read_text(encoding="utf-8")
    row_pattern = re.compile(
        r"'\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\s*',\s*'([^']+)',\s*(\d+),\s*'([^']*)'",
        re.MULTILINE
    )
    sql_matches = row_pattern.findall(sql_content)

    if not sql_matches:
        raise ValueError("Could not parse test records from create_test_table.sql")

    sql_tests = {
        uuid: {
            "description": desc,
            "number": int(num_str),
            "expected": expected
        }
        for uuid, desc, num_str, expected in sql_matches
    }

    # Verify counts
    assert len(active_toml) == len(sql_tests), (
        f"Test count mismatch: tests.toml has {len(active_toml)} active tests, "
        f"but create_test_table.sql has {len(sql_tests)} tests."
    )

    # Verify each UUID and description matches
    for uuid, toml_desc in active_toml.items():
        assert uuid in sql_tests, f"UUID {uuid} from tests.toml is missing in create_test_table.sql"
        sql_desc = sql_tests[uuid]["description"]
        assert toml_desc == sql_desc, (
            f"Description mismatch for UUID {uuid}: tests.toml='{toml_desc}' vs sql='{sql_desc}'"
        )

    if verbose:
        print(f"Consistency check PASSED: {len(active_toml)} tests matched between tests.toml and create_test_table.sql.", file=sys.stderr)
    return {
        "active_cases_count": len(active_toml),
        "cases": sql_tests
    }


def run_test_suite_in_temp_dir(exercise_dir: pathlib.Path, verbose: bool = True) -> dict:
    """
    Run secret-handshake tests against .meta/example.sql in an isolated temporary directory.
    Returns parsed test results from output.json.
    """
    example_file = exercise_dir / ".meta" / "example.sql"
    if not example_file.exists():
        raise FileNotFoundError(f"Missing example solution at {example_file}")

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = pathlib.Path(tmp_dir_str)
        temp_exercise = tmp_dir / "secret-handshake"
        shutil.copytree(exercise_dir, temp_exercise)

        # Replace secret-handshake.sql with .meta/example.sql in temp copy only
        temp_stub = temp_exercise / "secret-handshake.sql"
        temp_example = temp_exercise / ".meta" / "example.sql"
        shutil.copyfile(temp_example, temp_stub)

        # Run sqlite3 -bail < secret-handshake_test.sql
        cmd = "sqlite3 -bail < secret-handshake_test.sql"
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=temp_exercise,
            capture_output=True,
            text=True
        )

        if proc.returncode != 0:
            raise RuntimeError(
                f"sqlite3 execution failed with exit code {proc.returncode}.\n"
                f"Stdout: {proc.stdout}\nStderr: {proc.stderr}"
            )

        output_json_path = temp_exercise / "output.json"
        if not output_json_path.exists():
            raise FileNotFoundError(f"output.json was not created at {output_json_path}")

        with open(output_json_path, "r", encoding="utf-8") as f:
            results = json.load(f)

        assert len(results) > 0, "output.json contains no test results"

        for case in results:
            status = case.get("status")
            desc = case.get("description", "unknown")
            msg = case.get("message", "")
            assert status == "pass", f"Test case '{desc}' failed: {msg}"

        if verbose:
            print(f"Test suite execution PASSED: all {len(results)} cases reported status 'pass'.", file=sys.stderr)
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "total_cases": len(results),
            "results": results
        }


def main():
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    exercise_dir = repo_root / "exercises" / "practice" / "secret-handshake"
    json_mode = "--json" in sys.argv

    if not json_mode:
        print("=== Running tools/course_checks/r08-t012.py ===")
        print(f"Exercise Directory: {exercise_dir}")

    # Step 1: Consistency check
    consistency_info = verify_tests_toml_consistency(exercise_dir, verbose=not json_mode)

    # Step 2: Isolated test suite execution
    execution_info = run_test_suite_in_temp_dir(exercise_dir, verbose=not json_mode)

    output = {
        "status": "PASS",
        "consistency": consistency_info,
        "execution": execution_info
    }

    if json_mode:
        print(json.dumps(output, indent=2))
    else:
        print(f"Verification successful: {execution_info['total_cases']} cases verified.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
