#!/usr/bin/env python3
"""Run the phone-number reference in a disposable copy of its exercise."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath


class RunnerError(RuntimeError):
    """The isolated test run could not produce a fully passing result."""


def resolve_declared_path(root, raw_path, role):
    if not isinstance(raw_path, str) or not raw_path:
        raise RunnerError(f"config.json files.{role} contains an invalid path")
    relative = PurePosixPath(raw_path.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts:
        raise RunnerError(f"config.json files.{role} must stay inside the exercise: {raw_path}")
    try:
        resolved = root.joinpath(*relative.parts).resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (FileNotFoundError, ValueError) as error:
        raise RunnerError(f"config.json files.{role} path does not exist inside the exercise: {raw_path}") from error
    if not resolved.is_file():
        raise RunnerError(f"config.json files.{role} path is not a file: {raw_path}")
    return resolved


def learner_hashes(exercise, config):
    hashes = {}
    for raw_path in config["files"].get("solution", []):
        path = resolve_declared_path(exercise, raw_path, "solution")
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not hashes:
        raise RunnerError("config.json declares no learner solution files")
    return hashes


def run(solution_sql=None, test_sql=None, timeout=30.0):
    exercise = Path(__file__).resolve().parents[2] / "exercises/practice/phone-number"
    config_path = exercise / ".meta/config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    files = config.get("files", {})
    for role in ("solution", "test", "example"):
        if not isinstance(files.get(role), list) or not files[role]:
            raise RunnerError(f"config.json must declare files.{role}")
    originals = learner_hashes(exercise, config)
    try:
        with tempfile.TemporaryDirectory(prefix="r08-t059-copy-") as temporary:
            copied = Path(temporary) / "phone-number"
            shutil.copytree(exercise, copied)
            copied_config = json.loads((copied / ".meta/config.json").read_text(encoding="utf-8"))
            solution_path = resolve_declared_path(copied, copied_config["files"]["solution"][0], "solution")
            example_path = resolve_declared_path(copied, copied_config["files"]["example"][0], "example")
            configured_test_path = resolve_declared_path(copied, copied_config["files"]["test"][0], "test")
            if solution_sql is None:
                replacement = example_path.read_text(encoding="utf-8")
            else:
                replacement = Path(solution_sql).read_text(encoding="utf-8")
            solution_path.write_text(replacement, encoding="utf-8")
            sql = Path(test_sql).read_text(encoding="utf-8") if test_sql else configured_test_path.read_text(encoding="utf-8")
            try:
                child = subprocess.run(["sqlite3", "-bail"], input=sql, cwd=copied,
                                       capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired as error:
                raise RunnerError(f"sqlite3 was interrupted after {timeout:g} seconds") from error
            if child.returncode:
                detail = child.stderr.strip() or child.stdout.strip()
                raise RunnerError(f"sqlite3 exited with code {child.returncode}: {detail}")
            output_path = copied / "output.json"
            if not output_path.is_file() or not output_path.stat().st_size:
                raise RunnerError("the test script did not write output.json")
            output = json.loads(output_path.read_text(encoding="utf-8"))
            if not isinstance(output, list) or not output:
                raise RunnerError("zero test cases were reported")
            failures = [item for item in output if item.get("status") != "pass"]
            if failures:
                raise RunnerError(f"{len(failures)} of {len(output)} test cases failed")
            assertion_path = copied / "assertions.json"
            assertions = json.loads(assertion_path.read_text(encoding="utf-8")) if assertion_path.exists() else output
            return {"cases_executed": len(output), "passed": len(output), "cases": assertions}
    finally:
        current = learner_hashes(exercise, config)
        if current != originals:
            raise RunnerError("learner solution file hashes changed during the isolated run")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solution-sql", help="Use this SQL only in the temporary copy (checker override).")
    parser.add_argument("--test-sql", help="Use this test script instead of the configured test file (checker override).")
    parser.add_argument("--timeout", type=float, default=30.0, help="Maximum seconds for the sqlite3 child process.")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    try:
        result = run(args.solution_sql, args.test_sql, args.timeout)
    except Exception as error:
        print(f"r08-t059: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
