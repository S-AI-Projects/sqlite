#!/usr/bin/env python3
"""Run matching-brackets in a temporary copy and test failure propagation."""

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
SLUG = "matching-brackets"
EXERCISE = ROOT / "exercises" / "practice" / SLUG
TASK_DIR = ROOT / "work" / "R08-T009"
LEARNER = EXERCISE / "matching-brackets.sql"


def configured(config: dict, key: str) -> Path:
    rel = Path(config["files"][key][0])
    root = EXERCISE.resolve()
    path = (EXERCISE / rel).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise AssertionError(f"invalid configured {key} path: {rel}")
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_suite(*, solution_text: str | None = None, test_mutator: Callable[[str], str] | None = None) -> dict:
    config = json.loads((EXERCISE / ".meta/config.json").read_text())
    solution = configured(config, "solution")
    test = configured(config, "test")
    example = configured(config, "example")
    with tempfile.TemporaryDirectory(prefix="r08-t009-") as temp:
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
    expected_count = sum(entry.get("include", True) for entry in metadata.values())

    runs: dict[str, dict] = {}
    before = sha256(LEARNER)
    runs["reference"] = {"result": run_suite(), "hash_before": before, "hash_after": sha256(LEARNER)}
    passed = assert_all_pass(runs["reference"]["result"])
    if len(passed) != expected_count:
        raise AssertionError(f"expected {expected_count} cases, got {len(passed)}")
    if runs["reference"]["hash_before"] != runs["reference"]["hash_after"]:
        raise AssertionError("learner file changed during the successful run")

    before = sha256(LEARNER)
    runs["failing_reference"] = {"result": run_suite(solution_text="-- deliberately incomplete reference"), "hash_before": before, "hash_after": sha256(LEARNER)}
    failing = runs["failing_reference"]["result"]
    if failing["returncode"] == 0 and failing["rows"] and all(row.get("status") == "pass" for row in failing["rows"]):
        raise AssertionError("a deliberately failing reference was accepted")
    if runs["failing_reference"]["hash_before"] != runs["failing_reference"]["hash_after"]:
        raise AssertionError("learner file changed during the failing run")

    before = sha256(LEARNER)
    runs["interrupted_reference"] = {"result": run_suite(solution_text="THIS IS NOT SQL;"), "hash_before": before, "hash_after": sha256(LEARNER)}
    interrupted = runs["interrupted_reference"]["result"]
    if interrupted["returncode"] == 0:
        raise AssertionError("a syntax-invalid reference unexpectedly succeeded")
    if runs["interrupted_reference"]["hash_before"] != runs["interrupted_reference"]["hash_after"]:
        raise AssertionError("learner file changed during the interrupted run")

    before = sha256(LEARNER)
    runs["zero_tests"] = {"result": run_suite(test_mutator=lambda sql: sql + "\nDELETE FROM tests;\n"), "hash_before": before, "hash_after": sha256(LEARNER)}
    zero = runs["zero_tests"]["result"]
    if zero["returncode"] != 0 or zero["rows"] != []:
        raise AssertionError("the zero-test fixture did not produce an empty report")
    if runs["zero_tests"]["hash_before"] != runs["zero_tests"]["hash_after"]:
        raise AssertionError("learner file changed during the zero-test run")

    TASK_DIR.mkdir(parents=True, exist_ok=True)
    (TASK_DIR / "results.json").write_text(
        json.dumps({"expected_cases": expected_count, "executed_cases": len(passed), "learner_sha256": sha256(LEARNER), "hashes_unchanged": all(run["hash_before"] == run["hash_after"] for run in runs.values())}, indent=2) + "\n"
    )
    (TASK_DIR / "tool_versions.txt").write_text(
        f"python: {subprocess.check_output(['python3', '--version'], text=True).strip()}\n"
        f"sqlite3: {subprocess.check_output(['sqlite3', '--version'], text=True).strip()}\n"
    )
    print(f"matching-brackets: {len(passed)} cases passed; all learner hashes unchanged")


if __name__ == "__main__":
    main()
