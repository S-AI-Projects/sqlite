#!/usr/bin/env python3
import argparse
import csv
import difflib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

# Data-driven list of mutants at the top of the script
MUTANTS = [
    {
        "id": "M1",
        "description": "left and right turns swapped",
        "patches": [
            ('\'{"L": -90, "R": 90}\'', '\'{"L": 90, "R": -90}\'')
        ],
        "expected_failing_uuids": {
            "8cbd0086-6392-4680-b9b9-73cf491e67e5",
            "8abc87fc-eab2-4276-93b7-9c009e866ba1",
            "3cfe1b85-bbf2-4bae-b54d-d73e7e93617a",
            "5ea9fb99-3f2c-47bd-86f7-46b7d8c3c716",
            "fa0c40f5-6ba3-443d-a4b3-58cbd6cb8d63",
            "da33d734-831f-445c-9907-d66d7d2a92e2",
            "bd1ca4b9-4548-45f4-b32e-900fc7c19389",
            "2de27b67-a25c-4b59-9883-bc03b1b55bba",
            "e34ac672-4ed4-4be3-a0b8-d9af259cbaa1",
            "f30e4955-4b47-4aa3-8b39-ae98cfbd515b",
            "3e466bf6-20ab-4d79-8b51-264165182fca",
            "41f0bb96-c617-4e6b-acff-a4b279d44514",
        },
        "documented": False,
    },
    {
        "id": "M2",
        "description": "west moves along the wrong sign (+x instead of -x)",
        "patches": [
            ("('west', 270, 'x', -1)", "('west', 270, 'x', 1)")
        ],
        "expected_failing_uuids": {
            "bb69c4a7-3bbf-4f64-b415-666fa72d7b04",
            "f30e4955-4b47-4aa3-8b39-ae98cfbd515b",
            "3e466bf6-20ab-4d79-8b51-264165182fca",
        },
        "documented": False,
    },
    {
        "id": "M4",
        "description": "only the first instruction of a sequence runs",
        "patches": [
            ("JSON_REMOVE(instructions, '$[0]')", "'[]'")
        ],
        "expected_failing_uuids": {
            "e34ac672-4ed4-4be3-a0b8-d9af259cbaa1",
            "f30e4955-4b47-4aa3-8b39-ae98cfbd515b",
            "3e466bf6-20ab-4d79-8b51-264165182fca",
            "41f0bb96-c617-4e6b-acff-a4b279d44514",
        },
        "documented": False,
    },
    {
        "id": "M5",
        "description": "instructions processed in reverse order",
        "patches": [
            ("SUBSTR(string, 2)", "SUBSTR(string, 1, LENGTH(string) - 1)"),
            ("SUBSTR(string, 1, 1)", "SUBSTR(string, -1)"),
        ],
        "expected_failing_uuids": {
            "e34ac672-4ed4-4be3-a0b8-d9af259cbaa1",
            "f30e4955-4b47-4aa3-8b39-ae98cfbd515b",
            "3e466bf6-20ab-4d79-8b51-264165182fca",
            "41f0bb96-c617-4e6b-acff-a4b279d44514",
        },
        "documented": True,
    },
]

# Separate data-driven list of observations
OBSERVATIONS = [
    {
        "id": "M6",
        "description": "unknown instruction letters make the state NULL instead of being ignored",
        "patches": [
            ("ELSE jobject", "ELSE NULL")
        ],
        "note": "unspecified behaviour; no test case is proposed",
    }
]

NAMED_ASSERTION_UUID = "e34ac672-4ed4-4be3-a0b8-d9af259cbaa1"

DETAIL_QUERY_SQL = """
.mode json
.once './detail.json'
SELECT
  t.uuid,
  t.description,
  t.property,
  t.input,
  t.expected,
  r.result AS actual,
  t.status
FROM
  tests t
LEFT JOIN
  "robot-simulator" r ON r.property = t.property AND r.input = t.input
ORDER BY
  t.rowid;
"""


class ExerciseRunError(Exception):
    """Exception raised for exercise execution failures."""
    pass


class NotAValidMutation(Exception):
    """Exception raised when a proposed mutation is formatting-only or has no failing tests."""
    pass


def get_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "exercises" / "practice" / "robot-simulator").is_dir():
            return parent
    return current.parents[2]


def load_config(exercise_dir: Path):
    config_path = exercise_dir / ".meta" / "config.json"
    if not config_path.is_file():
        raise ExerciseRunError(f"Config file not found at {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    solution_rel = config["files"]["solution"][0]
    test_rel = config["files"]["test"][0]
    example_rel = config["files"]["example"][0]
    return (
        exercise_dir / solution_rel,
        exercise_dir / test_rel,
        exercise_dir / example_rel,
        solution_rel,
        test_rel,
        example_rel,
    )


def normalize_sql(sql: str) -> str:
    lines = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        lines.append(line)
    return " ".join("".join(lines).split())


def run_exercise(
    exercise_dir: Path,
    solution_source: str | Path,
    test_sql_text: str | None = None,
    with_detail: bool = False,
):
    _, _, _, solution_rel, test_rel, _ = load_config(exercise_dir)

    with tempfile.TemporaryDirectory() as tmp_dir:
        copy_dir = Path(tmp_dir) / "exercise"
        shutil.copytree(exercise_dir, copy_dir)

        dest_solution = copy_dir / solution_rel
        if isinstance(solution_source, Path):
            shutil.copy2(solution_source, dest_solution)
        else:
            dest_solution.write_text(solution_source, encoding="utf-8")

        dest_test = copy_dir / test_rel
        if test_sql_text is not None:
            dest_test.write_text(test_sql_text, encoding="utf-8")
        elif with_detail:
            existing = dest_test.read_text(encoding="utf-8")
            dest_test.write_text(existing + "\n" + DETAIL_QUERY_SQL, encoding="utf-8")

        with open(dest_test, "rb") as stdin_f:
            try:
                proc = subprocess.run(
                    ["sqlite3", "-bail"],
                    stdin=stdin_f,
                    cwd=copy_dir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except subprocess.TimeoutExpired as e:
                raise ExerciseRunError(f"sqlite3 execution timed out: {e}")

        if proc.returncode != 0:
            if proc.stderr:
                print(proc.stderr, file=sys.stderr)
            raise ExerciseRunError(f"sqlite3 exited with non-zero return code {proc.returncode}")

        out_json = copy_dir / "output.json"
        if not out_json.is_file():
            raise ExerciseRunError("output.json is missing")
        if out_json.stat().st_size == 0:
            raise ExerciseRunError("output.json is empty")

        try:
            results = json.loads(out_json.read_text(encoding="utf-8"))
        except Exception as e:
            raise ExerciseRunError(f"output.json is not valid JSON: {e}")

        if not isinstance(results, list):
            raise ExerciseRunError("output.json is not a JSON array")

        detail_results = None
        if with_detail:
            det_json = copy_dir / "detail.json"
            if not det_json.is_file():
                raise ExerciseRunError("detail.json is missing")
            if det_json.stat().st_size == 0:
                raise ExerciseRunError("detail.json is empty")
            try:
                detail_results = json.loads(det_json.read_text(encoding="utf-8"))
            except Exception as e:
                raise ExerciseRunError(f"detail.json is not valid JSON: {e}")
            if not isinstance(detail_results, list):
                raise ExerciseRunError("detail.json is not a JSON array")
            if len(detail_results) != len(results):
                raise ExerciseRunError(
                    f"detail.json row count ({len(detail_results)}) differs from output.json ({len(results)})"
                )

        return results, detail_results


def check_all_pass(results):
    failing = [r for r in results if r.get("status") != "pass"]
    if failing:
        raise AssertionError(f"{len(failing)} tests failed in run")


def check_zero_tests(results):
    if len(results) == 0:
        raise AssertionError("Zero tests executed")


def guard_check(repo_root: Path) -> str:
    target_rel = "exercises/practice/robot-simulator"
    ref_used = "origin/main"
    proc = subprocess.run(
        ["git", "diff", "--quiet", "origin/main", "--", target_rel],
        cwd=repo_root,
    )
    if proc.returncode != 0:
        check_ref = subprocess.run(
            ["git", "rev-parse", "--verify", "origin/main"],
            cwd=repo_root,
            capture_output=True,
        )
        if check_ref.returncode != 0:
            ref_used = "HEAD"
            proc = subprocess.run(
                ["git", "diff", "--quiet", "HEAD", "--", target_rel],
                cwd=repo_root,
            )

    if proc.returncode != 0:
        raise ExerciseRunError(
            f"Guard failure: working tree has modifications under {target_rel} relative to {ref_used}"
        )
    print(f"Guard clean: {target_rel} is clean against {ref_used}")
    return ref_used


def apply_patches(source: str, patches: list[tuple[str, str]]) -> str:
    mutated = source
    for old_str, new_str in patches:
        count = mutated.count(old_str)
        if count != 1:
            raise ExerciseRunError(
                f"Patch drift: target string {old_str!r} occurred {count} times (expected exactly 1) in source."
            )
        mutated = mutated.replace(old_str, new_str, 1)
    return mutated


def validate_mutation(orig_sql: str, mutated_sql: str, failing_uuids: set[str]):
    norm_orig = normalize_sql(orig_sql)
    norm_mut = normalize_sql(mutated_sql)
    if norm_orig == norm_mut:
        raise NotAValidMutation("formatting-only changes are not mutations: normalized text is identical")
    if len(failing_uuids) == 0:
        raise NotAValidMutation("formatting-only changes are not mutations: zero tests failed")


def run_custom_inputs(
    exercise_dir: Path,
    sql_texts: list[str],
    inputs: list[str],
    property_name: str = "move",
) -> list[dict[str, str | None]]:
    """Runs a list of SQL solutions against custom input rows in a single temp exercise copy.

    Returns a list of dicts (one per sql_text in sql_texts), mapping input_str -> result.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        copy_dir = Path(tmp_dir) / "exercise"
        shutil.copytree(exercise_dir, copy_dir)

        csv_path = copy_dir / "data.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            for inp in inputs:
                writer.writerow([property_name, inp, ""])

        driver_sql = """
.read ./create_fixture.sql
.read ./robot-simulator.sql
.mode json
SELECT property, input, result FROM "robot-simulator";
"""
        driver_path = copy_dir / "driver.sql"
        driver_path.write_text(driver_sql, encoding="utf-8")

        all_results = []
        for sql in sql_texts:
            (copy_dir / "robot-simulator.sql").write_text(sql, encoding="utf-8")
            with open(driver_path, "rb") as stdin_f:
                proc = subprocess.run(
                    ["sqlite3", "-bail"],
                    stdin=stdin_f,
                    cwd=copy_dir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            if proc.returncode != 0:
                raise ExerciseRunError(f"Custom driver sqlite3 execution failed: {proc.stderr}")
            data = json.loads(proc.stdout)
            all_results.append({item["input"]: item["result"] for item in data})

        return all_results


def run_diagnostics(exercise_dir: Path, example_sql_text: str, mutant_m5_sql_text: str, custom_expected_ar=None):
    ra_input_obj = {"position": {"x": 0, "y": 0}, "direction": "north", "instructions": "RA"}
    ar_input_obj = {"position": {"x": 0, "y": 0}, "direction": "north", "instructions": "AR"}
    ra_input_str = json.dumps(ra_input_obj, separators=(",", ":"))
    ar_input_str = json.dumps(ar_input_obj, separators=(",", ":"))

    results = run_custom_inputs(
        exercise_dir,
        [example_sql_text, mutant_m5_sql_text],
        [ra_input_str, ar_input_str],
    )
    orig_results = results[0]
    mut_results = results[1]

    expected_ra = {"position": {"x": 1, "y": 0}, "direction": "east"}
    expected_ar = custom_expected_ar if custom_expected_ar is not None else {"position": {"x": 0, "y": 1}, "direction": "east"}

    orig_ra_res = json.loads(orig_results.get(ra_input_str, "null"))
    orig_ar_res = json.loads(orig_results.get(ar_input_str, "null"))
    mut_ra_res = json.loads(mut_results.get(ra_input_str, "null"))
    mut_ar_res = json.loads(mut_results.get(ar_input_str, "null"))

    if orig_ra_res != expected_ra:
        raise AssertionError(f"Diagnostic assertion failed for RA: expected {expected_ra}, got {orig_ra_res}")
    if orig_ar_res != expected_ar:
        raise AssertionError(f"Diagnostic assertion failed for AR: expected {expected_ar}, got {orig_ar_res}")
    if orig_ra_res == mut_ra_res:
        raise AssertionError(f"Mutant M5 output matches original for RA: {orig_ra_res}")
    if orig_ar_res == mut_ar_res:
        raise AssertionError(f"Mutant M5 output matches original for AR: {orig_ar_res}")

    diag_data = {
        "RA": {
            "input": ra_input_str,
            "original_output": orig_results.get(ra_input_str),
            "mutant_output": mut_results.get(ra_input_str),
        },
        "AR": {
            "input": ar_input_str,
            "original_output": orig_results.get(ar_input_str),
            "mutant_output": mut_results.get(ar_input_str),
        },
    }
    print("Diagnostics: verified minimal differentiating inputs RA and AR for M5")
    return diag_data


def assert_unknown_letter_divergence(orig_out: str | None, mut_out: str | None):
    expected_orig = {"position": {"x": 0, "y": 0}, "direction": "north"}
    parsed_orig = json.loads(orig_out) if orig_out is not None else None
    if parsed_orig != expected_orig:
        raise AssertionError(
            f"Original output for unknown letter did not preserve state: expected {expected_orig}, got {parsed_orig}"
        )
    if orig_out == mut_out:
        raise AssertionError(
            f"Mutant output does not differ from original on unknown letter input: both produced {orig_out!r}"
        )


def run_unknown_letter_check(
    exercise_dir: Path,
    orig_sql: str,
    mut_sql: str,
) -> tuple[str, str | None, str | None]:
    unknown_input_obj = {"position": {"x": 0, "y": 0}, "direction": "north", "instructions": "X"}
    unknown_input_str = json.dumps(unknown_input_obj, separators=(",", ":"))
    results = run_custom_inputs(
        exercise_dir,
        [orig_sql, mut_sql],
        [unknown_input_str],
    )
    orig_results = results[0]
    mut_results = results[1]
    orig_out = orig_results.get(unknown_input_str)
    mut_out = mut_results.get(unknown_input_str)
    assert_unknown_letter_divergence(orig_out, mut_out)
    return unknown_input_str, orig_out, mut_out


def get_tool_version(cmd: list) -> str:
    try:
        return subprocess.check_output(cmd, text=True).strip()
    except Exception as e:
        return f"unknown ({e})"


def run_self_test(repo_root: Path):
    exercise_dir = repo_root / "exercises" / "practice" / "robot-simulator"
    solution_file, _, example_file, _, _, _ = load_config(exercise_dir)
    orig_example_text = example_file.read_text(encoding="utf-8")
    print("Running self-test scenarios...")

    # (a) stub as solution -> all-pass assertion fails
    scenario_a_ok = False
    try:
        stub_results, _ = run_exercise(exercise_dir, solution_file, with_detail=False)
        check_all_pass(stub_results)
        print("Scenario (a) FAILED: all-pass assertion did not fail.")
    except AssertionError as e:
        scenario_a_ok = True
        print(f"Scenario (a) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (a) FAILED with unexpected exception: {e}")

    # (b) test SQL with non-existent table -> non-zero child exit
    scenario_b_ok = False
    try:
        run_exercise(
            exercise_dir,
            orig_example_text,
            test_sql_text="SELECT * FROM table_that_does_not_exist;",
        )
        print("Scenario (b) FAILED: non-zero exit was not triggered.")
    except ExerciseRunError as e:
        scenario_b_ok = True
        print(f"Scenario (b) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (b) FAILED with unexpected exception: {e}")

    # (c) test SQL that writes [] to output.json -> zero-test check fails
    scenario_c_ok = False
    test_sql_zero = """.mode json
.once './output.json'
.print []
SELECT 1 WHERE 0;
"""
    try:
        zero_results, _ = run_exercise(
            exercise_dir,
            orig_example_text,
            test_sql_text=test_sql_zero,
        )
        check_zero_tests(zero_results)
        print("Scenario (c) FAILED: zero-test check did not fail.")
    except AssertionError as e:
        scenario_c_ok = True
        print(f"Scenario (c) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (c) FAILED with unexpected exception: {e}")

    # (d) formatting-only mutant -> NotAValidMutation
    scenario_d_ok = False
    try:
        formatting_only_sql = "-- extra comment\n" + orig_example_text + "\n   \n"
        validate_mutation(orig_example_text, formatting_only_sql, set())
        print("Scenario (d) FAILED: formatting-only mutant was not rejected.")
    except NotAValidMutation as e:
        scenario_d_ok = True
        print(f"Scenario (d) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (d) FAILED with unexpected exception: {e}")

    # (e) mutant patch whose old string does not occur -> patch drift failure
    scenario_e_ok = False
    try:
        bad_patches = [("STRING_THAT_DOES_NOT_EXIST_IN_EXAMPLE_SQL", "replacement")]
        apply_patches(orig_example_text, bad_patches)
        print("Scenario (e) FAILED: non-existent patch string was not rejected.")
    except ExerciseRunError as e:
        scenario_e_ok = True
        print(f"Scenario (e) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (e) FAILED with unexpected exception: {e}")

    # (f) documented mutant checked against wrong expected_failing_uuids -> set-equality failure
    scenario_f_ok = False
    try:
        m5_entry = [m for m in MUTANTS if m["id"] == "M5"][0]
        m5_sql = apply_patches(orig_example_text, m5_entry["patches"])
        m5_results, m5_detail = run_exercise(exercise_dir, m5_sql, with_detail=True)
        actual_failing_uuids = {d["uuid"] for d in m5_detail if d.get("status") != "pass"}
        wrong_expected = {"00000000-0000-0000-0000-000000000000"}
        if actual_failing_uuids != wrong_expected:
            raise ExerciseRunError(
                f"Failing UUID set mismatch: actual={actual_failing_uuids} vs expected={wrong_expected}"
            )
        print("Scenario (f) FAILED: wrong expected failing UUIDs set was not rejected.")
    except ExerciseRunError as e:
        scenario_f_ok = True
        print(f"Scenario (f) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (f) FAILED with unexpected exception: {e}")

    # (g) diagnostics check with wrong expected output for AR -> assertion failure
    scenario_g_ok = False
    try:
        m5_entry = [m for m in MUTANTS if m["id"] == "M5"][0]
        m5_sql = apply_patches(orig_example_text, m5_entry["patches"])
        wrong_ar = {"position": {"x": 999, "y": 999}, "direction": "north"}
        run_diagnostics(exercise_dir, orig_example_text, m5_sql, custom_expected_ar=wrong_ar)
        print("Scenario (g) FAILED: wrong expected AR output was not rejected.")
    except AssertionError as e:
        scenario_g_ok = True
        print(f"Scenario (g) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (g) FAILED with unexpected exception: {e}")

    # (h) feed check (c) a pair of identical outputs (simulate a no-op mutant) -> AssertionError
    scenario_h_ok = False
    try:
        sample_out = '{"position":{"x":0,"y":0},"direction":"north"}'
        assert_unknown_letter_divergence(sample_out, sample_out)
        print("Scenario (h) FAILED: identical outputs were not rejected.")
    except AssertionError as e:
        scenario_h_ok = True
        print(f"Scenario (h) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (h) FAILED with unexpected exception: {e}")

    if (
        scenario_a_ok
        and scenario_b_ok
        and scenario_c_ok
        and scenario_d_ok
        and scenario_e_ok
        and scenario_f_ok
        and scenario_g_ok
        and scenario_h_ok
    ):
        print("ALL SELF-TEST SCENARIOS PASSED")
        sys.exit(0)
    else:
        print("ONE OR MORE SELF-TEST SCENARIOS FAILED", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Robot-Simulator verification and mutation check")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test failure scenarios",
    )
    args = parser.parse_args()

    repo_root = get_repo_root()
    exercise_dir = repo_root / "exercises" / "practice" / "robot-simulator"
    work_dir = Path(__file__).resolve().parent

    if args.self_test:
        run_self_test(repo_root)

    solution_file, test_file, example_file, _, _, _ = load_config(exercise_dir)
    orig_example_text = example_file.read_text(encoding="utf-8")

    # 1. Reference run
    tests_toml_path = exercise_dir / ".meta" / "tests.toml"
    with open(tests_toml_path, "rb") as f:
        toml_data = tomllib.load(f)
    total_count = len(toml_data)
    included_count = sum(1 for v in toml_data.values() if isinstance(v, dict) and v.get("include") is not False)
    excluded_count = total_count - included_count
    print(f"tests.toml: {total_count} total, {included_count} included, {excluded_count} excluded")

    ref_results, ref_detail = run_exercise(exercise_dir, orig_example_text, with_detail=True)
    check_zero_tests(ref_results)
    if len(ref_results) != included_count:
        raise ExerciseRunError(
            f"Executed count ({len(ref_results)}) does not match included count in tests.toml ({included_count})"
        )
    print(f"Executed {len(ref_results)} cases")
    check_all_pass(ref_results)

    # 2. Stub run
    stub_results, _ = run_exercise(exercise_dir, solution_file, with_detail=False)
    stub_pass = sum(1 for r in stub_results if r.get("status") == "pass")
    stub_fail = sum(1 for r in stub_results if r.get("status") != "pass")
    print(f"Stub cases passed: {stub_pass}, failed: {stub_fail}")
    if stub_fail == 0:
        raise ExerciseRunError("Negative control failed: learner stub passed all tests!")

    # 3. Guard
    guard_ref = guard_check(repo_root)

    # 4. Mutants
    mutants_evidence = []
    named_assertion_data = None
    m5_sql_text = None

    for m in MUTANTS:
        m_id = m["id"]
        m_desc = m["description"]
        m_patches = m["patches"]
        expected_failing = m["expected_failing_uuids"]
        is_documented = m.get("documented", False)

        mutated_sql = apply_patches(orig_example_text, m_patches)
        if is_documented:
            m5_sql_text = mutated_sql

        diff_lines = list(
            difflib.unified_diff(
                orig_example_text.splitlines(keepends=True),
                mutated_sql.splitlines(keepends=True),
                fromfile=".meta/example.sql",
                tofile="robot-simulator.sql",
            )
        )
        unified_diff_str = "".join(diff_lines[:40])

        mut_results, mut_detail = run_exercise(exercise_dir, mutated_sql, with_detail=True)
        failing_cases_detail = [d for d in mut_detail if d.get("status") != "pass"]
        actual_failing_uuids = {d["uuid"] for d in failing_cases_detail}

        validate_mutation(orig_example_text, mutated_sql, actual_failing_uuids)

        if actual_failing_uuids != expected_failing:
            diff_missing = expected_failing - actual_failing_uuids
            diff_extra = actual_failing_uuids - expected_failing
            raise ExerciseRunError(
                f"Mutant {m_id} failing UUID set mismatch: missing={diff_missing}, extra={diff_extra}"
            )

        failing_summaries = ", ".join(f"'{d['description']}'" for d in failing_cases_detail)
        print(f"Mutant {m_id}: {len(actual_failing_uuids)} failing: {failing_summaries}")

        failing_records = [
            {
                "actual": d["actual"],
                "description": d["description"],
                "expected": d["expected"],
                "input": d["input"],
                "uuid": d["uuid"],
            }
            for d in failing_cases_detail
        ]

        if is_documented:
            named_d = [d for d in failing_cases_detail if d["uuid"] == NAMED_ASSERTION_UUID]
            if not named_d:
                raise ExerciseRunError(
                    f"Named assertion UUID {NAMED_ASSERTION_UUID} not found among failing cases of {m_id}"
                )
            named_target = named_d[0]
            named_assertion_data = {
                "description": named_target["description"],
                "expected": named_target["expected"],
                "input": named_target["input"],
                "mutant_actual": named_target["actual"],
                "uuid": named_target["uuid"],
            }

        mutants_evidence.append({
            "description": m_desc,
            "documented": is_documented,
            "failing_cases": failing_records,
            "failing_count": len(failing_records),
            "id": m_id,
            "pass_count": len(mut_results) - len(failing_records),
            "unified_diff": unified_diff_str,
        })

    # 5. Observations
    observations_evidence = []
    for obs in OBSERVATIONS:
        obs_id = obs["id"]
        obs_desc = obs["description"]
        obs_patches = obs["patches"]

        obs_sql = apply_patches(orig_example_text, obs_patches)

        # a. Normalized text check (same as mutants)
        norm_orig = normalize_sql(orig_example_text)
        norm_obs = normalize_sql(obs_sql)
        if norm_orig == norm_obs:
            raise ExerciseRunError(f"Observation {obs_id}: normalized text is identical to original")

        # b. Run all cases: failing set must be empty (survives)
        obs_results, obs_detail = run_exercise(exercise_dir, obs_sql, with_detail=True)
        obs_failing = [d for d in obs_detail if d.get("status") != "pass"]
        if len(obs_failing) != 0:
            raise ExerciseRunError(
                f"Observation {obs_id} expected 0 failing cases, got {len(obs_failing)}: {[d['uuid'] for d in obs_failing]}"
            )
        print(f"Observation {obs_id}: 0 failing (survives; behaviour not specified)")

        # c. Unknown letter isolated check
        unknown_inp, orig_out, mut_out = run_unknown_letter_check(
            exercise_dir,
            orig_example_text,
            obs_sql,
        )
        print(f"Unknown letter 'X': original={orig_out}, mutant={mut_out}")

        observations_evidence.append({
            "description": obs_desc,
            "failing_count": 0,
            "failing_uuids": [],
            "id": obs_id,
            "mutant_output": mut_out,
            "mutant_output_for_unknown": mut_out,
            "note": obs.get("note", "unspecified behaviour; no test case is proposed"),
            "original_output": orig_out,
            "original_output_for_unknown": orig_out,
            "patch": [list(p) for p in obs_patches],
            "patches": [list(p) for p in obs_patches],
            "survives": True,
            "surviving": True,
            "unknown_letter_input": unknown_inp,
        })

    # 6. Diagnostics
    if m5_sql_text is None:
        raise ExerciseRunError("Documented mutant M5 was not generated")
    diag_data = run_diagnostics(exercise_dir, orig_example_text, m5_sql_text)

    # 7. Write evidence and versions
    work_dir.mkdir(parents=True, exist_ok=True)

    tool_versions = {
        "git": get_tool_version(["git", "--version"]),
        "jq": get_tool_version(["jq", "--version"]),
        "os": f"{platform.system()} {platform.release()} {platform.machine()}",
        "python": f"Python {platform.python_version()}",
        "sqlite3": get_tool_version(["sqlite3", "--version"]),
    }

    # versions.txt
    versions_file = work_dir / "versions.txt"
    with open(versions_file, "w", encoding="utf-8") as f:
        for tool in sorted(tool_versions.keys()):
            f.write(f"{tool}: {tool_versions[tool]}\n")

    # evidence.json
    evidence = {
        "counts": {
            "excluded": excluded_count,
            "included": included_count,
            "total": total_count,
        },
        "diagnostics": diag_data,
        "executed_count": len(ref_results),
        "guard_ref": guard_ref,
        "mutants": mutants_evidence,
        "named_assertion": named_assertion_data,
        "observations": observations_evidence,
        "pass_count": len(ref_results),
        "stub_fail_count": stub_fail,
        "stub_pass_count": stub_pass,
        "tests": [
            {
                "actual": d["actual"],
                "description": d["description"],
                "expected": d["expected"],
                "input": d["input"],
                "property": d["property"],
                "status": d["status"],
                "uuid": d["uuid"],
            }
            for d in ref_detail
        ],
        "tool_versions": tool_versions,
    }

    evidence_file = work_dir / "evidence.json"
    with open(evidence_file, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2, sort_keys=True)
        f.write("\n")

    print("ALL CHECKS PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
