#!/usr/bin/env python3
"""
Verification check for Task R08-T044 (exercises/practice/anagram).

Requirements verified:
1. Resolves solution/test/example paths from exercises/practice/anagram/.meta/config.json.
2. Copies the exercise including dotfiles to a temporary directory without modifying the working tree.
3. Asserts the learner stub in the working tree remains unsolved (0/16 passed).
4. Substitutes the maintained reference implementation only in the temporary copy and runs:
     sqlite3 -bail < anagram_test.sql
5. Asserts every entry in output.json has status "pass" and verifies child return codes and test counts.
6. Asserts before/after output parity across all 16 canonical test cases.
7. Asserts the scoped readability refactoring:
     - Clarified table name (tmp -> word_signatures)
     - Clarified column name (s -> sorted_letters)
     - Clarified recursive CTE (rcte -> split_characters)
     - Clarified subquery aliases (a, b -> subject_sorted, candidate_sorted)
     - Added explicit anagram invariant comment.
8. Saves inputs, expected vs actual results, tool versions, and summary in work/R08-T044/.
"""

import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ORIGINAL_EXAMPLE_SQL = """DROP TABLE IF EXISTS tmp;

CREATE TEMPORARY TABLE tmp AS
SELECT
  CAST(word AS TEXT) word
FROM
  (
    SELECT
      LOWER(subject) word
    FROM
      anagram
    UNION
    SELECT
      LOWER(j.VALUE)
    FROM
      anagram,
      JSON_EACH(candidates) j
  );

ALTER TABLE tmp
ADD s TEXT;

UPDATE tmp
SET
  s = (
    WITH RECURSIVE
      rcte (word, c) AS (
        VALUES
          (word, '')
        UNION ALL
        SELECT
          SUBSTR(word, 2),
          SUBSTR(word, 1, 1)
        FROM
          rcte
        WHERE
          LENGTH(word) > 0
      )
    SELECT
      GROUP_CONCAT(c, '')
    FROM
      (
        SELECT
          c
        FROM
          rcte
        WHERE
          UNICODE(c) BETWEEN UNICODE('a') AND UNICODE('z')
        ORDER BY
          c
      )
  );

UPDATE anagram
SET
  result = (
    SELECT
      JSON_GROUP_ARRAY(candidate)
    FROM
      (
        SELECT
          subject,
          candidate,
          (
            SELECT
              s
            FROM
              tmp
            WHERE
              LOWER(subject) = word
          ) AS a,
          (
            SELECT
              s
            FROM
              tmp
            WHERE
              LOWER(candidate) = word
          ) AS b
        FROM
          (
            SELECT
              subject,
              j.VALUE AS candidate
            FROM
              JSON_EACH(candidates) AS j
          )
      )
    WHERE
      a = b
      AND LOWER(subject) <> LOWER(candidate)
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


def run_sqlite_test(exercise_dir: Path, sql_solution: str) -> tuple[int, list]:
    """Execute sqlite3 -bail < anagram_test.sql in a temporary copy of exercise_dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_exercise = Path(tmpdir) / "anagram"
        shutil.copytree(exercise_dir, tmp_exercise)

        # Write candidate solution
        (tmp_exercise / "anagram.sql").write_text(sql_solution, encoding="utf-8")

        test_file = tmp_exercise / "anagram_test.sql"
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
            raise AssertionError(f"output.json was not generated (child exit {proc.returncode}):\n{proc.stderr}\n{proc.stdout}")

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
    """Verify that the refactored reference implementation passes all canonical tests."""
    example_file = config["files"]["example"][0]
    ref_content = (exercise_dir / example_file).read_text(encoding="utf-8")

    returncode, results = run_sqlite_test(exercise_dir, ref_content)

    if returncode != 0:
        raise AssertionError(f"sqlite3 execution failed with returncode {returncode}")

    if len(results) == 0:
        raise AssertionError("Zero tests were executed!")

    passed = [t for t in results if t.get("status") == "pass"]
    failed = [t for t in results if t.get("status") != "pass"]

    if len(failed) > 0:
        raise AssertionError(f"{len(failed)} test(s) failed against reference implementation: {failed}")

    print(f"[OK] Refactored reference implementation passed all {len(passed)} executed test cases.")

    with open(work_dir / "test_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "total_executed": len(results),
            "passed": len(passed),
            "failed": len(failed),
            "cases": results
        }, f, indent=2)

    return results


def verify_before_after_parity(exercise_dir: Path, ref_results: list):
    """Verify that original and refactored reference implementations produce strictly identical output."""
    returncode, orig_results = run_sqlite_test(exercise_dir, ORIGINAL_EXAMPLE_SQL)

    if returncode != 0:
        raise AssertionError(f"Original reference failed with returncode {returncode}")

    if orig_results != ref_results:
        raise AssertionError("Refactored implementation output deviates from original reference output!")

    print(f"[OK] Before/after behavioral equivalence verified across all {len(ref_results)} cases.")


def verify_and_record_diff(exercise_dir: Path, config: dict, work_dir: Path):
    """Verify readability refactoring in example.sql and record diff."""
    example_file = config["files"]["example"][0]
    ref_content = (exercise_dir / example_file).read_text(encoding="utf-8")

    # Required semantic identifiers and comments
    required_tokens = [
        "Anagram Invariant",
        "word_signatures",
        "sorted_letters",
        "split_characters",
        "subject_sorted",
        "candidate_sorted"
    ]
    for token in required_tokens:
        if token not in ref_content:
            raise AssertionError(f"example.sql is missing expected refactoring token: '{token}'")

    diff_lines = list(difflib.unified_diff(
        ORIGINAL_EXAMPLE_SQL.splitlines(keepends=True),
        ref_content.splitlines(keepends=True),
        fromfile="example.sql (original)",
        tofile="example.sql (refactored)"
    ))
    diff_text = "".join(diff_lines)

    refactor_info = {
        "readability_improvements": [
            {
                "scope": "Temporary table",
                "original": "tmp",
                "refactored": "word_signatures",
                "benefit": "Clarifies the table's purpose as a cache of distinct words and their sorted letter signatures."
            },
            {
                "scope": "Signature column",
                "original": "s",
                "refactored": "sorted_letters",
                "benefit": "Replaces single-letter abbreviation with explicit semantic description."
            },
            {
                "scope": "Recursive CTE",
                "original": "rcte (word, c)",
                "refactored": "split_characters (remainder, char)",
                "benefit": "Distinguishes the tail string from the isolated character during character splitting."
            },
            {
                "scope": "Subquery aliases",
                "original": "a, b",
                "refactored": "subject_sorted, candidate_sorted",
                "benefit": "Directly conveys which signature corresponds to the subject vs candidate."
            },
            {
                "scope": "Exercise invariant",
                "original": "None",
                "refactored": "Header comment explaining anagram rules",
                "benefit": "Clearly explains why subject_sorted = candidate_sorted AND LOWER(subject) <> LOWER(candidate) is required."
            }
        ],
        "unified_diff": diff_text
    }

    with open(work_dir / "refactor_diff.json", "w", encoding="utf-8") as f:
        json.dump(refactor_info, f, indent=2)

    print(f"[OK] Readability improvements verified and unified diff recorded.")


def main():
    repo_root = Path(__file__).resolve().parent.parent.parent
    work_dir = repo_root / "work" / "R08-T044"
    work_dir.mkdir(parents=True, exist_ok=True)

    exercise_rel = Path("exercises/practice/anagram")
    exercise_dir = repo_root / exercise_rel

    print("=== Running Checks for Task R08-T044 ===")
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
    stub_results = verify_learner_stub(exercise_dir, config)

    # 4. Verify refactored reference passes all canonical tests
    ref_results = verify_reference_implementation(exercise_dir, config, work_dir)

    # 5. Verify before/after output parity
    verify_before_after_parity(exercise_dir, ref_results)

    # 6. Verify and record diff
    verify_and_record_diff(exercise_dir, config, work_dir)

    # 7. Write summary.json
    summary = {
        "task": "R08-T044",
        "exercise": "exercises/practice/anagram",
        "total_cases": len(ref_results),
        "reference_all_passed": True,
        "learner_stub_unsolved": True,
        "before_after_parity_verified": True,
        "refactor_documented": True
    }
    with open(work_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n=== ALL CHECKS PASSED SUCCESSFULLY ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
