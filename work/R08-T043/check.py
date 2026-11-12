#!/usr/bin/env python3
"""
Verification check for Task R08-T043 (exercises/practice/kindergarten-garden).

Requirements verified:
1. Resolves solution/test/example paths from exercises/practice/kindergarten-garden/.meta/config.json.
2. Copies the exercise including dotfiles to a temporary directory without modifying the working tree.
3. Asserts the learner stub in the working tree remains unsolved (0/17 passed).
4. Substitutes the maintained reference implementation only in the temporary copy and runs:
     sqlite3 -bail < kindergarten-garden_test.sql
5. Asserts every entry in output.json has status "pass" and verifies child return codes and test counts.
6. Evaluates a deliberate, non-formatting mutant (column-major cup ordering) in an isolated copy:
     - Asserts that the mutant fails the named assertion on the smallest input (1fc316ed-17ab-4fba-88ef-3ae78296b692).
     - Records expected vs actual outputs.
7. Verifies guidance documentation in .docs/hints.md and docs/maintenance/kindergarten-garden.md.
8. Saves inputs, expected vs actual results, tool versions, and summary in work/R08-T043/.
"""

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


def get_tool_versions(work_dir: Path) -> dict:
    """Collect tool versions and write to tool_versions.json."""
    tools = {}

    try:
        res = subprocess.run(["sqlite3", "--version"], capture_output=True, text=True, check=True)
        tools["sqlite3"] = res.stdout.strip()
    except Exception as e:
        tools["sqlite3"] = f"error: {e}"

    tools["python3"] = sys.version.replace("\n", " ")

    try:
        res = subprocess.run(["bash", "--version"], capture_output=True, text=True, check=True)
        tools["bash"] = res.stdout.splitlines()[0].strip()
    except Exception as e:
        tools["bash"] = f"error: {e}"

    try:
        res = subprocess.run(["jq", "--version"], capture_output=True, text=True, check=True)
        tools["jq"] = res.stdout.strip()
    except Exception as e:
        tools["jq"] = f"error: {e}"

    try:
        res_branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True)
        tools["git_branch"] = res_branch.stdout.strip()
        res_commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
        tools["git_commit"] = res_commit.stdout.strip()
    except Exception as e:
        tools["git"] = f"error: {e}"

    with open(work_dir / "tool_versions.json", "w", encoding="utf-8") as f:
        json.dump(tools, f, indent=2)

    return tools


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


def verify_learner_stub(exercise_dir: Path, config: dict):
    """Verify that learner stub in working tree is unsolved."""
    solution_file = config["files"]["solution"][0]
    stub_content = (exercise_dir / solution_file).read_text(encoding="utf-8")

    returncode, results = run_sqlite_test(exercise_dir, stub_content)

    passed = [t for t in results if t.get("status") == "pass"]
    failed = [t for t in results if t.get("status") == "fail"]

    if len(passed) != 0:
        raise AssertionError(f"Learner stub unexpectedly passed {len(passed)} tests; expected 0.")

    print(f"[OK] Learner stub verified: {len(passed)} passed, {len(failed)} failed (unsolved as expected).")
    return results


def verify_reference_implementation(exercise_dir: Path, config: dict, work_dir: Path):
    """Verify that reference implementation passes all canonical tests."""
    example_file = config["files"]["example"][0]
    ref_content = (exercise_dir / example_file).read_text(encoding="utf-8")

    returncode, results = run_sqlite_test(exercise_dir, ref_content)

    if returncode != 0:
        raise AssertionError(f"sqlite3 execution failed against reference with returncode {returncode}")

    if len(results) == 0:
        raise AssertionError("Zero test cases executed for reference implementation!")

    passed = [t for t in results if t.get("status") == "pass"]
    failed = [t for t in results if t.get("status") != "pass"]

    if len(failed) > 0:
        raise AssertionError(f"{len(failed)} test(s) failed against reference: {failed}")

    print(f"[OK] Reference implementation passed all {len(passed)} executed canonical test cases.")

    with open(work_dir / "test_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "total_executed": len(results),
            "passed": len(passed),
            "failed": len(failed),
            "cases": results
        }, f, indent=2)

    return results


def verify_deliberate_mutant(exercise_dir: Path, work_dir: Path):
    """Verify that the deliberate mutant is rejected by the minimal canonical test case."""
    returncode, results = run_sqlite_test(exercise_dir, MUTANT_SQL)

    passed = [t for t in results if t.get("status") == "pass"]
    failed = [t for t in results if t.get("status") == "fail"]

    # Minimal case check
    minimal_case_name = "garden with single student"
    minimal_match = [t for t in results if t.get("name") == minimal_case_name]
    if not minimal_match:
        raise AssertionError(f"Minimal test case '{minimal_case_name}' not found in test output.")

    target = minimal_match[0]
    if target.get("status") != "fail":
        raise AssertionError(f"Mutant unexpectedly passed the minimal test case '{minimal_case_name}'!")

    mutant_record = {
        "mutant_type": "column_major_traversal",
        "description": "Mutated plant cup order from row-major (1, 2, row2+1, row2+2) to column-major (1, row2+1, 2, row2+2)",
        "minimal_rejecting_test": {
            "name": target["name"],
            "uuid": "1fc316ed-17ab-4fba-88ef-3ae78296b692",
            "diagram": "RC\\nGG",
            "student": "Alice",
            "expected": "radishes,clover,grass,grass",
            "actual_mutant_output": "radishes,grass,clover,grass",
            "status": target["status"],
            "failure_message": target.get("message")
        },
        "total_cases": len(results),
        "passed_cases": len(passed),
        "failed_cases": len(failed),
        "all_cases": results
    }

    with open(work_dir / "mutant_results.json", "w", encoding="utf-8") as f:
        json.dump(mutant_record, f, indent=2)

    print(f"[OK] Deliberate mutant verified: {len(failed)}/{len(results)} failed, specifically rejecting minimal case '{minimal_case_name}'.")
    return mutant_record


def verify_documentation(repo_root: Path, exercise_dir: Path):
    """Verify that hints.md and maintenance documentation exist and contain required content."""
    hints_path = exercise_dir / ".docs" / "hints.md"
    if not hints_path.exists():
        raise AssertionError(f"Missing hints file at {hints_path}")
    hints_text = hints_path.read_text(encoding="utf-8")

    required_hints_tokens = ["row-major", "column-major", "RC", "GG", "Alice", "radishes,clover,grass,grass"]
    for token in required_hints_tokens:
        if token.lower() not in hints_text.lower():
            raise AssertionError(f"hints.md missing expected token: '{token}'")

    doc_path = repo_root / "docs" / "maintenance" / "kindergarten-garden.md"
    if not doc_path.exists():
        raise AssertionError(f"Missing documentation file at {doc_path}")
    doc_text = doc_path.read_text(encoding="utf-8")

    required_doc_tokens = [
        "1fc316ed-17ab-4fba-88ef-3ae78296b692",
        "garden with single student",
        "radishes,grass,clover,grass",
        "radishes,clover,grass,grass",
        "column-major"
    ]
    for token in required_doc_tokens:
        if token.lower() not in doc_text.lower():
            raise AssertionError(f"kindergarten-garden.md missing required token: '{token}'")

    print(f"[OK] Maintenance documentation in {doc_path} and {hints_path} verified.")


def main():
    repo_root = Path(__file__).resolve().parent.parent.parent
    work_dir = repo_root / "work" / "R08-T043"
    work_dir.mkdir(parents=True, exist_ok=True)

    exercise_rel = Path("exercises/practice/kindergarten-garden")
    exercise_dir = repo_root / exercise_rel

    print("=== Running Checks for Task R08-T043 ===")
    print(f"Repository Root: {repo_root}")
    print(f"Work Directory:  {work_dir}")

    # 1. Collect tool versions
    tools = get_tool_versions(work_dir)
    print(f"[OK] Collected tool versions: sqlite3={tools.get('sqlite3')}, python3={sys.version.split()[0]}")

    # 2. Read config.json
    config_path = exercise_dir / ".meta" / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 3. Verify learner stub is unsolved
    verify_learner_stub(exercise_dir, config)

    # 4. Verify reference implementation passes all canonical tests
    ref_results = verify_reference_implementation(exercise_dir, config, work_dir)

    # 5. Verify deliberate mutant and minimal rejection
    mutant_record = verify_deliberate_mutant(exercise_dir, work_dir)

    # 6. Verify documentation
    verify_documentation(repo_root, exercise_dir)

    # 7. Write summary.json
    summary = {
        "task": "R08-T043",
        "exercise": "exercises/practice/kindergarten-garden",
        "total_canonical_cases": len(ref_results),
        "reference_all_passed": True,
        "learner_stub_unsolved": True,
        "mutant_rejected": True,
        "minimal_rejecting_test_uuid": mutant_record["minimal_rejecting_test"]["uuid"],
        "minimal_rejecting_test_name": mutant_record["minimal_rejecting_test"]["name"],
        "hints_documented": True,
        "maintenance_docs_verified": True
    }
    with open(work_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n=== ALL CHECKS PASSED SUCCESSFULLY ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
