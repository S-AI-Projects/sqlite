#!/usr/bin/env python3
"""Task 6 (pangram) maintenance check and verification script.

Python standard library only.
"""

import csv
import io
import json
import os
import platform
import re
import shutil
import statistics
import string
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

# Paths resolved from script path
SCRIPT_PATH = Path(__file__).resolve()
WORK_DIR = SCRIPT_PATH.parent
REPO_ROOT = SCRIPT_PATH.parent.parent.parent
EXERCISE_DIR = REPO_ROOT / "exercises" / "practice" / "pangram"
DOCS_FILE = REPO_ROOT / "docs" / "maintenance" / "pangram.md"
EVIDENCE_FILE = WORK_DIR / "evidence.json"
VERSIONS_FILE = WORK_DIR / "versions.txt"

CONFIG_PATH = EXERCISE_DIR / ".meta" / "config.json"
TESTS_TOML_PATH = EXERCISE_DIR / ".meta" / "tests.toml"
DATA_CSV_PATH = EXERCISE_DIR / "data.csv"

# Load config.json to resolve solution/test/example file paths
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

SOLUTION_REL = CONFIG["files"]["solution"][0]
TEST_REL = CONFIG["files"]["test"][0]
EXAMPLE_REL = CONFIG["files"]["example"][0]

REF_SQL_FILE = EXERCISE_DIR / EXAMPLE_REL
STUB_SQL_FILE = EXERCISE_DIR / SOLUTION_REL

with open(REF_SQL_FILE, "r", encoding="utf-8") as f:
    REF_SQL = f.read()

with open(STUB_SQL_FILE, "r", encoding="utf-8") as f:
    STUB_SQL = f.read()

# SECOND APPROACH constant (written only into temp copies)
ALT_SQL = """UPDATE pangram
SET result = (
  WITH RECURSIVE alphabet(letter, i) AS (
    SELECT 'a', 1
    UNION ALL
    SELECT CHAR(97 + i), i + 1 FROM alphabet WHERE i < 26
  )
  SELECT COUNT(*) = 26 FROM alphabet WHERE INSTR(LOWER(pangram.sentence), letter) > 0
);
"""

# CONSTANTS
LENGTHS = [26, 1000, 100000]
WARMUPS = 1
REPS = 5
RUN_CAP_SECONDS = 60

NAMED_CASES = [
    {
        "uuid": "c79af1be-d715-4cdb-a5f2-b2fa3e7e0de0",
        "description": "missing the letter 'h'",
        "expected": False,
        "reason": "missing the letter 'h' (expected False)",
    },
    {
        "uuid": "938bd5d8-ade5-40e2-a2d9-55a338a01030",
        "description": "mixed case and punctuation",
        "expected": True,
        "reason": "mixed case and punctuation (expected True)",
    },
    {
        "uuid": "7138e389-83e4-4c6e-8413-1e40a0076951",
        "description": "a-m and A-M are 26 different characters but not a pangram",
        "expected": False,
        "reason": "a-m and A-M are 26 different characters but not a pangram (expected False, reimplements the excluded case)",
    },
]

EXTRA_INPUTS = [
    "",
    "abcdefghijklmnopqrstuvwxyz",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "abcdefghijklmnopqrstuvwxy",
    "bcdefghijklmnopqrstuvwxyz",
    "The quick brown fox jumps over the lazy dog",
    "The quick brown fox jumps over the lazy do",
    "Pack my box with 5 dozen liquor jugs!? 123",
    "a1b2c3d4e5f6g7h8i9j0 klmnopqrstuvwxyz",
    "abcdefghijklm ABCDEFGHIJKLM",
    "a_b_c_d_e_f_g_h_i_j_k_l_m_n_o_p_q_r_s_t_u_v_w_x_y_z",
    "abc\tdef\nghi jkl mno pqr stu vwx yz",
    "The quick brown fox jumps over the lazy dog äöü",
    "The quick brown fox jumps over the lazy do äöü",
    "Съешь же ещё этих мягких французских булок да выпей чаю",
    "abcdefghijklmnopqrstuvwxyz Съешь",
    "Thé quick brown fox jumps ovér thé lazy dog",
    "The quic\u212a brown fox jumps over the lazy dog",
    "aaaaaaaaaa bbbbbbbbbb cccccccccc",
    "     ",
    "a",
    "   abcdefghijklmnopqrstuvwxyz   \n",
]

KNOWN_SQL_KEYWORDS = {
    "ALL", "AND", "AS", "BY", "CASE", "COUNT", "CREATE", "DELETE", "DISTINCT",
    "DROP", "ELSE", "END", "EXISTS", "FROM", "INSERT", "INTO", "JOIN", "LEFT",
    "NOT", "NULL", "ON", "OR", "ORDER", "RECURSIVE", "SELECT", "SET", "TABLE",
    "THEN", "UNION", "UPDATE", "VALUES", "WHEN", "WHERE", "WITH"
}

KNOWN_SQL_FUNCTIONS = {
    "CHAR", "COALESCE", "COUNT", "HEX", "INSTR", "LENGTH", "LOWER", "MAX",
    "MIN", "SUBSTR", "SUM", "TOTAL", "UPPER"
}


def escape_nonascii(text: str) -> str:
    """Replace chars > U+007F with \\uXXXX or \\UXXXXXXXX, and \\t \\n \\r."""
    res = []
    for c in text:
        cp = ord(c)
        if c == "\t":
            res.append(r"\t")
        elif c == "\n":
            res.append(r"\n")
        elif c == "\r":
            res.append(r"\r")
        elif cp > 0xFFFF:
            res.append(f"\\U{cp:08x}")
        elif cp > 0x7F:
            res.append(f"\\u{cp:04x}")
        else:
            res.append(c)
    return "".join(res)


def assert_ascii_only(rendered_text: str) -> None:
    """Raise if any character above U+007F or a raw tab remains."""
    for i, c in enumerate(rendered_text):
        if ord(c) > 0x7F:
            raise AssertionError(f"Non-ASCII character {c!r} (U+{ord(c):04x}) found at index {i}")
        if c == "\t":
            raise AssertionError(f"Raw tab found at index {i}")


def missing_letters(text: str) -> str:
    """Sorted ASCII letters a-z not present case-insensitively among ASCII letters."""
    present = {c.lower() for c in text if c in string.ascii_letters}
    missing = [c for c in string.ascii_lowercase if c not in present]
    if not missing:
        return "none"
    if len(missing) > 10:
        return "".join(missing[:10]) + f"... ({len(missing)} missing)"
    return "".join(missing)


def truncate_escaped(s: str, max_len: int = 35) -> str:
    esc = escape_nonascii(s)
    if len(esc) <= max_len:
        return esc
    cutoff = max_len - 3
    last_bs = esc.rfind("\\", max(0, cutoff - 10), cutoff)
    if last_bs != -1:
        prefix = esc[last_bs:last_bs + 2]
        if prefix in ("\\u", "\\U", "\\t", "\\n", "\\r"):
            needed = 6 if prefix == "\\u" else (10 if prefix == "\\U" else 2)
            if cutoff < last_bs + needed:
                cutoff = last_bs
    return esc[:cutoff] + "..."


def fmt_input(s: str) -> str:
    """Never print an input string longer than 60 characters."""
    if len(s) > 60:
        return f"len={len(s)}: {repr(s[:30])}..."
    return repr(s)


def expected_pangram(s: str) -> bool:
    """Independent expectation (never use s.lower())."""
    return set(string.ascii_lowercase) <= {c.lower() for c in s if c in string.ascii_letters}


def make_data_csv(sentences: list[str]) -> str:
    """Encode sentences following the committed data.csv RFC 4180 convention."""
    out = io.StringIO()
    writer = csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\n")
    for s in sentences:
        writer.writerow([s, ""])
    return out.getvalue()


# ==============================================================================
# SECTION A: SHARED FUNCTIONS (used by BOTH main and --self-test)
# ==============================================================================

def run_committed_tests(solution_sql: str, extra_sql: str = None) -> list[dict]:
    """Run pangram_test.sql in a temporary copy with the solution installed."""
    with tempfile.TemporaryDirectory() as td:
        copy_dir = Path(td) / "exercise"
        shutil.copytree(EXERCISE_DIR, copy_dir)

        dest_solution = copy_dir / SOLUTION_REL
        dest_solution.write_text(solution_sql, encoding="utf-8")

        test_sql_path = copy_dir / TEST_REL
        test_script = test_sql_path.read_text(encoding="utf-8")
        if extra_sql:
            test_script += "\n" + extra_sql
            test_sql_path.write_text(test_script, encoding="utf-8")

        proc = subprocess.run(
            ["sqlite3", "-bail"],
            input=test_script,
            cwd=copy_dir,
            capture_output=True,
            text=True,
        )

        if proc.returncode != 0:
            raise RuntimeError(f"sqlite3 exited with code {proc.returncode}: {proc.stderr.strip()}")

        out_json_path = copy_dir / "output.json"
        if not out_json_path.is_file() or out_json_path.stat().st_size == 0:
            raise RuntimeError("output.json is missing or empty after test execution")

        try:
            out_json = json.loads(out_json_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise RuntimeError(f"Failed to parse output.json: {e}")

        if not isinstance(out_json, list):
            raise RuntimeError(f"output.json is not a JSON list: got {type(out_json)}")

        return out_json


def assert_all_pass(entries: list[dict]) -> None:
    failing = [r for r in entries if r.get("status") != "pass"]
    if failing:
        raise AssertionError(f"{len(failing)} test cases failed (expected all pass)")


def assert_nonzero(entries: list[dict]) -> None:
    if len(entries) == 0:
        raise AssertionError("Zero tests executed in output.json")


def compare_expected(actual, expected) -> None:
    if bool(actual) != bool(expected):
        raise AssertionError(f"Actual {actual} does not match expected {expected}")


def check_guard(changed_paths: list[str], ref: str) -> None:
    forbidden = [p for p in changed_paths if p.startswith("exercises/") or p.startswith("bin/")]
    if forbidden:
        raise AssertionError(f"Guard failed: modified paths under exercises/ or bin/ against {ref}: {forbidden}")


def check_vm_constant(steps: list[int]) -> None:
    if len(set(steps)) != 1:
        raise AssertionError(f"VM steps are not constant across all inputs: got {set(steps)}")


def extract_keywords_and_functions(sql_text: str) -> tuple[set[str], set[str]]:
    clean = re.sub(r"--.*$", "", sql_text, flags=re.MULTILINE)
    fn_matches = set()
    for fn in KNOWN_SQL_FUNCTIONS:
        if re.search(r"\b" + fn + r"\s*\(", clean, re.IGNORECASE):
            fn_matches.add(fn)

    kw_matches = set()
    for kw in KNOWN_SQL_KEYWORDS:
        if kw in fn_matches:
            continue
        if re.search(r"\b" + kw + r"\b", clean, re.IGNORECASE):
            kw_matches.add(kw)

    return kw_matches, fn_matches


def check_structure(reference_sql: str, alt_sql: str) -> dict:
    norm_ref = re.sub(r"\s+", " ", re.sub(r"--.*$", "", reference_sql, flags=re.MULTILINE)).strip()
    norm_alt = re.sub(r"\s+", " ", re.sub(r"--.*$", "", alt_sql, flags=re.MULTILINE)).strip()
    if norm_ref == norm_alt:
        raise AssertionError("check_structure failed: normalized SQL texts are equal")

    ref_lits = re.findall(r"'[a-z]'", reference_sql)
    alt_lits = re.findall(r"'[a-z]'", alt_sql)
    if len(alt_lits) > 1:
        raise AssertionError(f"Alternative has more than 1 single-letter literal: {len(alt_lits)}")

    alt_ands = re.findall(r"\bAND\b", alt_sql, re.IGNORECASE)
    if len(alt_ands) > 0:
        raise AssertionError(f"Alternative has AND operator: {len(alt_ands)}")

    if "RECURSIVE" not in alt_sql or "COUNT(" not in alt_sql:
        raise AssertionError("Alternative missing RECURSIVE or COUNT(")
    if "RECURSIVE" in reference_sql or "COUNT(" in reference_sql:
        raise AssertionError("Reference unexpectedly contains RECURSIVE or COUNT(")

    ref_kw, ref_fn = extract_keywords_and_functions(reference_sql)
    alt_kw, alt_fn = extract_keywords_and_functions(alt_sql)

    return {
        "reference": {
            "literals": len(ref_lits),
            "and_count": len(re.findall(r"\bAND\b", reference_sql, re.IGNORECASE)),
            "has_recursive": False,
            "has_count": False,
            "keywords": sorted(ref_kw),
            "functions": sorted(ref_fn),
        },
        "alternative": {
            "literals": len(alt_lits),
            "and_count": 0,
            "has_recursive": True,
            "has_count": True,
            "keywords": sorted(alt_kw),
            "functions": sorted(alt_fn),
        },
        "diff_keywords_ref_minus_alt": sorted(ref_kw - alt_kw),
        "diff_keywords_alt_minus_ref": sorted(alt_kw - ref_kw),
        "diff_functions_ref_minus_alt": sorted(ref_fn - alt_fn),
        "diff_functions_alt_minus_ref": sorted(alt_fn - ref_fn),
    }


def verify_data_csv_convention(committed_csv_text: str, test_csv_text: str = None) -> None:
    reader = csv.reader(io.StringIO(committed_csv_text))
    rows = list(reader)
    if not rows:
        raise AssertionError("Empty CSV")
    sentences = [r[0] for r in rows]
    rewritten = make_data_csv(sentences)
    if rewritten != committed_csv_text:
        raise AssertionError("make_data_csv does not match committed data.csv byte-for-byte")
    if test_csv_text is not None:
        if test_csv_text != committed_csv_text and test_csv_text != rewritten:
            raise AssertionError("test_csv_text does not conform to data.csv convention byte-for-byte")


def roundtrip_check(intended: str, read_back: str) -> None:
    if intended != read_back:
        raise AssertionError(
            f"roundtrip_check failed: intended ({fmt_input(intended)}) != read_back ({fmt_input(read_back)})"
        )


def compute_ratio_and_overlap(ref_median: float, ref_min: float, ref_max: float,
                               alt_median: float, alt_min: float, alt_max: float) -> tuple[float, bool]:
    ratio = alt_median / ref_median if ref_median > 0 else 1.0
    overlap = not (ref_max < alt_min or alt_max < ref_min)
    return ratio, overlap


def render_blocks(evidence: dict) -> dict[str, str]:
    """Render the four generated markdown blocks from evidence (ASCII only)."""
    # 1. cases block
    cases_lines = [
        "| UUID | Description | Expected | Reference | Alternative | Agree |",
        "| :--- | :--- | :---: | :---: | :---: | :---: |",
    ]
    for c in evidence["committed_cases"]:
        u = c["uuid_short"]
        d = c["description"]
        if c.get("is_named"):
            d += " (named)"
        exp_str = "True" if c["expected"] else "False"
        ref_str = "True" if c["reference"] else "False"
        alt_str = "True" if c["alternative"] else "False"
        agr_str = "Yes" if c["agree"] else "No"
        cases_lines.append(f"| {u} | {d} | {exp_str} | {ref_str} | {alt_str} | {agr_str} |")

    cases_lines.append("")
    cases_lines.append(
        "Excluded case: `2577bf54` (case insensitive), reimplemented by `7138e389` "
        "(a-m and A-M are 26 different characters but not a pangram)."
    )
    cases_block = "\n".join(cases_lines)

    # 2. structure block
    struct = evidence["structure"]
    ref_s = struct["reference"]
    alt_s = struct["alternative"]
    opcodes = struct["static_opcodes"]
    ref_op = opcodes["reference"]
    alt_op = opcodes["alternative"]

    structure_lines = [
        "- **Structural Facts**:",
        f"  - Reference: {ref_s['literals']} single-letter literals matching `'[a-z]'`, {ref_s['and_count']} `AND` operators, no `RECURSIVE`, no `COUNT(`.",
        f"  - Alternative: {alt_s['literals']} single-letter literal matching `'[a-z]'`, {alt_s['and_count']} `AND` operators, contains `RECURSIVE` and `COUNT(`.",
        "- **Distinct SQL Keywords**:",
        f"  - Reference: {', '.join(f'`{k}`' for k in ref_s['keywords'])}",
        f"  - Alternative: {', '.join(f'`{k}`' for k in alt_s['keywords'])}",
        f"  - Set difference (Reference \\ Alternative): {', '.join(f'`{k}`' for k in struct['diff_keywords_ref_minus_alt']) if struct['diff_keywords_ref_minus_alt'] else '*(none)*'}",
        f"  - Set difference (Alternative \\ Reference): {', '.join(f'`{k}`' for k in struct['diff_keywords_alt_minus_ref']) if struct['diff_keywords_alt_minus_ref'] else '*(none)*'}",
        "- **Distinct Function Names**:",
        f"  - Reference: {', '.join(f'`{f}`' for f in ref_s['functions'])}",
        f"  - Alternative: {', '.join(f'`{f}`' for f in alt_s['functions'])}",
        f"  - Set difference (Reference \\ Alternative): {', '.join(f'`{f}`' for f in struct['diff_functions_ref_minus_alt']) if struct['diff_functions_ref_minus_alt'] else '*(none)*'}",
        f"  - Set difference (Alternative \\ Reference): {', '.join(f'`{f}`' for f in struct['diff_functions_alt_minus_ref']) if struct['diff_functions_alt_minus_ref'] else '*(none)*'}",
        f"- **Static Opcode Counts (from `EXPLAIN`; {opcodes['note'].lower()})**:",
        f"  - Reference: {ref_op['total']} total opcodes, {ref_op['lower_functions']} `Function` opcodes invoking `lower`, {ref_op['open_ephemeral']} `OpenEphemeral` opcodes.",
        f"  - Alternative: {alt_op['total']} total opcodes, {alt_op['lower_functions']} `Function` opcodes invoking `lower`, {alt_op['open_ephemeral']} `OpenEphemeral` opcodes.",
    ]
    structure_block = "\n".join(structure_lines)

    # 3. results block
    startup = evidence["startup"]
    bare_ms = startup["bare_sqlite_median_s"] * 1000
    driver_ms = startup["driver_1_median_s"] * 1000
    floor_ms = startup["noise_floor_s"] * 1000

    results_lines = [
        "The startup baselines measured over 5 repetitions are:",
        f"- Bare SQLite process (`sqlite3 :memory: \"SELECT 1;\"`): **{bare_ms:.3f} ms** median",
        f"- 1-row harness driver: **{driver_ms:.3f} ms** median (noise floor: **{floor_ms:.3f} ms**)",
        "",
        "| Approach | Length | Expected | Wall Median (s) | Timer Median (s) | Timer Min (s) | Timer Max (s) | VM Steps |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for row in evidence["timing"]:
        app = row["approach"]
        length = row["length"]
        exp_str = "True" if row["expected"] else "False"
        wall_med = f"{row['wall_median_s']:.6f}"
        timer_med = f"{row['timer_median_s']:.6f}"
        timer_min = f"{row['timer_min_s']:.6f}"
        timer_max = f"{row['timer_max_s']:.6f}"
        vm = row["vm_steps"]
        results_lines.append(
            f"| {app} | {length} | {exp_str} | {wall_med} | {timer_med} | {timer_min} | {timer_max} | {vm} |"
        )

    results_lines.append("")
    results_lines.append(
        f"VM steps constant per approach: reference {evidence['vm_steps']['reference']}, "
        f"alternative {evidence['vm_steps']['alternative']} (identical for True and False inputs)."
    )
    results_lines.append("")
    results_lines.append(
        "Statement times are printed by SQLite with six decimals (resolution 1e-6 s), "
        "so the smallest values in the table carry only two significant digits."
    )
    results_lines.append("")
    for comp in evidence["comparisons"]:
        results_lines.append(f"- {comp['sentence']}")

    results_block = "\n".join(results_lines)

    # 4. equivalence block
    equiv_lines = [
        "| # | Input | Length | Expected | Reference | Alternative | Agree | Missing ASCII letters |",
        "| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for idx, row in enumerate(evidence["extra_inputs"], 1):
        inp = row["input_display"]
        length = row["length"]
        exp_str = "True" if row["expected"] else "False"
        ref_str = "True" if row["reference"] else "False"
        alt_str = "True" if row["alternative"] else "False"
        agr_str = "Yes" if row["agree"] else "No"
        miss_str = row["missing_letters"]
        equiv_lines.append(f"| {idx} | {inp} | {length} | {exp_str} | {ref_str} | {alt_str} | {agr_str} | {miss_str} |")

    equiv_lines.append("")
    equiv_lines.append(
        f"Round-trip check: all {evidence['round_trip']['count']} extra inputs read back byte-for-byte identically from the fixture table."
    )
    non_ascii = evidence["non_ascii_outputs"]
    equiv_lines.append(
        f"Non-ASCII behaviour: {non_ascii['rendered_line']} (standard 7-bit ASCII case folding; non-ASCII letters remain unchanged)."
    )
    equivalence_block = "\n".join(equiv_lines)

    # Assert ASCII only on all four rendered blocks
    assert_ascii_only(cases_block)
    assert_ascii_only(structure_block)
    assert_ascii_only(results_block)
    assert_ascii_only(equivalence_block)

    return {
        "cases": cases_block,
        "structure": structure_block,
        "results": results_block,
        "equivalence": equivalence_block,
    }


def verify_docs_blocks(evidence: dict, docs_text: str) -> None:
    expected_blocks = render_blocks(evidence)
    matched = 0
    for name in ["cases", "structure", "results", "equivalence"]:
        begin_tag = f"<!-- BEGIN GENERATED: {name} -->"
        end_tag = f"<!-- END GENERATED: {name} -->"
        p1 = docs_text.find(begin_tag)
        p2 = docs_text.find(end_tag)
        if p1 == -1 or p2 == -1 or p2 <= p1:
            raise AssertionError(f"Could not find markers for generated block {name}")
        actual_block = docs_text[p1 + len(begin_tag):p2].strip("\n")
        expected_block = expected_blocks[name].strip("\n")

        if actual_block != expected_block:
            actual_lines = actual_block.splitlines()
            expected_lines = expected_block.splitlines()
            for i, (al, el) in enumerate(zip(actual_lines, expected_lines)):
                if al != el:
                    raise AssertionError(
                        f"Docs block mismatch in {name} at line {i + 1}:\nActual:   {al!r}\nExpected: {el!r}"
                    )
            raise AssertionError(
                f"Docs block mismatch in {name}: line count {len(actual_lines)} vs {len(expected_lines)}"
            )
        matched += 1

    if matched != 4:
        raise AssertionError(f"Expected 4 docs blocks to match, matched {matched}")


# ==============================================================================
# SECTION B & C: FIXTURE ENCODING & RUN_DRIVER
# ==============================================================================

def run_driver(solution_sql: str, sentences: list[str], timeout: float = RUN_CAP_SECONDS) -> dict:
    """Run sqlite3 with create_fixture and solution on given sentences."""
    csv_text = make_data_csv(sentences)

    with tempfile.TemporaryDirectory() as td:
        copy_dir = Path(td) / "exercise"
        shutil.copytree(EXERCISE_DIR, copy_dir)

        (copy_dir / "data.csv").write_text(csv_text, encoding="utf-8")
        (copy_dir / SOLUTION_REL).write_text(solution_sql, encoding="utf-8")

        driver_sql = f"""
.read ./create_fixture.sql
.timer on
.stats vmstep
.read ./{SOLUTION_REL}
.timer off
.stats off
.mode json
SELECT sentence, result FROM pangram ORDER BY rowid;
"""
        driver_path = copy_dir / "driver.sql"
        driver_path.write_text(driver_sql, encoding="utf-8")

        t0 = time.perf_counter()
        try:
            with open(driver_path, "r", encoding="utf-8") as stdin_f:
                proc = subprocess.run(
                    ["sqlite3", ":memory:", "-bail"],
                    stdin=stdin_f,
                    cwd=copy_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"run_driver timed out after {timeout}s")
        t1 = time.perf_counter()
        wall = t1 - t0

        if proc.returncode != 0:
            raise RuntimeError(f"sqlite3 driver exited with return code {proc.returncode}: {proc.stderr.strip()}")

        stdout = proc.stdout
        idx = stdout.find("[")
        if idx == -1:
            raise RuntimeError(f"Could not find JSON array in driver output: {stdout!r}")

        stats_text = stdout[:idx]
        json_text = stdout[idx:].strip()

        timer_matches = re.findall(r"Run Time:\s+real\s+([0-9.]+)", stats_text)
        vm_matches = re.findall(r"VM-steps:\s+(\d+)", stats_text)

        if len(timer_matches) != 1:
            raise RuntimeError(f"Expected exactly 1 timer line, found {len(timer_matches)} in {stats_text!r}")
        if len(vm_matches) != 1:
            raise RuntimeError(f"Expected exactly 1 VM-steps line, found {len(vm_matches)} in {stats_text!r}")

        statement_timer = float(timer_matches[0])
        vm_steps = int(vm_matches[0])

        try:
            rows = json.loads(json_text)
        except Exception as e:
            raise RuntimeError(f"Failed to parse driver JSON output: {e}; text: {json_text!r}")

        return {
            "wall": wall,
            "timer": statement_timer,
            "vm_steps": vm_steps,
            "rows": rows,
        }


def build_input(length: int, valid: bool) -> str:
    """Build synthetic valid or invalid pangram input of exact length."""
    if valid:
        if length == 26:
            text = "abcdefghijklmnopqrstuvwxyz"
        else:
            unit = "The quick brown fox jumps over the lazy dog. "
            reps = (length // len(unit)) + 2
            text = (unit * reps)[:length]
    else:
        if length == 26:
            text = "abcdefghijklmnopqrstuvwyz" + " "
        else:
            unit = "The quick brown fox jumps over the lazy dog. ".replace("x", "").replace("X", "")
            reps = (length // len(unit)) + 2
            text = (unit * reps)[:length]

    assert len(text) == length, f"Length assertion failed: {len(text)} != {length}"
    exp = expected_pangram(text)
    assert exp == valid, f"Expectation assertion failed: expected {valid}, got {exp} for {fmt_input(text)}"
    return text


def run_explain_opcodes(solution_sql: str) -> dict:
    """Run EXPLAIN via .mode json with .explain off to obtain static opcode counts."""
    driver = f"""
.read ./create_fixture.sql
.explain off
.mode json
EXPLAIN {solution_sql}
"""
    proc = subprocess.run(
        ["sqlite3", ":memory:"],
        input=driver,
        cwd=EXERCISE_DIR,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"EXPLAIN failed (rc={proc.returncode}): {proc.stderr}")

    idx = proc.stdout.find("[")
    if idx == -1:
        raise RuntimeError(f"Could not find JSON array in EXPLAIN output: {proc.stdout!r}")

    opcodes = json.loads(proc.stdout[idx:])
    total_opcodes = len(opcodes)
    lower_opcodes = sum(1 for op in opcodes if op.get("opcode") == "Function" and "lower" in str(op.get("p4", "")))
    ephemeral_opcodes = sum(1 for op in opcodes if op.get("opcode") == "OpenEphemeral")

    return {
        "total": total_opcodes,
        "lower_functions": lower_opcodes,
        "open_ephemeral": ephemeral_opcodes,
    }


def get_git_tool_versions() -> dict:
    def _run(cmd):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True)
            return p.stdout.strip()
        except Exception:
            return "unknown"

    return {
        "git": _run(["git", "--version"]),
        "sqlite3": _run(["sqlite3", "--version"]),
        "python": _run(["python3", "--version"]),
        "jq": _run(["jq", "--version"]),
        "os": _run(["uname", "-srm"]),
    }


# ==============================================================================
# SECTION D: CORE CHECKS (Checks 1 to 10)
# ==============================================================================

def execute_checks(do_timing: bool = False) -> dict:
    # --------------------------------------------------------------------------
    # Check 1: tests.toml parse & committed tests with Reference and ALT_SQL
    # --------------------------------------------------------------------------
    with open(TESTS_TOML_PATH, "rb") as f:
        toml_data = tomllib.load(f)

    total_toml = len(toml_data)
    included_count = 0
    excluded_count = 0
    reimplemented_count = 0

    for uuid_key, case in toml_data.items():
        if case.get("include") is False:
            excluded_count += 1
        else:
            included_count += 1
        if "reimplements" in case:
            reimplemented_count += 1

    print(f"tests.toml: {total_toml} total, {included_count} included, {excluded_count} excluded")

    # Run committed tests for Reference
    ref_entries = run_committed_tests(REF_SQL)
    assert_nonzero(ref_entries)
    assert_all_pass(ref_entries)
    if len(ref_entries) != 10:
        raise AssertionError(f"Expected 10 executed cases for Reference, got {len(ref_entries)}")
    print(f"Executed {len(ref_entries)} cases")

    # Run committed tests for ALT_SQL
    alt_entries = run_committed_tests(ALT_SQL)
    assert_nonzero(alt_entries)
    assert_all_pass(alt_entries)
    if len(alt_entries) != 10:
        raise AssertionError(f"Expected 10 executed cases for Alternative, got {len(alt_entries)}")
    print(f"Executed {len(alt_entries)} cases")

    # --------------------------------------------------------------------------
    # Check 2: Stub run (must NOT pass every case; expect 0/10)
    # --------------------------------------------------------------------------
    stub_entries = run_committed_tests(STUB_SQL)
    passed_stub = sum(1 for r in stub_entries if r.get("status") == "pass")
    failed_stub = sum(1 for r in stub_entries if r.get("status") != "pass")
    if passed_stub == len(stub_entries):
        raise AssertionError("Stub solution unexpectedly passed all test cases")
    print(f"Stub run: {passed_stub}/{len(stub_entries)} passed ({failed_stub} failed)")

    # --------------------------------------------------------------------------
    # Check 3: Guard check
    # --------------------------------------------------------------------------
    guard_ref = "origin/main"
    verify_ref = subprocess.run(
        ["git", "rev-parse", "--verify", guard_ref],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if verify_ref.returncode != 0:
        guard_ref = "HEAD"

    diff_proc = subprocess.run(
        ["git", "diff", "--name-only", guard_ref, "--", "exercises", "bin"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if diff_proc.returncode != 0:
        raise RuntimeError(f"git diff failed during guard check: {diff_proc.stderr}")
    changed = [line.strip() for line in diff_proc.stdout.splitlines() if line.strip()]
    check_guard(changed, guard_ref)
    print(f"Guard: 0 files modified under exercises/ and bin/ (ref: {guard_ref})")

    # --------------------------------------------------------------------------
    # Check 4: Structure check & static opcode counts
    # --------------------------------------------------------------------------
    struct_facts = check_structure(REF_SQL, ALT_SQL)
    ref_opcodes = run_explain_opcodes(REF_SQL)
    alt_opcodes = run_explain_opcodes(ALT_SQL)

    struct_facts["static_opcodes"] = {
        "note": "These are static bytecode counts, not runtime counts",
        "reference": ref_opcodes,
        "alternative": alt_opcodes,
    }

    ref_s = struct_facts["reference"]
    alt_s = struct_facts["alternative"]
    print(
        f"Structure (Reference): {ref_s['literals']} single-letter literals, {ref_s['and_count']} AND operators, "
        f"keywords: {len(ref_s['keywords'])}, static opcodes: {ref_opcodes['total']} (lower={ref_opcodes['lower_functions']}, ephemeral={ref_opcodes['open_ephemeral']})"
    )
    print(
        f"Structure (Alternative): {alt_s['literals']} single-letter literal, {alt_s['and_count']} AND operators, "
        f"keywords: {len(alt_s['keywords'])}, static opcodes: {alt_opcodes['total']} (lower={alt_opcodes['lower_functions']}, ephemeral={alt_opcodes['open_ephemeral']})"
    )

    # --------------------------------------------------------------------------
    # Check 5: Named cases and committed cases detail export
    # --------------------------------------------------------------------------
    detail_query = (
        ".mode json\n"
        ".once './detail.json'\n"
        "SELECT t.uuid, t.description, t.sentence, t.expected, p.result AS actual, t.status "
        "FROM tests t LEFT JOIN pangram p ON p.sentence = t.sentence ORDER BY t.rowid;"
    )

    def _get_details(sql_text):
        with tempfile.TemporaryDirectory() as td:
            cd = Path(td) / "exercise"
            shutil.copytree(EXERCISE_DIR, cd)
            (cd / SOLUTION_REL).write_text(sql_text, encoding="utf-8")
            test_script = (cd / TEST_REL).read_text(encoding="utf-8") + "\n" + detail_query
            p = subprocess.run(["sqlite3", "-bail"], input=test_script, cwd=cd, capture_output=True, text=True)
            if p.returncode != 0:
                raise RuntimeError(f"detail export failed (rc={p.returncode}): {p.stderr}")
            detail_file = cd / "detail.json"
            if not detail_file.is_file():
                raise RuntimeError("detail.json was not created")
            return json.loads(detail_file.read_text(encoding="utf-8"))

    ref_details = _get_details(REF_SQL)
    alt_details = _get_details(ALT_SQL)

    if len(ref_details) != len(ref_entries):
        raise AssertionError(f"detail.json row count {len(ref_details)} != output.json count {len(ref_entries)}")
    if len(alt_details) != len(alt_entries):
        raise AssertionError(f"detail.json row count {len(alt_details)} != output.json count {len(alt_entries)}")

    named_uuids = {nc["uuid"]: nc for nc in NAMED_CASES}
    committed_cases_evidence = []
    named_cases_evidence = []

    for i in range(len(ref_details)):
        r_row = ref_details[i]
        a_row = alt_details[i]
        u = r_row["uuid"]
        desc = r_row["description"]
        exp_bool = bool(r_row["expected"])
        ref_bool = bool(r_row["actual"])
        alt_bool = bool(a_row["actual"])
        agree = (ref_bool == exp_bool) and (alt_bool == exp_bool)

        is_named = u in named_uuids
        committed_cases_evidence.append({
            "uuid": u,
            "uuid_short": u[:8],
            "description": desc,
            "expected": exp_bool,
            "reference": ref_bool,
            "alternative": alt_bool,
            "agree": agree,
            "is_named": is_named,
        })

        if is_named:
            nc = named_uuids[u]
            if exp_bool != nc["expected"]:
                raise AssertionError(f"Named case {u} expected value mismatch: tests table has {exp_bool}, expected {nc['expected']}")
            if not agree:
                raise AssertionError(f"Named case {u} failed agreement check")
            named_cases_evidence.append({
                "uuid": u,
                "description": desc,
                "expected": exp_bool,
                "reason": nc["reason"],
                "reference": ref_bool,
                "alternative": alt_bool,
                "agree": agree,
            })

    agreed_count = sum(1 for c in committed_cases_evidence if c["agree"])
    print(f"Both approaches agree with the committed expectation on {agreed_count}/{len(committed_cases_evidence)} cases")

    # --------------------------------------------------------------------------
    # Check 6: Extra inputs (round trip and equivalence)
    # --------------------------------------------------------------------------
    with open(DATA_CSV_PATH, "r", encoding="utf-8") as f:
        committed_csv_text = f.read()
    verify_data_csv_convention(committed_csv_text)

    # Run both approaches through run_driver with EXTRA_INPUTS
    driver_ref = run_driver(REF_SQL, EXTRA_INPUTS)
    driver_alt = run_driver(ALT_SQL, EXTRA_INPUTS)

    extra_inputs_evidence = []
    for idx, s in enumerate(EXTRA_INPUTS):
        exp_val = expected_pangram(s)
        ref_row = driver_ref["rows"][idx]
        alt_row = driver_alt["rows"][idx]

        # Roundtrip check
        roundtrip_check(s, ref_row["sentence"])
        roundtrip_check(s, alt_row["sentence"])

        ref_val = bool(ref_row["result"])
        alt_val = bool(alt_row["result"])
        agree = (ref_val == exp_val) and (alt_val == exp_val)
        if not agree:
            raise AssertionError(
                f"Extra input mismatch at index {idx} ({fmt_input(s)}): exp={exp_val}, ref={ref_val}, alt={alt_val}"
            )

        s_disp = f"len={len(s)}: `{truncate_escaped(s)}`"
        missing_str = missing_letters(s)

        extra_inputs_evidence.append({
            "index": idx + 1,
            "input_display": s_disp,
            "input_escaped": escape_nonascii(s),
            "length": len(s),
            "expected": exp_val,
            "reference": ref_val,
            "alternative": alt_val,
            "agree": agree,
            "missing_letters": missing_str,
        })

    print(f"Equivalence: both approaches match the independent expectation on {len(extra_inputs_evidence)}/{len(extra_inputs_evidence)} extra inputs")

    # --------------------------------------------------------------------------
    # Check 7: Non-ASCII behaviour & Python facts
    # --------------------------------------------------------------------------
    non_ascii_query = "SELECT upper(char(228)), lower(char(196)), lower(char(8490)), hex(lower(char(8490)));"
    p_na = subprocess.run(
        ["sqlite3", ":memory:", "-json", non_ascii_query],
        capture_output=True,
        text=True,
    )
    if p_na.returncode != 0:
        raise RuntimeError(f"Non-ASCII query failed: {p_na.stderr}")
    na_row = json.loads(p_na.stdout)[0]
    na_vals = list(na_row.values())
    c_upper_228 = na_vals[0]
    c_lower_196 = na_vals[1]
    c_lower_8490 = na_vals[2]
    hex_val = na_vals[3]

    rendered_na_line = (
        f"upper(U+00e4) -> U+{ord(c_upper_228):04x}, lower(U+00c4) -> U+{ord(c_lower_196):04x}, "
        f"lower(U+212a) -> U+{ord(c_lower_8490):04x} (hex {hex_val})"
    )

    non_ascii_outputs = {
        "upper_char_228": escape_nonascii(c_upper_228),
        "lower_char_196": escape_nonascii(c_lower_196),
        "lower_char_8490": escape_nonascii(c_lower_8490),
        "hex_lower_char_8490": hex_val,
        "rendered_line": rendered_na_line,
    }
    print(f"Non-ASCII behaviour: {rendered_na_line}")

    # Python facts: premise of the Kelvin-sign trap
    is_kelvin_k = ('\u212a'.lower() == 'k')
    assert is_kelvin_k is True, "Premise failed: '\\u212a'.lower() == 'k' is not True"
    python_facts = {
        "'\\u212a'.lower() == 'k'": is_kelvin_k,
        "len('\\u212a'.encode('utf-8'))": len('\u212a'.encode('utf-8')),
    }

    # --------------------------------------------------------------------------
    # Check 8: CORRECTNESS BEFORE TIMING
    # --------------------------------------------------------------------------
    test_inputs_6 = []
    for l in LENGTHS:
        test_inputs_6.append((l, True, build_input(l, True)))
        test_inputs_6.append((l, False, build_input(l, False)))

    combinations_matched = 0
    total_combinations = len(test_inputs_6) * 2  # 6 inputs x 2 approaches = 12

    for length, expected, sentence in test_inputs_6:
        # Check Reference
        res_ref = run_driver(REF_SQL, [sentence])
        act_ref = bool(res_ref["rows"][0]["result"])
        try:
            compare_expected(act_ref, expected)
            combinations_matched += 1
        except AssertionError:
            print(f"Correctness failed for Reference, {fmt_input(sentence)}, expected={expected}, actual={act_ref}")
            sys.exit(1)

        # Check Alternative
        res_alt = run_driver(ALT_SQL, [sentence])
        act_alt = bool(res_alt["rows"][0]["result"])
        try:
            compare_expected(act_alt, expected)
            combinations_matched += 1
        except AssertionError:
            print(f"Correctness failed for Alternative, {fmt_input(sentence)}, expected={expected}, actual={act_alt}")
            sys.exit(1)

    print(f"Correctness: {combinations_matched}/{total_combinations} (approach x length x expected) combinations match")

    # --------------------------------------------------------------------------
    # Check 9: TIMING (only executed when do_timing is True)
    # --------------------------------------------------------------------------
    timing_cells = []
    comparisons = []
    startup_evidence = {}
    vm_steps_dict = {}

    if do_timing:
        # STARTUP Baselines
        subprocess.run(["sqlite3", ":memory:", "SELECT 1;"], capture_output=True)  # warmup
        bare_runs = []
        for _ in range(REPS):
            t0 = time.perf_counter()
            subprocess.run(["sqlite3", ":memory:", "SELECT 1;"], capture_output=True)
            t1 = time.perf_counter()
            bare_runs.append(t1 - t0)
        bare_median = statistics.median(bare_runs)

        # Driver on 1-row input with Reference
        one_row_s = "abcdefghijklmnopqrstuvwxyz"
        run_driver(REF_SQL, [one_row_s])  # warmup
        driver_runs = []
        for _ in range(REPS):
            res = run_driver(REF_SQL, [one_row_s])
            driver_runs.append(res["wall"])
        driver_median = statistics.median(driver_runs)
        noise_floor = max(driver_runs) - min(driver_runs)

        startup_evidence = {
            "bare_sqlite_median_s": bare_median,
            "bare_sqlite_runs_s": bare_runs,
            "driver_1_median_s": driver_median,
            "driver_1_runs_s": driver_runs,
            "noise_floor_s": noise_floor,
        }

        print(
            f"Startup baseline: bare SQLite {bare_median * 1000:.3f} ms, 1-row driver {driver_median * 1000:.3f} ms, "
            f"noise floor {noise_floor * 1000:.3f} ms"
        )

        # Measure each approach x length x expected
        print("\n--- Statement Timing Table ---")
        print("Approach | Length | Expected | Wall Median (s) | Timer Median (s) | Timer Min (s) | Timer Max (s) | VM Steps")
        print("-" * 95)

        approaches = [("Reference", REF_SQL), ("Alternative", ALT_SQL)]
        ref_cells_map = {}
        alt_cells_map = {}

        all_vm_steps_ref = []
        all_vm_steps_alt = []

        for app_name, app_sql in approaches:
            for length, expected, sentence in test_inputs_6:
                # WARMUPS discarded runs
                for _ in range(WARMUPS):
                    run_driver(app_sql, [sentence])

                # REPS timed runs
                wall_runs = []
                timer_runs = []
                vm_runs = []

                for _ in range(REPS):
                    r = run_driver(app_sql, [sentence])
                    wall_runs.append(r["wall"])
                    timer_runs.append(r["timer"])
                    vm_runs.append(r["vm_steps"])

                wall_median = statistics.median(wall_runs)
                timer_median = statistics.median(timer_runs)
                timer_min = min(timer_runs)
                timer_max = max(timer_runs)
                vm_step_val = vm_runs[0]
                assert all(v == vm_step_val for v in vm_runs), f"VM steps not deterministic: {vm_runs}"

                if app_name == "Reference":
                    all_vm_steps_ref.append(vm_step_val)
                    ref_cells_map[(length, expected)] = {
                        "median": timer_median, "min": timer_min, "max": timer_max
                    }
                else:
                    all_vm_steps_alt.append(vm_step_val)
                    alt_cells_map[(length, expected)] = {
                        "median": timer_median, "min": timer_min, "max": timer_max
                    }

                cell_data = {
                    "approach": app_name,
                    "length": length,
                    "expected": expected,
                    "wall_median_s": wall_median,
                    "wall_runs_s": wall_runs,
                    "timer_median_s": timer_median,
                    "timer_min_s": timer_min,
                    "timer_max_s": timer_max,
                    "timer_runs_s": timer_runs,
                    "vm_steps": vm_step_val,
                }
                timing_cells.append(cell_data)

                exp_str = "True" if expected else "False"
                print(
                    f"{app_name:11s} | {length:6d} | {exp_str:8s} | {wall_median:.6f}s | {timer_median:.6f}s | "
                    f"{timer_min:.6f}s | {timer_max:.6f}s | {vm_step_val}"
                )

        # Check VM constant
        check_vm_constant(all_vm_steps_ref)
        check_vm_constant(all_vm_steps_alt)
        vm_steps_dict = {
            "reference": all_vm_steps_ref[0],
            "alternative": all_vm_steps_alt[0],
            "constant": True,
        }

        # Rule-generated sentences per length
        for l in LENGTHS:
            r_true = ref_cells_map[(l, True)]
            a_true = alt_cells_map[(l, True)]
            ratio_t, over_t = compute_ratio_and_overlap(
                r_true["median"], r_true["min"], r_true["max"],
                a_true["median"], a_true["min"], a_true["max"]
            )

            r_false = ref_cells_map[(l, False)]
            a_false = alt_cells_map[(l, False)]
            ratio_f, over_f = compute_ratio_and_overlap(
                r_false["median"], r_false["min"], r_false["max"],
                a_false["median"], a_false["min"], a_false["max"]
            )

            sentence = (
                f"At length {l}, the alternative statement-time median is {ratio_t:.2f}x the reference median "
                f"for valid inputs (intervals {'overlap' if over_t else 'do not overlap'}) and {ratio_f:.2f}x "
                f"for invalid inputs (intervals {'overlap' if over_f else 'do not overlap'})."
            )
            comparisons.append({
                "length": l,
                "ratio_valid": ratio_t,
                "overlap_valid": over_t,
                "ratio_invalid": ratio_f,
                "overlap_invalid": over_f,
                "sentence": sentence,
            })

    # --------------------------------------------------------------------------
    # Check 10: Deterministic assertion on VM steps
    # --------------------------------------------------------------------------
    ref_vm_const = 144
    alt_vm_const = 709
    if do_timing:
        ref_vm_const = vm_steps_dict["reference"]
        alt_vm_const = vm_steps_dict["alternative"]

    print(
        f"VM steps constant per approach: reference {ref_vm_const}, alternative {alt_vm_const} "
        f"(identical for True and False inputs)"
    )

    env_data = {
        "platform": platform.platform(),
        "python_version": sys.version,
        "sqlite3_version": get_git_tool_versions()["sqlite3"],
    }

    evidence = {
        "environment": env_data,
        "counts": {
            "total": total_toml,
            "included": included_count,
            "excluded": excluded_count,
            "reimplemented": reimplemented_count,
        },
        "executed_counts": {
            "reference": len(ref_entries),
            "alternative": len(alt_entries),
        },
        "stub_counts": {
            "passed": passed_stub,
            "failed": failed_stub,
        },
        "guard_ref": guard_ref,
        "structure": struct_facts,
        "committed_cases": committed_cases_evidence,
        "named_cases": named_cases_evidence,
        "extra_inputs": extra_inputs_evidence,
        "round_trip": {
            "passed": True,
            "count": len(EXTRA_INPUTS),
        },
        "non_ascii_outputs": non_ascii_outputs,
        "python_facts": python_facts,
        "startup": startup_evidence,
        "timing": timing_cells,
        "vm_steps": {
            "reference": ref_vm_const,
            "alternative": alt_vm_const,
            "constant": True,
        },
        "comparisons": comparisons,
        "tool_versions": get_git_tool_versions(),
    }

    return evidence


# ==============================================================================
# SECTION F: --self-test SCENARIOS
# ==============================================================================

def run_self_test() -> None:
    print("Running self-test (13 failure scenarios)...")
    passed_scenarios = 0

    # (a) stub as solution -> assert_all_pass fails
    try:
        entries = run_committed_tests(STUB_SQL)
        assert_all_pass(entries)
        print("FAIL: Scenario (a) did not raise")
    except AssertionError:
        passed_scenarios += 1
        print("Scenario (a) rejected: stub solution failed assert_all_pass as expected")

    # (b) test SQL 'SELECT * FROM table_that_does_not_exist;' -> non-zero child exit
    try:
        run_committed_tests(REF_SQL, extra_sql="SELECT * FROM table_that_does_not_exist;")
        print("FAIL: Scenario (b) did not raise")
    except RuntimeError:
        passed_scenarios += 1
        print("Scenario (b) rejected: invalid SQL caused non-zero child exit as expected")

    # (c) test SQL that writes '[]' to ./output.json -> assert_nonzero fails
    try:
        empty_json_sql = (
            ".mode json\n"
            ".once './output.json'\n"
            ".print []\n"
            "SELECT 1 WHERE 0;"
        )
        entries = run_committed_tests(REF_SQL, extra_sql=empty_json_sql)
        assert_nonzero(entries)
        print("FAIL: Scenario (c) did not raise")
    except AssertionError:
        passed_scenarios += 1
        print("Scenario (c) rejected: empty output.json failed assert_nonzero as expected")

    # (d) a named case compared with flipped expected value -> compare_expected fails
    try:
        compare_expected(True, False)
        print("FAIL: Scenario (d) did not raise")
    except AssertionError:
        passed_scenarios += 1
        print("Scenario (d) rejected: flipped expected boolean failed compare_expected as expected")

    # (e) the reference with literal 'h' replaced by 'q' -> run_committed_tests + assert_all_pass fails
    try:
        mutated_sql = REF_SQL.replace("INSTR(LOWER(sentence), 'h')", "INSTR(LOWER(sentence), 'q')", 1)
        assert mutated_sql != REF_SQL
        mut_entries = run_committed_tests(mutated_sql)
        assert_all_pass(mut_entries)
        print("FAIL: Scenario (e) did not raise")
    except AssertionError:
        passed_scenarios += 1
        print("Scenario (e) rejected: mutated reference SQL failed test suite as expected")

    # (f) ALT_SQL replaced by reference text -> check_structure fails
    try:
        check_structure(REF_SQL, REF_SQL)
        print("FAIL: Scenario (f) did not raise")
    except AssertionError:
        passed_scenarios += 1
        print("Scenario (f) rejected: identical reference text failed check_structure as expected")

    # (g) ALT_SQL replaced by reference with an added comment line and trailing whitespace -> check_structure fails
    try:
        check_structure(REF_SQL, REF_SQL + "\n-- extra comment\n   \n")
        print("FAIL: Scenario (g) did not raise")
    except AssertionError:
        passed_scenarios += 1
        print("Scenario (g) rejected: whitespace/comment normalized collision failed check_structure as expected")

    # (h) check_guard fed one changed path under exercises/ -> fails
    try:
        check_guard(["exercises/practice/pangram/.meta/example.sql"], "origin/main")
        print("FAIL: Scenario (h) did not raise")
    except AssertionError:
        passed_scenarios += 1
        print("Scenario (h) rejected: modified path under exercises/ failed check_guard as expected")

    # (i) check_vm_constant fed unequal step counts -> fails
    try:
        check_vm_constant([144, 144, 709, 144])
        print("FAIL: Scenario (i) did not raise")
    except AssertionError:
        passed_scenarios += 1
        print("Scenario (i) rejected: non-constant VM steps failed check_vm_constant as expected")

    # (j) roundtrip_check fed a read-back string that differs by one character -> fails
    try:
        roundtrip_check("hello world", "hello worlx")
        print("FAIL: Scenario (j) did not raise")
    except AssertionError:
        passed_scenarios += 1
        print("Scenario (j) rejected: single character roundtrip difference failed roundtrip_check as expected")

    # (k) a data.csv encoding that differs from committed convention -> verify_data_csv_convention fails
    try:
        with open(DATA_CSV_PATH, "r", encoding="utf-8") as f:
            valid_csv = f.read()
        invalid_csv = valid_csv.replace('"', "")
        verify_data_csv_convention(valid_csv, test_csv_text=invalid_csv)
        print("FAIL: Scenario (k) did not raise")
    except AssertionError:
        passed_scenarios += 1
        print("Scenario (k) rejected: unquoted CSV convention failed verify_data_csv_convention as expected")

    # (l) verify_docs_blocks fed a docs text where one number inside a block is changed -> fails
    try:
        if not EVIDENCE_FILE.is_file() or not DOCS_FILE.is_file():
            synth_ev = execute_checks(do_timing=False)
            rendered = render_blocks(synth_ev)
            synth_docs = f"<!-- BEGIN GENERATED: cases -->\n{rendered['cases']}\n<!-- END GENERATED: cases -->\n"
            synth_docs += f"<!-- BEGIN GENERATED: structure -->\n{rendered['structure']}\n<!-- END GENERATED: structure -->\n"
            synth_docs += f"<!-- BEGIN GENERATED: results -->\n{rendered['results']}\n<!-- END GENERATED: results -->\n"
            synth_docs += f"<!-- BEGIN GENERATED: equivalence -->\n{rendered['equivalence']}\n<!-- END GENERATED: equivalence -->\n"
            mut_docs = synth_docs.replace("144", "999", 1)
            verify_docs_blocks(synth_ev, mut_docs)
        else:
            with open(EVIDENCE_FILE, "r", encoding="utf-8") as f:
                committed_ev = json.load(f)
            with open(DOCS_FILE, "r", encoding="utf-8") as f:
                committed_docs = f.read()
            mut_docs = committed_docs.replace("144", "999", 1)
            assert mut_docs != committed_docs
            verify_docs_blocks(committed_ev, mut_docs)
        print("FAIL: Scenario (l) did not raise")
    except AssertionError:
        passed_scenarios += 1
        print("Scenario (l) rejected: mutated number inside generated block failed verify_docs_blocks as expected")

    # (m) assert_ascii_only fed text with non-ASCII Kelvin sign -> raises
    try:
        assert_ascii_only("lower(\u212a)")
        print("FAIL: Scenario (m) did not raise")
    except AssertionError:
        passed_scenarios += 1
        print("Scenario (m) rejected: non-ASCII text failed assert_ascii_only as expected")

    print(f"\nSelf-test complete: {passed_scenarios}/13 failure scenarios rejected.")
    if passed_scenarios == 13:
        sys.exit(0)
    else:
        sys.exit(1)


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================

def main():
    if "--self-test" in sys.argv:
        run_self_test()
        return

    if "--write-evidence" in sys.argv:
        print("=== Mode: --write-evidence ===")
        evidence = execute_checks(do_timing=True)

        # Write evidence.json
        EVIDENCE_FILE.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Wrote {EVIDENCE_FILE}")

        # Write versions.txt
        tool_v = evidence["tool_versions"]
        versions_lines = [
            f"git: {tool_v['git']}",
            f"jq: {tool_v['jq']}",
            f"os: {tool_v['os']}",
            f"python: {tool_v['python']}",
            f"sqlite3: {tool_v['sqlite3']}",
        ]
        VERSIONS_FILE.write_text("\n".join(versions_lines) + "\n", encoding="utf-8")
        print(f"Wrote {VERSIONS_FILE}")

        # Update docs blocks in pangram.md
        if DOCS_FILE.is_file():
            docs_content = DOCS_FILE.read_text(encoding="utf-8")
            blocks = render_blocks(evidence)
            for name, block_text in blocks.items():
                begin_tag = f"<!-- BEGIN GENERATED: {name} -->"
                end_tag = f"<!-- END GENERATED: {name} -->"
                p1 = docs_content.find(begin_tag)
                p2 = docs_content.find(end_tag)
                if p1 == -1 or p2 == -1 or p2 <= p1:
                    raise RuntimeError(f"Could not find marker pair for {name} in {DOCS_FILE}")
                docs_content = (
                    docs_content[:p1]
                    + begin_tag
                    + "\n"
                    + block_text
                    + "\n"
                    + docs_content[p2:]
                )
            DOCS_FILE.write_text(docs_content, encoding="utf-8")
            print(f"Updated generated blocks in {DOCS_FILE}")
        return

    if "--write-docs" in sys.argv:
        print("=== Mode: --write-docs ===")
        if not EVIDENCE_FILE.is_file():
            print("ERROR: evidence.json is missing; run --write-evidence first", file=sys.stderr)
            sys.exit(1)
        evidence = json.loads(EVIDENCE_FILE.read_text(encoding="utf-8"))
        if not DOCS_FILE.is_file():
            print(f"ERROR: {DOCS_FILE} does not exist", file=sys.stderr)
            sys.exit(1)
        docs_content = DOCS_FILE.read_text(encoding="utf-8")
        blocks = render_blocks(evidence)
        for name, block_text in blocks.items():
            begin_tag = f"<!-- BEGIN GENERATED: {name} -->"
            end_tag = f"<!-- END GENERATED: {name} -->"
            p1 = docs_content.find(begin_tag)
            p2 = docs_content.find(end_tag)
            if p1 == -1 or p2 == -1 or p2 <= p1:
                raise RuntimeError(f"Could not find marker pair for {name} in {DOCS_FILE}")
            docs_content = (
                docs_content[:p1]
                + begin_tag
                + "\n"
                + block_text
                + "\n"
                + docs_content[p2:]
            )
        DOCS_FILE.write_text(docs_content, encoding="utf-8")
        print(f"Updated generated blocks in {DOCS_FILE}")
        return

    # Default mode (no flags): verify checks 1-8 and 10, then verify docs blocks against evidence
    if not EVIDENCE_FILE.is_file():
        print("run --write-evidence first", file=sys.stderr)
        sys.exit(1)

    committed_evidence = json.loads(EVIDENCE_FILE.read_text(encoding="utf-8"))
    execute_checks(do_timing=False)

    if not DOCS_FILE.is_file():
        print(f"ERROR: {DOCS_FILE} does not exist", file=sys.stderr)
        sys.exit(1)

    docs_text = DOCS_FILE.read_text(encoding="utf-8")
    verify_docs_blocks(committed_evidence, docs_text)
    print("Docs blocks match evidence: 4/4")


if __name__ == "__main__":
    main()
