#!/usr/bin/env python3

"""Automated verification entry point for R08-T022."""

import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
WORK_DIR = Path(__file__).resolve().parent
CANONICAL_DATA = WORK_DIR / "canonical-data.json"
COURSE_CHECK = ROOT / "tools/course_checks/r08-t022.py"
EVIDENCE = WORK_DIR / "verification.json"


def version(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return (result.stdout or result.stderr).strip()


def run_missing_result_regression(case_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Confirm the course check rejects a truncated output.json result list."""
    with tempfile.TemporaryDirectory(prefix="r08-t022-missing-result-") as directory:
        temporary_root = Path(directory) / "repo"
        copied_exercise = temporary_root / "exercises/practice/two-fer"
        copied_exercise.parent.mkdir(parents=True)
        shutil.copytree(ROOT / "exercises/practice/two-fer", copied_exercise)
        (temporary_root / "bin").mkdir()
        shutil.copy2(ROOT / "bin/generate_tests", temporary_root / "bin/generate_tests")
        copied_check = temporary_root / "tools/course_checks/r08-t022.py"
        copied_check.parent.mkdir(parents=True)
        shutil.copy2(COURSE_CHECK, copied_check)
        copied_canonical = temporary_root / "work/R08-T022/canonical-data.json"
        copied_canonical.parent.mkdir(parents=True)
        shutil.copy2(CANONICAL_DATA, copied_canonical)

        fake_bin = Path(directory) / "fake-bin"
        fake_bin.mkdir()
        fake_sqlite = fake_bin / "sqlite3"
        fake_sqlite.write_text(
            f"#!{sys.executable}\n"
            "import json\n"
            "import os\n"
            "with open('output.json', 'w', encoding='utf-8') as output_file:\n"
            "    json.dump(json.loads(os.environ['R08_T022_PROBE_OUTPUT']), output_file)\n"
            "print('__R08_T022_CASE_ROWS__')\n"
            "print(os.environ['R08_T022_PROBE_CASE_ROWS'])\n",
            encoding="utf-8",
        )
        fake_sqlite.chmod(0o755)

        probe_output = [
            {"name": case_rows[0]["name"], "status": "pass"}
        ]
        environment = os.environ.copy()
        environment["PATH"] = (
            str(fake_bin) + os.pathsep + environment.get("PATH", "")
        )
        environment["R08_T022_PROBE_OUTPUT"] = json.dumps(probe_output)
        environment["R08_T022_PROBE_CASE_ROWS"] = json.dumps(case_rows)
        process = subprocess.run(
            [
                sys.executable,
                str(copied_check),
                "--canonical-data",
                str(copied_canonical),
            ],
            cwd=temporary_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = process.stdout + process.stderr
        missing_names = sorted(
            {case["name"] for case in case_rows} - {probe_output[0]["name"]}
        )
        passed = (
            process.returncode != 0
            and all(name in output for name in missing_names)
        )
        return {
            "description": "Three SQL case rows but only one passing output.json result",
            "sql_case_rows": len(case_rows),
            "output_json_results": len(probe_output),
            "expected_missing_names": missing_names,
            "returncode": process.returncode,
            "diagnostic": output.strip(),
            "passed": passed,
        }


def main() -> int:
    environment = os.environ.copy()
    before = {
        name: hashlib.sha256(
            (ROOT / "exercises/practice/two-fer" / name).read_bytes()
        ).hexdigest()
        for name in ["two-fer.sql", "two-fer_test.sql", "test_reporter.sql", "data.csv"]
    }
    process = subprocess.run(
        [
            sys.executable,
            str(COURSE_CHECK),
            "--canonical-data",
            str(CANONICAL_DATA),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    try:
        report: dict[str, Any] = json.loads(process.stdout)
    except json.JSONDecodeError:
        report = {
            "success": False,
            "error": "Focused check did not produce valid JSON",
            "stdout": process.stdout,
        }

    if process.returncode == 0 and report.get("success"):
        regression = run_missing_result_regression(
            report["sql_tests"]["actual_rows"]
        )
        report["missing_result_regression"] = regression
        if not regression["passed"]:
            report["success"] = False

    after = {
        name: hashlib.sha256(
            (ROOT / "exercises/practice/two-fer" / name).read_bytes()
        ).hexdigest()
        for name in before
    }
    report["working_files_unchanged"] = before == after
    report["tools"] = {
        "python": sys.version.splitlines()[0],
        "sqlite": version(["sqlite3", "--version"]),
        "jinja2": importlib.metadata.version("Jinja2")
        if importlib.metadata.packages_distributions().get("jinja2")
        else "not installed in checker environment",
        "configlet": "not installed; no configlet command run",
    }
    report["input_provenance"] = {
        "canonical_source": (
            "exercism/problem-specifications@84a96854db1bda581317164d3e6ac6aa01723182:"
            "exercises/two-fer/canonical-data.json"
        ),
        "canonical_sha256": hashlib.sha256(CANONICAL_DATA.read_bytes()).hexdigest(),
    }
    report["focused_check_returncode"] = process.returncode
    report["focused_check_stderr"] = process.stderr
    if process.returncode != 0:
        report["success"] = False
    if not report["working_files_unchanged"]:
        report["success"] = False
        report["error"] = "A working two-fer exercise file changed during verification"

    EVIDENCE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if process.stdout:
        print(process.stdout, end="" if process.stdout.endswith("\n") else "\n")
    if process.stderr:
        print(process.stderr, file=sys.stderr, end="" if process.stderr.endswith("\n") else "\n")
    print(f"Evidence: {EVIDENCE.relative_to(ROOT)}")
    print(f"Working exercise files unchanged: {report['working_files_unchanged']}")
    return 0 if report.get("success") and process.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
