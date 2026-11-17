#!/usr/bin/env python3
"""Verify reverse-string and record a small, correctness-first benchmark."""

from __future__ import annotations

import json
import shutil
import statistics
import subprocess
import tempfile
import time
import tomllib
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[2]
SLUG = "reverse-string"
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
    with tempfile.TemporaryDirectory(prefix="r08-t005-") as temp:
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


def benchmark(length: int, repetitions: int = 5) -> dict:
    text = "a" * length
    expected = text[::-1]
    times_ms: list[float] = []
    with tempfile.TemporaryDirectory(prefix="r08-t005-bench-") as temp:
        script = Path(temp) / "benchmark.sql"
        script.write_text(
            "CREATE TABLE \"reverse-string\" (input TEXT NOT NULL, result TEXT);\n"
            f"INSERT INTO \"reverse-string\" (input) VALUES ('{text}');\n"
            f".read '{(EXERCISE / '.meta/example.sql').as_posix()}'\n"
            ".mode list\nSELECT result FROM \"reverse-string\";\n"
        )
        for _ in range(repetitions):
            started = time.perf_counter()
            proc = subprocess.run(["sqlite3", ":memory:"], input=script.read_text(), text=True, capture_output=True)
            elapsed_ms = (time.perf_counter() - started) * 1000
            if proc.returncode != 0:
                raise AssertionError(proc.stderr)
            actual = proc.stdout.strip()
            if actual != expected:
                raise AssertionError(f"benchmark correctness failed for length {length}: {actual!r}")
            times_ms.append(round(elapsed_ms, 3))
    return {"length": length, "recursive_states": length + 1, "median_ms": round(statistics.median(times_ms), 3), "repetitions": repetitions, "times_ms": times_ms}


def main() -> None:
    config = json.loads((EXERCISE / ".meta/config.json").read_text())
    for key in ("solution", "test", "example"):
        configured(config, key)
    with (EXERCISE / ".meta/tests.toml").open("rb") as stream:
        metadata = tomllib.load(stream)
    passed = assert_all_pass(run_suite())
    if len(passed) != sum(entry.get("include", True) for entry in metadata.values()):
        raise AssertionError("the checker did not execute every included case")

    measurements = [benchmark(size) for size in (1, 5, 32)]
    broken = run_suite(solution_text="-- deliberately incomplete reference")
    if broken["returncode"] == 0 and broken["rows"] and all(row.get("status") == "pass" for row in broken["rows"]):
        raise AssertionError("the checker did not detect a broken reference")
    empty = run_suite(test_mutator=lambda sql: sql + "\nDELETE FROM tests;\n")
    if empty["returncode"] != 0 or empty["rows"] != []:
        raise AssertionError("the zero-test fixture did not produce an empty report")

    TASK_DIR.mkdir(parents=True, exist_ok=True)
    (TASK_DIR / "results.json").write_text(json.dumps({"executed_cases": len(passed), "measurements": measurements}, indent=2) + "\n")
    (TASK_DIR / "tool_versions.txt").write_text(
        f"python: {subprocess.check_output(['python3', '--version'], text=True).strip()}\n"
        f"sqlite3: {subprocess.check_output(['sqlite3', '--version'], text=True).strip()}\n"
    )
    print(f"reverse-string: {len(passed)} cases passed; measured lengths 1, 5, 32 with five repetitions each")


if __name__ == "__main__":
    main()
