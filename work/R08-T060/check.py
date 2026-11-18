#!/usr/bin/env python3
"""Run resistor-color's configured reference and verify its active cases."""

import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
EXERCISE = ROOT / "exercises/practice/resistor-color"


def command_version(command):
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return (result.stdout or result.stderr).strip().splitlines()[0]


def main():
    config = json.loads((EXERCISE / ".meta/config.json").read_text(encoding="utf-8"))
    for role in ("solution", "test", "example"):
        if not config["files"].get(role):
            raise AssertionError(f"config.json has no {role} file")
    learner_path = EXERCISE / config["files"]["solution"][0]
    learner_before = hashlib.sha256(learner_path.read_bytes()).hexdigest()
    tests_meta = tomllib.loads((EXERCISE / ".meta/tests.toml").read_text(encoding="utf-8"))
    enabled = [item for item in tests_meta.values() if item.get("include", True)]
    expected_names = [item["description"] for item in enabled]
    evidence_query = """
.mode json
.once 'assertions.json'
SELECT t.uuid, t.name, t.color AS input, t.result AS expected,
       actual.result AS actual, t.status
FROM test_color_code AS t
LEFT JOIN color_code AS actual ON actual.color = t.color
ORDER BY t.rowid;
"""
    with tempfile.TemporaryDirectory(prefix="r08-t060-") as temporary:
        copied = Path(temporary) / "resistor-color"
        shutil.copytree(EXERCISE, copied)
        copied_config = json.loads((copied / ".meta/config.json").read_text(encoding="utf-8"))
        (copied / copied_config["files"]["solution"][0]).write_text(
            (EXERCISE / copied_config["files"]["example"][0]).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        test_sql = (copied / copied_config["files"]["test"][0]).read_text(encoding="utf-8")
        result = subprocess.run(["sqlite3", "-bail"], input=test_sql + "\n" + evidence_query,
                                cwd=copied, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"sqlite3 exited {result.returncode}: {result.stderr.strip()}")
        output_path = copied / "output.json"
        if not output_path.is_file() or not output_path.stat().st_size:
            raise AssertionError("test run did not write output.json")
        output = json.loads(output_path.read_text(encoding="utf-8"))
        if not isinstance(output, list) or not output:
            raise AssertionError("zero test cases were reported")
        failures = [row for row in output if row.get("status") != "pass"]
        if failures:
            raise AssertionError(f"{len(failures)} of {len(output)} test cases failed")
        if Counter(row["name"] for row in output) != Counter(expected_names):
            raise AssertionError("enabled tests.toml descriptions do not match executed cases")
        assertions = json.loads((copied / "assertions.json").read_text(encoding="utf-8"))

    if len(assertions) != len(output):
        raise AssertionError("evidence query returned a different number of cases")
    for row in assertions:
        if row["status"] != "pass" or row["actual"] != row["expected"]:
            raise AssertionError(f"{row['name']}: expected {row['expected']}, got {row['actual']}")
    learner_after = hashlib.sha256(learner_path.read_bytes()).hexdigest()
    if learner_after != learner_before:
        raise AssertionError("learner solution changed during the check")

    versions = {
        "python": sys.version.splitlines()[0],
        "sqlite3": command_version(["sqlite3", "--version"]),
        "jq": command_version(["jq", "--version"]),
        "git": command_version(["git", "--version"]),
        "platform": platform.platform(),
    }
    evidence = {
        "cases_executed": len(output),
        "cases": [
            {"uuid": row["uuid"], "description": row["name"], "input": row["input"],
             "expected": row["expected"], "actual": row["actual"], "status": row["status"]}
            for row in assertions
        ],
        "excluded_case": {
            "description": "Colors",
            "include": tests_meta["581d68fa-f968-4be2-9f9d-880f2fb73cf7"]["include"],
        },
        "learner_solution_sha256": learner_before,
        "tool_versions": versions,
    }
    (WORK / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    (WORK / "versions.txt").write_text("\n".join(f"{key}: {value}" for key, value in versions.items()) + "\n",
                                       encoding="utf-8")
    print(f"resistor-color: {len(output)} selected cases passed; expected and actual results agree")


if __name__ == "__main__":
    main()
