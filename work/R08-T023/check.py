#!/usr/bin/env python3
"""Run ETL's checked-in tests against its maintained example in a temporary copy."""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


EXPECTED_CASES = {
    "78a7a9f9-4490-4a47-8ee9-5a38bb47d28f": "single letter",
    "60dbd000-451d-44c7-bdbb-97c73ac1f497": "single score with multiple letters",
    "f5c5de0c-301f-4fdd-a0e5-df97d4214f54": "multiple scores with multiple letters",
    "5db8ea89-ecb4-4dcd-902f-2b418cc87b9d": "multiple scores with differing numbers of letters",
}
class CheckError(Exception):
    """A validation failure with a message suitable for the command line."""


def configured_file(config: dict, key: str) -> str:
    files = config.get("files", {})
    paths = files.get(key)
    if not isinstance(paths, list) or not paths or not isinstance(paths[0], str):
        raise CheckError(f".meta/config.json has no configured {key} path")
    return paths[0]


def validate_case_sources(exercise: Path, test_path: Path) -> None:
    with (exercise / ".meta" / "tests.toml").open("rb") as file:
        metadata = tomllib.load(file)
    included = {
        uuid: case.get("description")
        for uuid, case in metadata.items()
        if case.get("include", True)
    }
    if included != EXPECTED_CASES:
        missing = sorted(set(EXPECTED_CASES.items()) - set(included.items()))
        extra = sorted(set(included.items()) - set(EXPECTED_CASES.items()))
        raise CheckError(
            f"Expected the four enabled ETL cases from tests.toml; "
            f"missing/mismatched={missing}, unexpected={extra}"
        )

    test_sql = test_path.read_text(encoding="utf-8")
    for uuid, name in EXPECTED_CASES.items():
        row = re.compile(
            rf"\(\s*'{re.escape(name)}'\s*,\s*'{re.escape(uuid)}'\s*,",
            re.DOTALL,
        )
        if not row.search(test_sql):
            raise CheckError(
                f"Configured test SQL does not associate {name!r} with UUID {uuid}"
            )

def validate_results(output_path: Path) -> tuple[int, int]:
    if not output_path.is_file():
        raise CheckError(f"SQLite did not create {output_path.name}")
    try:
        results = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CheckError(f"Could not parse {output_path.name}: {error}") from error
    if not isinstance(results, list):
        raise CheckError(f"{output_path.name} must contain a JSON array")
    if not results:
        raise CheckError("Zero ETL tests executed")

    counts: dict[str, int] = {}
    failures: list[str] = []
    for result in results:
        if not isinstance(result, dict) or not isinstance(result.get("name"), str):
            failures.append(f"Malformed result entry: {result!r}")
            continue
        name = result["name"]
        counts[name] = counts.get(name, 0) + 1
        if result.get("status") != "pass":
            failures.append(
                f"{name}: status={result.get('status')!r}; "
                f"message={result.get('message')!r}; output={result.get('output')!r}"
            )

    missing = sorted(set(EXPECTED_CASES.values()) - set(counts))
    duplicate = sorted(name for name, count in counts.items() if count > 1)
    unexpected = sorted(set(counts) - set(EXPECTED_CASES.values()))
    if missing:
        failures.append(f"Missing test results: {', '.join(missing)}")
    if duplicate:
        failures.append(f"Duplicate test results: {', '.join(duplicate)}")
    if unexpected:
        failures.append(f"Unexpected test results: {', '.join(unexpected)}")
    if len(results) != len(EXPECTED_CASES):
        failures.append(
            f"Expected {len(EXPECTED_CASES)} results, got {len(results)}"
        )
    if failures:
        raise CheckError("ETL test result validation failed:\n  - " + "\n  - ".join(failures))

    return len(results), sum(result["status"] == "pass" for result in results)


def run_check() -> None:
    repository = Path(__file__).resolve().parents[2]
    exercise = repository / "exercises" / "practice" / "etl"
    config_path = exercise / ".meta" / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CheckError(f"Could not read {config_path}: {error}") from error

    solution_rel = configured_file(config, "solution")
    test_rel = configured_file(config, "test")
    example_rel = configured_file(config, "example")
    original_test = exercise / test_rel
    original_example = exercise / example_rel
    validate_case_sources(exercise, original_test)

    with tempfile.TemporaryDirectory(prefix="etl-r08-t023-") as temporary:
        copied_exercise = Path(temporary) / "etl"
        shutil.copytree(exercise, copied_exercise, dirs_exist_ok=True)
        copied_solution = copied_exercise / solution_rel
        copied_solution.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original_example, copied_solution)

        command = [
            "sqlite3",
            "",
            "--init",
            test_rel,
            "-bail",
            ".exit",
        ]
        try:
            process = subprocess.run(
                command,
                cwd=copied_exercise,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as error:
            raise CheckError("SQLite CLI 'sqlite3' was not found on PATH") from error
        if process.returncode != 0:
            details = "\n".join(
                part for part in (process.stdout.strip(), process.stderr.strip()) if part
            )
            raise CheckError(
                f"SQLite test process exited with status {process.returncode}"
                + (f":\n{details}" if details else "")
            )

        executed, passed = validate_results(copied_exercise / "output.json")
        print(
            f"ETL checks passed: {executed} tests executed, "
            f"{passed} passed, {executed - passed} failed."
        )
        print("Confirmed required 'single letter' test is configured and passes.")


def main() -> int:
    try:
        run_check()
    except (CheckError, OSError, tomllib.TOMLDecodeError) as error:
        print(f"ETL check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
