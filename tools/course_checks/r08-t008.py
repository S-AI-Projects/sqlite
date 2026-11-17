#!/usr/bin/env python3
"""Validate Luhn metadata paths and run the configured reference in isolation."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[2]
SLUG = "luhn"
EXERCISE = ROOT / "exercises" / "practice" / SLUG
TASK_DIR = ROOT / "work" / "R08-T008"
REQUIRED = ("solution", "test", "example")


def resolve(config: dict, key: str, base: Path = EXERCISE) -> Path:
    rel = Path(config["files"][key][0])
    root = base.resolve()
    path = (base / rel).resolve()
    if not path.is_relative_to(root):
        raise AssertionError(f"{key} escapes the exercise directory: {rel}")
    if not path.is_file():
        raise AssertionError(f"{key} does not exist: {path}")
    return path


def validate_config(config: dict) -> None:
    for key in REQUIRED:
        resolve(config, key)


def run_suite(*, solution_text: str | None = None, test_mutator: Callable[[str], str] | None = None) -> dict:
    config = json.loads((EXERCISE / ".meta/config.json").read_text())
    solution = resolve(config, "solution")
    test = resolve(config, "test")
    example = resolve(config, "example")
    with tempfile.TemporaryDirectory(prefix="r08-t008-") as temp:
        copy_root = Path(temp) / SLUG
        shutil.copytree(EXERCISE, copy_root)
        copied_solution = copy_root / solution.relative_to(EXERCISE)
        copied_test = copy_root / test.relative_to(EXERCISE)
        copied_solution.write_text(example.read_text() if solution_text is None else solution_text)
        test_sql = copied_test.read_text()
        if test_mutator is not None:
            test_sql = test_mutator(test_sql)
        copied_test.write_text(test_sql + "\n.mode json\n.once 'output.json'\nSELECT * FROM tests;\n")
        proc = subprocess.run(["sqlite3", "-bail"], cwd=copy_root, input=copied_test.read_text(), text=True, capture_output=True)
        report = copy_root / "output.json"
        if report.exists():
            payload = report.read_text()
            rows = json.loads(payload) if payload.strip() else []
        else:
            rows = None
        return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "rows": rows}


def assert_all_pass(result: dict) -> list[dict]:
    if result["returncode"] != 0:
        raise AssertionError(result["stderr"] or result["stdout"])
    rows = result["rows"]
    if not isinstance(rows, list) or not rows:
        raise AssertionError("the run produced zero cases")
    bad = [row for row in rows if row.get("status") != "pass"]
    if bad:
        raise AssertionError(json.dumps(bad, indent=2))
    return rows


def expect_invalid(config: dict, key: str, value: str) -> None:
    fixture = json.loads(json.dumps(config))
    fixture["files"][key] = [value]
    try:
        validate_config(fixture)
    except AssertionError:
        return
    raise AssertionError(f"invalid {key} fixture was accepted: {value}")


def main() -> None:
    config_path = EXERCISE / ".meta/config.json"
    config = json.loads(config_path.read_text())
    validate_config(config)
    expect_invalid(config, "example", ".meta/missing-reference.sql")
    expect_invalid(config, "test", "missing-test.sql")
    expect_invalid(config, "solution", "../README.md")
    with (EXERCISE / ".meta/tests.toml").open("rb") as stream:
        metadata = tomllib.load(stream)
    passed = assert_all_pass(run_suite())
    if len(passed) != sum(entry.get("include", True) for entry in metadata.values()):
        raise AssertionError("the checker did not execute every included case")
    broken = run_suite(solution_text="-- deliberately incomplete reference")
    if broken["returncode"] == 0 and broken["rows"] and all(row.get("status") == "pass" for row in broken["rows"]):
        raise AssertionError("the checker did not detect a broken reference")
    empty = run_suite(test_mutator=lambda sql: sql + "\nDELETE FROM tests;\n")
    if empty["returncode"] != 0 or empty["rows"] != []:
        raise AssertionError("the zero-test fixture did not produce an empty report")

    TASK_DIR.mkdir(parents=True, exist_ok=True)
    (TASK_DIR / "results.json").write_text(
        json.dumps({"executed_cases": len(passed), "invalid_fixtures_rejected": 3, "config": str(config_path.relative_to(ROOT))}, indent=2) + "\n"
    )
    (TASK_DIR / "tool_versions.txt").write_text(
        f"python: {subprocess.check_output(['python3', '--version'], text=True).strip()}\n"
        f"sqlite3: {subprocess.check_output(['sqlite3', '--version'], text=True).strip()}\n"
    )
    print(f"luhn: {len(passed)} cases passed; three invalid metadata fixtures rejected")


if __name__ == "__main__":
    main()
