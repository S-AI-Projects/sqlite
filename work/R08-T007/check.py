#!/usr/bin/env python3
"""Verify the rotational-cipher reference and its SQLite-specific micro-example."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[2]
SLUG = "rotational-cipher"
EXERCISE = ROOT / "exercises" / "practice" / SLUG
TASK_DIR = Path(__file__).resolve().parent


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
    with tempfile.TemporaryDirectory(prefix="r08-t007-") as temp:
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


def micro_example() -> dict:
    sql = """
    WITH letters(ord, ch) AS (VALUES (1, 'a'), (2, 'b'), (3, 'a'))
    SELECT
      (SELECT group_concat(ch, '') FROM (SELECT ch FROM letters ORDER BY ord)) AS kept,
      (SELECT group_concat(ch) FROM (SELECT DISTINCT ch FROM letters ORDER BY ch)) AS collapsed;
    """
    with tempfile.TemporaryDirectory(prefix="r08-t007-micro-") as temp:
        script = Path(temp) / "micro.sql"
        script.write_text(".mode json\n.once 'micro.json'\n" + sql)
        proc = subprocess.run(["sqlite3", ":memory:"], cwd=temp, input=script.read_text(), text=True, capture_output=True)
        if proc.returncode != 0:
            raise AssertionError(proc.stderr)
        result = json.loads((Path(temp) / "micro.json").read_text())
    expected = [{"kept": "aba", "collapsed": "a,b"}]
    if result != expected:
        raise AssertionError(f"micro-example mismatch: {result!r}")
    return result[0]


def main() -> None:
    config = json.loads((EXERCISE / ".meta/config.json").read_text())
    for key in ("solution", "test", "example"):
        configured(config, key)
    with (EXERCISE / ".meta/tests.toml").open("rb") as stream:
        metadata = tomllib.load(stream)
    micro = micro_example()
    passed = assert_all_pass(run_suite())
    if len(passed) != len(metadata):
        raise AssertionError(f"expected {len(metadata)} cases, got {len(passed)}")
    broken = run_suite(solution_text="-- deliberately incomplete reference")
    if broken["returncode"] == 0 and broken["rows"] and all(row.get("status") == "pass" for row in broken["rows"]):
        raise AssertionError("the checker did not detect a broken reference")
    empty = run_suite(test_mutator=lambda sql: sql + "\nDELETE FROM tests;\n")
    if empty["returncode"] != 0 or empty["rows"] != []:
        raise AssertionError("the zero-test fixture did not produce an empty report")

    TASK_DIR.mkdir(parents=True, exist_ok=True)
    (TASK_DIR / "results.json").write_text(json.dumps({"executed_cases": len(passed), "micro_example": micro}, indent=2) + "\n")
    (TASK_DIR / "tool_versions.txt").write_text(
        f"python: {subprocess.check_output(['python3', '--version'], text=True).strip()}\n"
        f"sqlite3: {subprocess.check_output(['sqlite3', '--version'], text=True).strip()}\n"
    )
    print(f"rotational-cipher: {len(passed)} cases passed; micro-example kept={micro['kept']!r}, collapsed={micro['collapsed']!r}")


if __name__ == "__main__":
    main()
