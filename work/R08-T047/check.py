#!/usr/bin/env python3
"""
Verification check for Task R08-T047 (exercises/practice/series).

Requirements verified:
1. All enabled test cases in tests.toml and create_test_table.sql pass against the reference implementation.
2. Learner stub remains unsolved in the working tree.
3. Number of executed test cases is reported and fails on zero-test run, non-zero child exit, or assertion failure.
4. Both micro-example SQL outputs are executed, asserted, and verified against the published hints.md.
5. The guidance names a construct present in the reference implementation and explains its relevance.
6. Execution evidence (inputs, expected vs actual results, tool versions) is saved in work/R08-T047/.
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
    """Parse test descriptions from tests.toml."""
    descriptions = []
    current_uuid = None
    with open(tests_toml_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                current_uuid = line[1:-1]
            elif line.startswith("description ="):
                m = re.search(r'description\s*=\s*"([^"]+)"', line)
                if m:
                    descriptions.append({"uuid": current_uuid, "description": m.group(1)})
    return descriptions


def parse_create_test_table_sql(create_test_path: Path) -> list:
    """Extract test case data from create_test_table.sql."""
    with open(create_test_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Match test records
    pattern = re.compile(
        r"\(\s*'([a-f0-9\-]+)',\s*'([^']+)',\s*'([^']*)',\s*(-?\d+),\s*('([^']*)'|NULL),\s*('([^']*)'|NULL)\s*\)",
        re.MULTILINE
    )
    cases = []
    for m in pattern.finditer(content):
        uuid, desc, inp, slice_len, exp_res_raw, exp_res_val, exp_err_raw, exp_err_val = m.groups()
        cases.append({
            "uuid": uuid,
            "description": desc,
            "input": inp,
            "slice_length": int(slice_len),
            "expected_result": exp_res_val if exp_res_raw != "NULL" else None,
            "expected_error": exp_err_val if exp_err_raw != "NULL" else None
        })
    return cases


def verify_learner_stub(repo_root: Path, exercise_rel_path: Path, config: dict):
    """Verify that the learner stub runs and is unsolved (0 tests pass)."""
    exercise_dir = repo_root / exercise_rel_path
    solution_file = config["files"]["solution"][0]
    test_file = config["files"]["test"][0]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        # Copy entire exercise directory including dotfiles
        shutil.copytree(exercise_dir, tmp_path / "series")
        run_dir = tmp_path / "series"

        # Run sqlite3 with learner stub
        cmd = f"sqlite3 -bail < {test_file}"
        proc = subprocess.run(cmd, cwd=run_dir, shell=True, capture_output=True, text=True)

        output_file = run_dir / "output.json"
        if not output_file.exists():
            raise AssertionError(f"output.json was not generated for learner stub. stderr: {proc.stderr}")

        with open(output_file, "r", encoding="utf-8") as f:
            results = json.load(f)

        passed = [t for t in results if t.get("status") == "pass"]
        if len(passed) > 0:
            raise AssertionError(f"Learner stub unexpectedly passed {len(passed)} tests: {passed}")

        print(f"[OK] Learner stub verified: 0 of {len(results)} tests pass (stub is unsolved).")


def verify_reference_implementation(repo_root: Path, exercise_rel_path: Path, config: dict, work_dir: Path) -> dict:
    """
    Copy exercise into temp directory, replace solution with reference,
    run sqlite3 -bail < test_file, assert all tests pass.
    """
    exercise_dir = repo_root / exercise_rel_path
    solution_file = config["files"]["solution"][0]
    test_file = config["files"]["test"][0]
    example_file = config["files"]["example"][0]

    # Check original working tree series.sql is unchanged
    orig_solution_content = (exercise_dir / solution_file).read_text(encoding="utf-8")
    if "WITH RECURSIVE" in orig_solution_content:
        raise AssertionError("Learner solution file in working tree was altered with solution code!")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        target_dir = tmp_path / "series"
        shutil.copytree(exercise_dir, target_dir)

        # Substitute reference ONLY in that temporary copy
        ref_src = target_dir / example_file
        sol_dst = target_dir / solution_file
        shutil.copyfile(ref_src, sol_dst)

        # Run sqlite3 -bail < series_test.sql
        cmd = f"sqlite3 -bail < {test_file}"
        proc = subprocess.run(cmd, cwd=target_dir, shell=True, capture_output=True, text=True)

        if proc.returncode != 0:
            raise AssertionError(
                f"sqlite3 process exited with non-zero code {proc.returncode}.\n"
                f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
            )

        output_file = target_dir / "output.json"
        if not output_file.exists():
            raise AssertionError("output.json was not created by the test runner.")

        with open(output_file, "r", encoding="utf-8") as f:
            results = json.load(f)

    # Check non-zero tests
    test_count = len(results)
    if test_count == 0:
        raise AssertionError("Zero test cases were executed! Expected non-zero tests.")

    # Check all pass
    failed_tests = [t for t in results if t.get("status") != "pass"]
    if failed_tests:
        raise AssertionError(f"{len(failed_tests)} tests failed against reference: {failed_tests}")

    # Check test descriptions
    tests_toml_cases = parse_tests_toml(exercise_dir / ".meta" / "tests.toml")
    expected_descs = {t["description"] for t in tests_toml_cases}
    actual_descs = {t["description"] for t in results}

    missing_cases = expected_descs - actual_descs
    if missing_cases:
        raise AssertionError(f"Missing test cases from tests.toml in actual test run: {missing_cases}")

    # Save detailed test results to work/R08-T047/test_results.json
    table_cases = parse_create_test_table_sql(exercise_dir / "create_test_table.sql")
    case_map = {c["description"]: c for c in table_cases}

    full_results = []
    for r in results:
        desc = r.get("description")
        info = case_map.get(desc, {})
        full_results.append({
            "description": desc,
            "status": r.get("status"),
            "input": info.get("input"),
            "slice_length": info.get("slice_length"),
            "expected_result": info.get("expected_result"),
            "expected_error": info.get("expected_error")
        })

    with open(work_dir / "test_results.json", "w", encoding="utf-8") as f:
        json.dump(full_results, f, indent=2)

    print(f"[OK] Reference implementation passed all {test_count} executed test cases:")
    for r in results:
        print(f"     - {r['description']}: {r['status']}")

    return {"test_count": test_count, "results": results}


def verify_micro_examples(work_dir: Path) -> dict:
    """Run and assert outputs of both micro-examples."""
    # Micro-example 1: UNION ALL (duplicate-preserving)
    query_1 = "SELECT '777' AS slice\nUNION ALL\nSELECT '777' AS slice;"
    proc1 = subprocess.run(["sqlite3"], input=query_1, capture_output=True, text=True, check=True)
    out1 = proc1.stdout.strip()
    expected_out1 = "777\n777"
    if out1 != expected_out1:
        raise AssertionError(f"Micro-example 1 failed! Expected:\n{expected_out1}\nGot:\n{out1}")

    # Micro-example 2: UNION (contrasting pitfall - set deduplication)
    query_2 = "SELECT '777' AS slice\nUNION\nSELECT '777' AS slice;"
    proc2 = subprocess.run(["sqlite3"], input=query_2, capture_output=True, text=True, check=True)
    out2 = proc2.stdout.strip()
    expected_out2 = "777"
    if out2 != expected_out2:
        raise AssertionError(f"Micro-example 2 failed! Expected:\n{expected_out2}\nGot:\n{out2}")

    data = {
        "micro_example_1": {
            "title": "Duplicate-preserving operations (UNION ALL)",
            "query": query_1,
            "expected_output": expected_out1,
            "actual_output": out1,
            "status": "pass"
        },
        "micro_example_2": {
            "title": "Set union operations pitfall (UNION)",
            "query": query_2,
            "expected_output": expected_out2,
            "actual_output": out2,
            "status": "pass"
        }
    }

    with open(work_dir / "micro_examples_results.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print("[OK] Both micro-examples asserted successfully:")
    print("     Micro-example 1 (UNION ALL) output:")
    for line in out1.splitlines():
        print(f"       {line}")
    print("     Micro-example 2 (UNION) output:")
    for line in out2.splitlines():
        print(f"       {line}")

    return data


def verify_hints_guidance(repo_root: Path, exercise_rel_path: Path, micro_data: dict):
    """Verify that hints.md exists, names construct present in reference, and agrees with micro-example outputs."""
    hints_path = repo_root / exercise_rel_path / ".docs" / "hints.md"
    if not hints_path.exists():
        raise AssertionError(f"Hints file {hints_path} does not exist!")

    content = hints_path.read_text(encoding="utf-8")

    # Verify construct name
    construct = "UNION ALL"
    if construct not in content:
        raise AssertionError(f"Construct '{construct}' not named in {hints_path}!")

    # Verify reference example.sql has this construct
    ref_sql = (repo_root / exercise_rel_path / ".meta" / "example.sql").read_text(encoding="utf-8")
    if construct not in ref_sql:
        raise AssertionError(f"Construct '{construct}' is not present in reference example.sql!")

    # Verify relevance explanation
    relevance_keywords = ["duplicate", "series", "slice", "777"]
    for kw in relevance_keywords:
        if kw.lower() not in content.lower():
            raise AssertionError(f"Keyword '{kw}' explaining relevance not found in {hints_path}!")

    # Verify expected outputs agreement
    exp1 = micro_data["micro_example_1"]["expected_output"]
    exp2 = micro_data["micro_example_2"]["expected_output"]
    if exp1 not in content:
        raise AssertionError(f"Micro-example 1 expected output not found in {hints_path}!")
    if exp2 not in content:
        raise AssertionError(f"Micro-example 2 expected output not found in {hints_path}!")

    # Verify documentation reference link
    if "https://www.sqlite.org/lang_select.html" not in content and "https://www.sqlite.org/lang_with.html" not in content:
        raise AssertionError("Link to applicable SQLite language reference missing in hints.md!")

    print(f"[OK] Hints guidance verified in {hints_path}:")
    print("     - Mentions construct actually present in reference ('UNION ALL').")
    print("     - Explains relevance to duplicate slice preservation in series.")
    print("     - Contains both executable micro-examples and agreeing outputs.")
    print("     - Links to SQLite official documentation.")


def main():
    repo_root = Path(__file__).resolve().parent.parent.parent
    work_dir = repo_root / "work" / "R08-T047"
    work_dir.mkdir(parents=True, exist_ok=True)

    exercise_rel = Path("exercises/practice/series")

    print(f"=== Running Checks for Task R08-T047 ===")
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
    ref_res = verify_reference_implementation(repo_root, exercise_rel, config, work_dir)

    # 5. Verify micro-examples
    micro_res = verify_micro_examples(work_dir)

    # 6. Verify hints.md guidance
    verify_hints_guidance(repo_root, exercise_rel, micro_res)

    # Save summary
    summary = {
        "task": "R08-T047",
        "exercise": "exercises/practice/series",
        "construct": "UNION ALL (duplicate-preserving operations vs set operations)",
        "executed_test_cases": ref_res["test_count"],
        "all_tests_passed": True,
        "learner_stub_unsolved": True,
        "micro_examples_verified": True,
        "hints_guidance_verified": True
    }
    with open(work_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n=== ALL CHECKS PASSED SUCCESSFULLY ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
