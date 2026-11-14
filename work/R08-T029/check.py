#!/usr/bin/env python3
"""Verify the tournament reference without changing learner files."""

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
import time
import tomllib
import traceback
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EXERCISE = ROOT / "exercises/practice/tournament"
TASK_DIR = ROOT / "work/R08-T029"
CONFIG_PATH = EXERCISE / ".meta/config.json"
TESTS_TOML_PATH = EXERCISE / ".meta/tests.toml"
EVIDENCE_PATH = TASK_DIR / "verification.json"

EXPECTED_DESCRIPTIONS = {
    "67e9fab1-07c1-49cf-9159-bc8671cc7c9c": "just the header if no input",
    "1b4a8aef-0734-4007-80a2-0626178c88f4": "a win is three points, a loss is zero points",
    "5f45ac09-4efe-46e7-8ddb-75ad85f86e05": "a win can also be expressed as a loss",
    "fd297368-efa0-442d-9f37-dd3f9a437239": "a different team can win",
    "26c016f9-e753-4a93-94e9-842f7b4d70fc": "a draw is one point each",
    "731204f6-4f34-4928-97eb-1c307ba83e62": "There can be more than one match",
    "49dc2463-42af-4ea6-95dc-f06cc5776adf": "There can be more than one winner",
    "6d930f33-435c-4e6f-9e2d-63fa85ce7dc7": "There can be more than two teams",
    "97022974-0c8a-4a50-8fe7-e36bdd8a5945": "typical input",
    "fe562f0d-ac0a-4c62-b9c9-44ee3236392b": "incomplete competition (not all pairs have played)",
    "3aa0386f-150b-4f99-90bb-5195e7b7d3b8": "ties broken alphabetically",
    "f9e20931-8a65-442a-81f6-503c0205b17a": "ensure points sorted numerically",
}

CASE_RESULTS_BEGIN = "__R08_T029_RESULTS_BEGIN__"
CASE_RESULTS_END = "__R08_T029_RESULTS_END__"
CASE_RESULTS_SQL = f"""
.print {CASE_RESULTS_BEGIN}
.mode json
SELECT
  tests.uuid,
  tests.description,
  tests.input,
  tests.expected,
  actual.result AS actual_result
FROM
  tests
  LEFT JOIN tournament AS actual ON actual.input = tests.input
ORDER BY
  tests.rowid;
.print {CASE_RESULTS_END}
"""
INTERRUPT_SQL = """
WITH RECURSIVE counter(value) AS (
  VALUES (1)
  UNION ALL
  SELECT value + 1
  FROM counter
  WHERE value < 1000000000
)
SELECT SUM(value) FROM counter;
"""
FAILING_REFERENCE_SQL = (
    "UPDATE tournament SET result = 'intentionally incorrect';\n"
)
PROBE_JSON_MARKER = "__R08_T029_PROBE_JSON__"
TIMEOUT_READY_FILE = "timeout-probe-ready"
PROBE_SPECS = {
    "real-reference": {"expected_checker_exit": 0},
    "failing-reference": {
        "expected_checker_exit": 1,
        "expected_failure_text": "Non-pass output.json entries",
        "failing_reference": True,
    },
    "empty-test-selection": {
        "expected_checker_exit": 1,
        "expected_failure_text": "zero tests",
        "empty_selection": True,
    },
    "sqlite-child-error": {
        "expected_checker_exit": 1,
        "expected_failure_text": "SQLite child exited",
        "child_error": True,
    },
    "interrupted-sqlite-child": {
        "expected_checker_exit": 1,
        "expected_failure_text": "SQLite child exited",
        "interrupt": True,
    },
}


class CheckFailure(Exception):
    """A validation failure with an actionable diagnostic."""


def load_config(config_path: Path) -> dict[str, Any]:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CheckFailure(f"Could not read valid config JSON at {config_path}: {error}") from error
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
        raise CheckFailure("Config must contain a files object")

    resolved: dict[str, list[Path]] = {}
    for kind, entries in files.items():
        if not isinstance(entries, list) or not entries:
            raise CheckFailure(f"Config files.{kind} must be a non-empty path array")
        resolved_entries = []
        for entry in entries:
            if not isinstance(entry, str) or not entry:
                raise CheckFailure(f"Config files.{kind} contains an invalid path")
            relative_path = Path(entry)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise CheckFailure(f"Config files.{kind} escapes the exercise: {entry!r}")
            target = (exercise_root / relative_path).resolve()
            try:
                target.relative_to(exercise_root)
            except ValueError as error:
                raise CheckFailure(
                    f"Config files.{kind} resolves outside the exercise: {entry!r}"
                ) from error
            if not target.is_file():
                raise CheckFailure(f"Config files.{kind} file does not exist: {entry!r}")
            resolved_entries.append(target)
        resolved[kind] = resolved_entries

    for kind in ("solution", "test", "example"):
        if kind not in resolved:
            raise CheckFailure(f"Config files is missing required {kind!r}")
        if len(resolved[kind]) != 1:
            raise CheckFailure(
                f"Expected exactly one configured {kind} file; got {len(resolved[kind])}"
            )
    return config, resolved


def load_enabled_cases() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    try:
        metadata = tomllib.loads(TESTS_TOML_PATH.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise CheckFailure(f"Could not parse {TESTS_TOML_PATH}: {error}") from error

    if set(metadata) != set(EXPECTED_DESCRIPTIONS):
        raise CheckFailure(
            "tests.toml UUID mismatch: "
            f"missing={sorted(set(EXPECTED_DESCRIPTIONS) - set(metadata))}, "
            f"extra={sorted(set(metadata) - set(EXPECTED_DESCRIPTIONS))}"
        )
    for uuid, description in EXPECTED_DESCRIPTIONS.items():
        entry = metadata[uuid]
        if not isinstance(entry, dict) or entry.get("description") != description:
            raise CheckFailure(f"tests.toml description mismatch for UUID {uuid}")

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
    return metadata, enabled


def single_path(files: dict[str, list[Path]], kind: str) -> Path:
    return files[kind][0]


def file_hashes(paths: list[Path]) -> dict[str, str]:
    hashes = {}
    for path in paths:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        hashes[str(path.relative_to(ROOT))] = digest.hexdigest()
    return hashes


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
        raise CheckFailure(f"Could not query SQLite CLI version: {error}") from error
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
        raise CheckFailure("Actual-results query did not produce a JSON array")
    return rows


def run_sqlite(
    copied_exercise: Path,
    test_sql: str,
    *,
    interrupt: bool = False,
) -> dict[str, Any]:
    script = f"{test_sql.rstrip()}\n\n{CASE_RESULTS_SQL}"
    if interrupt:
        script += f"\n{INTERRUPT_SQL}\n"
    record: dict[str, Any] = {
        "command": ["sqlite3", "-bail"],
        "cwd": str(copied_exercise),
        "interruption_signal_sent": False,
        "forced_kill": False,
        "return_code": None,
        "stdout": "",
        "stderr": "",
    }

    if not interrupt:
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
            record.update(
                {
                    "timed_out": True,
                    "stdout": error.stdout or "",
                    "stderr": error.stderr or "",
                    "return_code": None,
                }
            )
            return record
        record.update(
            {
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        return record

    try:
        process = subprocess.Popen(
            ["sqlite3", "-bail"],
            cwd=copied_exercise,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as error:
        raise CheckFailure("SQLite CLI 'sqlite3' was not found on PATH") from error
    assert process.stdin is not None
    process.stdin.write(script)
    process.stdin.close()
    try:
        process.wait(timeout=0.2)
    except subprocess.TimeoutExpired:
        process.send_signal(signal.SIGINT)
        record["interruption_signal_sent"] = True
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
            record["forced_kill"] = True
    record["return_code"] = process.returncode
    assert process.stdout is not None
    assert process.stderr is not None
    record["stdout"] = process.stdout.read()
    record["stderr"] = process.stderr.read()
    return record


def read_output_json(copied_exercise: Path) -> tuple[Any, str | None]:
    output_path = copied_exercise / "output.json"
    if not output_path.is_file():
        return None, "output.json was not created"
    try:
        contents = output_path.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as error:
        return None, str(error)
    if not contents.strip():
        return [], None
    try:
        return json.loads(contents), None
    except json.JSONDecodeError as error:
        return None, str(error)


def validate_run(
    record: dict[str, Any],
    output: Any,
    output_error: str | None,
    actual_rows: list[dict[str, Any]] | None,
    actual_rows_error: str | None,
    enabled: dict[str, dict[str, Any]],
) -> None:
    if record["return_code"] != 0:
        raise CheckFailure(
            f"SQLite child exited {record['return_code']}; stderr={record['stderr']!r}"
        )
    if not isinstance(output, list):
        raise CheckFailure(f"Invalid output.json: {output_error}")
    if not output:
        raise CheckFailure("Test run executed zero tests")

    expected_count = len(enabled)
    if len(output) != expected_count:
        raise CheckFailure(
            f"output.json contains {len(output)} tests; expected {expected_count}"
        )
    expected_descriptions = [entry["description"] for entry in enabled.values()]
    if not all(isinstance(item, dict) for item in output):
        raise CheckFailure("output.json contains a non-object test entry")
    actual_descriptions = [
        item.get("description") for item in output
    ]
    if Counter(actual_descriptions) != Counter(expected_descriptions):
        raise CheckFailure(
            "output.json descriptions mismatch: "
            f"expected={expected_descriptions}, actual={actual_descriptions}"
        )
    failed = [
        (item.get("description"), item.get("status"))
        for item in output
        if item.get("status") != "pass"
    ]
    if failed:
        raise CheckFailure(f"Non-pass output.json entries: {failed}")
    if not isinstance(actual_rows, list):
        raise CheckFailure(f"Could not read actual results: {actual_rows_error}")
    if len(actual_rows) != expected_count:
        raise CheckFailure(
            f"Actual-results query returned {len(actual_rows)} cases; "
            f"expected {expected_count}"
        )

    by_uuid: dict[str, dict[str, Any]] = {}
    for row in actual_rows:
        if not isinstance(row, dict):
            raise CheckFailure(f"Invalid actual-results row: {row!r}")
        uuid = row.get("uuid")
        if uuid in by_uuid:
            raise CheckFailure(f"Duplicate SQL test UUID: {uuid}")
        by_uuid[uuid] = row
    if set(by_uuid) != set(enabled):
        raise CheckFailure(
            "SQL result UUID mismatch: "
            f"missing={sorted(set(enabled) - set(by_uuid))}, "
            f"extra={sorted(set(by_uuid) - set(enabled))}"
        )

    for uuid, metadata_entry in enabled.items():
        row = by_uuid[uuid]
        expected_description = metadata_entry["description"]
        if row.get("description") != expected_description:
            raise CheckFailure(f"Generated description mismatch for UUID {uuid}")
        if row.get("expected") != row.get("actual_result"):
            raise CheckFailure(
                f"Wrong result for {expected_description}: "
                f"expected={row.get('expected')!r}, "
                f"actual={row.get('actual_result')!r}"
            )

    record["executed_test_count"] = len(output)
    record["passed_test_count"] = len(output)
    record["failed_test_count"] = 0
    record["expected_vs_actual"] = [
        {
            "uuid": row["uuid"],
            "description": row["description"],
            "input": row["input"],
            "expected": row["expected"],
            "actual": row["actual_result"],
        }
        for row in actual_rows
    ]


def run_probe(
    *,
    name: str,
    temporary_root: Path,
    configured_files: dict[str, list[Path]],
    learner_files: list[Path],
    enabled: dict[str, dict[str, Any]],
    expected_checker_exit: int,
    expected_failure_text: str | None = None,
    failing_reference: bool = False,
    empty_selection: bool = False,
    child_error: bool = False,
    interrupt: bool = False,
) -> dict[str, Any]:
    before_hashes = file_hashes(learner_files)
    temporary_path: Path | None = None
    record: dict[str, Any] = {
        "name": name,
        "expected_checker_exit_status": expected_checker_exit,
        "checker_exit_status": None,
        "checker_failure": None,
        "sqlite": None,
        "output_json": None,
        "output_json_error": None,
        "actual_results": None,
        "actual_results_error": None,
        "learner_hashes_before": before_hashes,
        "learner_hashes_after": None,
        "learner_hashes_unchanged": False,
        "temporary_directory": None,
        "temporary_directory_removed": False,
        "passed": False,
    }
    temporary_path = temporary_root / f"{name}-exercise-copy"

    try:
        temporary_path.mkdir()
        record["temporary_directory"] = str(temporary_path)
        copied_exercise = temporary_path / "tournament"
        shutil.copytree(EXERCISE, copied_exercise)
        _, copied_files = resolve_configured_files(copied_exercise / ".meta/config.json")

        copied_solution = single_path(copied_files, "solution")
        copied_example = single_path(copied_files, "example")
        copied_test = single_path(copied_files, "test")
        if failing_reference:
            copied_solution.write_text(FAILING_REFERENCE_SQL, encoding="utf-8")
        else:
            shutil.copyfile(copied_example, copied_solution)

        if empty_selection:
            generated_tests = copied_exercise / "create_test_table.sql"
            with generated_tests.open("a", encoding="utf-8") as destination:
                destination.write("\nDELETE FROM tests;\n")

        test_sql = copied_test.read_text(encoding="utf-8")
        if child_error:
            test_sql += "\nSELECT * FROM r08_t029_missing_table;\n"
        sqlite_record = run_sqlite(
            copied_exercise,
            test_sql,
            interrupt=interrupt,
        )
        output, output_error = read_output_json(copied_exercise)
        actual_rows = None
        actual_rows_error = None
        if "stdout" in sqlite_record:
            try:
                actual_rows = parse_marked_results(sqlite_record["stdout"])
            except CheckFailure as error:
                actual_rows_error = str(error)

        record["sqlite"] = sqlite_record
        record["output_json"] = output
        record["output_json_error"] = output_error
        record["executed_test_count"] = (
            len(output) if isinstance(output, list) else 0
        )
        record["output_statuses"] = [
            {
                "description": item.get("description"),
                "status": item.get("status"),
            }
            for item in output
            if isinstance(item, dict)
        ] if isinstance(output, list) else []
        record["actual_results"] = actual_rows
        record["actual_results_error"] = actual_rows_error

        validation_error = None
        try:
            validate_run(
                sqlite_record,
                output,
                output_error,
                actual_rows,
                actual_rows_error,
                enabled,
            )
        except CheckFailure as error:
            validation_error = str(error)
        observed_checker_exit = 1 if validation_error else 0
        record["checker_exit_status"] = observed_checker_exit
        record["checker_failure"] = validation_error

        expected_failure_matches = (
            expected_failure_text is None
            and validation_error is None
            or expected_failure_text is not None
            and validation_error is not None
            and expected_failure_text in validation_error
        )
        interruption_matches = not interrupt or (
            sqlite_record["interruption_signal_sent"]
            and sqlite_record["return_code"] != 0
        )
        record["passed"] = (
            observed_checker_exit == expected_checker_exit
            and expected_failure_matches
            and interruption_matches
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
            if temporary_path.exists():
                shutil.rmtree(temporary_path)
        except OSError as error:
            record["cleanup_error"] = str(error)
        record["learner_hashes_after"] = file_hashes(learner_files)
        record["learner_hashes_unchanged"] = (
            record["learner_hashes_before"] == record["learner_hashes_after"]
        )
        record["temporary_directory_removed"] = not temporary_path.exists()
        if not record["learner_hashes_unchanged"]:
            record["passed"] = False
            record["failure"] = "Learner file hashes changed during probe"
        if not record["temporary_directory_removed"]:
            record["passed"] = False
            record["failure"] = "Temporary exercise directory was not removed"
    return record


def write_evidence(evidence: dict[str, Any]) -> None:
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def terminate_process_tree(process: subprocess.Popen[str]) -> tuple[str, str, str, bool]:
    if process.poll() is not None:
        stdout, stderr = process.communicate()
        return stdout, stderr, "already-exited", False

    if os.name == "posix":
        os.killpg(process.pid, signal.SIGTERM)
        termination_signal = "SIGTERM"
    else:
        process.terminate()
        termination_signal = "terminate"

    try:
        stdout, stderr = process.communicate(timeout=3)
        return stdout, stderr, termination_signal, False
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
            termination_signal = "SIGKILL"
        else:
            process.kill()
            termination_signal = "kill"
        stdout, stderr = process.communicate(timeout=10)
        return stdout, stderr, termination_signal, True


def timeout_probe_main(temporary_root: Path) -> int:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    probe_copy = temporary_root / "timeout-exercise-copy"
    probe_copy.mkdir(parents=True)
    (probe_copy / TIMEOUT_READY_FILE).write_text(
        "parent owns and will remove this directory\n",
        encoding="utf-8",
    )
    print("R08-T029 timeout probe ready", flush=True)
    time.sleep(3600)
    return 0


def run_probe_subprocess(
    name: str,
    learner_files: list[Path],
    *,
    timeout_seconds: float = 120,
) -> dict[str, Any]:
    timeout_probe = name == "timeout-cleanup"
    specification = PROBE_SPECS.get(name)
    hashes_before = file_hashes(learner_files)
    record: dict[str, Any] = {
        "name": name,
        "command": [],
        "expected_process_exit_status": (
            "terminated-after-timeout"
            if timeout_probe
            else specification["expected_checker_exit"]
        ),
        "process_exit_status": None,
        "stdout": "",
        "stderr": "",
        "learner_hashes_before": hashes_before,
        "learner_hashes_after": None,
        "learner_hashes_unchanged": False,
        "parent_owned_temp_root": None,
        "parent_owned_temp_root_removed": False,
        "passed": False,
    }
    temp_root: Path | None = None
    process: subprocess.Popen[str] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix=f"r08-t029-parent-{name}-") as directory:
            temp_root = Path(directory)
            record["parent_owned_temp_root"] = str(temp_root)
            if timeout_probe:
                command = [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--timeout-probe",
                    str(temp_root),
                ]
            else:
                command = [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--scenario",
                    name,
                    "--temp-root",
                    str(temp_root),
                ]
            record["command"] = command
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=os.name == "posix",
            )
            try:
                if timeout_probe:
                    ready_file = temp_root / "timeout-exercise-copy" / TIMEOUT_READY_FILE
                    ready_deadline = time.monotonic() + 10
                    while (
                        not ready_file.is_file()
                        and process.poll() is None
                        and time.monotonic() < ready_deadline
                    ):
                        time.sleep(0.01)
                    record["child_temp_directory_created"] = ready_file.is_file()
                    if not record["child_temp_directory_created"]:
                        record["failure"] = "Timeout probe child did not create its temp directory"
                        stdout, stderr, termination, forced_kill = terminate_process_tree(process)
                        record["termination_signal"] = termination
                        record["forced_kill"] = forced_kill
                    else:
                        try:
                            stdout, stderr = process.communicate(timeout=timeout_seconds)
                            record["timeout_triggered"] = False
                        except subprocess.TimeoutExpired:
                            record["timeout_triggered"] = True
                            stdout, stderr, termination, forced_kill = terminate_process_tree(process)
                            record["termination_signal"] = termination
                            record["forced_kill"] = forced_kill
                else:
                    try:
                        stdout, stderr = process.communicate(timeout=timeout_seconds)
                        record["timeout_triggered"] = False
                    except subprocess.TimeoutExpired:
                        record["timeout_triggered"] = True
                        record["failure"] = "Checker scenario process timed out"
                        stdout, stderr, termination, forced_kill = terminate_process_tree(process)
                        record["termination_signal"] = termination
                        record["forced_kill"] = forced_kill

                record["process_exit_status"] = process.returncode
                record["stdout"] = stdout
                record["stderr"] = stderr
                if timeout_probe:
                    record["passed"] = bool(
                        record.get("child_temp_directory_created")
                        and record.get("timeout_triggered")
                        and record["process_exit_status"] != 0
                        and record.get("termination_signal") in ("SIGTERM", "SIGKILL", "terminate", "kill")
                    )
                    if not record["passed"] and "failure" not in record:
                        record["failure"] = "Timeout/termination behavior did not match expectations"
                elif not record.get("timeout_triggered"):
                    marker_line = next(
                        (
                            line[len(PROBE_JSON_MARKER) :]
                            for line in stdout.splitlines()
                            if line.startswith(PROBE_JSON_MARKER)
                        ),
                        None,
                    )
                    if marker_line is None:
                        record["failure"] = "Scenario process did not emit probe evidence"
                    else:
                        try:
                            probe = json.loads(marker_line)
                        except json.JSONDecodeError as error:
                            record["failure"] = (
                                f"Could not parse scenario probe evidence: {error}"
                            )
                        else:
                            record["probe"] = probe
                            status_matches = (
                                process.returncode
                                == specification["expected_checker_exit"]
                            )
                            hashes_match = (
                                probe.get("learner_hashes_unchanged")
                                and probe.get("learner_hashes_before")
                                == probe.get("learner_hashes_after")
                            )
                            record["passed"] = bool(
                                status_matches
                                and probe.get("passed")
                                and probe.get("checker_exit_status")
                                == process.returncode
                                and hashes_match
                                and probe.get("temporary_directory_removed")
                            )
                            if not status_matches:
                                record["failure"] = (
                                    f"Scenario process exited {process.returncode}; "
                                    f"expected {specification['expected_checker_exit']}"
                                )
                            elif not probe.get("passed"):
                                record["failure"] = probe.get("failure") or probe.get(
                                    "checker_failure", "Scenario assertions failed"
                                )
            finally:
                if process.poll() is None:
                    stdout, stderr, termination, forced_kill = terminate_process_tree(process)
                    record["stdout"] = stdout
                    record["stderr"] = stderr
                    record["termination_signal"] = termination
                    record["forced_kill"] = forced_kill
        record["parent_owned_temp_root_removed"] = (
            temp_root is not None and not temp_root.exists()
        )
        if not record["parent_owned_temp_root_removed"]:
            record["passed"] = False
            record["failure"] = "Parent-owned temporary root was not removed"
        if timeout_probe:
            ready_file = (
                temp_root / "timeout-exercise-copy" / TIMEOUT_READY_FILE
                if temp_root is not None
                else None
            )
            record["child_temp_directory_removed"] = (
                ready_file is not None and not ready_file.exists()
            )
            record["passed"] = bool(
                record["passed"] and record["child_temp_directory_removed"]
            )
        elif record.get("probe"):
            record["probe"]["parent_owned_temp_root_removed"] = (
                record["parent_owned_temp_root_removed"]
            )
    except Exception as error:
        record["failure"] = f"Unexpected {type(error).__name__}: {error}"
        record["unexpected_exception"] = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
        if process is not None and process.poll() is None:
            stdout, stderr, termination, forced_kill = terminate_process_tree(process)
            record["stdout"] = stdout
            record["stderr"] = stderr
            record["termination_signal"] = termination
            record["forced_kill"] = forced_kill

    record["learner_hashes_after"] = file_hashes(learner_files)
    record["learner_hashes_unchanged"] = (
        record["learner_hashes_before"] == record["learner_hashes_after"]
    )
    if not record["learner_hashes_unchanged"]:
        record["passed"] = False
        record["failure"] = "Learner file hashes changed during checker process"
    return record


def scenario_main(name: str, temporary_root: Path) -> int:
    if name not in PROBE_SPECS:
        print(f"Unknown scenario: {name}", file=sys.stderr)
        return 2
    if not temporary_root.is_dir():
        print(f"Parent-owned temporary root is missing: {temporary_root}", file=sys.stderr)
        return 2
    try:
        _, configured_files = resolve_configured_files(CONFIG_PATH)
        _, enabled = load_enabled_cases()
        probe = run_probe(
            name=name,
            temporary_root=temporary_root,
            configured_files=configured_files,
            learner_files=configured_files["solution"],
            enabled=enabled,
            **PROBE_SPECS[name],
        )
    except Exception as error:
        probe = {
            "name": name,
            "passed": False,
            "checker_exit_status": 1,
            "failure": f"Unexpected {type(error).__name__}: {error}",
            "unexpected_exception": {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            },
        }
    print(PROBE_JSON_MARKER + json.dumps(probe, ensure_ascii=False))
    if probe.get("passed"):
        return probe["checker_exit_status"]
    return 1


def main() -> int:
    evidence: dict[str, Any] = {
        "task": "R08-T029",
        "issue": "S-AI-Projects/sqlite#32",
        "status": "running",
        "checker_command": ["python3", "work/R08-T029/check.py"],
        "config_path": str(CONFIG_PATH.relative_to(ROOT)),
        "tool_versions": {
            "python": sys.version,
            "sqlite_cli": None,
        },
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "resolved_paths": None,
        "expected_enabled_test_count": len(EXPECTED_DESCRIPTIONS),
        "learner_hashes_before_all_probes": None,
        "learner_hashes_after_all_probes": None,
        "all_learner_hashes_unchanged": False,
        "probes": [],
        "failures": [],
    }

    try:
        _, configured_files = resolve_configured_files(CONFIG_PATH)
        _, enabled = load_enabled_cases()
        learner_files = configured_files["solution"]
        evidence["resolved_paths"] = {
            kind: [str(path.relative_to(EXERCISE)) for path in paths]
            for kind, paths in configured_files.items()
        }
        evidence["expected_enabled_test_count"] = len(enabled)
        evidence["tool_versions"]["sqlite_cli"] = sqlite_version()
        initial_hashes = file_hashes(learner_files)
        evidence["learner_hashes_before_all_probes"] = initial_hashes

        for name in PROBE_SPECS:
            probe = run_probe_subprocess(name, learner_files)
            evidence["probes"].append(probe)
            if not probe["passed"]:
                evidence["failures"].append(
                    f"{probe['name']}: {probe.get('failure') or 'scenario probe failed'}"
                )
        timeout_probe = run_probe_subprocess(
            "timeout-cleanup",
            learner_files,
            timeout_seconds=0.1,
        )
        evidence["probes"].append(timeout_probe)
        if not timeout_probe["passed"]:
            evidence["failures"].append(
                f"{timeout_probe['name']}: "
                f"{timeout_probe.get('failure') or 'timeout cleanup probe failed'}"
            )

        final_hashes = file_hashes(learner_files)
        evidence["learner_hashes_after_all_probes"] = final_hashes
        evidence["all_learner_hashes_unchanged"] = initial_hashes == final_hashes
        if not evidence["all_learner_hashes_unchanged"]:
            evidence["failures"].append("Learner solution hashes changed across probes")
        if any(
            not (
                probe.get("parent_owned_temp_root_removed")
                and (
                    probe.get("child_temp_directory_removed", True)
                    if probe["name"] == "timeout-cleanup"
                    else probe.get("probe", {}).get("temporary_directory_removed", False)
                )
            )
            for probe in evidence["probes"]
        ):
            evidence["failures"].append("At least one temporary exercise copy remains")
        evidence["status"] = "passed" if not evidence["failures"] else "failed"
    except CheckFailure as error:
        evidence["status"] = "failed"
        evidence["failures"].append(str(error))
        evidence["failure_traceback"] = traceback.format_exc()
    except Exception as error:
        evidence["status"] = "failed"
        evidence["failures"].append(f"Unexpected {type(error).__name__}: {error}")
        evidence["unexpected_exception"] = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }

    write_evidence(evidence)
    if evidence["status"] != "passed":
        print("FAIL: " + "; ".join(evidence["failures"]), file=sys.stderr)
        for probe in evidence["probes"]:
            if probe.get("passed"):
                continue
            sqlite_record = probe.get("probe", {}).get("sqlite")
            if isinstance(sqlite_record, dict):
                for stream in ("stdout", "stderr"):
                    if sqlite_record.get(stream):
                        print(
                            f"--- {probe['name']} SQLite {stream} ---",
                            file=sys.stderr,
                        )
                        print(sqlite_record[stream], file=sys.stderr)
            for stream in ("stdout", "stderr"):
                if probe.get(stream):
                    print(f"--- {probe['name']} checker {stream} ---", file=sys.stderr)
                    print(probe[stream], file=sys.stderr)
        print(f"Evidence written to {EVIDENCE_PATH.relative_to(ROOT)}", file=sys.stderr)
        return 1

    for probe in evidence["probes"]:
        if probe["name"] == "timeout-cleanup":
            print(
                f"{probe['name']}: timed out={probe.get('timeout_triggered')}, "
                f"termination={probe.get('termination_signal')}, "
                f"child temp created={probe.get('child_temp_directory_created')}, "
                f"parent temp cleaned={probe.get('parent_owned_temp_root_removed')}"
            )
            continue
        sqlite_record = probe["probe"]["sqlite"]
        print(
            f"{probe['name']}: checker process exit {probe['process_exit_status']} "
            f"(expected {probe['expected_process_exit_status']}), "
            f"SQLite exit {sqlite_record['return_code']}, "
            f"{probe['probe'].get('executed_test_count', 0)} cases, "
            f"hashes unchanged={probe['learner_hashes_unchanged']}, "
            f"temp cleaned={probe['probe'].get('temporary_directory_removed')}"
        )
    real_probe = evidence["probes"][0]
    print(
        f"Passed {real_probe['probe']['sqlite']['executed_test_count']} reference tests; "
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
    if len(sys.argv) == 3 and sys.argv[1] == "--timeout-probe":
        raise SystemExit(timeout_probe_main(Path(sys.argv[2])))
    if len(sys.argv) != 1:
        print("Usage: check.py [--scenario NAME]", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main())
