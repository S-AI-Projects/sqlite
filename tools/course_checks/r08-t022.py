#!/usr/bin/env python3

"""Check two-fer canonical data, generated fixture data, and SQL tests."""

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EXERCISE = ROOT / "exercises/practice/two-fer"
TEST_MARKER = "__R08_T022_CASE_ROWS__"


class CheckFailure(Exception):
    """A validation failed and should be reported by the check entry point."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailure(message)


def load_cases(canonical_path: Path) -> list[dict[str, Any]]:
    try:
        canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
        with (EXERCISE / ".meta/tests.toml").open("rb") as tests_file:
            metadata = tomllib.load(tests_file)
    except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        raise CheckFailure(f"Unable to read canonical or metadata input: {error}") from error

    require(canonical.get("exercise") == "two-fer", "Canonical data is not for two-fer")
    cases = canonical.get("cases")
    require(isinstance(cases, list), "Canonical data must contain a cases array")
    selected = [
        case
        for case in cases
        if case.get("uuid") in metadata
        and metadata[case["uuid"]].get("include", True)
    ]
    require(len(selected) == 3, f"Expected three included canonical cases, found {len(selected)}")
    require(
        {case["uuid"] for case in selected} == set(metadata),
        "Included tests.toml UUIDs do not match selected canonical case UUIDs",
    )

    for case in selected:
        test = metadata[case["uuid"]]
        require(
            case.get("description") == test.get("description"),
            f"Description mismatch for {case['uuid']}: canonical={case.get('description')!r}, "
            f"tests.toml={test.get('description')!r}",
        )
        require(
            isinstance(case.get("input"), dict) and "name" in case["input"],
            f"Canonical input.name is missing for {case['uuid']}",
        )
        require(isinstance(case.get("expected"), str), f"Canonical expected output is invalid for {case['uuid']}")
    return selected


def expected_test_rows(cases: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "uuid": case["uuid"],
            "name": case["description"],
            "input": case["input"]["name"] or "",
            "expected": case["expected"],
        }
        for case in cases
    ]


def run_generator(canonical_path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="r08-t022-generate-") as directory:
        temporary_root = Path(directory) / "repo"
        copied_exercise = temporary_root / "exercises/practice/two-fer"
        copied_exercise.parent.mkdir(parents=True)
        shutil.copytree(EXERCISE, copied_exercise)
        (temporary_root / "bin").mkdir()
        shutil.copy2(ROOT / "bin/generate_tests", temporary_root / "bin/generate_tests")

        xdg_cache = Path(directory) / "xdg-cache"
        canonical_destination = (
            xdg_cache
            / "exercism/configlet/problem-specifications/exercises/two-fer/canonical-data.json"
        )
        canonical_destination.parent.mkdir(parents=True)
        shutil.copy2(canonical_path, canonical_destination)

        environment = os.environ.copy()
        environment["XDG_CACHE_HOME"] = str(xdg_cache)
        process = subprocess.run(
            [sys.executable, "bin/generate_tests", "--no-pull", "two-fer"],
            cwd=temporary_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        result: dict[str, Any] = {
            "command": [sys.executable, "bin/generate_tests", "--no-pull", "two-fer"],
            "returncode": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
            "canonical_input_sha256": sha256(canonical_destination),
        }
        require(
            process.returncode == 0,
            f"bin/generate_tests failed with status {process.returncode}: "
            f"{process.stderr.strip() or process.stdout.strip()}",
        )

        generated_data = copied_exercise / "data.csv"
        original_data = EXERCISE / "data.csv"
        require(generated_data.is_file(), "Generator did not create data.csv in the temporary copy")
        generated_text = generated_data.read_text(encoding="utf-8")
        original_text = original_data.read_text(encoding="utf-8")
        require(generated_text == original_text, "Regenerated data.csv differs from the working exercise")
        generated_rows = list(csv.reader(generated_text.splitlines()))
        expected_csv_rows = [[row["input"], ""] for row in expected_test_rows(load_cases(canonical_path))]
        require(
            generated_rows == expected_csv_rows,
            f"Generated data.csv rows do not match canonical input names: {generated_rows!r}",
        )

        untouched_files = [
            "two-fer.sql",
            "two-fer_test.sql",
            "test_reporter.sql",
        ]
        unchanged = {
            name: sha256(copied_exercise / name) == sha256(EXERCISE / name)
            for name in untouched_files
        }
        require(all(unchanged.values()), "Generator modified a file outside its data.csv output")
        result["outputs"] = {
            "data.csv": {
                "template": ".meta/template.data.j2",
                "matches_working_copy": True,
                "rows": generated_rows,
            },
            "create_test_table.sql": {
                "template_present": (copied_exercise / ".meta/template.create_test_table.j2").is_file(),
                "generated": (copied_exercise / "create_test_table.sql").is_file(),
            },
            "test_reporter.sql": {
                "template_present": (copied_exercise / ".meta/template.test_reporter.sql.j2").is_file(),
                "modified": not unchanged["test_reporter.sql"],
            },
        }
        result["protected_files_unchanged_in_copy"] = unchanged
        return result


def run_sql_tests(cases: list[dict[str, Any]]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="r08-t022-tests-") as directory:
        copied_exercise = Path(directory) / "two-fer"
        shutil.copytree(EXERCISE, copied_exercise)
        shutil.copy2(
            copied_exercise / ".meta/example.sql",
            copied_exercise / "two-fer.sql",
        )

        test_script = (copied_exercise / "two-fer_test.sql").read_text(encoding="utf-8")
        query = (
            f"\n.print {TEST_MARKER}\n"
            ".mode json\n"
            "SELECT uuid, name, input, expected FROM tests ORDER BY rowid;\n"
        )
        process = subprocess.run(
            ["sqlite3", "-bail"],
            input=test_script + query,
            cwd=copied_exercise,
            capture_output=True,
            text=True,
            check=False,
        )
        result: dict[str, Any] = {
            "command": ["sqlite3", "-bail", "<", "two-fer_test.sql"],
            "returncode": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
        }
        require(
            process.returncode == 0,
            f"sqlite3 exited with status {process.returncode}: "
            f"{process.stderr.strip() or process.stdout.strip()}",
        )

        output_path = copied_exercise / "output.json"
        require(output_path.is_file(), "two-fer_test.sql did not create output.json")
        try:
            test_results = json.loads(output_path.read_text(encoding="utf-8"))
            case_rows_text = process.stdout.split(TEST_MARKER, 1)[1].strip()
            actual_rows = json.loads(case_rows_text)
        except (OSError, json.JSONDecodeError, IndexError) as error:
            raise CheckFailure(f"Unable to parse SQLite test results: {error}") from error

        require(isinstance(test_results, list), "output.json must contain a JSON array")
        executed = len(test_results)
        require(executed > 0, "Zero tests executed")
        expected_rows = expected_test_rows(cases)
        expected_names = [row["name"] for row in expected_rows]
        actual_names = [
            test.get("name")
            for test in test_results
            if isinstance(test, dict) and isinstance(test.get("name"), str)
        ]
        duplicates = sorted(
            name for name in set(actual_names) if actual_names.count(name) > 1
        )
        missing = sorted(set(expected_names) - set(actual_names))
        unexpected = sorted(set(actual_names) - set(expected_names))
        malformed = [
            index
            for index, test in enumerate(test_results)
            if not isinstance(test, dict) or not isinstance(test.get("name"), str)
        ]
        require(
            executed == len(expected_names)
            and not missing
            and not duplicates
            and not unexpected
            and not malformed,
            "output.json result mismatch: "
            f"expected_count={len(expected_names)}, actual_count={executed}, "
            f"missing={missing}, duplicated={duplicates}, unexpected={unexpected}, "
            f"malformed_indexes={malformed}",
        )
        statuses = {
            test["name"]: test.get("status")
            for test in test_results
        }
        failed_names = sorted(
            name for name in expected_names if statuses[name] != "pass"
        )
        require(
            not failed_names,
            f"output.json tests did not pass: {failed_names}",
        )
        require(
            actual_rows == expected_rows,
            f"SQL test case mapping differs from canonical cases: expected={expected_rows!r}, "
            f"actual={actual_rows!r}",
        )
        failed_results = [
            test for test in test_results
            if not isinstance(test, dict) or test.get("status") != "pass"
        ]
        result["test_count"] = executed
        result["passed"] = executed - len(failed_results)
        result["failed"] = len(failed_results)
        result["expected_rows"] = expected_rows
        result["actual_rows"] = actual_rows
        result["results"] = test_results
        require(not failed_results, f"SQL test assertions failed: {failed_results!r}")
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-data", type=Path, required=True)
    args = parser.parse_args()

    exercise_files = ["two-fer.sql", "two-fer_test.sql", "test_reporter.sql", "data.csv"]
    before = {name: sha256(EXERCISE / name) for name in exercise_files}
    try:
        cases = load_cases(args.canonical_data.resolve())
        report = {
            "success": True,
            "canonical_input": str(args.canonical_data.resolve()),
            "canonical_sha256": sha256(args.canonical_data.resolve()),
            "case_count": len(cases),
            "cases": expected_test_rows(cases),
            "generation": run_generator(args.canonical_data.resolve()),
            "sql_tests": run_sql_tests(cases),
        }
    except CheckFailure as error:
        report = {"success": False, "error": str(error)}
        print(json.dumps(report, indent=2))
        return 1

    after = {name: sha256(EXERCISE / name) for name in exercise_files}
    report["working_files_unchanged"] = before == after
    report["working_file_sha256"] = after
    if before != after:
        report["success"] = False
        report["error"] = "A working exercise file changed during the temporary-copy checks"
    print(json.dumps(report, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
