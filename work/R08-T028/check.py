#!/usr/bin/env python3
"""Validate Wordy's configured paths and run the reference tests safely."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib
import traceback
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EXERCISE = ROOT / "exercises/practice/wordy"
TASK_DIR = ROOT / "work/R08-T028"
CONFIG_PATH = EXERCISE / ".meta/config.json"
TESTS_TOML_PATH = EXERCISE / ".meta/tests.toml"
VERIFICATION_PATH = TASK_DIR / "verification.json"
EXPECTED_DESCRIPTIONS = {
    "88bf4b28-0de3-4883-93c7-db1b14aa806e": "just a number",
    "18983214-1dfc-4ebd-ac77-c110dde699ce": "just a zero",
    "607c08ee-2241-4288-916d-dae5455c87e6": "just a negative number",
    "bb8c655c-cf42-4dfc-90e0-152fcfd8d4e0": "addition",
    "bb9f2082-171c-46ad-ad4e-c3f72087c1b5": "addition with a left hand zero",
    "6fa05f17-405a-4742-80ae-5d1a8edb0d5d": "addition with a right hand zero",
    "79e49e06-c5ae-40aa-a352-7a3a01f70015": "more addition",
    "b345dbe0-f733-44e1-863c-5ae3568f3803": "addition with negative numbers",
    "cd070f39-c4cc-45c4-97fb-1be5e5846f87": "large addition",
    "0d86474a-cd93-4649-a4fa-f6109a011191": "subtraction",
    "30bc8395-5500-4712-a0cf-1d788a529be5": "multiplication",
    "34c36b08-8605-4217-bb57-9a01472c427f": "division",
    "da6d2ce4-fb94-4d26-8f5f-b078adad0596": "multiple additions",
    "7fd74c50-9911-4597-be09-8de7f2fea2bb": "addition and subtraction",
    "b120ffd5-bad6-4e22-81c8-5512e8faf905": "multiple subtraction",
    "4f4a5749-ef0c-4f60-841f-abcfaf05d2ae": "subtraction then addition",
    "312d908c-f68f-42c9-aa75-961623cc033f": "multiple multiplication",
    "38e33587-8940-4cc1-bc28-bfd7e3966276": "addition and multiplication",
    "3c854f97-9311-46e8-b574-92b60d17d394": "multiple division",
    "3ad3e433-8af7-41ec-aa9b-97b42ab49357": "unknown operation",
    "8a7e85a8-9e7b-4d46-868f-6d759f4648f8": "Non math question",
    "42d78b5f-dbd7-4cdb-8b30-00f794bb24cf": "reject problem missing an operand",
    "c2c3cbfc-1a72-42f2-b597-246e617e66f5": "reject problem with no operands or operators",
    "4b3df66d-6ed5-4c95-a0a1-d38891fbdab6": "reject two operations in a row",
    "6abd7a50-75b4-4665-aa33-2030fd08bab1": "reject two numbers in a row",
    "10a56c22-e0aa-405f-b1d2-c642d9c4c9de": "reject postfix notation",
    "0035bc63-ac43-4bb5-ad6d-e8651b7d954e": "reject prefix notation",
}

CASE_RESULTS_BEGIN = "__R08_T028_CASE_RESULTS_BEGIN__"
CASE_RESULTS_END = "__R08_T028_CASE_RESULTS_END__"
CSV_IMPORT_WARNING = "expected 3 columns but found 2 - filling the rest with NULL"
CASE_RESULTS_SQL = f"""
.print {CASE_RESULTS_BEGIN}
.mode json
SELECT
  tests.uuid,
  tests.description,
  tests.question,
  tests.expected_result,
  tests.expected_error,
  actual.result AS actual_result,
  actual.error AS actual_error
FROM
  tests
  JOIN wordy AS actual ON actual.question = tests.question
ORDER BY
  tests.rowid;
.print {CASE_RESULTS_END}
"""


class CheckFailure(Exception):
    """A validation failure that should be written to verification.json."""


class MetadataPathError(CheckFailure):
    """An invalid configured file path, categorized for fixture assertions."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


def write_evidence(evidence: dict[str, Any]) -> None:
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    VERIFICATION_PATH.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_config(config_path: Path) -> dict[str, Any]:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CheckFailure(f"Invalid JSON in {config_path}: {error}") from error
    if not isinstance(config, dict):
        raise CheckFailure(f"Config must contain a JSON object: {config_path}")
    return config


def resolve_configured_files(
    config_path: Path,
) -> tuple[dict[str, Any], dict[str, list[Path]]]:
    exercise_root = config_path.parent.parent.resolve()
    config = load_config(config_path)
    files = config.get("files")
    if not isinstance(files, dict):
        raise MetadataPathError("invalid_files", "Config has no files object")

    for required in ("solution", "test", "example"):
        if required not in files:
            raise MetadataPathError(
                "missing_key", f"Config files object is missing {required!r}"
            )

    resolved: dict[str, list[Path]] = {}
    for kind, entries in files.items():
        if not isinstance(entries, list) or not entries:
            raise MetadataPathError(
                "invalid_path_list",
                f"Config files.{kind} must be a non-empty array of paths",
            )
        resolved_entries = []
        for entry in entries:
            if not isinstance(entry, str) or not entry:
                raise MetadataPathError(
                    "invalid_path",
                    f"Config files.{kind} contains a non-string or empty path",
                )
            relative_path = Path(entry)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise MetadataPathError(
                    "outside_exercise",
                    f"Config files.{kind} path escapes the exercise: {entry!r}",
                )

            target = (exercise_root / relative_path).resolve()
            try:
                target.relative_to(exercise_root)
            except ValueError as error:
                raise MetadataPathError(
                    "outside_exercise",
                    f"Config files.{kind} path resolves outside the exercise: {entry!r}",
                ) from error
            if not target.is_file():
                raise MetadataPathError(
                    "missing_file",
                    f"Config files.{kind} file does not exist: {entry!r}",
                )
            resolved_entries.append(target)
        resolved[kind] = resolved_entries
    return config, resolved


def single_configured_path(files: dict[str, list[Path]], kind: str) -> Path:
    entries = files[kind]
    if len(entries) != 1:
        raise CheckFailure(
            f"Expected exactly one configured {kind} file, found {len(entries)}"
        )
    return entries[0]


def validate_metadata() -> dict[str, dict[str, Any]]:
    try:
        metadata = tomllib.loads(TESTS_TOML_PATH.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise CheckFailure(f"Invalid TOML in {TESTS_TOML_PATH}: {error}") from error

    if set(metadata) != set(EXPECTED_DESCRIPTIONS):
        raise CheckFailure(
            "tests.toml UUID mismatch: "
            f"missing={sorted(set(EXPECTED_DESCRIPTIONS) - set(metadata))}, "
            f"extra={sorted(set(metadata) - set(EXPECTED_DESCRIPTIONS))}"
        )
    for uuid, expected_description in EXPECTED_DESCRIPTIONS.items():
        entry = metadata[uuid]
        if entry.get("description") != expected_description:
            raise CheckFailure(f"tests.toml description mismatch for UUID {uuid}")

    enabled = {
        uuid: entry
        for uuid, entry in metadata.items()
        if entry.get("include", True)
    }
    reimplemented = {
        entry["reimplements"]
        for entry in enabled.values()
        if "reimplements" in entry
    }
    enabled = {
        uuid: entry for uuid, entry in enabled.items() if uuid not in reimplemented
    }
    if set(enabled) != set(EXPECTED_DESCRIPTIONS):
        raise CheckFailure(
            "Enabled metadata case mismatch: "
            f"expected {len(EXPECTED_DESCRIPTIONS)}, found {len(enabled)}"
        )
    return metadata


def mutate_config(config_path: Path, field: str, path: str) -> None:
    config = load_config(config_path)
    config["files"][field] = [path]
    config_path.write_text(
        json.dumps(config, indent=2) + "\n",
        encoding="utf-8",
    )


def check_invalid_metadata_fixtures() -> list[dict[str, Any]]:
    fixtures = [
        {
            "name": "missing configured reference",
            "field": "example",
            "path": ".meta/missing-example.sql",
            "expected_reason": "missing_file",
            "outside_file": False,
        },
        {
            "name": "missing configured test",
            "field": "test",
            "path": "missing_test.sql",
            "expected_reason": "missing_file",
            "outside_file": False,
        },
        {
            "name": "configured path outside exercise",
            "field": "example",
            "path": "../outside.sql",
            "expected_reason": "outside_exercise",
            "outside_file": True,
        },
    ]
    results = []
    for fixture in fixtures:
        with tempfile.TemporaryDirectory(
            prefix="r08-t028-invalid-metadata-"
        ) as temporary_dir:
            temporary_root = Path(temporary_dir)
            copied_exercise = temporary_root / "wordy"
            shutil.copytree(EXERCISE, copied_exercise)
            config_path = copied_exercise / ".meta/config.json"
            mutate_config(config_path, fixture["field"], fixture["path"])
            if fixture["outside_file"]:
                (temporary_root / "outside.sql").write_text(
                    "-- outside exercise fixture\n",
                    encoding="utf-8",
                )

            try:
                resolve_configured_files(config_path)
            except MetadataPathError as error:
                if error.reason != fixture["expected_reason"]:
                    raise CheckFailure(
                        f"{fixture['name']} failed for {error.reason}, "
                        f"expected {fixture['expected_reason']}: {error}"
                    ) from error
                results.append(
                    {
                        "name": fixture["name"],
                        "config_change": {
                            f"files.{fixture['field']}": [fixture["path"]]
                        },
                        "expected_failure_reason": fixture["expected_reason"],
                        "actual_failure_reason": error.reason,
                        "diagnostic": str(error),
                        "passed": True,
                    }
                )
            else:
                raise CheckFailure(
                    f"Invalid metadata fixture was accepted: {fixture['name']}"
                )
    return results


def sqlite_version() -> dict[str, Any]:
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
    return {
        "command": "sqlite3 --version",
        "return_code": process.returncode,
        "version": process.stdout.strip(),
        "stdout": process.stdout,
        "stderr": process.stderr,
    }


def parse_marked_results(stdout: str) -> list[dict[str, Any]]:
    start = stdout.find(CASE_RESULTS_BEGIN)
    end = stdout.find(CASE_RESULTS_END)
    if start < 0 or end < 0 or end <= start:
        raise CheckFailure("SQLite output is missing the actual-results query block")
    payload = stdout[start + len(CASE_RESULTS_BEGIN) : end].strip()
    try:
        rows = json.loads(payload)
    except json.JSONDecodeError as error:
        raise CheckFailure(f"Could not parse actual-results JSON: {error}") from error
    if not isinstance(rows, list):
        raise CheckFailure("Actual-results query did not return a JSON array")
    return rows


def run_reference_tests(
    configured_files: dict[str, list[Path]],
) -> dict[str, Any]:
    solution_path = single_configured_path(configured_files, "solution")
    test_path = single_configured_path(configured_files, "test")
    example_path = single_configured_path(configured_files, "example")

    with tempfile.TemporaryDirectory(prefix="r08-t028-reference-") as temporary_dir:
        copied_exercise = Path(temporary_dir) / "wordy"
        shutil.copytree(EXERCISE, copied_exercise)
        _, copied_files = resolve_configured_files(
            copied_exercise / ".meta/config.json"
        )

        copied_solution = copied_files["solution"][0]
        copied_example = copied_files["example"][0]
        copied_test = copied_files["test"][0]
        shutil.copyfile(copied_example, copied_solution)

        test_sql = copied_test.read_text(encoding="utf-8")
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
            raise CheckFailure("Wordy SQLite tests exceeded 60 seconds") from error

        record: dict[str, Any] = {
            "command": "sqlite3 -bail < wordy_test.sql (plus read-only actual-results query)",
            "return_code": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
            "sqlite_csv_import_warning_count": sum(
                CSV_IMPORT_WARNING in line for line in process.stderr.splitlines()
            ),
            "output_json": None,
            "output_json_error": None,
            "actual_rows": None,
            "actual_rows_error": None,
            "configured_paths": {
                "solution": str(solution_path.relative_to(EXERCISE)),
                "test": str(test_path.relative_to(EXERCISE)),
                "example": str(example_path.relative_to(EXERCISE)),
            },
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
                record["actual_rows"] = parse_marked_results(process.stdout)
            except CheckFailure as error:
                record["actual_rows_error"] = str(error)
        return record


def validate_test_results(
    record: dict[str, Any],
    metadata: dict[str, dict[str, Any]],
) -> None:
    if record["return_code"] != 0:
        raise CheckFailure(
            f"SQLite test process exited {record['return_code']}; "
            f"stderr={record['stderr']!r}"
        )

    output = record["output_json"]
    if not isinstance(output, list):
        raise CheckFailure(f"Invalid output.json: {record['output_json_error']}")
    if not output:
        raise CheckFailure("Test run executed zero cases")
    expected_count = len(EXPECTED_DESCRIPTIONS)
    if len(output) != expected_count:
        raise CheckFailure(
            f"output.json has {len(output)} entries; expected {expected_count}"
        )

    expected_enabled = {
        uuid: entry
        for uuid, entry in metadata.items()
        if entry.get("include", True)
    }
    reimplemented = {
        entry["reimplements"]
        for entry in expected_enabled.values()
        if "reimplements" in entry
    }
    expected_enabled = {
        uuid: entry
        for uuid, entry in expected_enabled.items()
        if uuid not in reimplemented
    }
    expected_descriptions = [
        EXPECTED_DESCRIPTIONS[uuid] for uuid in expected_enabled
    ]
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

    failed_results = []
    for item in output:
        if not isinstance(item, dict):
            failed_results.append((repr(item), "invalid result entry"))
        elif item.get("status") != "pass":
            failed_results.append((item.get("description"), item.get("status")))
    if failed_results:
        raise CheckFailure(f"Non-pass output.json results: {failed_results}")

    actual_rows = record["actual_rows"]
    if not isinstance(actual_rows, list):
        raise CheckFailure(
            f"Could not read actual results: {record['actual_rows_error']}"
        )
    if len(actual_rows) != expected_count:
        raise CheckFailure(
            f"Test SQL returned {len(actual_rows)} actual rows; expected {expected_count}"
        )

    actual_by_uuid: dict[str, dict[str, Any]] = {}
    for row in actual_rows:
        uuid = row.get("uuid")
        if uuid in actual_by_uuid:
            raise CheckFailure(f"Duplicate test UUID in SQL results: {uuid}")
        actual_by_uuid[uuid] = row
    if set(actual_by_uuid) != set(expected_enabled):
        raise CheckFailure(
            "SQL test UUID mismatch: "
            f"missing={sorted(set(expected_enabled) - set(actual_by_uuid))}, "
            f"extra={sorted(set(actual_by_uuid) - set(expected_enabled))}"
        )

    expected_vs_actual = []
    for uuid, metadata_entry in expected_enabled.items():
        row = actual_by_uuid[uuid]
        description = EXPECTED_DESCRIPTIONS[uuid]
        if metadata_entry.get("description") != description:
            raise CheckFailure(f"Metadata description mismatch for {uuid}")
        if row.get("description") != description:
            raise CheckFailure(f"Generated test description mismatch for {uuid}")
        if row.get("actual_result") != row.get("expected_result"):
            raise CheckFailure(
                f"Wrong result for {description}: expected "
                f"{row.get('expected_result')!r}, got {row.get('actual_result')!r}"
            )
        if row.get("actual_error") != row.get("expected_error"):
            raise CheckFailure(
                f"Wrong error for {description}: expected "
                f"{row.get('expected_error')!r}, got {row.get('actual_error')!r}"
            )
        expected_vs_actual.append(
            {
                "uuid": uuid,
                "description": description,
                "question": row["question"],
                "expected": {
                    "result": row.get("expected_result"),
                    "error": row.get("expected_error"),
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
    record["output_json_results"] = [
        {"description": row["description"], "status": row["status"]}
        for row in output
    ]
    record["expected_vs_actual"] = expected_vs_actual
    warning_count = record["sqlite_csv_import_warning_count"]
    record["sqlite_csv_import_warnings"] = {
        "count": warning_count,
        "classification": "non-fatal" if warning_count else "none",
        "assessment": (
            f"All {warning_count} CSV import warnings were non-fatal: SQLite "
            f"exited with code {record['return_code']}, and all "
            f"{record['passed_test_count']} tests passed with expected results."
            if warning_count
            else "No CSV import warnings were emitted."
        ),
    }


def main() -> int:
    evidence: dict[str, Any] = {
        "task": "R08-T028",
        "status": "running",
        "checker_command": "python3 work/R08-T028/check.py",
        "config_path": str(CONFIG_PATH.relative_to(ROOT)),
        "tool_versions": {
            "python": sys.version,
            "sqlite_cli": None,
        },
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "expected_enabled_test_count": len(EXPECTED_DESCRIPTIONS),
        "resolved_paths": None,
        "invalid_metadata_fixtures": [],
        "test_run": None,
    }

    try:
        metadata = validate_metadata()
        _, configured_files = resolve_configured_files(CONFIG_PATH)
        evidence["resolved_paths"] = {
            kind: [str(path.relative_to(EXERCISE)) for path in paths]
            for kind, paths in configured_files.items()
        }
        evidence["tool_versions"]["sqlite_cli"] = sqlite_version()
        evidence["invalid_metadata_fixtures"] = check_invalid_metadata_fixtures()
        record = run_reference_tests(configured_files)
        evidence["test_run"] = record
        validate_test_results(record, metadata)
        evidence["status"] = "passed"
    except CheckFailure as error:
        evidence["status"] = "failed"
        evidence["failure"] = str(error)
        write_evidence(evidence)
        print(f"FAIL: {error}", file=sys.stderr)
        run = evidence.get("test_run")
        if isinstance(run, dict):
            if run.get("stdout"):
                print("--- SQLite stdout ---", file=sys.stderr)
                print(run["stdout"], file=sys.stderr)
            if run.get("stderr"):
                print("--- SQLite stderr ---", file=sys.stderr)
                print(run["stderr"], file=sys.stderr)
        return 1
    except Exception as error:
        evidence["status"] = "failed"
        evidence["failure"] = f"Unexpected {type(error).__name__}: {error}"
        evidence["unexpected_exception"] = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
        write_evidence(evidence)
        print(f"FAIL: {evidence['failure']}", file=sys.stderr)
        print(evidence["unexpected_exception"]["traceback"], file=sys.stderr)
        run = evidence.get("test_run")
        if isinstance(run, dict):
            if run.get("stdout"):
                print("--- SQLite stdout ---", file=sys.stderr)
                print(run["stdout"], file=sys.stderr)
            if run.get("stderr"):
                print("--- SQLite stderr ---", file=sys.stderr)
                print(run["stderr"], file=sys.stderr)
        return 1

    write_evidence(evidence)
    record = evidence["test_run"]
    print(
        f"Passed {record['executed_test_count']} tests "
        f"({record['passed_test_count']} passed, {record['failed_test_count']} failed)."
    )
    print(
        "Passed all "
        f"{len(evidence['invalid_metadata_fixtures'])} invalid metadata fixtures."
    )
    print(f"Evidence written to {VERIFICATION_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
