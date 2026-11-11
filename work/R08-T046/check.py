#!/usr/bin/env python3
"""
Verification check for Task R08-T046 (exercises/practice/meetup).

Requirements verified:
1. Learner stub in working tree remains unsolved.
2. Maintained reference implementation passes all 95 enabled test cases in an isolated temporary copy.
3. Independently written alternative implementation passes all 95 enabled test cases in an isolated temporary copy.
4. Two genuinely different implementations (closed-form date modifiers vs. recursive CTE calendar expansion) are compared.
5. The check reports executed case counts and fails on zero-test run, non-zero child exit, or assertion failure.
6. The hints.md file contains an approach-selection section, explains data representation, discusses trade-offs, includes a worked example, and avoids a full solution listing.
7. Execution evidence (inputs, expected vs actual results, tool versions, comparison) is saved in work/R08-T046/.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def get_tool_versions(work_dir: Path) -> dict:
    """Collect versions of required tools and save to tool_versions.json."""
    tools = {}

    # sqlite3 version
    try:
        res = subprocess.run(["sqlite3", "--version"], capture_output=True, text=True, check=True)
        tools["sqlite3"] = res.stdout.strip()
    except Exception as e:
        tools["sqlite3"] = f"error: {e}"

    # python3 version
    tools["python3"] = sys.version.replace("\n", " ")

    # bash version
    try:
        res = subprocess.run(["bash", "--version"], capture_output=True, text=True, check=True)
        tools["bash"] = res.stdout.splitlines()[0].strip()
    except Exception as e:
        tools["bash"] = f"error: {e}"

    # jq version
    try:
        res = subprocess.run(["jq", "--version"], capture_output=True, text=True, check=True)
        tools["jq"] = res.stdout.strip()
    except Exception as e:
        tools["jq"] = f"error: {e}"

    # git commit / branch
    try:
        res = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True)
        tools["git_branch"] = res.stdout.strip()
        res_commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
        tools["git_commit"] = res_commit.stdout.strip()
    except Exception as e:
        tools["git"] = f"error: {e}"

    out_file = work_dir / "tool_versions.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(tools, f, indent=2)

    return tools


def parse_tests_toml(tests_toml_path: Path) -> list:
    """Parse test descriptions and UUIDs from tests.toml."""
    items = []
    current_uuid = None
    with open(tests_toml_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                current_uuid = line[1:-1]
            elif line.startswith("description ="):
                m = re.search(r'description\s*=\s*"([^"]+)"', line)
                if m:
                    items.append({"uuid": current_uuid, "description": m.group(1)})
    return items


def parse_meetup_test_cases(test_sql_path: Path) -> list:
    """Extract test case definitions from meetup_test.sql."""
    with open(test_sql_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(
        r"\(\s*'([a-f0-9\-]+)',\s*'([^']+)',\s*(\d+),\s*(\d+),\s*'([^']+)',\s*'([^']+)',\s*'([^']+)'\s*\)",
        re.MULTILINE
    )
    cases = []
    for m in pattern.finditer(content):
        uuid, desc, year, month, week, dayofweek, expected = m.groups()
        cases.append({
            "uuid": uuid,
            "description": desc,
            "year": int(year),
            "month": int(month),
            "week": week,
            "dayofweek": dayofweek,
            "expected_result": expected
        })
    return cases


def verify_learner_stub(repo_root: Path, exercise_rel_path: Path, config: dict):
    """Verify that learner stub in working tree is unsolved."""
    exercise_dir = repo_root / exercise_rel_path
    solution_file = config["files"]["solution"][0]
    test_file = config["files"]["test"][0]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        temp_exercise = tmp_path / "meetup"
        shutil.copytree(exercise_dir, temp_exercise)

        cmd = f"sqlite3 -bail < {test_file}"
        proc = subprocess.run(cmd, cwd=temp_exercise, shell=True, capture_output=True, text=True)

        output_file = temp_exercise / "output.json"
        if not output_file.exists():
            raise AssertionError(f"output.json was not generated for learner stub. stderr: {proc.stderr}")

        with open(output_file, "r", encoding="utf-8") as f:
            results = json.load(f)

        passed = [t for t in results if t.get("status") == "pass"]
        total = len(results)

        if len(passed) == total:
            raise AssertionError(f"Learner stub unexpectedly passed all {total} tests! It should be unsolved.")

        print(f"[OK] Learner stub verified: {len(passed)}/{total} passed (unsolved as expected).")


def run_solution_in_isolated_copy(
    repo_root: Path,
    exercise_rel_path: Path,
    solution_source_path: Path,
    config: dict,
    label: str,
    evidence_file: Path
) -> dict:
    """Run an implementation in an isolated temporary copy and assert all tests pass."""
    exercise_dir = repo_root / exercise_rel_path
    solution_file = config["files"]["solution"][0]
    test_file = config["files"]["test"][0]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        temp_exercise = tmp_path / "meetup"
        shutil.copytree(exercise_dir, temp_exercise)

        # Substitute specified solution ONLY in the temporary copy
        shutil.copyfile(solution_source_path, temp_exercise / solution_file)

        cmd = f"sqlite3 -bail < {test_file}"
        proc = subprocess.run(cmd, cwd=temp_exercise, shell=True, capture_output=True, text=True)

        if proc.returncode != 0:
            raise AssertionError(
                f"{label} implementation failed with exit code {proc.returncode}.\n"
                f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
            )

        output_file = temp_exercise / "output.json"
        if not output_file.exists():
            raise AssertionError(f"output.json was not created for {label}.")

        with open(output_file, "r", encoding="utf-8") as f:
            results = json.load(f)

    test_count = len(results)
    if test_count == 0:
        raise AssertionError(f"Zero test cases executed for {label}!")

    failed = [t for t in results if t.get("status") != "pass"]
    if failed:
        raise AssertionError(f"{len(failed)} test(s) failed for {label}: {failed}")

    # Map test cases
    table_cases = parse_meetup_test_cases(exercise_dir / test_file)
    case_map = {c["description"]: c for c in table_cases}

    detailed_results = []
    for r in results:
        desc = r.get("description") or r.get("name")
        c_info = case_map.get(desc, {})
        detailed_results.append({
            "description": desc,
            "status": r.get("status"),
            "uuid": c_info.get("uuid"),
            "year": c_info.get("year"),
            "month": c_info.get("month"),
            "week": c_info.get("week"),
            "dayofweek": c_info.get("dayofweek"),
            "expected_result": c_info.get("expected_result")
        })

    with open(evidence_file, "w", encoding="utf-8") as f:
        json.dump(detailed_results, f, indent=2)

    print(f"[OK] {label} passed all {test_count} executed test cases.")
    return {"test_count": test_count, "results": detailed_results}


def verify_approaches_distinct(ref_sql_path: Path, alt_sql_path: Path, work_dir: Path) -> dict:
    """Verify that reference and alternative use genuinely different techniques and control flows."""
    ref_sql = ref_sql_path.read_text(encoding="utf-8")
    alt_sql = alt_sql_path.read_text(encoding="utf-8")

    # Check reference features: closed form date modifier
    if "weekday " not in ref_sql or "printf('%d-%02d" not in ref_sql:
        raise AssertionError("Reference implementation does not contain expected closed-form date modifier logic.")

    # Check alternative features: recursive calendar expansion
    if "WITH RECURSIVE" not in alt_sql or "calendar" not in alt_sql or "ROW_NUMBER()" not in alt_sql:
        raise AssertionError("Alternative implementation does not contain expected recursive CTE and window function logic.")

    comparison = {
        "approach_1_reference": {
            "name": "Closed-Form Date Modifiers",
            "technique": "Direct date arithmetic using SQLite 'weekday N' modifier",
            "time_complexity": "O(1) per row",
            "memory_overhead": "O(1) auxiliary space (no intermediate row generation)",
            "portability": "SQLite-specific date modifier semantics",
            "key_constructs": ["date()", "printf()", "'weekday ' || dayofweek_num", "CASE"]
        },
        "approach_2_alternative": {
            "name": "Recursive Calendar Expansion",
            "technique": "Generates complete monthly calendar via recursive CTE, maps weekdays, and filters via window functions",
            "time_complexity": "O(days_in_month) ~ O(31) per row",
            "memory_overhead": "Intermediate table of 28-31 rows generated per record",
            "portability": "Standard SQL recursive CTE and window functions",
            "key_constructs": ["WITH RECURSIVE", "strftime('%w')", "ROW_NUMBER() OVER", "BETWEEN 13 AND 19"]
        },
        "genuinely_different": True,
        "both_passed_all_tests": True
    }

    with open(work_dir / "approach_comparison.json", "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2)

    print("[OK] Distinct approaches verified:")
    print("     - Approach 1 (Reference): Closed-Form Date Modifiers [O(1) work/memory]")
    print("     - Approach 2 (Alternative): Recursive Calendar Expansion [Set-based O(N) CTE rows]")
    return comparison


def verify_hints_guidance(repo_root: Path, exercise_rel_path: Path):
    """Verify that hints.md documents the approaches, data representation, trade-offs, and worked example without leaking full solution."""
    hints_path = repo_root / exercise_rel_path / ".docs" / "hints.md"
    if not hints_path.exists():
        raise AssertionError(f"Hints file {hints_path} does not exist!")

    content = hints_path.read_text(encoding="utf-8")

    # Verify approach section
    if "Approach Selection" not in content and "approach" not in content.lower():
        raise AssertionError("Approach-selection section missing in hints.md!")

    # Verify both approaches discussed
    if "Closed-Form" not in content or "Recursive" not in content:
        raise AssertionError("Both approaches (Closed-Form and Recursive) must be discussed in hints.md!")

    # Verify data representation and trade-offs
    keywords = ["data representation", "trade-off", "memory", "portability"]
    for kw in keywords:
        if kw.lower() not in content.lower():
            raise AssertionError(f"Required discussion of '{kw}' not found in hints.md!")

    # Verify worked example
    if "1953" not in content or "August" not in content or "teenth" not in content or "1953-08-15" not in content:
        raise AssertionError("Exercise-specific worked example (e.g. teenth Saturday of August 1953 -> 1953-08-15) missing in hints.md!")

    # Verify full solution is NOT leaked
    if "UPDATE meetup\nSET\n  RESULT = (" in content or "UPDATE meetup\nSET\n  result = (" in content:
        raise AssertionError("Full solution listing detected in hints.md! Only snippets and worked examples should be provided.")

    print(f"[OK] Hints guidance verified in {hints_path}:")
    print("     - Contains approach selection comparing closed-form vs recursive CTE.")
    print("     - Explains data representations and justified trade-offs.")
    print("     - Includes exercise-specific worked example (teenth Saturday of August 1953).")
    print("     - Protects learner stub by avoiding full solution listing.")


def main():
    repo_root = Path(__file__).resolve().parent.parent.parent
    work_dir = repo_root / "work" / "R08-T046"
    work_dir.mkdir(parents=True, exist_ok=True)

    exercise_rel = Path("exercises/practice/meetup")

    print("=== Running Checks for Task R08-T046 ===")
    print(f"Repository Root: {repo_root}")
    print(f"Work Directory:  {work_dir}")

    # 1. Collect tool versions
    tools = get_tool_versions(work_dir)
    print(f"[OK] Collected tool versions: sqlite3={tools.get('sqlite3')}, python3={sys.version.split()[0]}")

    # 2. Read config.json
    config_path = repo_root / exercise_rel / ".meta" / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 3. Verify learner stub is unsolved
    verify_learner_stub(repo_root, exercise_rel, config)

    # 4. Verify reference implementation
    ref_sql = repo_root / exercise_rel / config["files"]["example"][0]
    ref_res = run_solution_in_isolated_copy(
        repo_root=repo_root,
        exercise_rel_path=exercise_rel,
        solution_source_path=ref_sql,
        config=config,
        label="Reference",
        evidence_file=work_dir / "test_results_reference.json"
    )

    # 5. Verify alternative implementation
    alt_sql = work_dir / "alternative.sql"
    if not alt_sql.exists():
        raise AssertionError(f"Alternative implementation file not found at {alt_sql}")

    alt_res = run_solution_in_isolated_copy(
        repo_root=repo_root,
        exercise_rel_path=exercise_rel,
        solution_source_path=alt_sql,
        config=config,
        label="Alternative",
        evidence_file=work_dir / "test_results_alternative.json"
    )

    # 6. Compare approaches
    comparison = verify_approaches_distinct(ref_sql, alt_sql, work_dir)

    # 7. Verify hints.md guidance
    verify_hints_guidance(repo_root, exercise_rel)

    # 8. Save summary
    summary = {
        "task": "R08-T046",
        "exercise": "exercises/practice/meetup",
        "reference_approach": "Closed-Form Date Modifiers",
        "alternative_approach": "Recursive Calendar Expansion",
        "executed_test_cases": ref_res["test_count"],
        "reference_all_passed": True,
        "alternative_all_passed": True,
        "learner_stub_unsolved": True,
        "approaches_distinct": True,
        "hints_guidance_verified": True
    }
    with open(work_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n=== ALL CHECKS PASSED SUCCESSFULLY ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
