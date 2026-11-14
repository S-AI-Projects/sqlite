#!/usr/bin/env python3
"""Verify RNA transcription's maintained reference in isolated exercise copies."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import tomllib
import traceback
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EXERCISE = ROOT / "exercises/practice/rna-transcription"
TASK_DIR = ROOT / "work/R08-T030"
CONFIG_PATH = EXERCISE / ".meta/config.json"
TESTS_TOML_PATH = EXERCISE / ".meta/tests.toml"
EVIDENCE_PATH = TASK_DIR / "verification.json"

EXPECTED_CASES = {
    "b4631f82-c98c-4a2f-90b3-c5c2b6c6f661": {
        "description": "Empty RNA sequence",
        "input": "",
        "expected": "",
    },
    "a9558a3c-318c-4240-9256-5d5ed47005a6": {
        "description": "RNA complement of cytosine is guanine",
        "input": "C",
        "expected": "G",
    },
    "6eedbb5c-12cb-4c8b-9f51-f8320b4dc2e7": {
        "description": "RNA complement of guanine is cytosine",
        "input": "G",
        "expected": "C",
    },
    "870bd3ec-8487-471d-8d9a-a25046488d3e": {
        "description": "RNA complement of thymine is adenine",
        "input": "T",
        "expected": "A",
    },
    "aade8964-02e1-4073-872f-42d3ffd74c5f": {
        "description": "RNA complement of adenine is uracil",
        "input": "A",
        "expected": "U",
    },
    "79ed2757-f018-4f47-a1d7-34a559392dbf": {
        "description": "RNA complement",
        "input": "ACGTGGTCTTAA",
        "expected": "UGCACCAGAAUU",
    },
}

RESULTS_BEGIN = "__R08_T030_RESULTS_BEGIN__"
RESULTS_END = "__R08_T030_RESULTS_END__"
PROBE_MARKER = "__R08_T030_PROBE__"
RESULTS_SQL = f"""
.print {RESULTS_BEGIN}
.mode json
SELECT
  tests.uuid,
  tests.name,
  tests.dna,
  tests.expected,
  actual.result AS actual_result
FROM
  tests
  LEFT JOIN "rna-transcription" AS actual ON actual.dna = tests.dna
ORDER BY
  tests.rowid;
.print {RESULTS_END}
"""

FAILING_REFERENCE_SQL = """
UPDATE "rna-transcription"
SET result = dna;
"""

SCENARIOS = {
    "reference": {
        "expected_exit": 0,
        "expected_failure": None,
    },
    "failing-reference": {
        "expected_exit": 1,
        "expected_failure": "Non-pass output.json entries",
    },
    "empty-selection": {
        "expected_exit": 1,
        "expected_failure": "zero tests",
    },
    "sqlite-error": {
        "expected_exit": 1,
        "expected_failure": "SQLite child exited",
    },
}


class CheckFailure(Exception):
    """A validation failure that should result in a non-zero checker status."""


def load_config(config_path: Path) -> dict[str, Any]:
    try:
        value = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CheckFailure(f"Could not read config JSON {config_path}: {error}") from error
    if not isinstance(value, dict):
        raise CheckFailure(f"Config must contain a JSON object: {config_path}")
    return value


def resolve_configured_files(
    config_path: Path,
) -> tuple[dict[str, Any], dict[str, list[Path]]]:
    exercise_root = config_path.parent.parent.resolve()
    config = load_config(config_path)
    declared = config.get("files")
    if not isinstance(declared, dict):
        raise CheckFailure("Config must contain a files object")

    resolved: dict[str, list[Path]] = {}
    for kind, entries in declared.items():
        if not isinstance(entries, list) or not entries:
            raise CheckFailure(f"Config files.{kind} must be a non-empty path array")
        paths = []
        for entry in entries:
            if not isinstance(entry, str) or not entry:
                raise CheckFailure(f"Config files.{kind} contains an invalid path")
            relative = Path(entry)
            if relative.is_absolute() or ".." in relative.parts:
                raise CheckFailure(f"Config files.{kind} escapes the exercise: {entry!r}")
            path = (exercise_root / relative).resolve()
            try:
                path.relative_to(exercise_root)
            except ValueError as error:
                raise CheckFailure(
                    f"Config files.{kind} resolves outside the exercise: {entry!r}"
                ) from error
            if not path.is_file():
                raise CheckFailure(f"Config files.{kind} file does not exist: {entry!r}")
            paths.append(path)
        resolved[kind] = paths

    for kind in ("solution", "test", "example"):
        if kind not in resolved:
            raise CheckFailure(f"Config files is missing required {kind!r}")
        if len(resolved[kind]) != 1:
            raise CheckFailure(f"Expected one configured {kind} file")
    return config, resolved


def load_enabled_cases() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    try:
        metadata = tomllib.loads(TESTS_TOML_PATH.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise CheckFailure(f"Could not parse {TESTS_TOML_PATH}: {error}") from error

    if set(metadata) != set(EXPECTED_CASES):
        raise CheckFailure(
            "tests.toml UUID mismatch: "
            f"missing={sorted(set(EXPECTED_CASES) - set(metadata))}, "
            f"extra={sorted(set(metadata) - set(EXPECTED_CASES))}"
        )
    for uuid, case in EXPECTED_CASES.items():
        entry = metadata[uuid]
        if not isinstance(entry, dict) or entry.get("description") != case["description"]:
            raise CheckFailure(f"Description metadata mismatch for UUID {uuid}")

    enabled = {
        uuid: entry
        for uuid, entry in metadata.items()
        if entry.get("include", True)
    }
    reimplemented = {
        entry["reimplements"]
        for entry in enabled.values()
        if isinstance(entry, dict) and "reimplements" in entry
    }
    enabled = {
        uuid: entry for uuid, entry in enabled.items() if uuid not in reimplemented
    }
    if set(enabled) != set(EXPECTED_CASES):
        raise CheckFailure(
            f"Expected all {len(EXPECTED_CASES)} selected cases enabled; "
            f"found {len(enabled)}"
        )
    return metadata, enabled


def hash_files(paths: list[Path]) -> dict[str, str]:
    digests = {}
    for path in sorted(paths):
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        digests[str(path.relative_to(ROOT))] = digest.hexdigest()
    return digests


def exercise_hashes() -> dict[str, str]:
    paths = sorted(path for path in EXERCISE.rglob("*") if path.is_file())
    return hash_files(paths)


def sqlite_version() -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["sqlite3", "--version"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise CheckFailure(f"Could not query SQLite version: {error}") from error
    if result.returncode != 0:
        raise CheckFailure(
            f"sqlite3 --version exited {result.returncode}: {result.stderr}"
        )
    return {
        "command": ["sqlite3", "--version"],
        "return_code": result.returncode,
        "version": result.stdout.strip(),
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def parse_result_rows(stdout: str) -> list[dict[str, Any]]:
    start = stdout.find(RESULTS_BEGIN)
    end = stdout.find(RESULTS_END)
    if start < 0 or end < 0 or end <= start:
        raise CheckFailure("SQLite output is missing the actual-results query block")
    payload = stdout[start + len(RESULTS_BEGIN) : end].strip()
    if not payload:
        return []
    try:
        rows = json.loads(payload)
    except json.JSONDecodeError as error:
        raise CheckFailure(f"Could not parse actual-results JSON: {error}") from error
    if not isinstance(rows, list):
        raise CheckFailure("Actual-results query did not return a JSON array")
    return rows


def read_output_json(path: Path) -> tuple[Any, str | None]:
    if not path.is_file():
        return None, "output.json was not created"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        return None, str(error)
    if not text.strip():
        return [], None
    try:
        return json.loads(text), None
    except json.JSONDecodeError as error:
        return None, str(error)


def validate_run(
    sqlite_record: dict[str, Any],
    output: Any,
    output_error: str | None,
    actual_rows: list[dict[str, Any]] | None,
    actual_rows_error: str | None,
    enabled: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if sqlite_record["return_code"] != 0:
        raise CheckFailure(
            f"SQLite child exited {sqlite_record['return_code']}; "
            f"stderr={sqlite_record['stderr']!r}"
        )
    if not isinstance(output, list):
        raise CheckFailure(f"Invalid output.json: {output_error}")
    if not output:
        raise CheckFailure("Test run executed zero tests")
    if len(output) != len(enabled):
        raise CheckFailure(
            f"output.json has {len(output)} entries; expected {len(enabled)}"
        )
    if not all(isinstance(item, dict) for item in output):
        raise CheckFailure("output.json contains a non-object test entry")

    expected_names = [entry["description"] for entry in enabled.values()]
    actual_names = [item.get("name") for item in output]
    if Counter(actual_names) != Counter(expected_names):
        raise CheckFailure(
            f"output.json names mismatch: expected={expected_names}, actual={actual_names}"
        )
    failed = [
        (item.get("name"), item.get("status"))
        for item in output
        if item.get("status") != "pass"
    ]
    if failed:
        raise CheckFailure(f"Non-pass output.json entries: {failed}")
    if not isinstance(actual_rows, list):
        raise CheckFailure(f"Could not read actual results: {actual_rows_error}")
    if len(actual_rows) != len(enabled):
        raise CheckFailure(
            f"Actual-results query returned {len(actual_rows)} rows; "
            f"expected {len(enabled)}"
        )

    by_uuid = {}
    for row in actual_rows:
        if not isinstance(row, dict):
            raise CheckFailure(f"Invalid actual-results row: {row!r}")
        uuid = row.get("uuid")
        if uuid in by_uuid:
            raise CheckFailure(f"Duplicate UUID in actual results: {uuid}")
        by_uuid[uuid] = row
    if set(by_uuid) != set(enabled):
        raise CheckFailure(
            "Actual-result UUID mismatch: "
            f"missing={sorted(set(enabled) - set(by_uuid))}, "
            f"extra={sorted(set(by_uuid) - set(enabled))}"
        )

    expected_actual = []
    for uuid, metadata_entry in enabled.items():
        row = by_uuid[uuid]
        case = EXPECTED_CASES[uuid]
        if row.get("name") != metadata_entry["description"]:
            raise CheckFailure(f"Generated test name mismatch for UUID {uuid}")
        if row.get("dna") != case["input"]:
            raise CheckFailure(f"Generated input mismatch for {metadata_entry['description']}")
        if row.get("expected") != case["expected"]:
            raise CheckFailure(
                f"Generated expected output mismatch for {metadata_entry['description']}"
            )
        if row.get("actual_result") != case["expected"]:
            raise CheckFailure(
                f"Wrong output for {metadata_entry['description']}: "
                f"expected={case['expected']!r}, actual={row.get('actual_result')!r}"
            )
        expected_actual.append(
            {
                "uuid": uuid,
                "description": metadata_entry["description"],
                "input": row["dna"],
                "expected": row["expected"],
                "actual": row["actual_result"],
            }
        )
    return expected_actual


def run_sqlite(
    copied_exercise: Path,
    test_sql: str,
    *,
    sqlite_error: bool,
) -> dict[str, Any]:
    script = f"{test_sql.rstrip()}\n\n{RESULTS_SQL}"
    if sqlite_error:
        script += "\nSELECT * FROM r08_t030_missing_table;\n"
    try:
        result = subprocess.run(
            ["sqlite3", "-bail"],
            input=script,
            cwd=copied_exercise,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError as error:
        raise CheckFailure("SQLite CLI 'sqlite3' was not found on PATH") from error
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        return {
            "command": ["sqlite3", "-bail"],
            "return_code": None,
            "timed_out": True,
            "stdout": stdout.decode(errors="replace") if isinstance(stdout, bytes) else stdout,
            "stderr": stderr.decode(errors="replace") if isinstance(stderr, bytes) else stderr,
            "stdin_sql_sha256": hashlib.sha256(script.encode("utf-8")).hexdigest(),
            "stdin_sql_bytes": len(script.encode("utf-8")),
            "stdin_sql_description": "Configured test SQL plus the checker results query",
        }
    return {
        "command": ["sqlite3", "-bail"],
        "return_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "stdin_sql_sha256": hashlib.sha256(script.encode("utf-8")).hexdigest(),
        "stdin_sql_bytes": len(script.encode("utf-8")),
        "stdin_sql_description": (
            "Configured test SQL plus the checker results query"
            + (
                "; includes an empty-selection deletion"
                if "DELETE FROM tests;" in script
                else ""
            )
            + (
                "; includes a deliberate missing-table query"
                if "r08_t030_missing_table" in script
                else ""
            )
        ),
    }


def build_scenario_sql(test_sql: str, scenario: str) -> str:
    if scenario == "empty-selection":
        marker = "-- Comparison of user input and the tests updates the status for each test:"
        if marker not in test_sql:
            raise CheckFailure("Could not locate comparison point for empty-selection probe")
        test_sql = test_sql.replace(
            marker,
            "DELETE FROM tests;\n\n" + marker,
            1,
        )
    return test_sql


def run_scenario(
    name: str,
    parent_temp_root: Path,
) -> dict[str, Any]:
    if name not in SCENARIOS:
        raise CheckFailure(f"Unknown scenario: {name}")

    _, configured_files = resolve_configured_files(CONFIG_PATH)
    _, enabled = load_enabled_cases()
    scenario_dir = parent_temp_root / f"exercise-copy-{name}"
    record: dict[str, Any] = {
        "name": name,
        "expected_checker_exit_status": SCENARIOS[name]["expected_exit"],
        "checker_exit_status": None,
        "checker_failure": None,
        "resolved_paths": {
            kind: [str(path.relative_to(EXERCISE)) for path in paths]
            for kind, paths in configured_files.items()
        },
        "copy_path": str(scenario_dir),
        "hidden_paths_verified": [],
        "sqlite": None,
        "output_json_error": None,
        "actual_results_error": None,
        "expected_vs_actual": [],
        "executed_test_count": 0,
        "copy_removed": False,
        "passed": False,
    }

    try:
        shutil.copytree(EXERCISE, scenario_dir)
        for hidden_path in (
            ".meta/config.json",
            ".meta/example.sql",
            ".docs/instructions.md",
            ".docs/hints.md",
        ):
            if not (scenario_dir / hidden_path).is_file():
                raise CheckFailure(f"Temporary copy is missing hidden file {hidden_path}")
            record["hidden_paths_verified"].append(hidden_path)
        _, copied_files = resolve_configured_files(scenario_dir / ".meta/config.json")
        copied_solution = copied_files["solution"][0]
        copied_example = copied_files["example"][0]
        copied_test = copied_files["test"][0]

        if name == "failing-reference":
            copied_solution.write_text(FAILING_REFERENCE_SQL, encoding="utf-8")
        else:
            shutil.copyfile(copied_example, copied_solution)

        test_sql = build_scenario_sql(
            copied_test.read_text(encoding="utf-8"),
            name,
        )
        sqlite_record = run_sqlite(
            scenario_dir,
            test_sql,
            sqlite_error=name == "sqlite-error",
        )
        record["sqlite"] = sqlite_record

        output, output_error = read_output_json(scenario_dir / "output.json")
        record["output_json_error"] = output_error
        record["executed_test_count"] = len(output) if isinstance(output, list) else 0
        record["output_statuses"] = [
            {"name": item.get("name"), "status": item.get("status")}
            for item in output
            if isinstance(item, dict)
        ] if isinstance(output, list) else []

        actual_rows = None
        actual_rows_error = None
        try:
            actual_rows = parse_result_rows(sqlite_record["stdout"])
        except CheckFailure as error:
            actual_rows_error = str(error)
        record["actual_results_error"] = actual_rows_error
        if isinstance(actual_rows, list):
            record["expected_vs_actual"] = [
                {
                    "uuid": row.get("uuid"),
                    "description": row.get("name"),
                    "input": row.get("dna"),
                    "expected": row.get("expected"),
                    "actual": row.get("actual_result"),
                }
                for row in actual_rows
                if isinstance(row, dict)
            ]

        validation_error = None
        try:
            record["expected_vs_actual"] = validate_run(
                sqlite_record,
                output,
                output_error,
                actual_rows,
                actual_rows_error,
                enabled,
            )
        except CheckFailure as error:
            validation_error = str(error)
        checker_exit_status = 1 if validation_error else 0
        record["checker_exit_status"] = checker_exit_status
        record["checker_failure"] = validation_error
        if validation_error or sqlite_record["return_code"] != 0:
            record["sqlite"]["stdout"] = sqlite_record["stdout"]
        else:
            record["sqlite"].pop("stdout", None)
        if not record["sqlite"]["stderr"]:
            record["sqlite"].pop("stderr", None)

        expected_failure = SCENARIOS[name]["expected_failure"]
        failure_matches = (
            validation_error is None
            if expected_failure is None
            else validation_error is not None and expected_failure in validation_error
        )
        record["passed"] = (
            checker_exit_status == SCENARIOS[name]["expected_exit"]
            and failure_matches
        )
    except Exception as error:
        record["unexpected_error"] = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
        record["checker_failure"] = f"Unexpected {type(error).__name__}: {error}"
        record["checker_exit_status"] = 1
    finally:
        try:
            if scenario_dir.exists():
                shutil.rmtree(scenario_dir)
        except OSError as error:
            record["cleanup_error"] = str(error)
        record["copy_removed"] = not scenario_dir.exists()
        if not record["copy_removed"]:
            record["passed"] = False
    return record


def terminate_process_tree(process: subprocess.Popen[str]) -> tuple[str, str]:
    if process.poll() is not None:
        return process.communicate()
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return process.communicate()
    else:
        process.terminate()
    try:
        return process.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        return process.communicate(timeout=10)


def scenario_main(name: str, parent_temp_root: Path) -> int:
    try:
        if not parent_temp_root.is_dir():
            raise CheckFailure(f"Parent temporary root does not exist: {parent_temp_root}")
        record = run_scenario(name, parent_temp_root)
    except Exception as error:
        record = {
            "name": name,
            "passed": False,
            "checker_exit_status": 1,
            "checker_failure": f"Unexpected {type(error).__name__}: {error}",
            "unexpected_error": {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            },
        }
    print(PROBE_MARKER + json.dumps(record, ensure_ascii=False))
    return record["checker_exit_status"]


def run_probe_subprocess(
    name: str,
    learner_files: list[Path],
) -> dict[str, Any]:
    before_hashes = exercise_hashes()
    learner_hashes_before = hash_files(learner_files)
    record: dict[str, Any] = {
        "name": name,
        "command": None,
        "expected_process_exit_status": SCENARIOS[name]["expected_exit"],
        "process_exit_status": None,
        "stdout": "",
        "stderr": "",
        "parent_temp_root": None,
        "parent_temp_root_removed": False,
        "exercise_hashes_before": before_hashes,
        "exercise_hashes_after": None,
        "learner_hashes_before": learner_hashes_before,
        "learner_hashes_after": None,
        "original_files_unchanged": False,
        "scenario": None,
        "passed": False,
    }
    temp_root: Path | None = None
    process: subprocess.Popen[str] | None = None

    try:
        with tempfile.TemporaryDirectory(prefix=f"r08-t030-{name}-") as directory:
            temp_root = Path(directory)
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--scenario",
                name,
                "--temp-root",
                str(temp_root),
            ]
            record["command"] = command
            record["parent_temp_root"] = str(temp_root)
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=os.name == "posix",
            )
            try:
                stdout, stderr = process.communicate(timeout=120)
            except subprocess.TimeoutExpired:
                record["timed_out"] = True
                stdout, stderr = terminate_process_tree(process)
            record["process_exit_status"] = process.returncode
            record["stdout"] = stdout
            record["stderr"] = stderr
            marker = next(
                (
                    line[len(PROBE_MARKER) :]
                    for line in stdout.splitlines()
                    if line.startswith(PROBE_MARKER)
                ),
                None,
            )
            if marker is not None:
                try:
                    scenario_record = json.loads(marker)
                except json.JSONDecodeError as error:
                    record["failure"] = f"Could not parse probe result: {error}"
                else:
                    record["scenario"] = scenario_record
                    record["stdout"] = "\n".join(
                        line
                        for line in stdout.splitlines()
                        if not line.startswith(PROBE_MARKER)
                    )
                    record["passed"] = bool(
                        not record.get("timed_out")
                        and process.returncode == SCENARIOS[name]["expected_exit"]
                        and scenario_record.get("checker_exit_status") == process.returncode
                        and scenario_record.get("passed")
                        and scenario_record.get("copy_removed")
                    )
                    if not record["passed"]:
                        record["failure"] = scenario_record.get(
                            "checker_failure", "Scenario did not meet its expected outcome"
                        )
            else:
                record["failure"] = "Scenario process did not emit probe evidence"
    except Exception as error:
        record["failure"] = f"Unexpected {type(error).__name__}: {error}"
        record["unexpected_error"] = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
        if process is not None:
            record["stdout"], record["stderr"] = terminate_process_tree(process)
    record["parent_temp_root_removed"] = (
        temp_root is not None and not temp_root.exists()
    )
    record["exercise_hashes_after"] = exercise_hashes()
    record["learner_hashes_after"] = hash_files(learner_files)
    record["original_files_unchanged"] = (
        record["exercise_hashes_before"] == record["exercise_hashes_after"]
        and record["learner_hashes_before"] == record["learner_hashes_after"]
    )
    if not record["parent_temp_root_removed"] or not record["original_files_unchanged"]:
        record["passed"] = False
        record["failure"] = "Parent cleanup or original-file integrity check failed"
    return record


def write_evidence(evidence: dict[str, Any]) -> None:
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    evidence: dict[str, Any] = {
        "task": "R08-T030",
        "issue": "S-AI-Projects/sqlite#33",
        "status": "running",
        "checker_command": ["python3", "work/R08-T030/check.py"],
        "config_path": str(CONFIG_PATH.relative_to(ROOT)),
        "resolved_paths": None,
        "tool_versions": {
            "python": sys.version,
            "sqlite_cli": None,
        },
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "expected_enabled_test_count": len(EXPECTED_CASES),
        "original_file_hashes_before": None,
        "original_file_hashes_after": None,
        "original_files_unchanged": False,
        "probes": [],
        "failures": [],
    }
    try:
        _, configured_files = resolve_configured_files(CONFIG_PATH)
        _, enabled = load_enabled_cases()
        evidence["resolved_paths"] = {
            kind: [str(path.relative_to(EXERCISE)) for path in paths]
            for kind, paths in configured_files.items()
        }
        evidence["expected_enabled_test_count"] = len(enabled)
        evidence["tool_versions"]["sqlite_cli"] = sqlite_version()
        original_hashes = exercise_hashes()
        evidence["original_file_hashes_before"] = original_hashes

        for name in SCENARIOS:
            probe = run_probe_subprocess(name, configured_files["solution"])
            evidence["probes"].append(probe)
            if not probe["passed"]:
                evidence["failures"].append(
                    f"{name}: {probe.get('failure', 'probe failed')}"
                )

        final_hashes = exercise_hashes()
        evidence["original_file_hashes_after"] = final_hashes
        evidence["original_files_unchanged"] = original_hashes == final_hashes
        if not evidence["original_files_unchanged"]:
            evidence["failures"].append("Original exercise files changed")
        evidence["status"] = "passed" if not evidence["failures"] else "failed"
    except CheckFailure as error:
        evidence["status"] = "failed"
        evidence["failures"].append(str(error))
        evidence["failure_traceback"] = traceback.format_exc()
    except Exception as error:
        evidence["status"] = "failed"
        evidence["failures"].append(f"Unexpected {type(error).__name__}: {error}")
        evidence["unexpected_error"] = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }

    write_evidence(evidence)
    if evidence["status"] != "passed":
        print("FAIL: " + "; ".join(evidence["failures"]), file=sys.stderr)
        for probe in evidence["probes"]:
            if not probe.get("passed"):
                if probe.get("stderr"):
                    print(f"--- {probe['name']} stderr ---", file=sys.stderr)
                    print(probe["stderr"], file=sys.stderr)
        print(f"Evidence written to {EVIDENCE_PATH.relative_to(ROOT)}", file=sys.stderr)
        return 1

    for probe in evidence["probes"]:
        scenario = probe["scenario"]
        print(
            f"{probe['name']}: checker exit {probe['process_exit_status']} "
            f"(expected {probe['expected_process_exit_status']}), "
            f"SQLite exit {scenario['sqlite']['return_code']}, "
            f"{scenario['executed_test_count']} tests, "
            f"copy cleaned={scenario['copy_removed']}, "
            f"original files unchanged={probe['original_files_unchanged']}"
        )
    successful = evidence["probes"][0]["scenario"]
    print(
        f"Passed {successful['executed_test_count']} reference tests; "
        f"all {len(evidence['probes'])} probes passed."
    )
    print(f"Evidence written to {EVIDENCE_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    if (
        len(sys.argv) == 5
        and sys.argv[1] == "--scenario"
        and sys.argv[3] == "--temp-root"
    ):
        raise SystemExit(scenario_main(sys.argv[2], Path(sys.argv[4])))
    if len(sys.argv) != 1:
        print("Usage: check.py [--scenario NAME --temp-root PATH]", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main())
