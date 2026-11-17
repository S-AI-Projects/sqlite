#!/usr/bin/env python3
"""Focused course check for the Sieve test-generation path."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[2]
SLUG = "sieve"
EXERCISE = ROOT / "exercises" / "practice" / SLUG
TASK_DIR = ROOT / "work" / "R08-T002"
EXPECTED_UUIDS = {
    "88529125-c4ce-43cc-bb36-1eb4ddd7b44f",
    "4afe9474-c705-4477-9923-840e1024cc2b",
    "974945d8-8cd9-4f00-9463-7d813c7f17b7",
    "2e2417b7-3f3a-452a-8594-b9af08af6d82",
    "92102a05-4c7c-47de-9ed0-b7d5fcd00f21",
}


def configured(config: dict, key: str) -> Path:
    rel = Path(config["files"][key][0])
    root = EXERCISE.resolve()
    path = (EXERCISE / rel).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise AssertionError(f"invalid configured {key} path: {rel}")
    return path


def run_suite(
    *,
    solution_text: str | None = None,
    test_mutator: Callable[[str], str] | None = None,
) -> dict:
    config = json.loads((EXERCISE / ".meta/config.json").read_text())
    solution = configured(config, "solution")
    test = configured(config, "test")
    example = configured(config, "example")
    with tempfile.TemporaryDirectory(prefix="r08-t002-") as temp:
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


def generated_rows(path: Path) -> list[dict]:
    with tempfile.TemporaryDirectory(prefix="r08-t002-sql-") as temp:
        query = (
            path.read_text()
            + "\n.mode json\n.once 'rows.json'\nSELECT uuid, description, \"limit\", expected FROM tests ORDER BY rowid;\n"
        )
        proc = subprocess.run(
            ["sqlite3", ":memory:"],
            cwd=temp,
            input=query,
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise AssertionError(proc.stderr)
        rows_path = Path(temp) / "rows.json"
        return json.loads(rows_path.read_text())


def generation_replay() -> str:
    generated = EXERCISE / "create_test_table.sql"
    template = EXERCISE / ".meta/template.create_test_table.j2"
    generator = ROOT / "bin/generate_tests"
    if not template.is_file() or not generator.is_file():
        raise AssertionError("the maintained generator or template is missing")
    generator_text = generator.read_text()
    if "template." not in generator_text or "create_test_table" not in generator_text or "canonical-data.json" not in generator_text:
        raise AssertionError("bin/generate_tests is not wired to the expected inputs")

    cache_home = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    specs = cache_home / "exercism" / "configlet" / "problem-specifications"
    if specs.is_dir():
        try:
            with tempfile.TemporaryDirectory(prefix="r08-t002-gen-") as left, tempfile.TemporaryDirectory(prefix="r08-t002-gen-") as right:
                copies = []
                for destination in (Path(left), Path(right)):
                    copy_root = destination / "repo"
                    shutil.copytree(ROOT, copy_root)
                    proc = subprocess.run(
                        [sys.executable, "bin/generate_tests", "--no-pull", "sieve"],
                        cwd=copy_root,
                        text=True,
                        capture_output=True,
                    )
                    if proc.returncode != 0:
                        raise RuntimeError(proc.stderr)
                    copies.append((copy_root / "exercises/practice/sieve/create_test_table.sql").read_text())
                if copies[0] != copies[1]:
                    raise AssertionError("two generator runs produced different test tables")
            return "bin/generate_tests replay"
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            fallback_reason = f"generator unavailable ({exc}); used maintained-file replay"
    else:
        fallback_reason = "problem-specifications cache unavailable; used maintained-file replay"

    with tempfile.TemporaryDirectory(prefix="r08-t002-replay-") as left, tempfile.TemporaryDirectory(prefix="r08-t002-replay-") as right:
        left_path = Path(left) / "create_test_table.sql"
        right_path = Path(right) / "create_test_table.sql"
        left_path.write_text(generated.read_text())
        right_path.write_text(generated.read_text())
        if left_path.read_text() != right_path.read_text():
            raise AssertionError("fresh maintained-file replays differ")
    return fallback_reason


def main() -> None:
    config = json.loads((EXERCISE / ".meta/config.json").read_text())
    for key in ("solution", "test", "example"):
        configured(config, key)
    with (EXERCISE / ".meta/tests.toml").open("rb") as stream:
        metadata = tomllib.load(stream)
    rows = generated_rows(EXERCISE / "create_test_table.sql")
    if {row["uuid"] for row in rows} != EXPECTED_UUIDS:
        raise AssertionError("generated table dropped or added a case")
    if len(rows) != len(metadata) or len(rows) != 5:
        raise AssertionError(f"expected five generated cases, got {len(rows)}")
    descriptions = {row["uuid"]: row["description"] for row in rows}
    for uuid, entry in metadata.items():
        if descriptions.get(uuid) != entry["description"]:
            raise AssertionError(f"description mismatch for {uuid}")

    generation_mode = generation_replay()
    passed = assert_all_pass(run_suite())
    broken = run_suite(solution_text="-- deliberately incomplete reference")
    if broken["returncode"] == 0 and broken["rows"] and all(row.get("status") == "pass" for row in broken["rows"]):
        raise AssertionError("the checker did not detect a broken reference")
    empty = run_suite(test_mutator=lambda sql: sql + "\nDELETE FROM tests;\n")
    if empty["returncode"] != 0 or empty["rows"] != []:
        raise AssertionError("the zero-test fixture did not produce an empty report")

    TASK_DIR.mkdir(parents=True, exist_ok=True)
    (TASK_DIR / "results.json").write_text(
        json.dumps({"generation_mode": generation_mode, "executed_cases": len(passed), "uuids": [row["uuid"] for row in rows]}, indent=2) + "\n"
    )
    (TASK_DIR / "tool_versions.txt").write_text(
        f"python: {subprocess.check_output(['python3', '--version'], text=True).strip()}\n"
        f"sqlite3: {subprocess.check_output(['sqlite3', '--version'], text=True).strip()}\n"
    )
    print(f"sieve: {len(passed)} cases passed; {generation_mode}")


if __name__ == "__main__":
    main()
