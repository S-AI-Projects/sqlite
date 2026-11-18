#!/usr/bin/env python3
"""Exercise the phone-number runner's pass, failure, empty and timeout paths."""

import hashlib
import json
import platform
import subprocess
import sys
import tempfile
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
EXERCISE = ROOT / "exercises/practice/phone-number"
RUNNER = ROOT / "tools/course_checks/r08-t059.py"


def hashes():
    config = json.loads((EXERCISE / ".meta/config.json").read_text(encoding="utf-8"))
    return {
        path: hashlib.sha256((EXERCISE / path).read_bytes()).hexdigest()
        for path in config["files"]["solution"]
    }


def temp_copies():
    return sorted(str(path) for path in Path(tempfile.gettempdir()).glob("r08-t059-copy-*"))


def invoke(extra_args=()):
    before_hashes = hashes()
    before_copies = temp_copies()
    result = subprocess.run([sys.executable, str(RUNNER), *map(str, extra_args)],
                            capture_output=True, text=True, timeout=10)
    after_hashes = hashes()
    after_copies = temp_copies()
    if after_hashes != before_hashes:
        raise AssertionError("learner file hashes changed during a runner invocation")
    if after_copies != before_copies:
        raise AssertionError("runner left a temporary exercise copy behind")
    result.course_evidence = {
        "learner_hashes_before": before_hashes,
        "learner_hashes_after": after_hashes,
        "temporary_copies_before": before_copies,
        "temporary_copies_after": after_copies,
    }
    return result


def command_version(command):
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return (result.stdout or result.stderr).strip().splitlines()[0]


def main():
    original_hashes = hashes()
    tests_meta = tomllib.loads((EXERCISE / ".meta/tests.toml").read_text(encoding="utf-8"))
    expected_descriptions = [item["description"] for item in tests_meta.values() if item.get("include", True)]
    evidence_query = """
.mode json
.once 'assertions.json'
SELECT t.uuid, t.description, t.phrase AS input, t.expected_result,
       t.expected_error, a.result AS actual_result, a.error AS actual_error, t.status
FROM tests AS t
LEFT JOIN "phone-number" AS a ON a.phrase = t.phrase
ORDER BY t.rowid;
"""
    with tempfile.TemporaryDirectory(prefix="r08-t059-check-inputs-") as temporary:
        temp = Path(temporary)
        selected_test = temp / "selected-tests.sql"
        configured_test = (EXERCISE / "phone-number_test.sql").read_text(encoding="utf-8")
        selected_test.write_text(configured_test + "\n" + evidence_query, encoding="utf-8")
        normal = invoke(["--test-sql", selected_test])
        if normal.returncode:
            raise AssertionError(f"reference run failed: {normal.stderr.strip()}")
        normal_result = json.loads(normal.stdout)
        if not normal_result["cases_executed"]:
            raise AssertionError("reference runner reported zero tests")
        if Counter(row["description"] for row in normal_result["cases"]) != Counter(expected_descriptions):
            raise AssertionError("enabled tests.toml descriptions do not match executed cases")
        if any(row.get("status") != "pass" for row in normal_result["cases"]):
            raise AssertionError("reference run contains a non-passing assertion")

        bad_solution = temp / "wrong-solution.sql"
        bad_solution.write_text('UPDATE "phone-number" SET result = \'not-a-number\';\n', encoding="utf-8")
        failing = invoke(["--solution-sql", bad_solution])
        if failing.returncode == 0 or "test cases failed" not in failing.stderr:
            raise AssertionError("deliberately wrong solution was not rejected for failed assertions")

        empty_tests = temp / "empty-tests.sql"
        empty_tests.write_text(
            ".mode list\n.once 'output.json'\n"
            "SELECT json_group_array(json_object('description', description, 'status', status)) "
            "FROM (SELECT 'none' AS description, 'pass' AS status WHERE 0);\n",
            encoding="utf-8",
        )
        empty = invoke(["--test-sql", empty_tests])
        if empty.returncode == 0 or "zero test cases" not in empty.stderr:
            raise AssertionError("empty test selection was not rejected")

        interrupted_sql = temp / "long-running-test.sql"
        interrupted_sql.write_text(
            "WITH RECURSIVE counter(n) AS (VALUES(0) UNION ALL "
            "SELECT n + 1 FROM counter WHERE n < 100000000) SELECT max(n) FROM counter;\n",
            encoding="utf-8",
        )
        interrupted = invoke(["--test-sql", interrupted_sql, "--timeout", "0.05"])
        if interrupted.returncode == 0 or "interrupted" not in interrupted.stderr:
            raise AssertionError("timeout did not interrupt and reject the long-running child")

    if hashes() != original_hashes:
        raise AssertionError("learner solution file hash changed after all runs")
    versions = {
        "python": sys.version.splitlines()[0],
        "sqlite3": command_version(["sqlite3", "--version"]),
        "jq": command_version(["jq", "--version"]),
        "git": command_version(["git", "--version"]),
        "platform": platform.platform(),
    }
    evidence = {
        "success": {
            "cases_executed": normal_result["cases_executed"],
            "cases": [
                {"uuid": row["uuid"], "description": row["description"], "input": row["input"],
                 "expected": {"result": row["expected_result"], "error": row["expected_error"]},
                 "actual": {"result": row["actual_result"], "error": row["actual_error"]},
                 "status": row["status"]}
                for row in normal_result["cases"]
            ],
        },
        "negative_checks": {
            "wrong_solution": {"expected": "non-zero with assertion failure", "actual": failing.stderr.strip()},
            "empty_selection": {"expected": "non-zero with zero-test failure", "actual": empty.stderr.strip()},
            "interrupted_child": {"expected": "non-zero after timeout", "actual": interrupted.stderr.strip()},
        },
        "per_run_integrity": {
            "success": normal.course_evidence,
            "wrong_solution": failing.course_evidence,
            "empty_selection": empty.course_evidence,
            "interrupted_child": interrupted.course_evidence,
        },
        "learner_solution_sha256": original_hashes,
        "temporary_copies_cleaned": True,
        "tool_versions": versions,
    }
    (WORK / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    (WORK / "versions.txt").write_text("\n".join(f"{key}: {value}" for key, value in versions.items()) + "\n",
                                       encoding="utf-8")
    print(f"phone-number: {normal_result['cases_executed']} cases passed; failure, zero-case, timeout and hash checks passed")


if __name__ == "__main__":
    main()
