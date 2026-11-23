#!/usr/bin/env python3
"""
Verification Script for Exercise: Diamond
Task: R08-T031

This script verifies the Diamond exercise using Python's subprocess module
and a temporary directory, adhering to all repository standards and assignment
specifications.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap


def parse_toml(toml_path: pathlib.Path) -> dict:
    """Parse a TOML file.

    Uses standard tomllib if available (Python 3.11+), otherwise falls back
    to a robust parser compatible with Python 3.9+ for the Exercism tests.toml format.
    """
    try:
        import tomllib
        with open(toml_path, "rb") as f:
            return tomllib.load(f)
    except ImportError:
        pass

    with open(toml_path, "r", encoding="utf-8") as f:
        content = f.read()

    data = {}
    current_section = None
    for line_num, line in enumerate(content.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        section_match = re.match(r"^\[([a-zA-Z0-9_\-]+)\]$", line)
        if section_match:
            current_section = section_match.group(1)
            data[current_section] = {}
            continue
        kv_match = re.match(r"^([a-zA-Z0-9_\-]+)\s*=\s*(.+)$", line)
        if kv_match:
            if current_section is None:
                raise ValueError(f"Key-value outside table at line {line_num}: {line}")
            key = kv_match.group(1)
            raw_val = kv_match.group(2).strip()
            if (raw_val.startswith('"') and raw_val.endswith('"')) or (
                raw_val.startswith("'") and raw_val.endswith("'")
            ):
                val = raw_val[1:-1]
            elif raw_val.lower() == "true":
                val = True
            elif raw_val.lower() == "false":
                val = False
            else:
                val = raw_val
            data[current_section][key] = val
            continue
        raise ValueError(f"Invalid TOML syntax at line {line_num}: {line}")

    return data


def get_sqlite_version() -> str:
    """Retrieve installed SQLite version."""
    proc = subprocess.run(
        ["sqlite3", "--version"], capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


def run_verification() -> dict:
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    exercise_rel = pathlib.Path("exercises/practice/diamond")
    exercise_dir = repo_root / exercise_rel

    if not exercise_dir.is_dir():
        print(f"Error: Exercise directory not found at {exercise_dir}", file=sys.stderr)
        sys.exit(1)

    work_dir = repo_root / "work" / "R08-T031"
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1. Inspect and parse config.json
    config_path = exercise_dir / ".meta" / "config.json"
    if not config_path.is_file():
        print(f"Error: config.json missing at {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    solution_file_rel = config["files"]["solution"][0]
    test_file_rel = config["files"]["test"][0]
    example_file_rel = config["files"]["example"][0]

    original_solution_path = exercise_dir / solution_file_rel
    original_test_path = exercise_dir / test_file_rel
    original_example_path = exercise_dir / example_file_rel

    for path, name in [
        (original_solution_path, "Solution stub"),
        (original_test_path, "Test runner"),
        (original_example_path, "Example implementation"),
    ]:
        if not path.is_file():
            print(f"Error: {name} file missing at {path}", file=sys.stderr)
            sys.exit(1)

    with open(original_solution_path, "r", encoding="utf-8") as f:
        original_solution_content = f.read()

    # 2. Inspect and parse tests.toml
    tests_toml_path = exercise_dir / ".meta" / "tests.toml"
    if not tests_toml_path.is_file():
        print(f"Error: tests.toml missing at {tests_toml_path}", file=sys.stderr)
        sys.exit(1)

    try:
        tests_toml_data = parse_toml(tests_toml_path)
    except Exception as e:
        print(f"Error: Failed to parse tests.toml: {e}", file=sys.stderr)
        sys.exit(1)

    total_canonical_cases = len(tests_toml_data)
    included_count_before = sum(
        1 for t in tests_toml_data.values() if t.get("include", True)
    )
    excluded_count_before = sum(
        1 for t in tests_toml_data.values() if not t.get("include", True)
    )

    # Required investigated UUIDs
    investigated_uuids = [
        "202fb4cc-6a38-4883-9193-a29d5cb92076",
        "bd6a6d78-9302-42e9-8f60-ac1461e9abae",
        "af8efb49-14ed-447f-8944-4cc59ce3fd76",
    ]
    for uuid in investigated_uuids:
        if uuid not in tests_toml_data:
            print(f"Error: Required UUID {uuid} not found in tests.toml", file=sys.stderr)
            sys.exit(1)

    # 3. Create isolated temporary directory and copy full exercise (including dotfiles)
    with tempfile.TemporaryDirectory(prefix="diamond_verify_") as tmpdir_str:
        tmp_dir = pathlib.Path(tmpdir_str)
        temp_exercise_dir = tmp_dir / "diamond"

        # Copy entire directory tree including hidden dotfiles
        shutil.copytree(exercise_dir, temp_exercise_dir)

        # Substitute maintained reference implementation ONLY inside the temporary copy
        temp_example_path = temp_exercise_dir / example_file_rel
        temp_solution_path = temp_exercise_dir / solution_file_rel
        shutil.copy(temp_example_path, temp_solution_path)

        # Assert learner's original solution has not been modified
        with open(original_solution_path, "r", encoding="utf-8") as f:
            current_solution_content = f.read()
        if current_solution_content != original_solution_content:
            print(
                "Error: Learner's original solution file was modified!",
                file=sys.stderr,
            )
            sys.exit(1)

        # 4. Generate and execute tests equivalent to: sqlite3 -bail < diamond_test.sql
        temp_test_sql = temp_exercise_dir / test_file_rel
        with open(temp_test_sql, "r", encoding="utf-8") as test_in:
            proc = subprocess.run(
                ["sqlite3", "-bail"],
                stdin=test_in,
                cwd=temp_exercise_dir,
                capture_output=True,
                text=True,
            )

        if proc.returncode != 0:
            print(
                f"Error: sqlite3 process failed with returncode {proc.returncode}\n{proc.stderr}",
                file=sys.stderr,
            )
            sys.exit(proc.returncode or 1)

        temp_output_json = temp_exercise_dir / "output.json"
        if not temp_output_json.is_file():
            print(
                "Error: output.json was not generated by test execution!",
                file=sys.stderr,
            )
            sys.exit(1)

        with open(temp_output_json, "r", encoding="utf-8") as jf:
            test_results = json.load(jf)

        executed_test_count = len(test_results)
        if executed_test_count == 0:
            print("Error: Zero tests were executed!", file=sys.stderr)
            sys.exit(1)

        failed_tests = [t for t in test_results if t.get("status") != "pass"]
        if failed_tests:
            print(f"Error: {len(failed_tests)} test(s) failed:", file=sys.stderr)
            for ft in failed_tests:
                print(f"  - {ft.get('description')}: {ft.get('message')}", file=sys.stderr)
            sys.exit(1)

        # 5. Extract detailed input/expected/actual pairs from test tables
        query_details = textwrap.dedent("""\
            .read ./create_fixture.sql
            .read ./diamond.sql
            .read ./create_test_table.sql
            .mode json
            SELECT
                tests.uuid,
                tests.letter,
                tests.description,
                tests.expected,
                diamond.result AS actual,
                (tests.expected = diamond.result) AS passed
            FROM tests
            JOIN diamond ON tests.letter = diamond.letter;
        """)
        detail_proc = subprocess.run(
            ["sqlite3", "-bail"],
            input=query_details,
            cwd=temp_exercise_dir,
            capture_output=True,
            text=True,
        )

        if detail_proc.returncode != 0:
            print(
                f"Error extracting test details: {detail_proc.stderr}",
                file=sys.stderr,
            )
            sys.exit(detail_proc.returncode or 1)

        try:
            detailed_cases = json.loads(detail_proc.stdout)
        except json.JSONDecodeError as jde:
            print(f"Error parsing detailed SQL test output: {jde}", file=sys.stderr)
            sys.exit(1)

        # Verify again original solution remains untouched
        with open(original_solution_path, "r", encoding="utf-8") as f:
            final_check_solution = f.read()
        if final_check_solution != original_solution_content:
            print("Error: Learner solution modified during execution!", file=sys.stderr)
            sys.exit(1)

    # Check after-counts for tests.toml
    tests_toml_after = parse_toml(tests_toml_path)
    included_count_after = sum(
        1 for t in tests_toml_after.values() if t.get("include", True)
    )
    excluded_count_after = sum(
        1 for t in tests_toml_after.values() if not t.get("include", True)
    )

    sqlite_version = get_sqlite_version()
    python_version = sys.version.replace("\n", " ")

    evidence = {
        "status": "success",
        "exercise": "diamond",
        "sqlite_version": sqlite_version,
        "python_version": python_version,
        "included_cases_before": included_count_before,
        "excluded_cases_before": excluded_count_before,
        "included_cases_after": included_count_after,
        "excluded_cases_after": excluded_count_after,
        "total_canonical_cases": total_canonical_cases,
        "executed_test_count": executed_test_count,
        "all_tests_passed": True,
        "inputs_verified": [c["letter"] for c in detailed_cases],
        "test_results": test_results,
        "detailed_cases": detailed_cases,
        "investigated_uuids": investigated_uuids,
        "console_output": proc.stdout.strip(),
    }

    # Save evidence files
    evidence_json_path = work_dir / "evidence.json"
    with open(evidence_json_path, "w", encoding="utf-8") as ef:
        json.dump(evidence, ef, indent=2)

    evidence_txt_path = work_dir / "verification_output.txt"
    with open(evidence_txt_path, "w", encoding="utf-8") as tf:
        tf.write("=== Diamond Exercise Test Verification ===\n")
        tf.write(f"SQLite Version: {sqlite_version}\n")
        tf.write(f"Python Version: {python_version}\n")
        tf.write(f"Total Canonical Cases: {total_canonical_cases}\n")
        tf.write(f"Included Cases Before/After: {included_count_before} / {included_count_after}\n")
        tf.write(f"Excluded Cases Before/After: {excluded_count_before} / {excluded_count_after}\n")
        tf.write(f"Tests Executed: {executed_test_count}\n")
        tf.write(f"Tests Passed: {executed_test_count} / {executed_test_count}\n\n")
        tf.write("Test Table Output:\n")
        tf.write(proc.stdout.strip() + "\n\n")
        tf.write("Detailed Test Case Evidence:\n")
        for dc in detailed_cases:
            tf.write(f"- UUID: {dc['uuid']}\n")
            tf.write(f"  Description: {dc['description']}\n")
            tf.write(f"  Input Letter: {dc['letter']}\n")
            tf.write(f"  Match (Expected == Actual): {bool(dc['passed'])}\n")

    # Print summary to stdout
    print("=================================================================")
    print("        Diamond Exercise Test Review and Verification           ")
    print("=================================================================")
    print(f"Environment: SQLite {sqlite_version}")
    print(f"Environment: Python {python_version}")
    print(f"Tests TOML Parsing: SUCCESS (valid TOML)")
    print(f"Canonical Test Cases Total: {total_canonical_cases}")
    print(f"Included Cases Count (Before -> After): {included_count_before} -> {included_count_after}")
    print(f"Excluded Cases Count (Before -> After): {excluded_count_before} -> {excluded_count_after}")
    print(f"Total Tests Executed: {executed_test_count}")
    print(f"All Executed Tests Status: PASS (100% passing)")
    print(f"Learner Solution Working Tree: UNMODIFIED (Stub preserved)")
    print(f"Evidence Saved to: {evidence_json_path.relative_to(repo_root)}")
    print(f"Verification Output Saved to: {evidence_txt_path.relative_to(repo_root)}")
    print("=================================================================")

    return evidence


if __name__ == "__main__":
    run_verification()
