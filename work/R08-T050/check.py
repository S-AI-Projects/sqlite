#!/usr/bin/env python3
"""
Verification check for Task R08-T050 (exercises/practice/hello-world).

Requirements verified:
1. Resolves solution/test/example paths from exercises/practice/hello-world/.meta/config.json.
2. Copies the exercise including dotfiles to a temporary directory without modifying the working tree.
3. Asserts the learner stub in the working tree remains unsolved (0/1 passed).
4. Substitutes the maintained reference implementation only in the temporary copy and runs:
     sqlite3 -bail < hello-world_test.sql
5. Asserts every entry in output.json has status "pass" and verifies child return codes and test counts.
6. Executes a decision table covering subtle contract cases (case sensitivity, punctuation, null values)
   and verifies expected outcomes.
7. Verifies guidance documentation in .docs/hints.md and docs/maintenance/hello-world.md.
8. Saves inputs, expected vs actual results, tool versions, and summary in work/R08-T050/.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


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


def run_sqlite_test(exercise_dir: Path, sql_statement: str) -> tuple[int, list]:
    """Execute hello-world_test.sql in a temporary copy of exercise_dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_exercise = Path(tmpdir) / "hello-world"
        shutil.copytree(exercise_dir, tmp_exercise)

        (tmp_exercise / "hello-world.sql").write_text(sql_statement, encoding="utf-8")

        test_file = tmp_exercise / "hello-world_test.sql"
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
    """Verify that reference implementation passes all canonical tests."""
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

    print(f"[OK] Reference implementation passed all {len(passed)} executed test cases.")

    with open(work_dir / "test_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "total_executed": len(results),
            "passed": len(passed),
            "failed": len(failed),
            "cases": results
        }, f, indent=2)

    return results


def verify_decision_table(exercise_dir: Path, work_dir: Path):
    """Run decision table test cases covering specified and unspecified contract conditions."""
    decision_table_cases = [
        {
            "case": "canonical_solution",
            "sql": "INSERT INTO hello_world (greeting) VALUES ('Hello, World!');",
            "inserted_value": "Hello, World!",
            "expected_status": "pass",
            "contract_rule": "Exact string literal specified by canonical problem specification."
        },
        {
            "case": "unsolved_stub_default",
            "sql": "INSERT INTO hello_world (greeting) VALUES ('Goodbye, Mars!');",
            "inserted_value": "Goodbye, Mars!",
            "expected_status": "fail",
            "contract_rule": "Default stub greeting differs from target string."
        },
        {
            "case": "lowercase_mismatch",
            "sql": "INSERT INTO hello_world (greeting) VALUES ('hello, world!');",
            "inserted_value": "hello, world!",
            "expected_status": "fail",
            "contract_rule": "SQLite binary collation requires exact character case match."
        },
        {
            "case": "missing_comma",
            "sql": "INSERT INTO hello_world (greeting) VALUES ('Hello World!');",
            "inserted_value": "Hello World!",
            "expected_status": "fail",
            "contract_rule": "Punctuation mismatch fails string equality."
        },
        {
            "case": "missing_exclamation",
            "sql": "INSERT INTO hello_world (greeting) VALUES ('Hello, World');",
            "inserted_value": "Hello, World",
            "expected_status": "fail",
            "contract_rule": "Missing trailing punctuation fails string equality."
        },
        {
            "case": "extra_whitespace",
            "sql": "INSERT INTO hello_world (greeting) VALUES (' Hello, World! ');",
            "inserted_value": " Hello, World! ",
            "expected_status": "fail",
            "contract_rule": "Leading/trailing whitespace fails exact character match."
        },
        {
            "case": "null_greeting",
            "sql": "INSERT INTO hello_world (greeting) VALUES (NULL);",
            "inserted_value": None,
            "expected_status": "fail",
            "contract_rule": "NULL comparison yields NULL, failing the WHERE filter."
        }
    ]

    results_record = []
    for entry in decision_table_cases:
        returncode, results = run_sqlite_test(exercise_dir, entry["sql"])
        actual_status = results[0].get("status") if results else "error"
        if actual_status != entry["expected_status"]:
            raise AssertionError(f"Decision table case '{entry['case']}' failed: expected {entry['expected_status']}, got {actual_status}")

        results_record.append({
            "case": entry["case"],
            "sql": entry["sql"],
            "inserted_value": entry["inserted_value"],
            "expected_status": entry["expected_status"],
            "actual_status": actual_status,
            "verified": True,
            "contract_rule": entry["contract_rule"]
        })

    print(f"[OK] Decision table verified: {len(results_record)} contract conditions asserted successfully.")

    with open(work_dir / "decision_table_results.json", "w", encoding="utf-8") as f:
        json.dump(results_record, f, indent=2)

    return results_record


def verify_documentation(repo_root: Path, exercise_dir: Path):
    """Verify that hints.md and maintenance documentation exist and contain required content."""
    hints_path = exercise_dir / ".docs" / "hints.md"
    if not hints_path.exists():
        raise AssertionError(f"Missing {hints_path}")
    hints_text = hints_path.read_text(encoding="utf-8")

    required_hints_tokens = ["Decision Table", "Unspecified Behavior", "af9ffe10-dc13-42d8-a742-e7bdafac449d", "Say Hi!"]
    for token in required_hints_tokens:
        if token not in hints_text:
            raise AssertionError(f"hints.md missing expected token: '{token}'")

    doc_path = repo_root / "docs" / "maintenance" / "hello-world.md"
    if not doc_path.exists():
        raise AssertionError(f"Missing {doc_path}")
    doc_text = doc_path.read_text(encoding="utf-8")

    required_doc_tokens = ["Decision Table", "Specified vs. Unspecified", "BINARY", "af9ffe10-dc13-42d8-a742-e7bdafac449d"]
    for token in required_doc_tokens:
        if token not in doc_text:
            raise AssertionError(f"hello-world.md missing expected token: '{token}'")

    print(f"[OK] Guidance documentation in {hints_path} and {doc_path} verified.")


def main():
    repo_root = Path(__file__).resolve().parent.parent.parent
    work_dir = repo_root / "work" / "R08-T050"
    work_dir.mkdir(parents=True, exist_ok=True)

    exercise_rel = Path("exercises/practice/hello-world")
    exercise_dir = repo_root / exercise_rel

    print("=== Running Checks for Task R08-T050 ===")
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

    # 4. Verify reference implementation passes
    ref_results = verify_reference_implementation(exercise_dir, config, work_dir)

    # 5. Verify contract decision table
    decision_results = verify_decision_table(exercise_dir, work_dir)

    # 6. Verify documentation
    verify_documentation(repo_root, exercise_dir)

    # 7. Write summary.json
    summary = {
        "task": "R08-T050",
        "exercise": "exercises/practice/hello-world",
        "canonical_cases_count": len(ref_results),
        "reference_all_passed": True,
        "learner_stub_unsolved": True,
        "decision_table_cases_verified": len(decision_results),
        "hints_documented": True,
        "maintenance_docs_verified": True
    }
    with open(work_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n=== ALL CHECKS PASSED SUCCESSFULLY ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
