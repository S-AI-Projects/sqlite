#!/usr/bin/env python3
"""Verify line-up and measure SQLite VM steps for valid row-count workloads."""

import csv
import json
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import tomllib
from collections import Counter
from pathlib import Path


EXPECTED_TEST_COUNT = 25
BENCHMARK_SIZES = (1, 10, 25)
REPETITIONS = 15
RESULTS_BEGIN = "__BENCHMARK_RESULTS_BEGIN__"
RESULTS_END = "__BENCHMARK_RESULTS_END__"


class CheckFailure(Exception):
    """A validation failure suitable for reporting on the command line."""


def configured_file(config: dict, key: str) -> str:
    paths = config.get("files", {}).get(key)
    if not isinstance(paths, list) or not paths or not isinstance(paths[0], str):
        raise CheckFailure(f".meta/config.json has no configured {key} path")
    return paths[0]


def emit_process_output(process: subprocess.CompletedProcess[str]) -> None:
    if process.stdout:
        print(process.stdout, end="")
    if process.stderr:
        print(process.stderr, end="", file=sys.stderr)


def enabled_descriptions(exercise: Path) -> list[str]:
    try:
        with (exercise / ".meta" / "tests.toml").open("rb") as file:
            metadata = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise CheckFailure(f"Could not read .meta/tests.toml: {error}") from error

    descriptions = [
        case["description"]
        for case in metadata.values()
        if case.get("include", True)
    ]
    if (
        len(descriptions) != EXPECTED_TEST_COUNT
        or len(set(descriptions)) != EXPECTED_TEST_COUNT
    ):
        raise CheckFailure(
            f"Expected {EXPECTED_TEST_COUNT} unique enabled tests in tests.toml; "
            f"found {len(descriptions)}"
        )
    return descriptions


def check_test_results(output_path: Path, expected_descriptions: list[str]) -> list[dict]:
    if not output_path.is_file():
        raise CheckFailure("SQLite did not create output.json")
    try:
        results = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CheckFailure(f"Could not parse output.json: {error}") from error

    if not isinstance(results, list):
        raise CheckFailure("output.json must contain a JSON array")
    if not results:
        raise CheckFailure("Zero line-up tests executed")

    counts: Counter[str] = Counter()
    failures: list[str] = []
    for result in results:
        if not isinstance(result, dict) or not isinstance(result.get("description"), str):
            failures.append(f"Malformed test result: {result!r}")
            continue
        description = result["description"]
        counts[description] += 1
        if result.get("status") != "pass":
            failures.append(
                f"{description}: status={result.get('status')!r}; "
                f"message={result.get('message')!r}"
            )

    expected = set(expected_descriptions)
    missing = sorted(expected - set(counts))
    duplicate = sorted(description for description, count in counts.items() if count > 1)
    unexpected = sorted(set(counts) - expected)
    if missing:
        failures.append(f"Missing test results: {', '.join(missing)}")
    if duplicate:
        failures.append(f"Duplicate test results: {', '.join(duplicate)}")
    if unexpected:
        failures.append(f"Unexpected test results: {', '.join(unexpected)}")
    if len(results) != EXPECTED_TEST_COUNT:
        failures.append(
            f"Expected {EXPECTED_TEST_COUNT} results, got {len(results)}"
        )
    if failures:
        raise CheckFailure("Test result validation failed:\n  - " + "\n  - ".join(failures))
    return results


def read_fixture_rows(path: Path) -> list[dict]:
    rows = []
    try:
        with path.open(newline="", encoding="utf-8") as file:
            for index, row in enumerate(csv.reader(file), start=1):
                if not row:
                    continue
                if len(row) < 2:
                    raise CheckFailure(f"Malformed data.csv row {index}: {row!r}")
                name = row[0]
                try:
                    number = int(row[1])
                except ValueError as error:
                    raise CheckFailure(
                        f"Non-integer number in data.csv row {index}: {row[1]!r}"
                    ) from error
                if not 1 <= number <= 999:
                    raise CheckFailure(
                        f"Number outside the exercise domain in data.csv row {index}: {number}"
                    )
                rows.append({"name": name, "number": number})
    except OSError as error:
        raise CheckFailure(f"Could not read data.csv: {error}") from error

    if len(rows) != EXPECTED_TEST_COUNT:
        raise CheckFailure(
            f"Expected {EXPECTED_TEST_COUNT} fixture rows; found {len(rows)}"
        )
    return rows


def sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run_benchmark(
    exercise: Path,
    example_rel: str,
    fixture_rows: list[dict],
    row_count: int,
) -> dict:
    selected = fixture_rows[:row_count]
    values = ",\n".join(
        f"({sql_string(row['name'])}, {row['number']}, NULL)"
        for row in selected
    )
    script = [
        'CREATE TABLE "line-up" (name TEXT NOT NULL, number INTEGER NOT NULL, result TEXT);',
        'INSERT INTO "line-up" (name, number, result) VALUES',
        values + ";",
        ".read create_test_table.sql",
        f".read {example_rel}",
        ".mode json",
        f".print {RESULTS_BEGIN}",
        (
            'SELECT customers.name, customers.number, tests.expected, '
            'customers.result AS actual '
            'FROM "line-up" AS customers '
            'JOIN tests ON tests.name = customers.name '
            'AND tests.number = customers.number '
            'ORDER BY customers.rowid;'
        ),
        f".print {RESULTS_END}",
        # Setup, fixture inserts, one correctness execution, and its SELECT are
        # deliberately before stats are enabled.
        ".stats vmstep",
    ]
    script.extend([f".read {example_rel}"] * REPETITIONS)
    script.extend([".stats off", ".exit"])

    try:
        process = subprocess.run(
            ["sqlite3", "-bail"],
            cwd=exercise,
            input="\n".join(script) + "\n",
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise CheckFailure("SQLite CLI 'sqlite3' was not found on PATH") from error

    emit_process_output(process)
    if process.returncode != 0:
        raise CheckFailure(
            f"SQLite benchmark process exited with status {process.returncode}"
        )

    try:
        payload = process.stdout.split(RESULTS_BEGIN, 1)[1].split(RESULTS_END, 1)[0].strip()
        outputs = json.loads(payload)
    except (IndexError, json.JSONDecodeError) as error:
        raise CheckFailure("Could not parse benchmark correctness output") from error

    if not isinstance(outputs, list) or len(outputs) != row_count:
        actual_count = len(outputs) if isinstance(outputs, list) else "non-array"
        raise CheckFailure(
            f"Expected {row_count} benchmark output rows; got {actual_count}"
        )
    for output in outputs:
        if output.get("expected") != output.get("actual"):
            raise CheckFailure(
                f"Benchmark correctness failure for "
                f"{output.get('name')!r}, {output.get('number')!r}: "
                f"expected {output.get('expected')!r}, "
                f"got {output.get('actual')!r}"
            )

    step_text = process.stdout + "\n" + process.stderr
    vm_steps = [
        int(value)
        for value in re.findall(r"VM-steps:\s*(\d+)", step_text)
    ]
    if len(vm_steps) != REPETITIONS:
        raise CheckFailure(
            f"Expected {REPETITIONS} VM-step samples for {row_count} rows; "
            f"found {len(vm_steps)}"
        )

    return {
        "row_count": row_count,
        "return_code": process.returncode,
        "inputs": [
            {"name": row["name"], "number": row["number"]}
            for row in selected
        ],
        "expected_actual_outputs": outputs,
        "repetitions": REPETITIONS,
        "vm_step_samples": vm_steps,
        "median_vm_steps": statistics.median(vm_steps),
        "stdout": process.stdout,
        "stderr": process.stderr,
    }


def run_check() -> None:
    repository = Path(__file__).resolve().parents[2]
    exercise = repository / "exercises" / "practice" / "line-up"
    try:
        config = json.loads(
            (exercise / ".meta" / "config.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        raise CheckFailure(f"Could not read .meta/config.json: {error}") from error

    solution_rel = configured_file(config, "solution")
    test_rel = configured_file(config, "test")
    example_rel = configured_file(config, "example")
    expected_descriptions = enabled_descriptions(exercise)
    fixture_rows = read_fixture_rows(exercise / "data.csv")

    try:
        sqlite_version = subprocess.run(
            ["sqlite3", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise CheckFailure("SQLite CLI 'sqlite3' was not found on PATH") from error
    if sqlite_version.returncode != 0:
        raise CheckFailure("Could not obtain the SQLite CLI version")

    with tempfile.TemporaryDirectory(prefix="line-up-r08-t025-") as temporary:
        copied_exercise = Path(temporary) / "line-up"
        shutil.copytree(exercise, copied_exercise)
        shutil.copyfile(
            exercise / example_rel,
            copied_exercise / solution_rel,
        )

        test_path = copied_exercise / test_rel
        try:
            with test_path.open(encoding="utf-8") as test_input:
                test_process = subprocess.run(
                    ["sqlite3", "-bail"],
                    cwd=copied_exercise,
                    stdin=test_input,
                    capture_output=True,
                    text=True,
                    check=False,
                )
        except FileNotFoundError as error:
            raise CheckFailure("SQLite CLI 'sqlite3' was not found on PATH") from error

        emit_process_output(test_process)
        if test_process.returncode != 0:
            raise CheckFailure(
                f"SQLite test process exited with status {test_process.returncode}"
            )
        test_results = check_test_results(
            copied_exercise / "output.json",
            expected_descriptions,
        )

        benchmarks = [
            run_benchmark(copied_exercise, example_rel, fixture_rows, size)
            for size in BENCHMARK_SIZES
        ]
        evidence = {
            "task": "R08-T025",
            "status": "passed",
            "tool_versions": {
                "python": sys.version.splitlines()[0],
                "sqlite_cli": sqlite_version.stdout.strip(),
            },
            "environment": {
                "platform": platform.platform(),
                "machine": platform.machine(),
            },
            "correctness": {
                "command": "sqlite3 -bail < line-up_test.sql",
                "return_code": test_process.returncode,
                "expected_test_count": len(expected_descriptions),
                "executed_test_count": len(test_results),
                "results": [
                    {
                        "description": row["description"],
                        "expected_status": "pass",
                        "actual_status": row["status"],
                    }
                    for row in test_results
                ],
                "stdout": test_process.stdout,
                "stderr": test_process.stderr,
            },
            "benchmark": {
                "metric": "SQLite CLI .stats vmstep, per reference UPDATE",
                "measurement_unit": "SQLite virtual machine steps",
                "repetitions_per_size": REPETITIONS,
                "setup_and_fixture_creation_measured": False,
                "workloads": benchmarks,
                "limitation": (
                    "VM-step counts depend on the SQLite version/build and are "
                    "not hardware instruction counts or wall-clock timings."
                ),
            },
        }
        evidence_path = Path(__file__).with_name("verification.json")
        evidence_path.write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        print(
            f"Verified {len(test_results)} tests: "
            f"{len(test_results)} passed, 0 failed."
        )
        for result in benchmarks:
            print(
                f"{result['row_count']} rows: median "
                f"{result['median_vm_steps']} VM steps "
                f"from {REPETITIONS} repetitions."
            )


def main() -> int:
    try:
        run_check()
    except (CheckFailure, OSError, tomllib.TOMLDecodeError) as error:
        print(f"line-up check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
