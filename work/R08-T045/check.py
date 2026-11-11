#!/usr/bin/env python3
"""
Verification check for Task R08-T045 (exercises/practice/isogram).

Requirements verified:
1. Learner stub in working tree remains unsolved.
2. Maintained reference implementation passes all 14 enabled test cases in an isolated temporary copy.
3. The check reports executed case counts and fails on zero-test run, non-zero child exit, or assertion failure.
4. Input size is defined in terms of the exercise domain (character count L, letter count K).
5. Three valid input sizes from the domain are measured with at least 5 repetitions, reporting medians.
6. Correctness is asserted before timing for each benchmarked input.
7. The cost statement distinguishes in-engine algorithm work from process-startup / compilation time.
8. Complexity comment in .meta/example.sql and documentation in docs/maintenance/isogram.md are verified.
9. Execution evidence (inputs, expected vs actual results, tool versions, scaling benchmark) is saved in work/R08-T045/.
"""

import json
import os
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
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


def parse_isogram_test_cases(test_sql_path: Path) -> list:
    """Extract test case definitions from isogram_test.sql."""
    with open(test_sql_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(
        r"\(\s*'([^']*)',\s*'([a-f0-9\-]+)',\s*'([^']*)',\s*(\d+)\s*\)",
        re.MULTILINE
    )
    cases = []
    for m in pattern.finditer(content):
        desc, uuid, phrase, expected = m.groups()
        cases.append({
            "uuid": uuid,
            "description": desc,
            "phrase": phrase,
            "expected_is_isogram": int(expected)
        })
    return cases


def verify_learner_stub(repo_root: Path, exercise_rel_path: Path, config: dict):
    """Verify that learner stub in working tree is unsolved."""
    exercise_dir = repo_root / exercise_rel_path
    solution_file = config["files"]["solution"][0]
    test_file = config["files"]["test"][0]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        temp_exercise = tmp_path / "isogram"
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


def verify_reference_implementation(
    repo_root: Path,
    exercise_rel_path: Path,
    config: dict,
    work_dir: Path
) -> dict:
    """Run reference implementation in isolated temporary copy and assert all tests pass."""
    exercise_dir = repo_root / exercise_rel_path
    solution_file = config["files"]["solution"][0]
    test_file = config["files"]["test"][0]
    example_file = config["files"]["example"][0]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        temp_exercise = tmp_path / "isogram"
        shutil.copytree(exercise_dir, temp_exercise)

        # Substitute reference ONLY in temporary copy
        shutil.copyfile(temp_exercise / example_file, temp_exercise / solution_file)

        cmd = f"sqlite3 -bail < {test_file}"
        proc = subprocess.run(cmd, cwd=temp_exercise, shell=True, capture_output=True, text=True)

        if proc.returncode != 0:
            raise AssertionError(
                f"Reference implementation failed with exit code {proc.returncode}.\n"
                f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
            )

        output_file = temp_exercise / "output.json"
        if not output_file.exists():
            raise AssertionError("output.json was not created for reference implementation.")

        with open(output_file, "r", encoding="utf-8") as f:
            results = json.load(f)

    test_count = len(results)
    if test_count == 0:
        raise AssertionError("Zero test cases executed against reference!")

    failed = [t for t in results if t.get("status") != "pass"]
    if failed:
        raise AssertionError(f"{len(failed)} test(s) failed against reference: {failed}")

    # Map test cases
    table_cases = parse_isogram_test_cases(exercise_dir / test_file)
    case_map = {c["description"]: c for c in table_cases}

    detailed_results = []
    for r in results:
        desc = r.get("description") or r.get("name")
        c_info = case_map.get(desc, {})
        detailed_results.append({
            "description": desc,
            "status": r.get("status"),
            "uuid": c_info.get("uuid"),
            "phrase": c_info.get("phrase"),
            "expected": c_info.get("expected_is_isogram")
        })

    with open(work_dir / "test_results.json", "w", encoding="utf-8") as f:
        json.dump(detailed_results, f, indent=2)

    print(f"[OK] Reference implementation passed all {test_count} executed test cases.")
    return {"test_count": test_count, "results": detailed_results}


def run_scaling_benchmark(repo_root: Path, exercise_rel_path: Path, work_dir: Path) -> dict:
    """
    Measure operations, in-engine query time, and subprocess startup time across
    three valid input sizes from the exercise domain with at least 5 repetitions each.
    """
    example_sql = (repo_root / exercise_rel_path / ".meta" / "example.sql").read_text(encoding="utf-8")

    bench_cases = [
        {
            "category": "Small",
            "phrase": "isogram",
            "length": 7,
            "letter_count": 7,
            "expected_is_isogram": 1
        },
        {
            "category": "Medium",
            "phrase": "subdermatoglyphic",
            "length": 17,
            "letter_count": 17,
            "expected_is_isogram": 1
        },
        {
            "category": "Large",
            "phrase": "Emily Jung Schwartzkopf",
            "length": 23,
            "letter_count": 21,
            "expected_is_isogram": 1
        }
    ]

    con = sqlite3.connect(":memory:")

    # Measure baseline subprocess startup time over 5 repetitions
    subprocess_times_ms = []
    for _ in range(5):
        t0 = time.perf_counter()
        subprocess.run(["sqlite3", ":memory:", "SELECT 1;"], capture_output=True, check=True)
        t1 = time.perf_counter()
        subprocess_times_ms.append((t1 - t0) * 1000.0)
    median_subprocess_ms = statistics.median(subprocess_times_ms)

    benchmark_data = {
        "subprocess_startup_overhead": {
            "repetitions": 5,
            "timings_ms": subprocess_times_ms,
            "median_ms": round(median_subprocess_ms, 2)
        },
        "cases": []
    }

    for case in bench_cases:
        phrase = case["phrase"]
        expected = case["expected_is_isogram"]

        # Setup table
        con.execute("DROP TABLE IF EXISTS isogram;")
        con.execute("CREATE TABLE isogram (phrase TEXT, is_isogram INT);")
        con.execute("INSERT INTO isogram (phrase) VALUES (?);", (phrase,))

        # 1. Assert correctness BEFORE timing
        con.execute("UPDATE isogram SET is_isogram = NULL;")
        con.executescript(example_sql)
        cur = con.execute("SELECT is_isogram FROM isogram;")
        actual_result = cur.fetchone()[0]
        if actual_result != expected:
            raise AssertionError(f"Correctness check failed for '{phrase}': expected {expected}, got {actual_result}")

        # 2. Count operations / rows generated
        chars_count = len(phrase) + 1
        letters_count = len([c for c in phrase if c.isalpha()])
        uniq_letters_count = len(set(c.lower() for c in phrase if c.isalpha()))
        total_intermediate_rows = chars_count + letters_count + uniq_letters_count

        # 3. Measure in-engine algorithm query time across 5 repetitions
        in_engine_timings_us = []
        for _ in range(5):
            con.execute("UPDATE isogram SET is_isogram = NULL;")
            t0 = time.perf_counter_ns()
            con.executescript(example_sql)
            t1 = time.perf_counter_ns()
            in_engine_timings_us.append((t1 - t0) / 1000.0)

        median_in_engine_us = statistics.median(in_engine_timings_us)

        case_entry = {
            "category": case["category"],
            "phrase": phrase,
            "length_L": case["length"],
            "letter_count_K": case["letter_count"],
            "correctness_asserted": True,
            "expected_is_isogram": expected,
            "actual_is_isogram": actual_result,
            "operation_counts": {
                "chars_rows": chars_count,
                "letters_rows": letters_count,
                "unique_letters_rows": uniq_letters_count,
                "total_intermediate_rows": total_intermediate_rows
            },
            "timing": {
                "repetitions": 5,
                "timings_us": [round(t, 2) for t in in_engine_timings_us],
                "median_in_engine_us": round(median_in_engine_us, 2),
                "median_subprocess_ms": round(median_subprocess_ms, 2),
                "ratio_process_to_algorithm": round((median_subprocess_ms * 1000.0) / median_in_engine_us, 1)
            }
        }
        benchmark_data["cases"].append(case_entry)

        print(f"[OK] Measured {case['category']} ({phrase}, L={case['length']}): "
              f"Correctness asserted={actual_result}, Rows={total_intermediate_rows}, "
              f"In-Engine Median={median_in_engine_us:.1f}us vs Subprocess={median_subprocess_ms:.2f}ms "
              f"(~{case_entry['timing']['ratio_process_to_algorithm']}x process startup overhead)")

    con.close()

    with open(work_dir / "scaling_benchmark.json", "w", encoding="utf-8") as f:
        json.dump(benchmark_data, f, indent=2)

    return benchmark_data


def verify_complexity_comment_and_docs(repo_root: Path, exercise_rel_path: Path):
    """Verify that example.sql has complexity comments and docs/maintenance/isogram.md exists."""
    example_path = repo_root / exercise_rel_path / ".meta" / "example.sql"
    example_text = example_path.read_text(encoding="utf-8")

    required_comment_tokens = ["Complexity", "Invariant", "O(L", "Time Complexity"]
    for token in required_comment_tokens:
        if token not in example_text:
            raise AssertionError(f"example.sql missing expected complexity comment token: '{token}'")

    doc_path = repo_root / "docs" / "maintenance" / "isogram.md"
    if not doc_path.exists():
        raise AssertionError(f"Documentation file {doc_path} does not exist!")

    doc_text = doc_path.read_text(encoding="utf-8")
    required_doc_tokens = [
        "isogram",
        "subdermatoglyphic",
        "Emily Jung Schwartzkopf",
        "process startup",
        "algorithm",
        "Limits of the Conclusion"
    ]
    for token in required_doc_tokens:
        if token.lower() not in doc_text.lower():
            raise AssertionError(f"isogram.md missing required section/token: '{token}'")

    print(f"[OK] Complexity comment in {example_path} and maintenance docs in {doc_path} verified.")


def main():
    repo_root = Path(__file__).resolve().parent.parent.parent
    work_dir = repo_root / "work" / "R08-T045"
    work_dir.mkdir(parents=True, exist_ok=True)

    exercise_rel = Path("exercises/practice/isogram")

    print("=== Running Checks for Task R08-T045 ===")
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

    # 5. Measure scaling benchmark across 3 sizes with 5 repetitions each
    bench_res = run_scaling_benchmark(repo_root, exercise_rel, work_dir)

    # 6. Verify complexity comment and documentation
    verify_complexity_comment_and_docs(repo_root, exercise_rel)

    # Save summary
    summary = {
        "task": "R08-T045",
        "exercise": "exercises/practice/isogram",
        "executed_test_cases": ref_res["test_count"],
        "reference_all_passed": True,
        "learner_stub_unsolved": True,
        "scaling_benchmark_verified": True,
        "benchmark_cases_count": len(bench_res["cases"]),
        "complexity_comment_verified": True,
        "maintenance_docs_verified": True
    }
    with open(work_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n=== ALL CHECKS PASSED SUCCESSFULLY ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
