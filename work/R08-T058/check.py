#!/usr/bin/env python3
"""Validate grade-school metadata fixtures and run the maintained reference."""

import hashlib
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
EXERCISE = ROOT / "exercises/practice/grade-school"
CHECKER_PATH = ROOT / "tools/course_checks/r08-t058.py"
SPEC = importlib.util.spec_from_file_location("grade_school_checker", CHECKER_PATH)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command_version(command):
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return (result.stdout or result.stderr).strip().splitlines()[0]


def fixture_config(root, files):
    exercise = root / "exercise"
    (exercise / ".meta").mkdir(parents=True)
    for name in ("solution.sql", "test.sql", "example.sql", "editor.txt", "create_test_table.sql"):
        target = exercise / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture\n", encoding="utf-8")
    (exercise / ".meta/config.json").write_text(json.dumps({"files": files}), encoding="utf-8")
    (exercise / "test.sql").write_text(".read ./create_test_table.sql\n", encoding="utf-8")
    return exercise


def check_invalid_metadata_fixtures():
    cases = [
        ("missing reference", {"solution": ["solution.sql"], "test": ["test.sql"],
                                "example": ["missing-example.sql"]}, "does not resolve"),
        ("missing test", {"solution": ["solution.sql"], "test": ["missing-test.sql"],
                           "example": ["example.sql"]}, "does not resolve"),
        ("outside exercise", {"solution": ["solution.sql"], "test": ["test.sql"],
                              "example": ["../outside.sql"]}, "relative path within the exercise"),
    ]
    results = []
    for index, (label, files, expected_error) in enumerate(cases):
        with tempfile.TemporaryDirectory(prefix=f"r08-t058-fixture-{index}-") as temporary:
            exercise = fixture_config(Path(temporary), files)
            try:
                CHECKER.validate(exercise / ".meta/config.json", exercise)
            except CHECKER.MetadataError as error:
                actual_error = str(error)
                if expected_error not in actual_error:
                    raise AssertionError(f"{label}: expected {expected_error!r}, got {actual_error!r}")
            else:
                raise AssertionError(f"{label}: invalid fixture unexpectedly passed")
            results.append({"fixture": label, "expected": expected_error, "actual": actual_error, "rejected": True})
    return results


def main():
    stub_path = EXERCISE / "grade-school.sql"
    stub_before = digest(stub_path)
    metadata_result = CHECKER.validate(EXERCISE / ".meta/config.json", EXERCISE)
    fixture_results = check_invalid_metadata_fixtures()
    tests_meta = tomllib.loads((EXERCISE / ".meta/tests.toml").read_text(encoding="utf-8"))
    expected_descriptions = [item["description"] for item in tests_meta.values() if item.get("include", True)]
    evidence_query = """
.mode json
.once 'assertions.json'
SELECT t.uuid, t.description, t.property, t.input, t.expected,
       a.result AS actual, t.status
FROM tests AS t
LEFT JOIN "grade-school" AS a ON a.property = t.property AND a.input = t.input
ORDER BY t.rowid;
"""
    with tempfile.TemporaryDirectory(prefix="r08-t058-") as temporary:
        copy = Path(temporary) / "grade-school"
        shutil.copytree(EXERCISE, copy)
        config = json.loads((copy / ".meta/config.json").read_text(encoding="utf-8"))
        (copy / config["files"]["solution"][0]).write_text(
            (EXERCISE / config["files"]["example"][0]).read_text(encoding="utf-8"), encoding="utf-8"
        )
        test_sql = (copy / config["files"]["test"][0]).read_text(encoding="utf-8")
        result = subprocess.run(["sqlite3", "-bail"], input=test_sql + "\n" + evidence_query,
                                cwd=copy, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"sqlite3 exited {result.returncode}: {result.stderr.strip()}")
        output_path = copy / "output.json"
        if not output_path.is_file() or not output_path.stat().st_size:
            raise AssertionError("test run did not write output.json")
        output = json.loads(output_path.read_text(encoding="utf-8"))
        if not isinstance(output, list) or not output:
            raise AssertionError("zero test cases were reported")
        failures = [row for row in output if row.get("status") != "pass"]
        if failures:
            raise AssertionError(f"{len(failures)} of {len(output)} test cases failed")
        if Counter(row["description"] for row in output) != Counter(expected_descriptions):
            raise AssertionError("enabled tests.toml descriptions do not match executed cases")
        assertions = json.loads((copy / "assertions.json").read_text(encoding="utf-8"))

    if digest(stub_path) != stub_before:
        raise AssertionError("learner solution changed during the check")
    versions = {
        "python": sys.version.splitlines()[0],
        "sqlite3": command_version(["sqlite3", "--version"]),
        "jq": command_version(["jq", "--version"]),
        "git": command_version(["git", "--version"]),
        "platform": platform.platform(),
    }
    evidence = {
        "metadata": {"roles": metadata_result["roles"], "create_test_table_read": True},
        "invalid_metadata_fixtures": fixture_results,
        "cases_executed": len(output),
        "cases": [
            {"uuid": row["uuid"], "description": row["description"], "input": row["input"],
             "expected": row["expected"], "actual": row["actual"], "status": row["status"]}
            for row in assertions
        ],
        "learner_solution_sha256": stub_before,
        "tool_versions": versions,
    }
    (WORK / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    (WORK / "versions.txt").write_text("\n".join(f"{key}: {value}" for key, value in versions.items()) + "\n",
                                       encoding="utf-8")
    print(f"grade-school: metadata and 3 invalid fixtures passed; {len(output)} cases passed")


if __name__ == "__main__":
    main()
