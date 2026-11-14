#!/usr/bin/env python3
"""Verify the Hamming example against its configured tests in a temporary copy."""

import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections import Counter
from pathlib import Path


EXPECTED_DESCRIPTIONS = (
    "empty strands",
    "single letter identical strands",
    "single letter different strands",
    "long identical strands",
    "long different strands",
    "disallow first strand longer",
    "disallow second strand longer",
    "disallow empty first strand",
    "disallow empty second strand",
)


class CheckError(Exception):
    """A validation failure suitable for reporting on the command line."""


def configured_file(config: dict, key: str) -> str:
    paths = config.get("files", {}).get(key)
    if not isinstance(paths, list) or not paths or not isinstance(paths[0], str):
        raise CheckError(f".meta/config.json has no configured {key} path")
    return paths[0]


def validate_metadata(exercise: Path) -> None:
    try:
        with (exercise / ".meta" / "tests.toml").open("rb") as file:
            metadata = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise CheckError(f"Could not read .meta/tests.toml: {error}") from error

    enabled = [
        case["description"]
        for case in metadata.values()
        if case.get("include", True)
    ]
    if Counter(enabled) != Counter(EXPECTED_DESCRIPTIONS):
        raise CheckError(
            "Enabled test descriptions in .meta/tests.toml do not match the "
            f"expected nine cases: {enabled!r}"
        )


def validate_results(output_path: Path) -> None:
    if not output_path.is_file():
        raise CheckError("SQLite did not create output.json")
    try:
        results = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CheckError(f"Could not parse output.json: {error}") from error
    if not isinstance(results, list):
        raise CheckError("output.json must contain a JSON array")
    if not results:
        raise CheckError("Zero Hamming tests executed")

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

    missing = sorted(set(EXPECTED_DESCRIPTIONS) - set(counts))
    duplicate = sorted(description for description, count in counts.items() if count > 1)
    unexpected = sorted(set(counts) - set(EXPECTED_DESCRIPTIONS))
    if missing:
        failures.append(f"Missing test results: {', '.join(missing)}")
    if duplicate:
        failures.append(f"Duplicate test results: {', '.join(duplicate)}")
    if unexpected:
        failures.append(f"Unexpected test results: {', '.join(unexpected)}")
    if len(results) != len(EXPECTED_DESCRIPTIONS):
        failures.append(
            f"Expected {len(EXPECTED_DESCRIPTIONS)} results, got {len(results)}"
        )
    if failures:
        raise CheckError("Hamming result validation failed:\n  - " + "\n  - ".join(failures))


def run_check() -> None:
    repository = Path(__file__).resolve().parents[2]
    exercise = repository / "exercises" / "practice" / "hamming"
    config_path = exercise / ".meta" / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CheckError(f"Could not read .meta/config.json: {error}") from error

    solution_rel = configured_file(config, "solution")
    test_rel = configured_file(config, "test")
    example_rel = configured_file(config, "example")
    validate_metadata(exercise)

    with tempfile.TemporaryDirectory(prefix="hamming-r08-t024-") as temporary:
        copied_exercise = Path(temporary) / "hamming"
        shutil.copytree(exercise, copied_exercise)
        shutil.copyfile(
            exercise / example_rel,
            copied_exercise / solution_rel,
        )

        command = ["sqlite3", "", "--init", test_rel, "-bail", ".exit"]
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

        if process.stdout:
            print(process.stdout, end="")
        if process.stderr:
            print(process.stderr, end="", file=sys.stderr)
        if process.returncode != 0:
            raise CheckError(
                f"SQLite test process exited with status {process.returncode}"
            )

        validate_results(copied_exercise / "output.json")
        print(
            f"Hamming checks passed: {len(EXPECTED_DESCRIPTIONS)} tests executed, "
            f"{len(EXPECTED_DESCRIPTIONS)} passed, 0 failed."
        )


def main() -> int:
    try:
        run_check()
    except (CheckError, OSError) as error:
        print(f"Hamming check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
