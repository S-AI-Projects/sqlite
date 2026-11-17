#!/usr/bin/env python3
"""Verify the high-scores reference and a contract-sensitive mutant."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[2]
SLUG = "high-scores"
EXERCISE = ROOT / "exercises" / "practice" / SLUG
TASK_DIR = Path(__file__).resolve().parent
TARGET_UUID = "1084ecb5-3eb4-46fe-a816-e40331a4e83a"


def configured(config: dict, key: str) -> Path:
    rel = Path(config["files"][key][0])
    root = EXERCISE.resolve()
    path = (EXERCISE / rel).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise AssertionError(f"invalid configured {key} path: {rel}")
    return path


def run_suite(*, solution_text: str | None = None, test_mutator: Callable[[str], str] | None = None) -> dict:
    config = json.loads((EXERCISE / ".meta/config.json").read_text())
    solution = configured(config, "solution")
    test = configured(config, "test")
    example = configured(config, "example")
    with tempfile.TemporaryDirectory(prefix="r08-t003-") as temp:
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


def main() -> None:
    config = json.loads((EXERCISE / ".meta/config.json").read_text())
    for key in ("solution", "test", "example"):
        configured(config, key)
    with (EXERCISE / ".meta/tests.toml").open("rb") as stream:
        metadata = tomllib.load(stream)
    if TARGET_UUID not in metadata:
        raise AssertionError("target canonical case is missing from tests.toml")

    original_text = configured(config, "example").read_text()
    passed = assert_all_pass(run_suite())
    if len(passed) != len(metadata):
        raise AssertionError(f"expected {len(metadata)} cases, got {len(passed)}")

    mutant_text = original_text.replace(
        "ORDER BY\n  scores.game_id ASC,\n  score DESC;",
        "ORDER BY\n  scores.game_id ASC,\n  score ASC;",
    )
    if mutant_text == original_text:
        raise AssertionError("the documented ordering mutation did not apply")
    mutant = run_suite(solution_text=mutant_text)
    if mutant["returncode"] != 0 or not mutant["rows"]:
        raise AssertionError("the mutant did not produce a report")
    target = next(row for row in mutant["rows"] if row.get("uuid") == TARGET_UUID)
    if target.get("status") == "pass":
        raise AssertionError("the canonical ordering case did not reject the mutant")
    if all(row.get("status") == "pass" for row in mutant["rows"]):
        raise AssertionError("the mutant was not detected")

    broken = run_suite(solution_text="-- deliberately incomplete reference")
    if broken["returncode"] == 0 and broken["rows"] and all(row.get("status") == "pass" for row in broken["rows"]):
        raise AssertionError("the checker did not detect a broken reference")
    empty = run_suite(test_mutator=lambda sql: sql + "\nDELETE FROM tests;\n")
    if empty["returncode"] != 0 or empty["rows"] != []:
        raise AssertionError("the zero-test fixture did not produce an empty report")

    TASK_DIR.mkdir(parents=True, exist_ok=True)
    (TASK_DIR / "results.json").write_text(
        json.dumps({"executed_cases": len(passed), "mutant_target": TARGET_UUID, "mutant_status": target["status"]}, indent=2) + "\n"
    )
    (TASK_DIR / "tool_versions.txt").write_text(
        f"python: {subprocess.check_output(['python3', '--version'], text=True).strip()}\n"
        f"sqlite3: {subprocess.check_output(['sqlite3', '--version'], text=True).strip()}\n"
    )
    print(f"high-scores: {len(passed)} cases passed; ordering mutant rejected by {TARGET_UUID}")


if __name__ == "__main__":
    main()
