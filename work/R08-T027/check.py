#!/usr/bin/env python3
"""Verify binary-search reference tests and the documented UNION example."""

from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EXERCISE = ROOT / "exercises/practice/binary-search"
TASK_DIR = ROOT / "work/R08-T027"
HINT_PATH = EXERCISE / ".docs/instructions.append.md"
VERIFICATION_PATH = TASK_DIR / "verification.json"

EXPECTED_CASES = [
    {
        "uuid": "b55c24a9-a98d-4379-a08c-2adcf8ebeee8",
        "description": "finds a value in an array with one element",
        "array": "[6]",
        "value": 6,
        "expected_result": 0,
        "expected_error": None,
    },
    {
        "uuid": "73469346-b0a0-4011-89bf-989e443d503d",
        "description": "finds a value in the middle of an array",
        "array": "[1,3,4,6,8,9,11]",
        "value": 6,
        "expected_result": 3,
        "expected_error": None,
    },
    {
        "uuid": "327bc482-ab85-424e-a724-fb4658e66ddb",
        "description": "finds a value at the beginning of an array",
        "array": "[1,3,4,6,8,9,11]",
        "value": 1,
        "expected_result": 0,
        "expected_error": None,
    },
    {
        "uuid": "f9f94b16-fe5e-472c-85ea-c513804c7d59",
        "description": "finds a value at the end of an array",
        "array": "[1,3,4,6,8,9,11]",
        "value": 11,
        "expected_result": 6,
        "expected_error": None,
    },
    {
        "uuid": "f0068905-26e3-4342-856d-ad153cadb338",
        "description": "finds a value in an array of odd length",
        "array": "[1,3,5,8,13,21,34,55,89,144,233,377,634]",
        "value": 144,
        "expected_result": 9,
        "expected_error": None,
    },
    {
        "uuid": "fc316b12-c8b3-4f5e-9e89-532b3389de8c",
        "description": "finds a value in an array of even length",
        "array": "[1,3,5,8,13,21,34,55,89,144,233,377]",
        "value": 21,
        "expected_result": 5,
        "expected_error": None,
    },
    {
        "uuid": "da7db20a-354f-49f7-a6a1-650a54998aa6",
        "description": "identifies that a value is not included in the array",
        "array": "[1,3,4,6,8,9,11]",
        "value": 7,
        "expected_result": None,
        "expected_error": "value not in array",
    },
    {
        "uuid": "95d869ff-3daf-4c79-b622-6e805c675f97",
        "description": (
            "a value smaller than the array's smallest value is not found"
        ),
        "array": "[1,3,4,6,8,9,11]",
        "value": 0,
        "expected_result": None,
        "expected_error": "value not in array",
    },
    {
        "uuid": "8b24ef45-6e51-4a94-9eac-c2bf38fdb0ba",
        "description": (
            "a value larger than the array's largest value is not found"
        ),
        "array": "[1,3,4,6,8,9,11]",
        "value": 13,
        "expected_result": None,
        "expected_error": "value not in array",
    },
    {
        "uuid": "f439a0fa-cf42-4262-8ad1-64bf41ce566a",
        "description": "nothing is found in an empty array",
        "array": "[]",
        "value": 1,
        "expected_result": None,
        "expected_error": "value not in array",
    },
    {
        "uuid": "2c353967-b56d-40b8-acff-ce43115eed64",
        "description": "nothing is found when the left and right bounds cross",
        "array": "[1,2]",
        "value": 0,
        "expected_result": None,
        "expected_error": "value not in array",
    },
]

CASE_RESULTS_BEGIN = "__R08_T027_CASE_RESULTS_BEGIN__"
CASE_RESULTS_END = "__R08_T027_CASE_RESULTS_END__"
CASE_RESULTS_SQL = f"""
.print {CASE_RESULTS_BEGIN}
.mode json
SELECT
  tests.uuid,
  tests.description,
  tests.array,
  tests.value,
  tests.expected_result,
  tests.expected_error,
  actual.result AS actual_result,
  actual.error AS actual_error
FROM
  tests
  JOIN "binary-search" AS actual
    ON actual.array = tests.array
    AND actual.value = tests.value
ORDER BY
  tests.rowid;
.print {CASE_RESULTS_END}
"""


class CheckFailure(Exception):
    """A validation failure that should be written to verification.json."""


def write_evidence(evidence: dict[str, Any]) -> None:
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    VERIFICATION_PATH.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def configured_file(config: dict[str, Any], key: str, exercise_dir: Path) -> Path:
    paths = config.get("files", {}).get(key)
    if not isinstance(paths, list) or len(paths) != 1:
        raise CheckFailure(f"Expected exactly one configured {key} path, got {paths!r}")

    path = exercise_dir / paths[0]
    if not path.is_file():
        raise CheckFailure(f"Configured {key} file does not exist: {path}")
    return path


def read_config(exercise_dir: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    config_path = exercise_dir / ".meta/config.json"
    if not config_path.is_file():
        raise CheckFailure(f"Exercise config does not exist: {config_path}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    paths = {
        key: configured_file(config, key, exercise_dir)
        for key in ("solution", "test", "example")
    }
    return config, paths


def validate_metadata() -> None:
    metadata_path = EXERCISE / ".meta/tests.toml"
    metadata = tomllib.loads(metadata_path.read_text(encoding="utf-8"))
    expected_by_uuid = {case["uuid"]: case for case in EXPECTED_CASES}
    if set(metadata) != set(expected_by_uuid):
        raise CheckFailure(
            "tests.toml UUID mismatch: "
            f"missing={sorted(set(expected_by_uuid) - set(metadata))}, "
            f"extra={sorted(set(metadata) - set(expected_by_uuid))}"
        )

    for uuid, case in expected_by_uuid.items():
        entry = metadata[uuid]
        if entry.get("description") != case["description"]:
            raise CheckFailure(f"tests.toml description mismatch for UUID {uuid}")
        if entry.get("include", True) is not True:
            raise CheckFailure(f"Expected case {uuid} to be included")


def sqlite_version() -> str:
    try:
        process = subprocess.run(
            ["sqlite3", "--version"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except FileNotFoundError as error:
        raise CheckFailure("SQLite CLI 'sqlite3' was not found on PATH") from error
    if process.returncode != 0:
        raise CheckFailure(
            f"SQLite version command failed ({process.returncode}): {process.stderr}"
        )
    return process.stdout.strip()


def run_hint_example() -> dict[str, Any]:
    hint = HINT_PATH.read_text(encoding="utf-8")
    snippets = re.findall(r"```sql\s*\n(.*?)\n```", hint, flags=re.DOTALL)
    if len(snippets) != 1:
        raise CheckFailure(
            f"Expected exactly one fenced SQL example in {HINT_PATH}, found {len(snippets)}"
        )

    sql = snippets[0]
    try:
        process = subprocess.run(
            ["sqlite3", "-bail", ":memory:"],
            input=sql,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except FileNotFoundError as error:
        raise CheckFailure("SQLite CLI 'sqlite3' was not found on PATH") from error
    except subprocess.TimeoutExpired as error:
        raise CheckFailure("Hint SQL example exceeded 10 seconds") from error

    example = {
        "command": "sqlite3 -bail :memory: (SQL read from instructions.append.md)",
        "sql": sql,
        "return_code": process.returncode,
        "stdout": process.stdout,
        "stderr": process.stderr,
        "expected": {"union_rows": 1, "union_all_rows": 2},
        "actual": None,
    }
    if process.returncode != 0:
        raise CheckFailure(
            f"Hint SQL example exited {process.returncode}: {process.stderr}"
        )

    fields = process.stdout.strip().split("|")
    try:
        actual = [int(field) for field in fields]
    except ValueError as error:
        raise CheckFailure(
            f"Could not parse hint SQL output {process.stdout!r}"
        ) from error
    example["actual"] = {
        "union_rows": actual[0] if len(actual) > 0 else None,
        "union_all_rows": actual[1] if len(actual) > 1 else None,
    }
    if actual != [1, 2]:
        raise CheckFailure(
            f"Hint SQL expected counts [1, 2], got {actual!r}"
        )
    return example


def marked_case_results(stdout: str) -> list[dict[str, Any]]:
    start = stdout.find(CASE_RESULTS_BEGIN)
    end = stdout.find(CASE_RESULTS_END)
    if start < 0 or end < 0 or end <= start:
        raise CheckFailure("SQLite output is missing the case-results block")
    payload = stdout[start + len(CASE_RESULTS_BEGIN) : end].strip()
    try:
        results = json.loads(payload)
    except json.JSONDecodeError as error:
        raise CheckFailure(f"Could not parse case-results JSON: {error}") from error
    if not isinstance(results, list):
        raise CheckFailure("Case-results diagnostic JSON is not an array")
    return results


def execute_reference() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="r08-t027-") as temporary_dir:
        copied_exercise = Path(temporary_dir) / "binary-search"
        shutil.copytree(EXERCISE, copied_exercise)
        _, copied_paths = read_config(copied_exercise)
        shutil.copyfile(copied_paths["example"], copied_paths["solution"])

        test_sql = copied_paths["test"].read_text(encoding="utf-8")
        input_sql = f"{test_sql.rstrip()}\n\n{CASE_RESULTS_SQL}"
        try:
            process = subprocess.run(
                ["sqlite3", "-bail"],
                input=input_sql,
                cwd=copied_exercise,
                text=True,
                capture_output=True,
                timeout=60,
                check=False,
            )
        except FileNotFoundError as error:
            raise CheckFailure("SQLite CLI 'sqlite3' was not found on PATH") from error
        except subprocess.TimeoutExpired as error:
            raise CheckFailure("Binary-search SQLite tests exceeded 60 seconds") from error

        record: dict[str, Any] = {
            "command": (
                "sqlite3 -bail (stdin: configured binary-search_test.sql "
                "followed by a read-only results query)"
            ),
            "return_code": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
            "output_json": None,
            "output_json_error": None,
            "case_results": None,
            "case_results_error": None,
        }

        output_path = copied_exercise / "output.json"
        if not output_path.is_file():
            record["output_json_error"] = "output.json was not created"
        else:
            try:
                record["output_json"] = json.loads(
                    output_path.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError as error:
                record["output_json_error"] = str(error)

        if process.returncode == 0:
            try:
                record["case_results"] = marked_case_results(process.stdout)
            except CheckFailure as error:
                record["case_results_error"] = str(error)
        return record


def validate_exercise_results(record: dict[str, Any]) -> None:
    if record["return_code"] != 0:
        raise CheckFailure(
            f"SQLite tests exited {record['return_code']}; stderr={record['stderr']!r}"
        )

    output = record["output_json"]
    if not isinstance(output, list):
        raise CheckFailure(f"Invalid output.json: {record['output_json_error']}")
    if not output:
        raise CheckFailure("The test run executed zero cases")
    if len(output) != len(EXPECTED_CASES):
        raise CheckFailure(
            f"output.json has {len(output)} entries; expected {len(EXPECTED_CASES)}"
        )

    expected_descriptions = [case["description"] for case in EXPECTED_CASES]
    actual_descriptions = [
        item.get("description") if isinstance(item, dict) else None
        for item in output
    ]
    expected_counts = Counter(expected_descriptions)
    actual_counts = Counter(actual_descriptions)
    missing = list((expected_counts - actual_counts).elements())
    extra = list((actual_counts - expected_counts).elements())
    duplicates = sorted(
        description
        for description, count in actual_counts.items()
        if description is not None and count > 1
    )
    if missing or extra or duplicates:
        raise CheckFailure(
            f"output.json descriptions mismatch: missing={missing}, "
            f"extra={extra}, duplicates={duplicates}"
        )

    failed = []
    for item in output:
        if not isinstance(item, dict):
            failed.append((repr(item), "invalid result entry"))
        elif item.get("status") != "pass":
            failed.append((item.get("description"), item.get("status")))
    if failed:
        raise CheckFailure(f"Non-pass output.json results: {failed}")

    rows = record["case_results"]
    if not isinstance(rows, list):
        raise CheckFailure(f"Could not read actual case outputs: {record['case_results_error']}")
    if len(rows) != len(EXPECTED_CASES):
        raise CheckFailure(
            f"SQL diagnostic returned {len(rows)} cases; expected {len(EXPECTED_CASES)}"
        )

    expected_by_uuid = {case["uuid"]: case for case in EXPECTED_CASES}
    actual_by_uuid: dict[str, dict[str, Any]] = {}
    for row in rows:
        uuid = row.get("uuid")
        if uuid in actual_by_uuid:
            raise CheckFailure(f"Duplicate SQL case UUID {uuid}")
        actual_by_uuid[uuid] = row
    if set(actual_by_uuid) != set(expected_by_uuid):
        raise CheckFailure(
            "SQL case UUID mismatch: "
            f"missing={sorted(set(expected_by_uuid) - set(actual_by_uuid))}, "
            f"extra={sorted(set(actual_by_uuid) - set(expected_by_uuid))}"
        )

    expected_vs_actual = []
    for uuid, expected in expected_by_uuid.items():
        row = actual_by_uuid[uuid]
        input_array = json.loads(expected["array"])
        if row.get("description") != expected["description"]:
            raise CheckFailure(f"SQL test description mismatch for {uuid}")
        if json.loads(row["array"]) != input_array:
            raise CheckFailure(f"SQL test input mismatch for {uuid}")
        if row.get("value") != expected["value"]:
            raise CheckFailure(f"SQL test target mismatch for {uuid}")
        if row.get("expected_result") != expected["expected_result"]:
            raise CheckFailure(f"SQL expected result mismatch for {uuid}")
        if row.get("expected_error") != expected["expected_error"]:
            raise CheckFailure(f"SQL expected error mismatch for {uuid}")
        if row.get("actual_result") != expected["expected_result"]:
            raise CheckFailure(
                f"Wrong result for {expected['description']}: "
                f"expected {expected['expected_result']!r}, "
                f"got {row.get('actual_result')!r}"
            )
        if row.get("actual_error") != expected["expected_error"]:
            raise CheckFailure(
                f"Wrong error for {expected['description']}: "
                f"expected {expected['expected_error']!r}, "
                f"got {row.get('actual_error')!r}"
            )
        expected_vs_actual.append(
            {
                "uuid": uuid,
                "description": expected["description"],
                "input": {"array": input_array, "value": expected["value"]},
                "expected": {
                    "result": expected["expected_result"],
                    "error": expected["expected_error"],
                },
                "actual": {
                    "result": row.get("actual_result"),
                    "error": row.get("actual_error"),
                },
            }
        )

    record["executed_test_count"] = len(output)
    record["passed_test_count"] = len(output)
    record["failed_test_count"] = 0
    record["expected_vs_actual"] = expected_vs_actual


def main() -> int:
    evidence: dict[str, Any] = {
        "task": "R08-T027",
        "status": "running",
        "checker_command": "python3 work/R08-T027/check.py",
        "tool_versions": {
            "python": sys.version,
            "sqlite_cli": None,
        },
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "expected_test_count": len(EXPECTED_CASES),
        "micro_example": None,
        "exercise_run": None,
    }

    try:
        validate_metadata()
        evidence["tool_versions"]["sqlite_cli"] = sqlite_version()
        evidence["micro_example"] = run_hint_example()

        _, paths = read_config(EXERCISE)
        if not paths["example"].is_file():
            raise CheckFailure(f"Reference example does not exist: {paths['example']}")
        record = execute_reference()
        evidence["exercise_run"] = record
        validate_exercise_results(record)
        evidence["status"] = "passed"
    except CheckFailure as error:
        evidence["status"] = "failed"
        evidence["failure"] = str(error)
        write_evidence(evidence)
        print(f"FAIL: {error}", file=sys.stderr)
        exercise_run = evidence.get("exercise_run")
        if isinstance(exercise_run, dict):
            if exercise_run.get("stdout"):
                print("--- SQLite stdout ---", file=sys.stderr)
                print(exercise_run["stdout"], file=sys.stderr)
            if exercise_run.get("stderr"):
                print("--- SQLite stderr ---", file=sys.stderr)
                print(exercise_run["stderr"], file=sys.stderr)
        return 1

    write_evidence(evidence)
    run = evidence["exercise_run"]
    print(
        f"Passed {run['executed_test_count']} tests "
        f"({run['passed_test_count']} passed, {run['failed_test_count']} failed)."
    )
    print(
        "Hint SQL outputs asserted: "
        f"UNION={evidence['micro_example']['actual']['union_rows']}, "
        "UNION ALL="
        f"{evidence['micro_example']['actual']['union_all_rows']}."
    )
    print(f"Evidence written to {VERIFICATION_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
