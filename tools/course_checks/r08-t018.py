#!/usr/bin/env python3
"""
Path, configuration, and execution validator for Task R08-T018 (matrix exercise).

Responsibilities:
1. Validate `config.json` schema and verify all referenced files exist on disk.
2. Verify completeness of required exercise files (fixtures, data, tests, docs).
3. Execute the full test suite in an isolated temporary directory against `.meta/example.sql`.
4. Return structured validation results and assert 100% test pass status.
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile


def validate_config_and_paths(exercise_dir: pathlib.Path) -> dict:
    """
    Validate config.json schema and verify that all referenced files exist.
    """
    config_path = exercise_dir / ".meta" / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Missing config.json at {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config_data = json.load(f)

    # 1. Verify top-level schema fields
    required_top_keys = ["files", "blurb"]
    for key in required_top_keys:
        if key not in config_data:
            raise KeyError(f"config.json missing required key: '{key}'")

    files_section = config_data.get("files", {})
    required_file_roles = ["solution", "test", "example"]
    for role in required_file_roles:
        if role not in files_section:
            raise KeyError(f"config.json files section missing role: '{role}'")

    # 2. Verify all referenced files exist on disk
    verified_files = {}
    for role, file_list in files_section.items():
        if not isinstance(file_list, list) or len(file_list) == 0:
            raise ValueError(f"Role '{role}' must be a non-empty list of file paths")
        for rel_file in file_list:
            file_path = exercise_dir / rel_file
            if not file_path.exists():
                raise FileNotFoundError(f"Referenced file for role '{role}' not found: {file_path}")
            verified_files[f"{role}:{rel_file}"] = {
                "role": role,
                "relative_path": rel_file,
                "absolute_path": str(file_path),
                "size_bytes": file_path.stat().st_size,
            }

    # 3. Verify additional standard exercise assets
    standard_assets = [
        "create_fixture.sql",
        "create_test_table.sql",
        "data.csv",
        ".meta/tests.toml",
        ".docs/instructions.md",
    ]
    verified_assets = {}
    for asset in standard_assets:
        asset_path = exercise_dir / asset
        if not asset_path.exists():
            raise FileNotFoundError(f"Missing standard exercise asset: {asset_path}")
        verified_assets[asset] = {
            "exists": True,
            "size_bytes": asset_path.stat().st_size,
        }

    return {
        "config_path": str(config_path),
        "blurb": config_data.get("blurb"),
        "authors": config_data.get("authors", []),
        "verified_referenced_files": verified_files,
        "verified_standard_assets": verified_assets,
    }


def run_isolated_test_suite(exercise_dir: pathlib.Path) -> dict:
    """
    Run matrix_test.sql in an isolated temporary directory using .meta/example.sql.
    """
    example_sql = exercise_dir / ".meta" / "example.sql"
    if not example_sql.exists():
        raise FileNotFoundError(f"Missing reference implementation at {example_sql}")

    required_harness_files = [
        "create_fixture.sql",
        "create_test_table.sql",
        "matrix_test.sql",
        "data.csv",
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = pathlib.Path(tmp_dir)

        for fname in required_harness_files:
            src = exercise_dir / fname
            if not src.exists():
                raise FileNotFoundError(f"Missing harness file: {src}")
            shutil.copy(src, tmp_path / fname)

        # Copy reference solution as matrix.sql
        shutil.copy(example_sql, tmp_path / "matrix.sql")

        proc = subprocess.run(
            ["sqlite3", "-bail"],
            input=".read matrix_test.sql\n",
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )

        output_json = tmp_path / "output.json"
        if not output_json.exists():
            raise RuntimeError(
                f"output.json was not produced by test runner.\n"
                f"Exit code: {proc.returncode}\n"
                f"Stdout: {proc.stdout}\n"
                f"Stderr: {proc.stderr}"
            )

        with open(output_json, "r", encoding="utf-8") as f:
            cases = json.load(f)

        total_cases = len(cases)
        passed_cases = sum(1 for c in cases if c.get("status") == "pass")
        failed_cases = total_cases - passed_cases

        return {
            "command": "sqlite3 -bail < matrix_test.sql",
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "total_canonical_cases": total_cases,
            "passed_count": passed_cases,
            "failed_count": failed_cases,
            "pass_percentage": f"{(passed_cases / total_cases * 100):.1f}%" if total_cases > 0 else "0.0%",
            "cases": cases,
        }


def run_validation(repo_root: pathlib.Path) -> dict:
    """
    Execute full path validation and test execution for matrix exercise.
    """
    exercise_dir = repo_root / "exercises" / "practice" / "matrix"
    config_validation = validate_config_and_paths(exercise_dir)
    test_results = run_isolated_test_suite(exercise_dir)

    all_passed = (test_results["failed_count"] == 0 and test_results["exit_code"] == 0)

    return {
        "status": "pass" if all_passed else "fail",
        "exercise": "matrix",
        "exercise_directory": str(exercise_dir),
        "configuration": config_validation,
        "test_execution": test_results,
    }


def main():
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    try:
        report = run_validation(repo_root)
        if "--json" in sys.argv:
            print(json.dumps(report, indent=2))
        else:
            print("=" * 60)
            print("Course Check R08-T018: Matrix Configuration & Path Validation")
            print("=" * 60)
            print(f"Status:       {report['status'].upper()}")
            print(f"Exercise:     {report['exercise']}")
            print(f"Files Checked: {len(report['configuration']['verified_referenced_files'])} referenced, {len(report['configuration']['verified_standard_assets'])} standard assets")
            print(f"Test Cases:   {report['test_execution']['total_canonical_cases']} total, {report['test_execution']['passed_count']} passed")
            print(f"Success Rate: {report['test_execution']['pass_percentage']}")
            print("=" * 60)

        if report["status"] != "pass":
            sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Validation failed with error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
