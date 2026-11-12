#!/usr/bin/env python3
"""
Reusable focused verification check for exercises/practice/kindergarten-garden (Task R08-T043).

Verifies:
1. Resolves solution, test, and example paths from .meta/config.json.
2. Asserts the learner stub in the working tree remains unsolved.
3. Tests the reference implementation in an isolated temporary copy and asserts 17/17 pass.
4. Executes the deliberate column-major mutant and asserts it is rejected by minimal case 1fc316ed-17ab-4fba-88ef-3ae78296b692.
5. Verifies documentation in .docs/hints.md and docs/maintenance/kindergarten-garden.md.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


MUTANT_SQL = """UPDATE "kindergarten-garden"
SET
  result = (
    WITH
      plants (p) AS (
        VALUES
          (1),
          (1 + instr(diagram, char(10))),
          (2),
          (2 + instr(diagram, char(10)))
      )
    SELECT
      group_concat(
        CASE SUBSTR(diagram, (unicode(student) - 65) * 2 + p, 1)
          WHEN 'G' THEN 'grass'
          WHEN 'V' THEN 'violets'
          WHEN 'C' THEN 'clover'
          WHEN 'R' THEN 'radishes'
        END
      )
    FROM
      plants
  );
"""


def find_repo_root() -> Path:
    """Locate the git repository root."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".git").exists() or (current / "exercises").exists():
            return current
        current = current.parent
    return Path.cwd()


def run_sqlite_test(exercise_dir: Path, sql_implementation: str) -> tuple[int, list]:
    """Execute kindergarten-garden_test.sql in a temporary copy of exercise_dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_exercise = Path(tmpdir) / "kindergarten-garden"
        shutil.copytree(exercise_dir, tmp_exercise)

        (tmp_exercise / "kindergarten-garden.sql").write_text(sql_implementation, encoding="utf-8")

        test_file = tmp_exercise / "kindergarten-garden_test.sql"
        with open(test_file, "r", encoding="utf-8") as f_in:
            proc = subprocess.run(
                ["sqlite3", "-bail"],
                cwd=tmp_exercise,
                stdin=f_in,
                capture_output=True,
                text=True
            )

        output_file = tmp_exercise / "output.json"
        if not output_file.exists():
            return proc.returncode, []

        with open(output_file, "r", encoding="utf-8") as f_out:
            results = json.load(f_out)

        return proc.returncode, results


def run_checks(repo_root: Path, quiet: bool = False) -> dict:
    """Execute all verification checks for R08-T043."""
    exercise_rel = Path("exercises/practice/kindergarten-garden")
    exercise_dir = repo_root / exercise_rel

    config_path = exercise_dir / ".meta" / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Missing config.json at {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    solution_rel = config["files"]["solution"][0]
    example_rel = config["files"]["example"][0]

    stub_code = (exercise_dir / solution_rel).read_text(encoding="utf-8")
    ref_code = (exercise_dir / example_rel).read_text(encoding="utf-8")

    # 1. Verify learner stub is unsolved
    stub_rc, stub_results = run_sqlite_test(exercise_dir, stub_code)
    stub_passed = [t for t in stub_results if t.get("status") == "pass"]
    if len(stub_passed) > 0:
        raise AssertionError(f"Learner stub unexpectedly passed {len(stub_passed)} tests; expected 0.")

    # 2. Verify reference implementation passes all canonical tests
    ref_rc, ref_results = run_sqlite_test(exercise_dir, ref_code)
    if ref_rc != 0:
        raise AssertionError(f"Reference implementation failed with returncode {ref_rc}")

    if len(ref_results) == 0:
        raise AssertionError("Zero test cases executed for reference!")

    ref_passed = [t for t in ref_results if t.get("status") == "pass"]
    if len(ref_passed) != len(ref_results):
        failed_tests = [t for t in ref_results if t.get("status") != "pass"]
        raise AssertionError(f"{len(failed_tests)} test(s) failed against reference: {failed_tests}")

    # 3. Verify mutant execution and minimal rejection
    mutant_rc, mutant_results = run_sqlite_test(exercise_dir, MUTANT_SQL)
    minimal_case_name = "garden with single student"
    minimal_match = [t for t in mutant_results if t.get("name") == minimal_case_name]
    if not minimal_match:
        raise AssertionError(f"Minimal test case '{minimal_case_name}' not found in test output.")

    if minimal_match[0].get("status") != "fail":
        raise AssertionError(f"Mutant unexpectedly passed minimal test case '{minimal_case_name}'!")

    # 4. Verify documentation
    hints_path = exercise_dir / ".docs" / "hints.md"
    if not hints_path.exists():
        raise AssertionError(f"Missing hints file at {hints_path}")
    hints_text = hints_path.read_text(encoding="utf-8")
    if "row-major" not in hints_text.lower() or "column-major" not in hints_text.lower():
        raise AssertionError("hints.md missing expected row-major vs column-major traversal explanation.")

    doc_path = repo_root / "docs" / "maintenance" / "kindergarten-garden.md"
    if not doc_path.exists():
        raise AssertionError(f"Missing documentation file at {doc_path}")

    return {
        "status": "success",
        "returncode": 0,
        "total_cases": len(ref_results),
        "reference_passed": len(ref_passed),
        "stub_unsolved": True,
        "mutant_rejected_by_minimal_case": True,
        "minimal_rejecting_case": minimal_case_name,
        "hints_verified": True,
        "docs_verified": True
    }


def main():
    parser = argparse.ArgumentParser(description="Focused check for kindergarten-garden mutation regression.")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format.")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal console output.")
    args = parser.parse_args()

    repo_root = find_repo_root()

    try:
        res = run_checks(repo_root, quiet=args.quiet)
    except Exception as e:
        if args.json:
            print(json.dumps({"status": "failure", "error": str(e), "returncode": 1}, indent=2))
        else:
            print(f"[FAILURE] Check failed: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(res, indent=2))
    elif not args.quiet:
        print(f"[SUCCESS] kindergarten-garden mutation regression verified successfully:")
        print(f"  - Learner stub remains unsolved (0/{res['total_cases']} passed).")
        print(f"  - Reference implementation passed all {res['total_cases']}/{res['total_cases']} canonical test cases.")
        print(f"  - Documented mutant failed minimal case '{res['minimal_rejecting_case']}'.")
        print(f"  - Guidance documentation in .docs/hints.md and docs/maintenance/kindergarten-garden.md verified.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
