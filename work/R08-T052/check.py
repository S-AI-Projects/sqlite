#!/usr/bin/env python3
import sys

# Requirement B: Check at start that jinja2 is importable
try:
    import jinja2
except ImportError:
    print(
        "ERROR: jinja2 is required. Please run this script with ~/venvs/t052/bin/python",
        file=sys.stderr,
    )
    sys.exit(1)

import argparse
import copy
import csv
import difflib
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
import tomllib

# Single constant ANCHOR_UUIDS at the top of the script
ANCHOR_UUIDS = [
    "4ff6c7d7-fcfc-43ef-b8e7-34ff1837a2d3",  # with apostrophes; reimplements 4185a902-...
    "4185a902-bdb0-4074-864c-f416e42a0f19",  # excluded original
    "be72af2b-8afe-4337-b151-b297202e4a7b",  # with quotations
]

VERIFIED_SPECS_COMMIT = "84a96854db1bda581317164d3e6ac6aa01723182"

# Robust regex to extract UUID as the first quoted value in the INSERT rows
UUID_REGEX = re.compile(
    r"^\s*'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})',",
    re.MULTILINE,
)

ISO_8601_REGEX = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?"
)

DETAIL_QUERY_SQL = """
.mode json
.once './detail.json'
SELECT
  t.uuid,
  t.description,
  t.sentence AS input,
  t.expected,
  w.result AS actual,
  t.status
FROM
  tests t
LEFT JOIN
  "word-count" w ON w.sentence = t.sentence
ORDER BY
  t.rowid;
"""


class ExerciseRunError(Exception):
    """Custom exception for validation and exercise run failures."""
    pass


def get_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "exercises" / "practice" / "word-count").is_dir():
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


def validate_specs_dir(specs_dir: Path | None) -> Path:
    error_msg = (
        "ERROR: --specs-dir is required (or set PROBLEM_SPECS_DIR) and must point to a valid problem-specifications checkout.\n"
        "To obtain it, run:\n"
        f"  git clone https://github.com/exercism/problem-specifications <dir> && git -C <dir> checkout {VERIFIED_SPECS_COMMIT}"
    )
    if specs_dir is None:
        raise ExerciseRunError(error_msg)
    specs_path = Path(specs_dir).resolve()
    canonical_file = specs_path / "exercises" / "word-count" / "canonical-data.json"
    if not canonical_file.is_file():
        raise ExerciseRunError(
            f"{error_msg}\n(Missing canonical data at {canonical_file})"
        )
    return specs_path


def load_canonical_data(specs_dir: Path) -> dict[str, dict]:
    canonical_file = specs_dir / "exercises" / "word-count" / "canonical-data.json"
    if not canonical_file.is_file():
        raise ExerciseRunError(
            "ERROR: canonical-data.json not found in problem-specifications directory.\n"
            f"Missing path: {canonical_file}"
        )
    with open(canonical_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases_by_uuid = {}

    def extract_cases(obj):
        if isinstance(obj, dict):
            if "uuid" in obj:
                cases_by_uuid[obj["uuid"]] = obj
            for v in obj.values():
                extract_cases(v)
        elif isinstance(obj, list):
            for item in obj:
                extract_cases(item)

    extract_cases(data)
    return cases_by_uuid


def get_specs_commit(specs_dir: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(specs_dir), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        commit = proc.stdout.strip()
    except Exception as e:
        raise ExerciseRunError(f"Failed to read problem-specifications commit: {e}")

    print(f"problem-specifications commit: {commit}")
    if commit != VERIFIED_SPECS_COMMIT:
        print(
            f"WARNING: problem-specifications commit {commit} differs from verified commit {VERIFIED_SPECS_COMMIT}",
            file=sys.stderr,
        )
    return commit


def normalize_content(text: str) -> tuple[str, int]:
    normalized_lines = []
    count = 0
    for line in text.splitlines(keepends=True):
        if ISO_8601_REGEX.search(line):
            norm_line = ISO_8601_REGEX.sub("<TIMESTAMP>", line)
            normalized_lines.append(norm_line)
            count += 1
        else:
            normalized_lines.append(line)
    return "".join(normalized_lines), count


def compare_files(path1: Path, path2: Path, desc: str) -> int:
    text1 = path1.read_text(encoding="utf-8")
    text2 = path2.read_text(encoding="utf-8")
    norm1, count1 = normalize_content(text1)
    norm2, count2 = normalize_content(text2)
    diff = list(
        difflib.unified_diff(
            norm1.splitlines(keepends=True),
            norm2.splitlines(keepends=True),
            fromfile=str(path1),
            tofile=str(path2),
        )
    )
    if diff:
        diff_preview = "".join(diff[:40])
        print(f"Unified diff ({desc}):\n{diff_preview}", file=sys.stderr)
        raise ExerciseRunError(f"Files differ ({desc}): {path1} vs {path2}")
    return count1 + count2


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def run_regeneration(repo_root: Path, specs_dir: Path):
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        copy1 = tmp_path / "gen1"
        copy2 = tmp_path / "gen2"
        cache1 = tmp_path / "cache1"
        cache2 = tmp_path / "cache2"

        ignore = shutil.ignore_patterns(".git", "__pycache__", "*.pyc")
        shutil.copytree(repo_root, copy1, ignore=ignore)
        shutil.copytree(repo_root, copy2, ignore=ignore)

        for cache in (cache1, cache2):
            symlink_dir = cache / "exercism" / "configlet"
            symlink_dir.mkdir(parents=True, exist_ok=True)
            (symlink_dir / "problem-specifications").symlink_to(specs_dir)

        gen_cmd = [sys.executable, "bin/generate_tests", "--no-pull", "word-count"]

        # Run 1
        env1 = os.environ.copy()
        env1["XDG_CACHE_HOME"] = str(cache1)
        proc1 = subprocess.run(
            gen_cmd,
            cwd=copy1,
            env=env1,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc1.returncode != 0:
            if proc1.stderr:
                print(proc1.stderr, file=sys.stderr)
            raise ExerciseRunError(f"Regeneration run 1 failed with exit code {proc1.returncode}")

        # Run 2
        env2 = os.environ.copy()
        env2["XDG_CACHE_HOME"] = str(cache2)
        proc2 = subprocess.run(
            gen_cmd,
            cwd=copy2,
            env=env2,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc2.returncode != 0:
            if proc2.stderr:
                print(proc2.stderr, file=sys.stderr)
            raise ExerciseRunError(f"Regeneration run 2 failed with exit code {proc2.returncode}")

        # File paths
        gen1_sql = copy1 / "exercises/practice/word-count/create_test_table.sql"
        gen1_csv = copy1 / "exercises/practice/word-count/data.csv"
        gen2_sql = copy2 / "exercises/practice/word-count/create_test_table.sql"
        gen2_csv = copy2 / "exercises/practice/word-count/data.csv"
        real_sql = repo_root / "exercises/practice/word-count/create_test_table.sql"
        real_csv = repo_root / "exercises/practice/word-count/data.csv"

        total_normalized = 0
        total_normalized += compare_files(gen1_sql, gen2_sql, "copy1 vs copy2 create_test_table.sql")
        total_normalized += compare_files(gen1_csv, gen2_csv, "copy1 vs copy2 data.csv")
        total_normalized += compare_files(gen1_sql, real_sql, "copy1 vs committed create_test_table.sql")
        total_normalized += compare_files(gen1_csv, real_csv, "copy1 vs committed data.csv")

        sha_data = {
            "committed_create_test_table_sql": compute_sha256(real_sql),
            "committed_data_csv": compute_sha256(real_csv),
            "regen_create_test_table_sql": compute_sha256(gen1_sql),
            "regen_data_csv": compute_sha256(gen1_csv),
        }

        # Read contents of regenerated files for count and UUID checks
        regen_sql_content = gen1_sql.read_text(encoding="utf-8")
        regen_csv_content = gen1_csv.read_text(encoding="utf-8")

        return (
            proc1.returncode,
            proc2.returncode,
            total_normalized,
            sha_data,
            regen_sql_content,
            regen_csv_content,
        )


def check_counts_and_uuids(tests_toml_path: Path, sql_content: str, csv_content: str):
    with open(tests_toml_path, "rb") as f:
        toml_data = tomllib.load(f)

    total_count = len(toml_data)
    included = {k for k, v in toml_data.items() if isinstance(v, dict) and v.get("include") is not False}
    excluded = {k for k, v in toml_data.items() if isinstance(v, dict) and v.get("include") is False}
    reimplemented = {
        v["reimplements"]
        for v in toml_data.values()
        if isinstance(v, dict) and v.get("include") is not False and "reimplements" in v
    }
    expected_rendered = included - reimplemented

    rendered_uuids = UUID_REGEX.findall(sql_content)
    rendered_uuid_set = set(rendered_uuids)

    import io
    csv_rows = list(csv.reader(io.StringIO(csv_content)))

    print(
        f"tests.toml: {total_count} total, {len(included)} included, {len(excluded)} excluded; "
        f"rendered {len(rendered_uuids)}; data.csv rows {len(csv_rows)}"
    )

    if rendered_uuid_set != expected_rendered:
        diff_missing = expected_rendered - rendered_uuid_set
        diff_extra = rendered_uuid_set - expected_rendered
        raise ExerciseRunError(
            f"Rendered UUID set mismatch: missing={diff_missing}, extra={diff_extra}"
        )

    if len(csv_rows) != len(expected_rendered):
        raise ExerciseRunError(
            f"data.csv row count mismatch: got {len(csv_rows)}, expected {len(expected_rendered)}"
        )

    overlap = rendered_uuid_set & excluded
    if overlap:
        raise ExerciseRunError(f"Excluded UUIDs found in create_test_table.sql: {overlap}")

    counts = {
        "data_csv_rows": len(csv_rows),
        "excluded": len(excluded),
        "included": len(included),
        "reimplemented": len(reimplemented),
        "rendered": len(rendered_uuids),
        "total": total_count,
    }
    return counts, toml_data, rendered_uuids


def run_exercise(
    exercise_dir: Path,
    solution_source: Path,
    is_reference: bool = False,
    test_sql_text: str = None,
):
    solution_file, test_file, example_file, solution_rel, test_rel, example_rel = load_config(exercise_dir)

    with tempfile.TemporaryDirectory() as tmp_dir:
        copy_dir = Path(tmp_dir) / "exercise"
        shutil.copytree(exercise_dir, copy_dir)

        # Overwrite solution file in copy
        shutil.copy2(solution_source, copy_dir / solution_rel)

        dest_test = copy_dir / test_rel
        if test_sql_text is not None:
            dest_test.write_text(test_sql_text, encoding="utf-8")
        elif is_reference:
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
        if is_reference:
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


def check_all_pass(results, verbose: bool = True):
    failing = [r for r in results if r.get("status") != "pass"]
    if failing:
        if verbose:
            for f in failing:
                print(f"FAILED: {f.get('description')} - {f.get('message')}", file=sys.stderr)
        raise AssertionError(f"{len(failing)} tests failed in run")


def check_zero_tests(results):
    if len(results) == 0:
        raise AssertionError("Zero tests executed")


def check_anchor_inputs(rendered_anchors: list[dict], canonical_cases: dict[str, dict]):
    """Requirement 3c: Check that rendered anchor inputs in detail.json match canonical input strings."""
    matched = 0
    total = len(rendered_anchors)
    for a in rendered_anchors:
        u = a["uuid"]
        detail_input = a.get("input")
        if u not in canonical_cases:
            raise ExerciseRunError(f"Anchor UUID {u} is missing from canonical data")
        c_case = canonical_cases[u]
        raw_input = c_case.get("input")
        canonical_str = (
            raw_input.get("sentence")
            if isinstance(raw_input, dict) and "sentence" in raw_input
            else str(raw_input)
        )
        if detail_input != canonical_str:
            raise ExerciseRunError(
                f"Anchor input mismatch for {u}:\n"
                f"  detail.json input: {detail_input!r}\n"
                f"  canonical string:  {canonical_str!r}"
            )
        matched += 1

    print(f"Anchor inputs match canonical data: {matched}/{total}")
    return matched


def guard_check(repo_root: Path):
    target_rel = "exercises/practice/word-count"
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


def get_tool_version(cmd: list) -> str:
    try:
        return subprocess.check_output(cmd, text=True).strip()
    except Exception as e:
        return f"unknown ({e})"


def run_self_test(repo_root: Path, specs_dir: Path | None):
    exercise_dir = repo_root / "exercises" / "practice" / "word-count"
    solution_file, test_file, example_file, _, _, _ = load_config(exercise_dir)
    print("Running self-test scenarios...")

    # (a) stub as solution -> all-pass assertion fails
    scenario_a_ok = False
    try:
        stub_results, _ = run_exercise(exercise_dir, solution_file, is_reference=False)
        check_all_pass(stub_results, verbose=False)
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
            example_file,
            is_reference=False,
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
            example_file,
            is_reference=False,
            test_sql_text=test_sql_zero,
        )
        check_zero_tests(zero_results)
        print("Scenario (c) FAILED: zero-test check did not fail.")
    except AssertionError as e:
        scenario_c_ok = True
        print(f"Scenario (c) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (c) FAILED with unexpected exception: {e}")

    # (d) change one character in regenerated create_test_table.sql -> comparison reports difference
    scenario_d_ok = False
    try:
        with tempfile.TemporaryDirectory() as tmp_d:
            tmp_path = Path(tmp_d)
            f1 = tmp_path / "orig.sql"
            f2 = tmp_path / "mutated.sql"
            real_sql = exercise_dir / "create_test_table.sql"
            content = real_sql.read_text(encoding="utf-8")
            f1.write_text(content, encoding="utf-8")
            # Mutate one character
            f2.write_text(content.replace("'word'", "'ward'", 1), encoding="utf-8")
            compare_files(f1, f2, "self-test mutation")
            print("Scenario (d) FAILED: file comparison did not detect difference.")
    except ExerciseRunError as e:
        scenario_d_ok = True
        print(f"Scenario (d) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (d) FAILED with unexpected exception: {e}")

    # (e) --specs-dir pointing at an empty temp directory -> clear failure message
    scenario_e_ok = False
    try:
        with tempfile.TemporaryDirectory() as empty_dir:
            validate_specs_dir(Path(empty_dir))
            print("Scenario (e) FAILED: empty specs dir was not rejected.")
    except ExerciseRunError as e:
        scenario_e_ok = True
        print(f"Scenario (e) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (e) FAILED with unexpected exception: {e}")

    # (f) feed check (c) a wrong canonical input -> check_anchor_inputs fails
    scenario_f_ok = False
    try:
        mock_rendered = [
            {
                "uuid": "4ff6c7d7-fcfc-43ef-b8e7-34ff1837a2d3",
                "input": "'First: don't laugh. Then: don't cry. You're getting it.'",
            }
        ]
        mock_canonical = {
            "4ff6c7d7-fcfc-43ef-b8e7-34ff1837a2d3": {
                "uuid": "4ff6c7d7-fcfc-43ef-b8e7-34ff1837a2d3",
                "input": {"sentence": "WRONG CANONICAL INPUT SENTENCE"},
                "expected": {"first": 1},
            }
        }
        check_anchor_inputs(mock_rendered, mock_canonical)
        print("Scenario (f) FAILED: wrong canonical input was not rejected.")
    except ExerciseRunError as e:
        scenario_f_ok = True
        print(f"Scenario (f) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (f) FAILED with unexpected exception: {e}")

    if (
        scenario_a_ok
        and scenario_b_ok
        and scenario_c_ok
        and scenario_d_ok
        and scenario_e_ok
        and scenario_f_ok
    ):
        print("ALL SELF-TEST SCENARIOS PASSED")
        sys.exit(0)
    else:
        print("ONE OR MORE SELF-TEST SCENARIOS FAILED", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Word-Count exercise validation check")
    parser.add_argument(
        "--specs-dir",
        type=str,
        default=os.getenv("PROBLEM_SPECS_DIR"),
        help="Path to problem-specifications directory",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test failure scenarios",
    )
    args = parser.parse_args()

    repo_root = get_repo_root()
    exercise_dir = repo_root / "exercises" / "practice" / "word-count"
    work_dir = Path(__file__).resolve().parent

    if args.self_test:
        specs_path = Path(args.specs_dir) if args.specs_dir else None
        run_self_test(repo_root, specs_path)

    # Validate specs-dir (never download anything)
    specs_dir = validate_specs_dir(args.specs_dir)

    # Load canonical cases from specs_dir
    canonical_cases = load_canonical_data(specs_dir)

    # C. Record problem-specifications commit
    specs_commit = get_specs_commit(specs_dir)

    # D. Regeneration check
    (
        run1_exit,
        run2_exit,
        ts_normalized,
        sha_data,
        regen_sql_content,
        regen_csv_content,
    ) = run_regeneration(repo_root, specs_dir)

    # E. Count & UUID checks
    tests_toml_path = exercise_dir / ".meta" / "tests.toml"
    counts, toml_data, rendered_uuids = check_counts_and_uuids(
        tests_toml_path, regen_sql_content, regen_csv_content
    )

    # F. Test run with reference and stub
    solution_file, test_file, example_file, _, _, _ = load_config(exercise_dir)

    ref_results, detail_results = run_exercise(exercise_dir, example_file, is_reference=True)
    check_zero_tests(ref_results)
    if len(ref_results) != counts["rendered"]:
        raise ExerciseRunError(
            f"Executed count ({len(ref_results)}) does not match rendered count ({counts['rendered']})"
        )
    print(f"Executed {len(ref_results)} cases")
    check_all_pass(ref_results)

    stub_results, _ = run_exercise(exercise_dir, solution_file, is_reference=False)
    stub_pass = sum(1 for r in stub_results if r.get("status") == "pass")
    stub_fail = sum(1 for r in stub_results if r.get("status") != "pass")
    print(f"Stub cases passed: {stub_pass}, failed: {stub_fail}")
    if stub_fail == 0:
        raise ExerciseRunError("Negative control failed: learner stub passed all tests!")

    # Check (c): Rendered anchor inputs match canonical data
    rendered_anchors = [d for d in detail_results if d["uuid"] in ANCHOR_UUIDS]
    check_anchor_inputs(rendered_anchors, canonical_cases)

    # G. Guard check against origin/main
    guard_check(repo_root)

    # H. Build evidence
    work_dir.mkdir(parents=True, exist_ok=True)

    # Anchor cases mapping
    detail_by_uuid = {d["uuid"]: d for d in detail_results} if detail_results else {}
    anchors_data = []

    # Map rendered locations
    rendered_row_indices = {u: idx + 1 for idx, u in enumerate(rendered_uuids)}

    for u in ANCHOR_UUIDS:
        if u not in canonical_cases:
            raise ExerciseRunError(f"Anchor UUID {u} missing from canonical data")
        c_case = canonical_cases[u]
        canonical_input = c_case.get("input")
        canonical_expected = c_case.get("expected")

        t_entry = toml_data.get(u, {})
        full_desc = t_entry.get("description", "")
        include_val = t_entry.get("include", True)
        reimplements_val = t_entry.get("reimplements")

        reimplemented_by_val = None
        for other_u, other_v in toml_data.items():
            if isinstance(other_v, dict) and other_v.get("reimplements") == u:
                reimplemented_by_val = other_u
                break

        in_rendered = u in rendered_uuids
        rendered_loc = None
        det = detail_by_uuid.get(u, {})
        if in_rendered:
            row_idx = rendered_row_indices.get(u)
            rendered_loc = f"create_test_table.sql (row {row_idx}), data.csv (row {row_idx})"

        anchors_data.append({
            "actual": det.get("actual"),
            "canonical_expected": canonical_expected,
            "canonical_input": canonical_input,
            "expected": det.get("expected"),
            "full_description": full_desc,
            "in_rendered_output": in_rendered,
            "include": include_val,
            "reimplemented_by": reimplemented_by_val,
            "reimplements": reimplements_val,
            "rendered_location": rendered_loc,
            "status": det.get("status"),
            "uuid": u,
        })

    tool_versions = {
        "git": get_tool_version(["git", "--version"]),
        "jinja2": jinja2.__version__,
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
        "anchors": anchors_data,
        "counts": counts,
        "executed_count": len(ref_results),
        "files_identical_between_runs": True,
        "files_identical_to_committed": True,
        "generator_command": "python3 bin/generate_tests --no-pull word-count",
        "pass_count": sum(1 for r in ref_results if r.get("status") == "pass"),
        "regen_run1_exit": run1_exit,
        "regen_run2_exit": run2_exit,
        "sha256": sha_data,
        "specs_commit": specs_commit,
        "stub_fail_count": stub_fail,
        "stub_pass_count": stub_pass,
        "tests": [
            {
                "actual": d["actual"],
                "description": d["description"],
                "expected": d["expected"],
                "input": d["input"],
                "status": d["status"],
                "uuid": d["uuid"],
            }
            for d in detail_results
        ],
        "timestamp_lines_normalized": ts_normalized,
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
