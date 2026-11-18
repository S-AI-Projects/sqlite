#!/usr/bin/env python3
"""Run the protein-translation reference and check its SQLite micro-example."""

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
EXERCISE = ROOT / "exercises/practice/protein-translation"
CONFIG = json.loads((EXERCISE / ".meta/config.json").read_text(encoding="utf-8"))
SOLUTION = EXERCISE / CONFIG["files"]["solution"][0]
TEST = EXERCISE / CONFIG["files"]["test"][0]
EXAMPLE = EXERCISE / CONFIG["files"]["example"][0]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command_version(command):
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return (result.stdout or result.stderr).strip().splitlines()[0]


def main():
    stub_before = digest(SOLUTION)
    config = CONFIG
    for role in ("solution", "test", "example"):
        if not config["files"].get(role):
            raise AssertionError(f"config.json has no {role} file")

    tests_meta = tomllib.loads((EXERCISE / ".meta/tests.toml").read_text(encoding="utf-8"))
    expected_descriptions = [
        item["description"]
        for item in tests_meta.values()
        if item.get("include", True)
    ]
    evidence_query = """
.mode json
.once 'assertions.json'
SELECT t.uuid, t.description, t.strand AS input, t.expected_result,
       t.expected_error, a.result AS actual_result, a.error AS actual_error,
       t.status
FROM tests AS t
LEFT JOIN "protein-translation" AS a ON a.strand = t.strand
ORDER BY t.rowid;
"""
    with tempfile.TemporaryDirectory(prefix="r08-t057-") as temporary:
        copy = Path(temporary) / "protein-translation"
        shutil.copytree(EXERCISE, copy)
        copied_config = json.loads((copy / ".meta/config.json").read_text(encoding="utf-8"))
        (copy / copied_config["files"]["solution"][0]).write_text(
            (EXERCISE / copied_config["files"]["example"][0]).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        test_sql = (copy / copied_config["files"]["test"][0]).read_text(encoding="utf-8")
        result = subprocess.run(
            ["sqlite3", "-bail"], input=test_sql + "\n" + evidence_query,
            cwd=copy, capture_output=True, text=True,
        )
        if result.returncode:
            raise RuntimeError(f"sqlite3 exited {result.returncode}: {result.stderr.strip()}")
        output_path = copy / "output.json"
        if not output_path.is_file() or not output_path.stat().st_size:
            raise AssertionError("test run did not write output.json")
        output = json.loads(output_path.read_text(encoding="utf-8"))
        if not isinstance(output, list) or not output:
            raise AssertionError("zero test cases were reported")
        failures = [row for row in output if row.get("status") != "pass"]
        if failures:
            raise AssertionError(f"{len(failures)} of {len(output)} test cases failed")
        if Counter(row["description"] for row in output) != Counter(expected_descriptions):
            raise AssertionError("enabled tests.toml descriptions do not match executed cases")
        assertions = json.loads((copy / "assertions.json").read_text(encoding="utf-8"))

    micro_sql = """
SELECT GROUP_CONCAT(amino_acid, ', ')
FROM (
  SELECT 'Phenylalanine' AS amino_acid
  UNION ALL
  SELECT 'Phenylalanine'
);
SELECT GROUP_CONCAT(amino_acid, ', ')
FROM (
  SELECT 'Phenylalanine' AS amino_acid
  UNION
  SELECT 'Phenylalanine'
);
"""
    micro = subprocess.run(["sqlite3", "-bail", "-noheader"], input=micro_sql,
                           capture_output=True, text=True)
    if micro.returncode:
        raise RuntimeError(f"micro-example sqlite3 exited {micro.returncode}: {micro.stderr.strip()}")
    micro_actual = micro.stdout.splitlines()
    micro_expected = ["Phenylalanine, Phenylalanine", "Phenylalanine"]
    if micro_actual != micro_expected:
        raise AssertionError(f"micro-example expected {micro_expected!r}, got {micro_actual!r}")
    if digest(SOLUTION) != stub_before:
        raise AssertionError("learner solution changed during the check")

    evidence = {
        "cases_executed": len(output),
        "cases": [
            {
                "uuid": row["uuid"],
                "description": row["description"],
                "input": row["input"],
                "expected": {"result": row["expected_result"], "error": row["expected_error"]},
                "actual": {"result": row["actual_result"], "error": row["actual_error"]},
                "status": row["status"],
            }
            for row in assertions
        ],
        "micro_example": {
            "input": "two identical Phenylalanine rows",
            "expected": micro_expected,
            "actual": micro_actual,
        },
        "learner_solution_sha256": stub_before,
        "tool_versions": {
            "python": sys.version.splitlines()[0],
            "sqlite3": command_version(["sqlite3", "--version"]),
            "jq": command_version(["jq", "--version"]),
            "git": command_version(["git", "--version"]),
            "platform": platform.platform(),
        },
    }
    (WORK / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    (WORK / "versions.txt").write_text(
        "\n".join(f"{key}: {value}" for key, value in evidence["tool_versions"].items()) + "\n",
        encoding="utf-8",
    )
    print(f"protein-translation: {len(output)} cases passed; micro-example outputs asserted")


if __name__ == "__main__":
    main()
