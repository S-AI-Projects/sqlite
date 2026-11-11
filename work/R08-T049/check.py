#!/usr/bin/env python3
"""
Automated verification check for Task R08-T049 (exercises/practice/leap).

Requirements verified:
1. All enabled test cases in tests.toml and leap_test.sql pass against the reference implementation in an isolated copy.
2. Learner stub remains unsolved in the working tree.
3. The check reports the number of executed cases and fails on zero-test run, non-zero child exit, or assertion failure.
4. The isolated runner tools/course_checks/r08-t049.py is tested across three distinct scenarios:
   - Real reference implementation (exit code 0, 9/9 passed)
   - Deliberately failing reference (exit code 1, assertion failure propagated)
   - Empty test selection (exit code 2, zero-test run detected)
5. Learner file hashes before and after every run (including failing/zero-test runs) are verified to be 100% identical.
6. Documentation in docs/maintenance/leap.md is verified.
7. Execution evidence (inputs, expected vs actual results, tool versions, hashes, scenario outputs) is saved in work/R08-T049/.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def compute_file_hash(path: Path) -> str:
    """Compute SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_learner_hashes(exercise_dir: Path) -> dict:
    """Compute SHA256 hashes of all learner starter and fixture files."""
    hashes = {}
    for entry in sorted(exercise_dir.iterdir()):
        if entry.is_file() and not entry.name.startswith("."):
            hashes[entry.name] = compute_file_hash(entry)
    return hashes


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


def parse_leap_test_cases(test_sql_path: Path) -> list:
    """Extract test case definitions from leap_test.sql."""
    with open(test_sql_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(
        r"\(\s*'([^']+)',\s*'([a-f0-9\-]+)',\s*(\d+),\s*(\d+)\s*\)",
        re.MULTILINE
    )
    cases = []
    for m in pattern.finditer(content):
        name, uuid, year, result = m.groups()
        cases.append({
            "name": name,
            "uuid": uuid,
            "year": int(year),
            "expected_is_leap": int(result)
        })
    return cases


def verify_learner_stub(repo_root: Path, exercise_rel_path: Path, config: dict):
    """Verify that learner stub in working tree is unsolved."""
    exercise_dir = repo_root / exercise_rel_path
    solution_file = config["files"]["solution"][0]
    test_file = config["files"]["test"][0]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        temp_exercise = tmp_path / "leap"
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


def verify_reference_implementation(repo_root: Path, exercise_rel_path: Path, config: dict, work_dir: Path) -> dict:
    """
    Verify reference implementation in an isolated temporary copy.
    Assert all 9 test cases pass, check returncode 0, save test_results.json.
    """
    exercise_dir = repo_root / exercise_rel_path
    solution_file = config["files"]["solution"][0]
    test_file = config["files"]["test"][0]
    example_file = config["files"]["example"][0]

    # Verify working tree solution is untouched
    orig_solution_content = (exercise_dir / solution_file).read_text(encoding="utf-8")
    if "year % 4 = 0" in orig_solution_content:
        raise AssertionError("Learner solution file in working tree was overwritten with reference code!")

    hashes_before = compute_learner_hashes(exercise_dir)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        temp_exercise = tmp_path / "leap"
        shutil.copytree(exercise_dir, temp_exercise)

        # Substitute reference ONLY in temporary copy
        shutil.copyfile(temp_exercise / example_file, temp_exercise / solution_file)

        # Run sqlite3 -bail < leap_test.sql
        cmd = f"sqlite3 -bail < {test_file}"
        proc = subprocess.run(cmd, cwd=temp_exercise, shell=True, capture_output=True, text=True)

        if proc.returncode != 0:
            raise AssertionError(
                f"sqlite3 exited with non-zero code {proc.returncode}.\n"
                f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
            )

        output_file = temp_exercise / "output.json"
        if not output_file.exists():
            raise AssertionError("output.json was not created by the test runner.")

        with open(output_file, "r", encoding="utf-8") as f:
            results = json.load(f)

    # Verify hashes after execution
    hashes_after = compute_learner_hashes(exercise_dir)
    if hashes_before != hashes_after:
        raise AssertionError("Working tree learner files were modified during isolated run!")

    test_count = len(results)
    if test_count == 0:
        raise AssertionError("Zero test cases were executed against reference!")

    failed = [t for t in results if t.get("status") != "pass"]
    if failed:
        raise AssertionError(f"{len(failed)} test(s) failed against reference: {failed}")

    # Verify all tests in tests.toml are accounted for
    tests_toml_items = parse_tests_toml(exercise_dir / ".meta" / "tests.toml")
    expected_descs = {t["description"] for t in tests_toml_items}
    actual_descs = {t.get("name") or t.get("description") for t in results}

    missing = expected_descs - actual_descs
    if missing:
        raise AssertionError(f"Missing tests from tests.toml in actual test run: {missing}")

    # Build detailed test results
    test_cases_info = parse_leap_test_cases(exercise_dir / test_file)
    case_map = {c["name"]: c for c in test_cases_info}

    detailed_results = []
    for r in results:
        desc = r.get("name") or r.get("description")
        c_info = case_map.get(desc, {})
        detailed_results.append({
            "name": desc,
            "status": r.get("status"),
            "uuid": c_info.get("uuid"),
            "year": c_info.get("year"),
            "expected_is_leap": c_info.get("expected_is_leap")
        })

    with open(work_dir / "test_results.json", "w", encoding="utf-8") as f:
        json.dump(detailed_results, f, indent=2)

    print(f"[OK] Reference implementation passed all {test_count} executed test cases:")
    for r in results:
        print(f"     ✓ {r.get('name') or r.get('description')}: {r.get('status')}")

    return {"test_count": test_count, "results": detailed_results}


def verify_runner_scenarios(repo_root: Path, work_dir: Path) -> dict:
    """
    Test the isolated runner (tools/course_checks/r08-t049.py) across:
    1. Real reference (exit code 0, 9 passed)
    2. Deliberately failing reference (exit code 1)
    3. Empty test selection (exit code 2)
    And verify learner file hashes remain identical before/after every single run.
    """
    exercise_dir = repo_root / "exercises" / "practice" / "leap"
    runner_script = repo_root / "tools" / "course_checks" / "r08-t049.py"

    if not runner_script.exists():
        raise AssertionError(f"Runner script not found at {runner_script}")

    scenarios = {}
    all_hashes = {}

    # Initial baseline hashes
    initial_hashes = compute_learner_hashes(exercise_dir)
    all_hashes["initial"] = initial_hashes

    # --- Scenario 1: Real Reference Implementation ---
    h_before = compute_learner_hashes(exercise_dir)
    proc1 = subprocess.run(
        [sys.executable, str(runner_script), "--json"],
        capture_output=True,
        text=True
    )
    h_after = compute_learner_hashes(exercise_dir)
    if h_before != h_after:
        raise AssertionError("Hashes changed during Scenario 1 (real reference)!")

    if proc1.returncode != 0:
        raise AssertionError(f"Scenario 1 failed with return code {proc1.returncode}: {proc1.stderr}")

    out1 = json.loads(proc1.stdout)
    if out1.get("status") != "success" or out1.get("passed_count") != 9:
        raise AssertionError(f"Scenario 1 unexpected output: {out1}")

    scenarios["scenario_1_real_reference"] = {
        "description": "Run isolated runner against real reference implementation",
        "expected_exit_code": 0,
        "actual_exit_code": proc1.returncode,
        "status": out1.get("status"),
        "test_count": out1.get("test_count"),
        "passed_count": out1.get("passed_count"),
        "failed_count": out1.get("failed_count"),
        "hashes_preserved": True
    }
    all_hashes["after_scenario_1"] = h_after
    print(f"[OK] Scenario 1 (Real reference): Exit code 0, {out1.get('passed_count')}/9 passed, hashes preserved.")

    # --- Scenario 2: Deliberately Failing Reference ---
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as f:
        f.write("UPDATE leap SET is_leap = 0;\n")
        failing_sql = Path(f.name)

    try:
        h_before = compute_learner_hashes(exercise_dir)
        proc2 = subprocess.run(
            [sys.executable, str(runner_script), "--solution-file", str(failing_sql), "--json"],
            capture_output=True,
            text=True
        )
        h_after = compute_learner_hashes(exercise_dir)
        if h_before != h_after:
            raise AssertionError("Hashes changed during Scenario 2 (failing reference)!")

        if proc2.returncode != 1:
            raise AssertionError(f"Scenario 2 expected exit code 1, got {proc2.returncode}")

        out2 = json.loads(proc2.stdout)
        if out2.get("status") != "assertion_failure":
            raise AssertionError(f"Scenario 2 expected status 'assertion_failure', got {out2.get('status')}")

        scenarios["scenario_2_failing_reference"] = {
            "description": "Run isolated runner against deliberately failing reference implementation",
            "expected_exit_code": 1,
            "actual_exit_code": proc2.returncode,
            "status": out2.get("status"),
            "test_count": out2.get("test_count"),
            "passed_count": out2.get("passed_count"),
            "failed_count": out2.get("failed_count"),
            "hashes_preserved": True
        }
        all_hashes["after_scenario_2"] = h_after
        print(f"[OK] Scenario 2 (Failing reference): Exit code 1, {out2.get('failed_count')} failed, hashes preserved.")
    finally:
        failing_sql.unlink(missing_ok=True)

    # --- Scenario 3: Empty Test Selection (Zero-Test Run) ---
    h_before = compute_learner_hashes(exercise_dir)
    proc3 = subprocess.run(
        [sys.executable, str(runner_script), "--empty-tests", "--json"],
        capture_output=True,
        text=True
    )
    h_after = compute_learner_hashes(exercise_dir)
    if h_before != h_after:
        raise AssertionError("Hashes changed during Scenario 3 (empty tests)!")

    if proc3.returncode != 2:
        raise AssertionError(f"Scenario 3 expected exit code 2, got {proc3.returncode}")

    out3 = json.loads(proc3.stdout)
    if out3.get("status") != "zero_tests":
        raise AssertionError(f"Scenario 3 expected status 'zero_tests', got {out3.get('status')}")

    scenarios["scenario_3_empty_tests"] = {
        "description": "Run isolated runner with zero tests selected",
        "expected_exit_code": 2,
        "actual_exit_code": proc3.returncode,
        "status": out3.get("status"),
        "test_count": 0,
        "passed_count": 0,
        "failed_count": 0,
        "hashes_preserved": True
    }
    all_hashes["after_scenario_3"] = h_after
    print(f"[OK] Scenario 3 (Empty tests): Exit code 2, zero_tests detected, hashes preserved.")

    # Save scenarios and hashes to evidence files
    with open(work_dir / "runner_scenarios.json", "w", encoding="utf-8") as f:
        json.dump(scenarios, f, indent=2)

    with open(work_dir / "learner_file_hashes.json", "w", encoding="utf-8") as f:
        json.dump(all_hashes, f, indent=2)

    return scenarios


def verify_documentation(repo_root: Path):
    """Verify that docs/maintenance/leap.md exists and documents commands and requirements."""
    doc_path = repo_root / "docs" / "maintenance" / "leap.md"
    if not doc_path.exists():
        raise AssertionError(f"Documentation file {doc_path} does not exist!")

    content = doc_path.read_text(encoding="utf-8")

    required_snippets = [
        "tools/course_checks/r08-t049.py",
        "--solution-file",
        "--empty-tests",
        "Python 3",
        "SQLite 3",
        "isolated",
        "Exit Code"
    ]
    for snip in required_snippets:
        if snip.lower() not in content.lower():
            raise AssertionError(f"Documentation missing required snippet: '{snip}'")

    print(f"[OK] Documentation verified in {doc_path}: contains command usage, options, tool prerequisites, and exit codes.")


def main():
    repo_root = Path(__file__).resolve().parent.parent.parent
    work_dir = repo_root / "work" / "R08-T049"
    work_dir.mkdir(parents=True, exist_ok=True)

    exercise_rel = Path("exercises/practice/leap")

    print("=== Running Checks for Task R08-T049 ===")
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

    # 4. Verify reference implementation in isolated temporary copy
    ref_res = verify_reference_implementation(repo_root, exercise_rel, config, work_dir)

    # 5. Verify isolated runner across all scenarios (real, failing, empty) and learner hashes
    verify_runner_scenarios(repo_root, work_dir)

    # 6. Verify documentation
    verify_documentation(repo_root)

    # Save summary
    summary = {
        "task": "R08-T049",
        "exercise": "exercises/practice/leap",
        "runner": "tools/course_checks/r08-t049.py",
        "documentation": "docs/maintenance/leap.md",
        "executed_test_cases": ref_res["test_count"],
        "all_tests_passed": True,
        "learner_stub_unsolved": True,
        "runner_scenarios_verified": True,
        "learner_hashes_preserved": True,
        "documentation_verified": True
    }
    with open(work_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n=== ALL CHECKS PASSED SUCCESSFULLY ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
