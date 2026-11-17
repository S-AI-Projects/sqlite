#!/usr/bin/env python3
"""Verify Pascal's triangle with the maintained reference in isolation."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[2]
SLUG = "pascals-triangle"
EXERCISE = ROOT / "exercises" / "practice" / SLUG
TASK_DIR = Path(__file__).resolve().parent
SELECTED = {
    "9920ce55-9629-46d5-85d6-4201f4a4234d",
    "70d643ce-a46d-4e93-af58-12d88dd01f21",
    "a6e5a2a2-fc9a-4b47-9f4f-ed9ad9fbe4bd",
}


def resolve_configured(config: dict, key: str) -> Path:
    rel = Path(config["files"][key][0])
    root = EXERCISE.resolve()
    path = (EXERCISE / rel).resolve()
    if not path.is_relative_to(root):
        raise AssertionError(f"{key} path escapes the exercise: {rel}")
    if not path.is_file():
        raise AssertionError(f"{key} path does not exist: {path}")
    return path


def metadata_counts() -> tuple[int, int, dict]:
    with (EXERCISE / ".meta/tests.toml").open("rb") as stream:
        tests = tomllib.load(stream)
    included = sum(entry.get("include", True) for entry in tests.values())
    excluded = len(tests) - included
    return included, excluded, tests


def run_suite(
    *,
    solution_text: str | None = None,
    test_mutator: Callable[[str], str] | None = None,
) -> dict:
    config = json.loads((EXERCISE / ".meta/config.json").read_text())
    solution = resolve_configured(config, "solution")
    test = resolve_configured(config, "test")
    example = resolve_configured(config, "example")

    with tempfile.TemporaryDirectory(prefix="r08-t001-") as temp:
        copy_root = Path(temp) / SLUG
        shutil.copytree(EXERCISE, copy_root)
        copied_solution = copy_root / solution.relative_to(EXERCISE)
        copied_test = copy_root / test.relative_to(EXERCISE)
        copied_solution.write_text(
            example.read_text() if solution_text is None else solution_text
        )
        test_sql = copied_test.read_text()
        if test_mutator is not None:
            test_sql = test_mutator(test_sql)
        # Some older track scripts write output.json through test_reporter.sql;
        # this final capture makes the evidence contract explicit for all cases.
        copied_test.write_text(
            test_sql
            + "\n.mode json\n.once 'output.json'\nSELECT * FROM tests;\n"
        )
        proc = subprocess.run(
            ["sqlite3", "-bail"],
            cwd=copy_root,
            input=copied_test.read_text(),
            text=True,
            capture_output=True,
        )
        report_path = copy_root / "output.json"
        if report_path.exists():
            payload = report_path.read_text()
            rows = json.loads(payload) if payload.strip() else []
        else:
            rows = None
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "rows": rows,
        }


def assert_pass(result: dict) -> list[dict]:
    if result["returncode"] != 0:
        raise AssertionError(result["stderr"] or result["stdout"])
    rows = result["rows"]
    if not isinstance(rows, list) or not rows:
        raise AssertionError("the test run produced zero JSON cases")
    failures = [row for row in rows if row.get("status") != "pass"]
    if failures:
        raise AssertionError(json.dumps(failures, indent=2))
    return rows


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    before_included, before_excluded, tests = metadata_counts()
    if before_included != 8 or before_excluded != 0:
        raise AssertionError(
            f"unexpected metadata counts: included={before_included}, excluded={before_excluded}"
        )
    for uuid in SELECTED:
        entry = tests.get(uuid)
        if not entry or not entry.get("comment"):
            raise AssertionError(f"missing rationale comment for {uuid}")

    solution_path = EXERCISE / "pascals-triangle.sql"
    learner_hash_before = sha256(solution_path)
    result = run_suite()
    rows = assert_pass(result)
    if len(rows) != before_included:
        raise AssertionError(f"expected {before_included} cases, got {len(rows)}")

    broken = run_suite(solution_text="-- deliberately incomplete reference")
    if broken["returncode"] == 0 and broken["rows"] and all(
        row.get("status") == "pass" for row in broken["rows"]
    ):
        raise AssertionError("the checker did not detect a broken reference")

    empty = run_suite(test_mutator=lambda sql: sql + "\nDELETE FROM tests;\n")
    if empty["returncode"] != 0 or empty["rows"] != []:
        raise AssertionError("the zero-test fixture did not produce an empty report")

    learner_hash_after = sha256(solution_path)
    if learner_hash_before != learner_hash_after:
        raise AssertionError("the learner solution changed during the check")

    after_included, after_excluded, _ = metadata_counts()
    if (before_included, before_excluded) != (after_included, after_excluded):
        raise AssertionError("metadata counts changed during the check")

    TASK_DIR.mkdir(parents=True, exist_ok=True)
    (TASK_DIR / "results.json").write_text(
        json.dumps(
            {
                "included_before": before_included,
                "excluded_before": before_excluded,
                "included_after": after_included,
                "excluded_after": after_excluded,
                "executed_cases": len(rows),
                "statuses": [row.get("status") for row in rows],
            },
            indent=2,
        )
        + "\n"
    )
    versions = subprocess.check_output(["sqlite3", "--version"], text=True).strip()
    (TASK_DIR / "tool_versions.txt").write_text(
        f"python: {subprocess.check_output(['python3', '--version'], text=True).strip()}\n"
        f"sqlite3: {versions}\n"
    )
    print(f"pascals-triangle: {len(rows)} cases passed; included={after_included}, excluded={after_excluded}")


if __name__ == "__main__":
    main()
