#!/usr/bin/env python3
"""Verify the saddle-points reference and independent alternative."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EXERCISE = ROOT / "exercises/practice/saddle-points"
TASK_DIR = ROOT / "work/R08-T026"
VERIFICATION_FILE = TASK_DIR / "verification.json"

EXPECTED_CASES = [
    {
        "uuid": "3e374e63-a2e0-4530-a39a-d53c560382bd",
        "description": "Can identify single saddle point",
        "matrix": "[[9,8,7],[5,3,2],[6,6,7]]",
        "expected": [{"row": 2, "column": 1}],
    },
    {
        "uuid": "6b501e2b-6c1f-491f-b1bb-7f278f760534",
        "description": "Can identify that empty matrix has no saddle points",
        "matrix": "[[]]",
        "expected": [],
    },
    {
        "uuid": "8c27cc64-e573-4fcb-a099-f0ae863fb02f",
        "description": "Can identify lack of saddle points when there are none",
        "matrix": "[[1,2,3],[3,1,2],[2,3,1]]",
        "expected": [],
    },
    {
        "uuid": "6d1399bd-e105-40fd-a2c9-c6609507d7a3",
        "description": "Can identify multiple saddle points in a column",
        "matrix": "[[4,5,4],[3,5,5],[1,5,4]]",
        "expected": [
            {"row": 1, "column": 2},
            {"row": 2, "column": 2},
            {"row": 3, "column": 2},
        ],
    },
    {
        "uuid": "3e81dce9-53b3-44e6-bf26-e328885fd5d1",
        "description": "Can identify multiple saddle points in a row",
        "matrix": "[[6,7,8],[5,5,5],[7,5,6]]",
        "expected": [
            {"row": 2, "column": 1},
            {"row": 2, "column": 2},
            {"row": 2, "column": 3},
        ],
    },
    {
        "uuid": "88868621-b6f4-4837-bb8b-3fad8b25d46b",
        "description": "Can identify saddle point in bottom right corner",
        "matrix": "[[8,7,9],[6,7,6],[3,2,5]]",
        "expected": [{"row": 3, "column": 3}],
    },
    {
        "uuid": "5b9499ca-fcea-4195-830a-9c4584a0ee79",
        "description": "Can identify saddle points in a non square matrix",
        "matrix": "[[3,1,3],[3,2,4]]",
        "expected": [
            {"row": 1, "column": 3},
            {"row": 1, "column": 1},
        ],
    },
    {
        "uuid": "ee99ccd2-a1f1-4283-ad39-f8c70f0cf594",
        "description": (
            "Can identify that saddle points in a single column matrix are "
            "those with the minimum value"
        ),
        "matrix": "[[2],[1],[4],[1]]",
        "expected": [
            {"row": 2, "column": 1},
            {"row": 4, "column": 1},
        ],
    },
    {
        "uuid": "63abf709-a84b-407f-a1b3-456638689713",
        "description": (
            "Can identify that saddle points in a single row matrix are "
            "those with the maximum value"
        ),
        "matrix": "[[2,5,3,5]]",
        "expected": [
            {"row": 1, "column": 2},
            {"row": 1, "column": 4},
        ],
    },
]

CASE_RESULTS_BEGIN = "__R08_T026_CASE_RESULTS_BEGIN__"
CASE_RESULTS_END = "__R08_T026_CASE_RESULTS_END__"
CASE_RESULTS_QUERY = f"""
.print {CASE_RESULTS_BEGIN}
.mode json
SELECT
  tests.uuid,
  tests.description,
  tests.matrix,
  tests.expected,
  actual.result AS actual_result
FROM
  tests
  JOIN "saddle-points" AS actual ON actual.matrix = tests.matrix
ORDER BY
  tests.rowid;
.print {CASE_RESULTS_END}
"""


class CheckFailure(Exception):
    """A validation failure that should be written to the evidence file."""


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
    tests_path = EXERCISE / ".meta/tests.toml"
    metadata = tomllib.loads(tests_path.read_text(encoding="utf-8"))
    expected_by_uuid = {case["uuid"]: case for case in EXPECTED_CASES}

    if set(metadata) != set(expected_by_uuid):
        missing = sorted(set(expected_by_uuid) - set(metadata))
        extra = sorted(set(metadata) - set(expected_by_uuid))
        raise CheckFailure(
            f"tests.toml UUID mismatch; missing={missing}, extra={extra}"
        )

    for uuid, expected in expected_by_uuid.items():
        entry = metadata[uuid]
        if entry.get("description") != expected["description"]:
            raise CheckFailure(
                f"tests.toml description mismatch for {uuid}: "
                f"{entry.get('description')!r}"
            )
        if entry.get("include", True) is not True:
            raise CheckFailure(f"Expected test {uuid} to be included")


def marked_json(stdout: str) -> list[dict[str, Any]]:
    start = stdout.find(CASE_RESULTS_BEGIN)
    end = stdout.find(CASE_RESULTS_END)
    if start < 0 or end < 0 or end <= start:
        raise CheckFailure("SQLite output is missing the case-results diagnostic block")

    payload_start = start + len(CASE_RESULTS_BEGIN)
    payload = stdout[payload_start:end].strip()
    try:
        rows = json.loads(payload)
    except json.JSONDecodeError as error:
        raise CheckFailure(f"Could not parse case-results diagnostic JSON: {error}") from error
    if not isinstance(rows, list):
        raise CheckFailure("Case-results diagnostic JSON is not an array")
    return rows


def execute_implementation(
    name: str,
    source_path: Path,
    sqlite_command: list[str],
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"r08-t026-{name}-") as temporary_dir:
        copied_exercise = Path(temporary_dir) / "saddle-points"
        shutil.copytree(EXERCISE, copied_exercise)
        _, copied_paths = read_config(copied_exercise)

        # Only the temporary learner file is replaced; the working exercise is untouched.
        shutil.copyfile(source_path, copied_paths["solution"])
        test_sql = copied_paths["test"].read_text(encoding="utf-8")
        input_sql = f"{test_sql.rstrip()}\n\n{CASE_RESULTS_QUERY}"

        try:
            process = subprocess.run(
                sqlite_command,
                input=input_sql,
                cwd=copied_exercise,
                text=True,
                capture_output=True,
                timeout=60,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise CheckFailure(f"{name} SQLite test run exceeded 60 seconds") from error

        record: dict[str, Any] = {
            "implementation": name,
            "source": str(source_path.relative_to(ROOT)),
            "command": (
                "sqlite3 -bail (stdin: configured saddle-points_test.sql "
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
        if output_path.is_file():
            try:
                record["output_json"] = json.loads(output_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                record["output_json_error"] = str(error)
        else:
            record["output_json_error"] = "output.json was not created"

        if process.returncode == 0:
            try:
                record["case_results"] = marked_json(process.stdout)
            except CheckFailure as error:
                record["case_results_error"] = str(error)

        return record


def expected_json(case: dict[str, Any]) -> str:
    ordered = sorted(
        case["expected"],
        key=lambda value: json.dumps(value, separators=(",", ":"), ensure_ascii=False),
    )
    return json.dumps(ordered, separators=(",", ":"), ensure_ascii=False)


def validate_run(record: dict[str, Any]) -> None:
    name = record["implementation"]
    if record["return_code"] != 0:
        raise CheckFailure(
            f"{name} SQLite process exited {record['return_code']}; "
            f"stderr={record['stderr']!r}"
        )

    results = record["output_json"]
    if not isinstance(results, list):
        raise CheckFailure(
            f"{name} output.json is invalid: {record['output_json_error']}"
        )
    if not results:
        raise CheckFailure(f"{name} executed zero tests")

    expected_descriptions = [case["description"] for case in EXPECTED_CASES]
    actual_descriptions = [
        result.get("description") if isinstance(result, dict) else None
        for result in results
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
    if len(results) != len(EXPECTED_CASES) or missing or extra or duplicates:
        raise CheckFailure(
            f"{name} output.json descriptions mismatch: "
            f"count={len(results)}, missing={missing}, extra={extra}, "
            f"duplicates={duplicates}"
        )

    failures = [
        (result.get("description"), result.get("status"))
        for result in results
        if not isinstance(result, dict) or result.get("status") != "pass"
    ]
    if failures:
        raise CheckFailure(f"{name} has non-pass output.json results: {failures}")

    case_rows = record["case_results"]
    if not isinstance(case_rows, list):
        raise CheckFailure(
            f"{name} could not read test inputs and actual results: "
            f"{record['case_results_error']}"
        )
    if len(case_rows) != len(EXPECTED_CASES):
        raise CheckFailure(
            f"{name} case result count is {len(case_rows)}, "
            f"expected {len(EXPECTED_CASES)}"
        )

    expected_by_uuid = {case["uuid"]: case for case in EXPECTED_CASES}
    actual_by_uuid: dict[str, dict[str, Any]] = {}
    for row in case_rows:
        uuid = row.get("uuid")
        if uuid in actual_by_uuid:
            raise CheckFailure(f"{name} returned duplicate case UUID {uuid}")
        actual_by_uuid[uuid] = row
    if set(actual_by_uuid) != set(expected_by_uuid):
        raise CheckFailure(
            f"{name} case UUID mismatch: missing="
            f"{sorted(set(expected_by_uuid) - set(actual_by_uuid))}, extra="
            f"{sorted(set(actual_by_uuid) - set(expected_by_uuid))}"
        )

    for uuid, expected in expected_by_uuid.items():
        row = actual_by_uuid[uuid]
        expected_matrix = json.loads(expected["matrix"])
        expected_text = json.dumps(expected["expected"], separators=(",", ":"))
        if row.get("description") != expected["description"]:
            raise CheckFailure(f"{name} SQL description mismatch for {uuid}")
        if json.loads(row["matrix"]) != expected_matrix:
            raise CheckFailure(f"{name} SQL input mismatch for {uuid}")
        if json.loads(row["expected"]) != expected["expected"]:
            raise CheckFailure(f"{name} SQL expected-output mismatch for {uuid}")

        actual_text = row.get("actual_result")
        wanted_actual_text = expected_json(expected)
        if actual_text != wanted_actual_text:
            raise CheckFailure(
                f"{name} output mismatch for {expected['description']}: "
                f"expected tested JSON {wanted_actual_text}, got {actual_text!r} "
                f"(canonical expected array: {expected_text})"
            )

    record["executed_test_count"] = len(results)
    record["passed_test_count"] = len(results)
    record["failed_test_count"] = 0
    record["expected_vs_actual"] = [
        {
            "uuid": case["uuid"],
            "description": case["description"],
            "input": json.loads(case["matrix"]),
            "expected": case["expected"],
            "actual": json.loads(actual_by_uuid[case["uuid"]]["actual_result"]),
        }
        for case in EXPECTED_CASES
    ]


def write_evidence(evidence: dict[str, Any]) -> None:
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    VERIFICATION_FILE.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    evidence: dict[str, Any] = {
        "task": "R08-T026",
        "status": "running",
        "checker_command": "python3 work/R08-T026/check.py",
        "tool_versions": {
            "python": sys.version,
            "sqlite_cli": None,
        },
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "expected_test_count": len(EXPECTED_CASES),
        "runs": [],
        "limitations": [
            "The SQLite harness compares result JSON text; the checker matches "
            "its ordering convention by sorting expected objects by their JSON value.",
            "Runtime and memory costs of the SQL approaches were not benchmarked.",
        ],
    }

    try:
        validate_metadata()
        version = subprocess.run(
            ["sqlite3", "--version"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        if version.returncode != 0:
            raise CheckFailure(
                f"Could not obtain SQLite CLI version: {version.stderr.strip()}"
            )
        evidence["tool_versions"]["sqlite_cli"] = version.stdout.strip()

        _, paths = read_config(EXERCISE)
        alternative = TASK_DIR / "alternative.sql"
        if not alternative.is_file():
            raise CheckFailure(f"Alternative SQL file does not exist: {alternative}")

        implementations = (
            ("reference", paths["example"]),
            ("alternative", alternative),
        )
        for name, source in implementations:
            record = execute_implementation(name, source, ["sqlite3", "-bail"])
            evidence["runs"].append(record)
            validate_run(record)

        evidence["status"] = "passed"
    except CheckFailure as error:
        evidence["status"] = "failed"
        evidence["failure"] = str(error)
        write_evidence(evidence)
        print(f"FAIL: {error}", file=sys.stderr)
        for run in evidence["runs"]:
            if run.get("stdout"):
                print(f"--- {run['implementation']} stdout ---", file=sys.stderr)
                print(run["stdout"], file=sys.stderr)
            if run.get("stderr"):
                print(f"--- {run['implementation']} stderr ---", file=sys.stderr)
                print(run["stderr"], file=sys.stderr)
        return 1

    write_evidence(evidence)
    for run in evidence["runs"]:
        print(
            f"{run['implementation']}: {run['executed_test_count']} tests, "
            f"{run['passed_test_count']} passed, {run['failed_test_count']} failed"
        )
    print(f"Evidence written to {VERIFICATION_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
