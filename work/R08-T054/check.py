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

PINNED_BEFORE_COMMIT = "4f26956df8ac8c261803011db8bc6a066e2b295c"

RENAME_FROM = "trimmed"
RENAME_TO = "trimmed_inputs"

NAMED_CASES = [
    {
        "uuid": "a5193c61-4a92-4f68-93e2-f554eb385ec6",
        "name": "forceful question",
        "reason": "Tests forceful question branch requiring both is_yelling=1 and is_question=1",
        "expected_silence": 0,
        "expected_question": 1,
        "expected_yelling": 1,
        "expected_reply": "Calm down, I know what I'm doing!",
        "expected_branch": "WHEN bools.is_yelling AND bools.is_question THEN 'Calm down, I know what I''m doing!'",
    },
    {
        "uuid": "4428f28d-4100-4d85-a902-e5a78cb0ecd3",
        "name": "alternate silence",
        "reason": "Tests silence branch requiring is_silence=1 on literal tab whitespace",
        "expected_silence": 1,
        "expected_question": 0,
        "expected_yelling": 0,
        "expected_reply": "Fine. Be that way!",
        "expected_branch": "WHEN bools.is_silence THEN 'Fine. Be that way!'",
    },
    {
        "uuid": "2c7278ac-f955-4eb4-bf8f-e33eb4116a15",
        "name": "multiple line question",
        "reason": "Tests question branch requiring is_question=1 on reimplemented multiline newline input",
        "expected_silence": 0,
        "expected_question": 1,
        "expected_yelling": 0,
        "expected_reply": "Sure.",
        "expected_branch": "WHEN bools.is_question THEN 'Sure.'",
    },
]

EXTRA_INPUTS = [
    "",
    "   ",
    "ARE YOU THERE?",
    "WHAT THE HECK ARE YOU DOING?!",
    "Is this real?   ",
    "\t\t\n\r   \n",
    "can you hear me now?",
    "123 #$%^&*() 456!",
    "Does this work?\r\n",
    "1, 2, 3 GO!",
]

AS_OCCURRENCES = [
    {
        "line": 2,
        "line_text": "trimmed_inputs AS (",
        "kind": "cte_definition",
        "token": "trimmed_inputs",
        "later_lines": [17],
    },
    {
        "line": 5,
        "line_text": "TRIM(input, CHAR(32, 9, 10, 13)) AS trimmed",
        "kind": "column_alias",
        "token": "trimmed",
        "later_lines": [12, 13, 14, 15],
    },
    {
        "line": 9,
        "line_text": "bools AS (",
        "kind": "cte_definition",
        "token": "bools",
        "later_lines": [22, 23, 24, 25, 26, 30, 32],
    },
    {
        "line": 12,
        "line_text": "trimmed = '' AS is_silence,",
        "kind": "column_alias",
        "token": "is_silence",
        "later_lines": [22],
    },
    {
        "line": 13,
        "line_text": "trimmed LIKE '%?' AS is_question,",
        "kind": "column_alias",
        "token": "is_question",
        "later_lines": [24, 26],
    },
    {
        "line": 15,
        "line_text": "AND trimmed = UPPER(trimmed) AS is_yelling",
        "kind": "column_alias",
        "token": "is_yelling",
        "later_lines": [23, 25],
    },
]

OLD_A1_BLOCK = """  )
UPDATE bob
SET
  reply = CASE
    WHEN bools.is_silence THEN 'Fine. Be that way!'
    WHEN bools.is_yelling
    AND bools.is_question THEN 'Calm down, I know what I''m doing!'
    WHEN bools.is_yelling THEN 'Whoa, chill out!'
    WHEN bools.is_question THEN 'Sure.'
    ELSE 'Whatever.'
  END
FROM
  bools
WHERE
  bob.input = bools.input;"""

NEW_A1_BLOCK = """  ),
  answers AS (
    SELECT
      input,
      CASE
        WHEN is_silence THEN 'Fine. Be that way!'
        WHEN is_yelling AND is_question THEN 'Calm down, I know what I''m doing!'
        WHEN is_yelling THEN 'Whoa, chill out!'
        WHEN is_question THEN 'Sure.'
        ELSE 'Whatever.'
      END AS reply
    FROM
      bools
  )
UPDATE bob
SET
  reply = answers.reply
FROM
  answers
WHERE
  bob.input = answers.input;"""

ALTERNATIVES = [
    {
        "id": "A1",
        "description": "extract the CASE into an `answers` CTE",
        "patches": [
            (OLD_A1_BLOCK, NEW_A1_BLOCK, 1),
        ],
        "reason_not_applied": "the issue asks for one readability improvement; this one adds more change than the rename",
    },
    {
        "id": "A2",
        "description": "drop the redundant `bools.` qualifiers in the CASE",
        "patches": [
            ("bools.is_", "is_", 5),
        ],
        "reason_not_applied": "removes qualifiers whose safety depends on `bob` never having a column named like a flag; not needed to clarify AS",
    },
]


class ExerciseRunError(Exception):
    """Exception raised for exercise execution failures."""
    pass


def get_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "exercises" / "practice" / "bob").is_dir():
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
    lines = [l for l in sql.splitlines() if not l.strip().startswith("--")]
    return " ".join("".join(lines).split())


def apply_patches(source: str, patches: list) -> str:
    mutated = source
    for p in patches:
        old_str = p[0]
        new_str = p[1]
        expected_count = p[2] if len(p) > 2 else 1
        count = mutated.count(old_str)
        if count != expected_count:
            raise ExerciseRunError(
                f"Patch drift: target string {old_str!r} occurred {count} times (expected exactly {expected_count}) in source."
            )
        mutated = mutated.replace(old_str, new_str)
    return mutated


def resolve_before_ref(repo_root: Path, pinned_commit: str, fallback_ref: str = "origin/main") -> tuple[str, str]:
    verify_cmd = subprocess.run(
        ["git", "rev-parse", "--verify", f"{pinned_commit}^{{commit}}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if verify_cmd.returncode == 0:
        full_sha = verify_cmd.stdout.strip()
        short_cmd = subprocess.run(
            ["git", "rev-parse", "--short", full_sha],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        return full_sha, short_cmd.stdout.strip()

    fallback_cmd = subprocess.run(
        ["git", "rev-parse", "--verify", f"{fallback_ref}^{{commit}}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if fallback_cmd.returncode == 0:
        full_sha = fallback_cmd.stdout.strip()
        short_cmd = subprocess.run(
            ["git", "rev-parse", "--short", full_sha],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        print(f"Note: PINNED_BEFORE_COMMIT not found; falling back to {fallback_ref}")
        return full_sha, short_cmd.stdout.strip()

    raise ExerciseRunError(
        f"Neither PINNED_BEFORE_COMMIT ({pinned_commit}) nor fallback ref ({fallback_ref}) could be resolved as a valid commit"
    )


def load_before_source(repo_root: Path, ref: str, example_rel: str) -> str:
    show_target = f"{ref}:exercises/practice/bob/{example_rel}"
    proc = subprocess.run(
        ["git", "show", show_target],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise ExerciseRunError(f"Failed to load BEFORE source from git show {show_target}: {proc.stderr}")
    return proc.stdout


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
            detail_query = """
.mode json
.once './detail.json'
SELECT
  t.uuid,
  t.name,
  t.input,
  t.expected,
  b.reply AS actual,
  t.status
FROM
  tests t
LEFT JOIN
  bob b ON b.input = t.input
ORDER BY
  t.rowid;
"""
            existing = dest_test.read_text(encoding="utf-8")
            dest_test.write_text(existing + "\n" + detail_query, encoding="utf-8")

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


def check_before_after_agreement(before_detail: list[dict], after_detail: list[dict]):
    before_by_uuid = {d["uuid"]: d for d in before_detail}
    after_by_uuid = {d["uuid"]: d for d in after_detail}

    if set(before_by_uuid.keys()) != set(after_by_uuid.keys()):
        raise AssertionError("UUID set mismatch between BEFORE and AFTER runs")

    for uuid, b_entry in before_by_uuid.items():
        a_entry = after_by_uuid[uuid]
        act_b = b_entry["actual"]
        act_a = a_entry["actual"]
        exp = b_entry["expected"]
        if not (act_b == act_a == exp):
            raise AssertionError(
                f"Mismatch for case '{b_entry['name']}' ({uuid}): before={act_b!r}, after={act_a!r}, expected={exp!r}"
            )


def run_extra_inputs(exercise_dir: Path, solution_sql: str, inputs: list[str]) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        copy_dir = Path(tmp_dir) / "exercise"
        shutil.copytree(exercise_dir, copy_dir)

        csv_path = copy_dir / "data.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            for inp in inputs:
                writer.writerow([inp, ""])

        (copy_dir / "bob.sql").write_text(solution_sql, encoding="utf-8")

        driver_sql = """
.read ./create_fixture.sql
.read ./bob.sql
.mode json
SELECT input, reply FROM bob;
"""
        driver_path = copy_dir / "driver.sql"
        driver_path.write_text(driver_sql, encoding="utf-8")

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
            raise ExerciseRunError(f"Extra inputs driver failed: {proc.stderr}")

        return json.loads(proc.stdout)


def check_extra_inputs_equivalence(before_results: list[dict], after_results: list[dict]):
    if len(before_results) != len(after_results):
        raise AssertionError("Extra inputs result length mismatch")
    for idx, (b, a) in enumerate(zip(before_results, after_results)):
        if b["input"] != a["input"]:
            raise AssertionError(f"Extra input mismatch at row {idx}: before={b['input']!r} vs after={a['input']!r}")
        if b["reply"] != a["reply"]:
            raise AssertionError(
                f"Extra input reply mismatch at row {idx} for input {b['input']!r}: before={b['reply']!r} vs after={a['reply']!r}"
            )


def check_rename_only(before_sql: str, after_sql: str):
    restored = after_sql.replace(RENAME_TO, RENAME_FROM)
    if restored != before_sql:
        raise AssertionError(
            "Rename-only proof failed: replacing RENAME_TO with RENAME_FROM does not recover BEFORE exactly"
        )

    occurrences_after = after_sql.count(RENAME_TO)
    if occurrences_after != 2:
        raise AssertionError(f"Expected RENAME_TO ({RENAME_TO}) to occur exactly 2 times in AFTER, got {occurrences_after}")

    occurrences_before = before_sql.count(RENAME_TO)
    if occurrences_before != 0:
        raise AssertionError(f"Expected RENAME_TO ({RENAME_TO}) to occur 0 times in BEFORE, got {occurrences_before}")

    if RENAME_FROM not in after_sql:
        raise AssertionError(f"Expected RENAME_FROM ({RENAME_FROM}) to remain present in AFTER (column alias)")

    def find_as_lines(sql: str) -> list[int]:
        lines = []
        for line_num, line_str in enumerate(sql.splitlines(), 1):
            if re.search(r"\bAS\b", line_str, re.IGNORECASE):
                lines.append(line_num)
        return lines

    as_lines_before = find_as_lines(before_sql)
    as_lines_after = find_as_lines(after_sql)
    expected_as_lines = [2, 5, 9, 12, 13, 15]

    if as_lines_before != expected_as_lines:
        raise AssertionError(f"BEFORE AS lines mismatch: got {as_lines_before}, expected {expected_as_lines}")
    if as_lines_after != expected_as_lines:
        raise AssertionError(f"AFTER AS lines mismatch: got {as_lines_after}, expected {expected_as_lines}")

    return occurrences_after, len(as_lines_before), len(as_lines_after)


def verify_as_occurrences(after_sql: str, as_entries: list[dict]):
    lines = after_sql.splitlines()
    for entry in as_entries:
        line_num = entry["line"]
        if line_num > len(lines):
            raise ExerciseRunError(f"AS occurrence line {line_num} exceeds file length ({len(lines)})")
        actual_line = lines[line_num - 1].strip()
        expected_line = entry["line_text"].strip()
        if actual_line != expected_line:
            raise ExerciseRunError(
                f"AS occurrence mismatch at line {line_num}: actual {actual_line!r} != expected {expected_line!r} (entry: {entry})"
            )

        token = entry.get("token")
        if not token:
            if entry["kind"] == "cte_definition":
                token = entry["line_text"].split()[0]
            else:
                token = entry["line_text"].split()[-1].rstrip(",")

        for later_l in entry["later_lines"]:
            if later_l > len(lines):
                raise ExerciseRunError(
                    f"Later line {later_l} for token {token!r} exceeds file length ({len(lines)}) (entry: {entry})"
                )
            target_line = lines[later_l - 1]
            if token == "trimmed":
                # Look for whole word 'trimmed'
                if not re.search(r"\btrimmed\b", target_line):
                    raise ExerciseRunError(
                        f"Later line {later_l} does not contain alias token {token!r}: {target_line!r} (entry: {entry})"
                    )
            else:
                if token not in target_line:
                    raise ExerciseRunError(
                        f"Later line {later_l} does not contain alias token {token!r}: {target_line!r} (entry: {entry})"
                    )
    print(f"AS occurrences verified: {len(as_entries)}/{len(as_entries)} (lines and later uses)")


def check_guard(changed_paths: list[str]) -> list[str]:
    expected_allowed = {"exercises/practice/bob/.meta/example.sql"}
    actual_changed = set(changed_paths)
    if actual_changed != expected_allowed:
        diff_extra = actual_changed - expected_allowed
        diff_missing = expected_allowed - actual_changed
        raise ExerciseRunError(
            f"Guard failure: unauthorized files modified under exercises/ or bin/. Extra: {diff_extra}, Missing: {diff_missing}"
        )
    return sorted(actual_changed)


def run_named_cases_trace(exercise_dir: Path, after_sql: str, detail_records: list[dict]):
    cte_part = after_sql[:after_sql.index("UPDATE bob")].strip()
    trace_sql = f"""
.read ./create_fixture.sql
.mode json
{cte_part}
SELECT
  b.input,
  t.trimmed,
  b.is_silence,
  b.is_question,
  b.is_yelling
FROM
  bools b
JOIN
  trimmed_inputs t ON t.input = b.input;
"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        copy_dir = Path(tmp_dir) / "exercise"
        shutil.copytree(exercise_dir, copy_dir)

        driver_path = copy_dir / "trace.sql"
        driver_path.write_text(trace_sql, encoding="utf-8")

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
            raise ExerciseRunError(f"Trace SQL failed: {proc.stderr}")

        trace_data = json.loads(proc.stdout)
        trace_by_input = {row["input"]: row for row in trace_data}

    detail_by_uuid = {d["uuid"]: d for d in detail_records}
    traced_evidence = []

    for named in NAMED_CASES:
        uuid = named["uuid"]
        detail = detail_by_uuid.get(uuid)
        if detail is None:
            raise ExerciseRunError(f"Named case UUID {uuid} not found in detail records")

        inp = detail["input"]
        traced_row = trace_by_input.get(inp)
        if traced_row is None:
            raise ExerciseRunError(f"Named case input {inp!r} not found in traced CTE rows")

        trimmed_val = traced_row["trimmed"]
        silence_val = traced_row["is_silence"]
        question_val = traced_row["is_question"]
        yelling_val = traced_row["is_yelling"]
        reply_val = detail["actual"]
        expected_reply = named["expected_reply"]
        branch_fired = named["expected_branch"]

        if silence_val != named["expected_silence"]:
            raise AssertionError(
                f"Named case {named['name']} ({uuid}) is_silence={silence_val} != expected {named['expected_silence']}"
            )
        if question_val != named["expected_question"]:
            raise AssertionError(
                f"Named case {named['name']} ({uuid}) is_question={question_val} != expected {named['expected_question']}"
            )
        if yelling_val != named["expected_yelling"]:
            raise AssertionError(
                f"Named case {named['name']} ({uuid}) is_yelling={yelling_val} != expected {named['expected_yelling']}"
            )
        if reply_val != expected_reply:
            raise AssertionError(
                f"Named case {named['name']} ({uuid}) reply={reply_val!r} != expected {expected_reply!r}"
            )

        traced_evidence.append({
            "branch": branch_fired,
            "input": inp,
            "is_question": question_val,
            "is_silence": silence_val,
            "is_yelling": yelling_val,
            "name": named["name"],
            "reason": named["reason"],
            "reply": reply_val,
            "trimmed": trimmed_val,
            "uuid": uuid,
        })

    return traced_evidence


def get_tool_version(cmd: list) -> str:
    try:
        return subprocess.check_output(cmd, text=True).strip()
    except Exception as e:
        return f"unknown ({e})"


def run_self_test(repo_root: Path):
    exercise_dir = repo_root / "exercises" / "practice" / "bob"
    solution_file, _, example_file, _, _, example_rel = load_config(exercise_dir)
    after_text = example_file.read_text(encoding="utf-8")
    before_sha, _ = resolve_before_ref(repo_root, PINNED_BEFORE_COMMIT)
    before_text = load_before_source(repo_root, before_sha, example_rel)

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
            after_text,
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
            after_text,
            test_sql_text=test_sql_zero,
        )
        check_zero_tests(zero_results)
        print("Scenario (c) FAILED: zero-test check did not fail.")
    except AssertionError as e:
        scenario_c_ok = True
        print(f"Scenario (c) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (c) FAILED with unexpected exception: {e}")

    # (d) AFTER source where one reply string is changed -> all-cases before/after check fails
    scenario_d_ok = False
    try:
        bad_reply_sql = after_text.replace("'Sure.'", "'Sure'")
        _, bad_detail = run_exercise(exercise_dir, bad_reply_sql, with_detail=True)
        _, orig_detail = run_exercise(exercise_dir, before_text, with_detail=True)
        check_before_after_agreement(orig_detail, bad_detail)
        print("Scenario (d) FAILED: changed reply string was not detected in agreement check.")
    except AssertionError as e:
        scenario_d_ok = True
        print(f"Scenario (d) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (d) FAILED with unexpected exception: {e}")

    # (e) same changed source on extra-inputs check -> reports difference
    scenario_e_ok = False
    try:
        bad_reply_sql = after_text.replace("'Sure.'", "'Sure'")
        before_extra = run_extra_inputs(exercise_dir, before_text, EXTRA_INPUTS)
        bad_extra = run_extra_inputs(exercise_dir, bad_reply_sql, EXTRA_INPUTS)
        check_extra_inputs_equivalence(before_extra, bad_extra)
        print("Scenario (e) FAILED: changed reply string was not detected in extra inputs check.")
    except AssertionError as e:
        scenario_e_ok = True
        print(f"Scenario (e) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (e) FAILED with unexpected exception: {e}")

    # (f) AFTER source with one extra comment line added -> rename-only proof fails
    scenario_f_ok = False
    try:
        extra_comment_sql = "-- extra comment line\n" + after_text
        check_rename_only(before_text, extra_comment_sql)
        print("Scenario (f) FAILED: extra comment line was not rejected by rename-only proof.")
    except AssertionError as e:
        scenario_f_ok = True
        print(f"Scenario (f) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (f) FAILED with unexpected exception: {e}")

    # (g) guard function fed changed-paths list plus exercises/practice/bob/bob.sql -> fails
    scenario_g_ok = False
    try:
        bad_changed_paths = [
            "exercises/practice/bob/.meta/example.sql",
            "exercises/practice/bob/bob.sql",
        ]
        check_guard(bad_changed_paths)
        print("Scenario (g) FAILED: unauthorized changed file was not rejected by guard.")
    except ExerciseRunError as e:
        scenario_g_ok = True
        print(f"Scenario (g) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (g) FAILED with unexpected exception: {e}")

    # (h) bogus PINNED commit -> clear failure message
    scenario_h_ok = False
    try:
        resolve_before_ref(
            repo_root,
            "0000000000000000000000000000000000000000",
            fallback_ref="nonexistent_fallback_branch_ref",
        )
        print("Scenario (h) FAILED: bogus commit was not rejected.")
    except ExerciseRunError as e:
        scenario_h_ok = True
        print(f"Scenario (h) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (h) FAILED with unexpected exception: {e}")

    # (i) named-case trace fed wrong expected flag -> assertion failure
    scenario_i_ok = False
    try:
        _, after_detail = run_exercise(exercise_dir, after_text, with_detail=True)
        bad_named_cases = [dict(NAMED_CASES[0])]
        bad_named_cases[0]["expected_silence"] = 999  # bogus flag
        saved_named = NAMED_CASES[:]
        NAMED_CASES.clear()
        NAMED_CASES.extend(bad_named_cases)
        try:
            run_named_cases_trace(exercise_dir, after_text, after_detail)
            print("Scenario (i) FAILED: wrong expected flag in trace was not rejected.")
        finally:
            NAMED_CASES.clear()
            NAMED_CASES.extend(saved_named)
    except AssertionError as e:
        scenario_i_ok = True
        print(f"Scenario (i) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (i) FAILED with unexpected exception: {e}")

    # (j) alternative patch with wrong expected_count -> patch-drift failure
    scenario_j_ok = False
    try:
        apply_patches(before_text, [("bools.is_", "is_", 99)])
        print("Scenario (j) FAILED: wrong expected_count was not rejected.")
    except ExerciseRunError as e:
        scenario_j_ok = True
        print(f"Scenario (j) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (j) FAILED with unexpected exception: {e}")

    # (k) wrong later line in AS_OCCURRENCES -> failure
    scenario_k_ok = False
    try:
        bad_as_entries = [dict(e) for e in AS_OCCURRENCES]
        bad_as_entries[0]["later_lines"] = [1]  # Line 1 does not contain trimmed_inputs
        verify_as_occurrences(after_text, bad_as_entries)
        print("Scenario (k) FAILED: wrong later line in AS_OCCURRENCES was not rejected.")
    except ExerciseRunError as e:
        scenario_k_ok = True
        print(f"Scenario (k) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (k) FAILED with unexpected exception: {e}")

    scenarios = [
        scenario_a_ok,
        scenario_b_ok,
        scenario_c_ok,
        scenario_d_ok,
        scenario_e_ok,
        scenario_f_ok,
        scenario_g_ok,
        scenario_h_ok,
        scenario_i_ok,
        scenario_j_ok,
        scenario_k_ok,
    ]
    passed_count = sum(1 for s in scenarios if s)
    total_count = len(scenarios)

    if passed_count == total_count:
        print(f"Self-test: {passed_count}/{total_count} scenarios correctly rejected")
        print("ALL SELF-TEST SCENARIOS PASSED")
        sys.exit(0)
    else:
        print(f"Self-test: {passed_count}/{total_count} scenarios rejected (FAILED)", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Bob reference rename verification")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test failure scenarios",
    )
    args = parser.parse_args()

    repo_root = get_repo_root()
    exercise_dir = repo_root / "exercises" / "practice" / "bob"
    work_dir = Path(__file__).resolve().parent

    if args.self_test:
        run_self_test(repo_root)

    solution_file, _, example_file, _, _, example_rel = load_config(exercise_dir)
    after_source = example_file.read_text(encoding="utf-8")

    # B. Resolve BEFORE ref and source
    before_sha_full, before_sha_short = resolve_before_ref(repo_root, PINNED_BEFORE_COMMIT)
    before_source = load_before_source(repo_root, before_sha_full, example_rel)
    print(f"BEFORE ref: {before_sha_short}")

    # D.1 tests.toml and BEFORE run
    tests_toml_path = exercise_dir / ".meta" / "tests.toml"
    with open(tests_toml_path, "rb") as f:
        toml_data = tomllib.load(f)
    total_count = len(toml_data)
    included_uuids = {k for k, v in toml_data.items() if isinstance(v, dict) and v.get("include") is not False}
    excluded_count = total_count - len(included_uuids)
    reimplemented_uuids = {v["reimplements"] for v in toml_data.values() if isinstance(v, dict) and "reimplements" in v}
    expected_rendered = included_uuids - reimplemented_uuids
    print(f"tests.toml: {total_count} total, {len(included_uuids)} included, {excluded_count} excluded")

    before_results, before_detail = run_exercise(exercise_dir, before_source, with_detail=True)
    check_zero_tests(before_results)
    check_all_pass(before_results)
    executed_n = len(before_results)
    if executed_n != len(expected_rendered) or executed_n != len(before_detail) or executed_n == 0:
        raise ExerciseRunError(
            f"Executed count ({executed_n}) mismatch: expected {len(expected_rendered)}, detail={len(before_detail)}"
        )
    print(f"Executed {executed_n} cases")

    # D.2 AFTER run
    after_results, after_detail = run_exercise(exercise_dir, after_source, with_detail=True)
    check_zero_tests(after_results)
    check_all_pass(after_results)
    if len(after_results) != executed_n:
        raise ExerciseRunError(f"AFTER executed count ({len(after_results)}) differs from BEFORE ({executed_n})")

    # D.3 Before/after equivalence on all enabled cases
    check_before_after_agreement(before_detail, after_detail)
    print(f"Before/after outputs agree on {executed_n}/{executed_n} enabled cases")

    # D.4 Extra inputs
    before_extra = run_extra_inputs(exercise_dir, before_source, EXTRA_INPUTS)
    after_extra = run_extra_inputs(exercise_dir, after_source, EXTRA_INPUTS)
    check_extra_inputs_equivalence(before_extra, after_extra)
    print(f"Extra inputs: before == after on {len(EXTRA_INPUTS)}/{len(EXTRA_INPUTS)}")

    # D.5 Rename-only proof
    rename_occ_after, as_b, as_a = check_rename_only(before_source, after_source)
    print(f"Rename-only: {rename_occ_after} identifier occurrences changed; AS count {as_b} -> {as_a}")

    # Verify AS occurrences
    verify_as_occurrences(after_source, AS_OCCURRENCES)

    # D.6 Guard
    proc_diff = subprocess.run(
        ["git", "diff", "--name-only", before_sha_full, "--", "exercises", "bin"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if proc_diff.returncode != 0:
        raise ExerciseRunError(f"git diff failed during guard check: {proc_diff.stderr}")
    changed_files = [line.strip() for line in proc_diff.stdout.splitlines() if line.strip()]
    guarded_paths = check_guard(changed_files)
    print("Guard: only .meta/example.sql changed under exercises/ and bin/")

    # D.7 Stub run
    stub_results, _ = run_exercise(exercise_dir, solution_file, with_detail=False)
    stub_pass = sum(1 for r in stub_results if r.get("status") == "pass")
    stub_fail = sum(1 for r in stub_results if r.get("status") != "pass")
    print(f"Stub cases passed: {stub_pass}, failed: {stub_fail}")
    if stub_fail == 0:
        raise ExerciseRunError("Negative control failed: stub passed all tests!")

    # D.8 Trace of NAMED_CASES
    traced_evidence = run_named_cases_trace(exercise_dir, after_source, after_detail)

    # Alternatives check
    alternatives_evidence = []
    for alt in ALTERNATIVES:
        alt_id = alt["id"]
        alt_desc = alt["description"]
        alt_patches = alt["patches"]
        alt_sql = apply_patches(before_source, alt_patches)

        norm_orig = normalize_sql(before_source)
        norm_alt = normalize_sql(alt_sql)
        if norm_orig == norm_alt:
            raise ExerciseRunError(f"Alternative {alt_id}: normalized text is identical to original")

        alt_results, _ = run_exercise(exercise_dir, alt_sql, with_detail=True)
        check_all_pass(alt_results)
        if len(alt_results) != executed_n:
            raise ExerciseRunError(
                f"Alternative {alt_id}: executed count ({len(alt_results)}) differs from BEFORE ({executed_n})"
            )

        alt_extra = run_extra_inputs(exercise_dir, alt_sql, EXTRA_INPUTS)
        check_extra_inputs_equivalence(before_extra, alt_extra)

        alt_diff = list(
            difflib.unified_diff(
                before_source.splitlines(keepends=True),
                alt_sql.splitlines(keepends=True),
                fromfile=".meta/example.sql",
                tofile=".meta/example.sql",
            )
        )
        lines_added = sum(1 for l in alt_diff if l.startswith("+") and not l.startswith("+++"))
        lines_removed = sum(1 for l in alt_diff if l.startswith("-") and not l.startswith("---"))

        print(
            f"Alternative {alt_id}: {len(alt_results)}/{executed_n} pass, extra inputs agree ({len(EXTRA_INPUTS)}/{len(EXTRA_INPUTS)}); not applied"
        )

        alternatives_evidence.append({
            "applied": False,
            "description": alt_desc,
            "executed": len(alt_results),
            "extra_inputs_agree": True,
            "id": alt_id,
            "lines_added": lines_added,
            "lines_removed": lines_removed,
            "passing": len(alt_results),
            "reason_not_applied": alt["reason_not_applied"],
        })

    # D.9 Write evidence and versions
    work_dir.mkdir(parents=True, exist_ok=True)

    tool_versions = {
        "git": get_tool_version(["git", "--version"]),
        "jq": get_tool_version(["jq", "--version"]),
        "os": f"{platform.system()} {platform.release()} {platform.machine()}",
        "python": f"Python {platform.python_version()}",
        "sqlite3": get_tool_version(["sqlite3", "--version"]),
    }

    versions_file = work_dir / "versions.txt"
    with open(versions_file, "w", encoding="utf-8") as f:
        for tool in sorted(tool_versions.keys()):
            f.write(f"{tool}: {tool_versions[tool]}\n")

    diff_lines = list(
        difflib.unified_diff(
            before_source.splitlines(keepends=True),
            after_source.splitlines(keepends=True),
            fromfile=".meta/example.sql",
            tofile=".meta/example.sql",
        )
    )
    unified_diff_str = "".join(diff_lines)

    before_map = {d["uuid"]: d for d in before_detail}
    cases_evidence = [
        {
            "actual_after": d["actual"],
            "actual_before": before_map[d["uuid"]]["actual"],
            "expected": d["expected"],
            "input": d["input"],
            "name": d["name"],
            "status_after": d["status"],
            "status_before": before_map[d["uuid"]]["status"],
            "uuid": d["uuid"],
        }
        for d in after_detail
    ]

    extra_evidence = [
        {
            "after": a["reply"],
            "before": b["reply"],
            "input": json.dumps(b["input"]),
        }
        for b, a in zip(before_extra, after_extra)
    ]

    evidence = {
        "alternatives": alternatives_evidence,
        "as_occurrences": AS_OCCURRENCES,
        "before_ref": {
            "full": before_sha_full,
            "short": before_sha_short,
        },
        "cases": cases_evidence,
        "executed_count": executed_n,
        "extra_inputs": extra_evidence,
        "guard": guarded_paths,
        "named_case_trace": traced_evidence,
        "rename": {
            "as_count_after": as_a,
            "as_count_before": as_b,
            "from": RENAME_FROM,
            "occurrences_after": rename_occ_after,
            "to": RENAME_TO,
        },
        "stub_fail_count": stub_fail,
        "stub_pass_count": stub_pass,
        "tests_toml": {
            "excluded": excluded_count,
            "included": len(included_uuids),
            "total": total_count,
        },
        "tool_versions": tool_versions,
        "unified_diff": unified_diff_str,
    }

    evidence_file = work_dir / "evidence.json"
    with open(evidence_file, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2, sort_keys=True)
        f.write("\n")

    print("ALL CHECKS PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
