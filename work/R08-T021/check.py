#!/usr/bin/env python3

"""Run nucleotide-count tests against the configured reference example."""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXERCISE_DIR = REPOSITORY_ROOT / "exercises/practice/nucleotide-count"
EXPECTED_TEST_NAMES = {
    "empty strand",
    "can count one nucleotide in single-character input",
    "strand with repeated nucleotide",
    "strand with multiple nucleotides",
    "strand with invalid nucleotides",
}


def configured_file(exercise_dir: Path, config: dict[str, Any], key: str) -> Path:
    """Resolve the first configured exercise file for a given purpose."""
    paths = config["files"][key]
    if not isinstance(paths, list) or not paths:
        raise ValueError(f"config.json must list a {key} file")

    exercise_root = exercise_dir.resolve()
    path = (exercise_root / paths[0]).resolve()
    if not path.is_relative_to(exercise_root):
        raise ValueError(f"configured {key} path escapes the exercise: {paths[0]}")
    if not path.is_file():
        raise FileNotFoundError(f"configured {key} file does not exist: {path}")
    return path


def run_check(exercise_dir: Path) -> int:
    """Run the configured test script in an isolated copy of the exercise."""
    config_path = exercise_dir / ".meta/config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        solution = configured_file(exercise_dir, config, "solution")
        test = configured_file(exercise_dir, config, "test")
        example = configured_file(exercise_dir, config, "example")
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        print(f"Unable to load exercise configuration: {error}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="nucleotide-count-") as temporary_dir:
        copied_exercise = Path(temporary_dir) / exercise_dir.name
        try:
            shutil.copytree(exercise_dir, copied_exercise)
            copied_solution = copied_exercise / solution.relative_to(exercise_dir.resolve())
            copied_example = copied_exercise / example.relative_to(exercise_dir.resolve())
            copied_test = copied_exercise / test.relative_to(exercise_dir.resolve())
            shutil.copy2(copied_example, copied_solution)
        except (OSError, ValueError) as error:
            print(f"Unable to prepare temporary exercise copy: {error}", file=sys.stderr)
            return 1

        try:
            with copied_test.open(encoding="utf-8") as test_script:
                process = subprocess.run(
                    ["sqlite3", "-bail"],
                    stdin=test_script,
                    cwd=copied_exercise,
                    capture_output=True,
                    text=True,
                    check=False,
                )
        except OSError as error:
            print(f"Unable to run sqlite3: {error}", file=sys.stderr)
            return 1

        if process.stdout:
            print(process.stdout, end="" if process.stdout.endswith("\n") else "\n")
        if process.stderr:
            print(process.stderr, end="" if process.stderr.endswith("\n") else "\n", file=sys.stderr)
        if process.returncode:
            print(f"sqlite3 exited with status {process.returncode}", file=sys.stderr)

        results_path = copied_exercise / "output.json"
        try:
            results_text = results_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            print("Test script did not create output.json", file=sys.stderr)
            print("Executed: 0, passed: 0, failed: 0")
            return 1
        except OSError as error:
            print(f"Unable to parse output.json: {error}", file=sys.stderr)
            print("Executed: 0, passed: 0, failed: 0")
            return 1

        if not results_text.strip():
            print("No tests executed: output.json is empty", file=sys.stderr)
            print("Executed: 0, passed: 0, failed: 0")
            return 1

        try:
            results = json.loads(results_text)
        except json.JSONDecodeError as error:
            print(f"Unable to parse output.json: {error}", file=sys.stderr)
            print("Executed: 0, passed: 0, failed: 0")
            return 1

        if not isinstance(results, list):
            print("output.json must contain a JSON array", file=sys.stderr)
            print("Executed: 0, passed: 0, failed: 0")
            return 1

        passed = sum(
            isinstance(result, dict) and result.get("status") == "pass"
            for result in results
        )
        failed = len(results) - passed
        present_names = {
            result["name"]
            for result in results
            if isinstance(result, dict) and isinstance(result.get("name"), str)
        }
        missing_names = sorted(EXPECTED_TEST_NAMES - present_names)
        print(f"Executed: {len(results)}, passed: {passed}, failed: {failed}")

        if missing_names:
            print(
                f"Missing expected tests: {', '.join(missing_names)}",
                file=sys.stderr,
            )

        for result in results:
            if not isinstance(result, dict) or result.get("status") != "pass":
                name = result.get("name", "<unnamed>") if isinstance(result, dict) else "<invalid result>"
                status = result.get("status", "<missing>") if isinstance(result, dict) else "<invalid>"
                message = result.get("message") if isinstance(result, dict) else None
                print(f"FAIL {name}: status={status}", file=sys.stderr)
                if message:
                    print(f"  {message}", file=sys.stderr)

        if not results:
            print("No tests executed", file=sys.stderr)

        return int(
            process.returncode != 0
            or not results
            or failed != 0
            or bool(missing_names)
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exercise-dir",
        type=Path,
        default=DEFAULT_EXERCISE_DIR,
        help="exercise directory (defaults to exercises/practice/nucleotide-count)",
    )
    args = parser.parse_args()
    return run_check(args.exercise_dir.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
