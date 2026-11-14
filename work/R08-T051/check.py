#!/usr/bin/env python3
import argparse
import copy
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib


class ExerciseRunError(Exception):
  """Custom exception for exercise run failures."""

  pass


def get_repo_root() -> Path:
  current = Path(__file__).resolve()
  for parent in current.parents:
    if (parent / "exercises" / "practice" / "clock").is_dir():
      return parent
  return current.parent.parent


REPO_ROOT = get_repo_root()
EXERCISE_DIR = REPO_ROOT / "exercises" / "practice" / "clock"
CONFIG_PATH = EXERCISE_DIR / ".meta" / "config.json"
TESTS_TOML_PATH = EXERCISE_DIR / ".meta" / "tests.toml"
WORK_DIR = Path(__file__).resolve().parent

DETAIL_QUERY_SQL = """
.mode json
.once './detail.json'
SELECT t.description, t.property, t.input, t.expected, c.result AS actual, t.status FROM tests t LEFT JOIN clock c ON c.property = t.property AND c.input = t.input ORDER BY t.rowid;
"""


def load_config():
  if not CONFIG_PATH.is_file():
    raise ExerciseRunError(f"Config file not found at {CONFIG_PATH}")
  with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)
  solution_rel = config["files"]["solution"][0]
  test_rel = config["files"]["test"][0]
  example_rel = config["files"]["example"][0]
  return (
      EXERCISE_DIR / solution_rel,
      EXERCISE_DIR / test_rel,
      EXERCISE_DIR / example_rel,
      solution_rel,
      test_rel,
      example_rel,
  )


def run_exercise(solution_source_path: Path, test_sql_text: str = None):
  (
      solution_file,
      test_file,
      example_file,
      solution_rel,
      test_rel,
      example_rel,
  ) = load_config()

  with tempfile.TemporaryDirectory() as tmp_dir:
    copy_dir = Path(tmp_dir) / "exercise"
    shutil.copytree(EXERCISE_DIR, copy_dir)

    # In the copy only, overwrite the solution file with solution_source_path
    dest_solution = copy_dir / solution_rel
    shutil.copy2(solution_source_path, dest_solution)

    # In the copy, overwrite or prepare test file
    dest_test = copy_dir / test_rel
    if test_sql_text is not None:
      dest_test.write_text(test_sql_text, encoding="utf-8")
    else:
      # Append detail query to the end of the test file
      existing_test_sql = dest_test.read_text(encoding="utf-8")
      dest_test.write_text(
          existing_test_sql + "\n" + DETAIL_QUERY_SQL, encoding="utf-8"
      )

    # Run sqlite3 -bail with test file as stdin, cwd = copy_dir
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
      raise ExerciseRunError(
          f"sqlite3 exited with non-zero return code {proc.returncode}"
      )

    output_json_path = copy_dir / "output.json"
    if not output_json_path.exists():
      raise ExerciseRunError("output.json is missing")

    if output_json_path.stat().st_size == 0:
      raise ExerciseRunError("output.json is empty")

    content = output_json_path.read_text(encoding="utf-8")
    try:
      results = json.loads(content)
    except json.JSONDecodeError as e:
      raise ExerciseRunError(f"output.json is not valid JSON: {e}")

    if not isinstance(results, list):
      raise ExerciseRunError("output.json is not a JSON array")

    detail_results = None
    if test_sql_text is None:
      detail_json_path = copy_dir / "detail.json"
      if not detail_json_path.exists():
        raise ExerciseRunError("detail.json is missing")
      if detail_json_path.stat().st_size == 0:
        raise ExerciseRunError("detail.json is empty")
      try:
        detail_results = json.loads(
            detail_json_path.read_text(encoding="utf-8")
        )
      except json.JSONDecodeError as e:
        raise ExerciseRunError(f"detail.json is not valid JSON: {e}")
      if not isinstance(detail_results, list):
        raise ExerciseRunError("detail.json is not a JSON array")
      if len(detail_results) != len(results):
        raise ExerciseRunError(
            f"detail.json has {len(detail_results)} rows, but output.json has"
            f" {len(results)} rows"
        )

    return results, detail_results


def check_all_pass(results, verbose: bool = True):
  failing = [r for r in results if r.get("status") != "pass"]
  if failing:
    if verbose:
      for f in failing:
        desc = f.get("description", "<no description>")
        msg = f.get("message", "<no message>")
        print(f"FAILED: {desc} - {msg}", file=sys.stderr)
    raise AssertionError(f"{len(failing)} tests failed in run")


def check_zero_tests(results):
  if len(results) == 0:
    raise AssertionError("Zero tests executed")


def get_tool_version(cmd: list) -> str:
  try:
    return subprocess.check_output(cmd, text=True).strip()
  except Exception as e:
    return f"unknown ({e})"


def get_before_tests_toml(repo_root: Path, rel_path: Path):
  ref_used = "origin/main"
  proc = subprocess.run(
      ["git", "show", f"origin/main:{rel_path}"],
      cwd=repo_root,
      capture_output=True,
      text=True,
  )
  if proc.returncode != 0:
    ref_used = "HEAD"
    proc = subprocess.run(
        ["git", "show", f"HEAD:{rel_path}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
      raise ExerciseRunError(
          f"Failed to read before version of {rel_path} from origin/main and"
          " HEAD"
      )
  return proc.stdout, ref_used


def parse_counts(toml_data: dict):
  included = sum(
      1
      for v in toml_data.values()
      if isinstance(v, dict) and v.get("include") is not False
  )
  excluded = sum(
      1
      for v in toml_data.values()
      if isinstance(v, dict) and v.get("include") is False
  )
  return {"excluded": excluded, "included": included}


def compare_toml_data(before_data: dict, after_data: dict):
  before_keys = set(k for k, v in before_data.items() if isinstance(v, dict))
  after_keys = set(k for k, v in after_data.items() if isinstance(v, dict))
  if before_keys != after_keys:
    diff = before_keys.symmetric_difference(after_keys)
    raise AssertionError(f"UUID mismatch between before and after: {diff}")

  for uuid in before_keys:
    b_entry = before_data[uuid]
    a_entry = after_data[uuid]

    b_inc = b_entry.get("include", True)
    a_inc = a_entry.get("include", True)
    if b_inc != a_inc:
      raise AssertionError(
          f"Include mismatch for UUID {uuid}: before={b_inc}, after={a_inc}"
      )

    b_desc = b_entry.get("description")
    a_desc = a_entry.get("description")
    if b_desc != a_desc:
      raise AssertionError(
          f"Description mismatch for UUID {uuid}: before={b_desc},"
          f" after={a_desc}"
      )


def check_stub_unchanged(repo_root: Path, solution_rel: str):
  ref_used = "origin/main"
  proc = subprocess.run(
      ["git", "diff", "--quiet", "origin/main", "--", solution_rel],
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
          ["git", "diff", "--quiet", "HEAD", "--", solution_rel], cwd=repo_root
      )

  if proc.returncode != 0:
    raise ExerciseRunError(
        f"Learner stub in real repo has modifications relative to {ref_used}:"
        f" {solution_rel}"
    )
  return ref_used


def run_self_test():
  (
      solution_file,
      test_file,
      example_file,
      solution_rel,
      test_rel,
      example_rel,
  ) = load_config()
  print("Running self-test scenarios...")

  # Scenario (a): assertion failure when using learner stub as solution (one-line summary)
  scenario_a_ok = False
  try:
    stub_results, _ = run_exercise(solution_file)
    check_all_pass(stub_results, verbose=False)
    print("Scenario (a) FAILED: all-pass assertion did not raise error.")
  except AssertionError as e:
    scenario_a_ok = True
    print(f"Scenario (a) correctly failed: {e}")
  except Exception as e:
    print(f"Scenario (a) FAILED with unexpected exception type: {e}")

  # Scenario (b): non-zero child exit
  scenario_b_ok = False
  try:
    run_exercise(
        example_file, test_sql_text="SELECT * FROM table_that_does_not_exist;"
    )
    print("Scenario (b) FAILED: non-zero child exit did not raise error.")
  except ExerciseRunError as e:
    scenario_b_ok = True
    print(f"Scenario (b) correctly failed: {e}")
  except Exception as e:
    print(f"Scenario (b) FAILED with unexpected exception type: {e}")

  # Scenario (c): zero-test run
  scenario_c_ok = False
  test_sql_zero = """.mode json
.once './output.json'
.print []
SELECT 1 WHERE 0;
"""
  try:
    zero_results, _ = run_exercise(example_file, test_sql_text=test_sql_zero)
    check_zero_tests(zero_results)
    print("Scenario (c) FAILED: zero-test check did not raise error.")
  except AssertionError as e:
    scenario_c_ok = True
    print(f"Scenario (c) correctly failed: {e}")
  except Exception as e:
    print(f"Scenario (c) FAILED with unexpected exception type: {e}")

  # Scenario (d): before/after comparison against modified copy in temp directory
  scenario_d_ok = False
  try:
    with open(TESTS_TOML_PATH, "rb") as f:
      real_toml_data = tomllib.load(f)
    with tempfile.TemporaryDirectory() as tmp_d:
      temp_toml_copy = Path(tmp_d) / "tests.toml"
      modified_data = copy.deepcopy(real_toml_data)
      target_uuid = "a577bacc-106b-496e-9792-b3083ea8705e"
      if target_uuid in modified_data:
        modified_data[target_uuid]["include"] = False
      compare_toml_data(real_toml_data, modified_data)
      print("Scenario (d) FAILED: comparison did not fail with flipped include.")
  except AssertionError as e:
    scenario_d_ok = True
    print(f"Scenario (d) correctly failed: {e}")
  except Exception as e:
    print(f"Scenario (d) FAILED with unexpected exception type: {e}")

  if scenario_a_ok and scenario_b_ok and scenario_c_ok and scenario_d_ok:
    print("ALL SELF-TEST SCENARIOS PASSED")
    sys.exit(0)
  else:
    print("ONE OR MORE SELF-TEST SCENARIOS FAILED", file=sys.stderr)
    sys.exit(1)


def main():
  parser = argparse.ArgumentParser(
      description="Exercise test validation runner"
  )
  parser.add_argument(
      "--self-test",
      action="store_true",
      help="Run self-test to verify failure paths",
  )
  args = parser.parse_args()

  if args.self_test:
    run_self_test()

  (
      solution_file,
      test_file,
      example_file,
      solution_rel,
      test_rel,
      example_rel,
  ) = load_config()

  # 1. Run with reference example.sql as solution (captures detail.json)
  results, detail_results = run_exercise(example_file)

  # 2. FAIL on zero tests. Print "Executed N cases"
  n_cases = len(results)
  check_zero_tests(results)
  print(f"Executed {n_cases} cases")

  # 3. Before/after counts from tests.toml
  rel_tests_toml = TESTS_TOML_PATH.relative_to(REPO_ROOT)
  before_text, ref_used = get_before_tests_toml(REPO_ROOT, rel_tests_toml)
  before_data = tomllib.loads(before_text)

  with open(TESTS_TOML_PATH, "rb") as f:
    after_data = tomllib.load(f)

  counts_before = parse_counts(before_data)
  counts_after = parse_counts(after_data)

  # Validate that include and description are unchanged for all UUIDs
  compare_toml_data(before_data, after_data)

  print(
      f"Counts before: {counts_before['included']} included,"
      f" {counts_before['excluded']} excluded; after:"
      f" {counts_after['included']} included, {counts_after['excluded']}"
      f" excluded (using {ref_used})"
  )

  if n_cases != counts_after["included"]:
    raise ExerciseRunError(
        f"Mismatch: executed {n_cases} cases but tests.toml has"
        f" {counts_after['included']} included cases"
    )

  # 4. FAIL unless every entry has status "pass"
  check_all_pass(results)

  # 5. Negative control: run learner stub and assert it does NOT pass every test
  stub_results, stub_details = run_exercise(solution_file)
  stub_passed = sum(1 for r in stub_results if r.get("status") == "pass")
  stub_failed = sum(1 for r in stub_results if r.get("status") != "pass")
  print(f"Stub cases passed: {stub_passed}, failed: {stub_failed}")
  if stub_failed == 0:
    raise ExerciseRunError(
        "Negative control failure: learner stub passed all tests!"
    )

  # 6. Stronger stub check against origin/main (fallback HEAD)
  stub_ref_used = check_stub_unchanged(
      REPO_ROOT, str(solution_file.relative_to(REPO_ROOT))
  )

  # Selected UUIDs mapping
  selected_uuid_list = [
      "a577bacc-106b-496e-9792-b3083ea8705e",
      "b5d0c360-3b88-489b-8e84-68a1c7a4fa23",
      "473223f4-65f3-46ff-a9f7-7663c7e59440",
  ]
  selected_uuids_data = []
  detail_by_desc = {d["description"]: d for d in detail_results}

  for u in selected_uuid_list:
    entry = after_data.get(u, {})
    full_desc = entry.get("description", "")
    short_desc = full_desc.split(" -> ")[-1] if " -> " in full_desc else full_desc
    matched_detail = detail_by_desc.get(short_desc, {})
    selected_uuids_data.append({
        "actual": matched_detail.get("actual"),
        "description": full_desc,
        "expected": matched_detail.get("expected"),
        "input": matched_detail.get("input"),
        "status": matched_detail.get("status"),
        "uuid": u,
    })

  # F. Write evidence files
  WORK_DIR.mkdir(parents=True, exist_ok=True)

  tool_versions = {
      "git": get_tool_version(["git", "--version"]),
      "jq": get_tool_version(["jq", "--version"]),
      "os": f"{platform.system()} {platform.release()} {platform.machine()}",
      "python": f"Python {platform.python_version()}",
      "sqlite3": get_tool_version(["sqlite3", "--version"]),
  }

  versions_file = WORK_DIR / "versions.txt"
  with open(versions_file, "w", encoding="utf-8") as f:
    for tool in sorted(tool_versions.keys()):
      f.write(f"{tool}: {tool_versions[tool]}\n")

  evidence_data = {
      "counts_after": counts_after,
      "counts_before": counts_before,
      "excluded_count": counts_after["excluded"],
      "executed_count": n_cases,
      "included_count": counts_after["included"],
      "pass_count": sum(1 for r in results if r.get("status") == "pass"),
      "selected_uuids": selected_uuids_data,
      "tests": [
          {
              "actual": d["actual"],
              "description": d["description"],
              "expected": d["expected"],
              "input": d["input"],
              "property": d["property"],
              "status": d["status"],
          }
          for d in detail_results
      ],
      "tool_versions": tool_versions,
  }

  evidence_file = WORK_DIR / "evidence.json"
  with open(evidence_file, "w", encoding="utf-8") as f:
    json.dump(evidence_data, f, indent=2, sort_keys=True)
    f.write("\n")

  print("ALL CHECKS PASSED")
  sys.exit(0)


if __name__ == "__main__":
  main()
