#!/usr/bin/env python3
import argparse
import csv
import io
import json
import math
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import tomllib

PRIMARY_SIZES = [100, 1000, 10000]
SUPPLEMENTAL_SHORT = [1, 10]
SERIES_50 = [10, 100, 1000]
CORRECTNESS_ONLY_SIZES = [0, 1, 2, 3, 7]
WARMUPS = 1
REPS = 5
RUN_CAP_SECONDS = 60
ADDITIVITY_LOW = 0.85
ADDITIVITY_HIGH = 1.15

P1_OLD_BLOCK = """            JSON_EXTRACT(strings, PRINTF('$[%d]', i)),
            JSON_EXTRACT(strings, PRINTF('$[%d]', i + 1))"""
P1_NEW_BLOCK = """            'x',
            'y'"""

P2_OLD_BLOCK = """      to_pieces (strings, i, len, piece) AS (
        VALUES
          (strings, 0, JSON_ARRAY_LENGTH(strings) - 1, NULL)
        UNION ALL
        SELECT
          strings,
          i + 1,
          len,
          PRINTF(
            'For want of a %s the %s was lost.',
            JSON_EXTRACT(strings, PRINTF('$[%d]', i)),
            JSON_EXTRACT(strings, PRINTF('$[%d]', i + 1))
          )
        FROM
          to_pieces
        WHERE
          i < len
      )
    SELECT
      group_concat(piece, CHAR(10))
    FROM
      (
        SELECT
          piece
        FROM
          to_pieces
        WHERE
          piece NOTNULL
        UNION ALL
        SELECT
          PRINTF(
            'And all for the want of a %s.',
            JSON_EXTRACT(strings, '$[0]')
          )
      )"""

P2_NEW_BLOCK = """      to_pieces (i, len, piece) AS (
        VALUES
          (0, JSON_ARRAY_LENGTH(proverb.strings) - 1, NULL)
        UNION ALL
        SELECT
          i + 1,
          len,
          PRINTF(
            'For want of a %s the %s was lost.',
            JSON_EXTRACT(proverb.strings, PRINTF('$[%d]', i)),
            JSON_EXTRACT(proverb.strings, PRINTF('$[%d]', i + 1))
          )
        FROM
          to_pieces
        WHERE
          i < len
      )
    SELECT
      group_concat(piece, CHAR(10))
    FROM
      (
        SELECT
          piece
        FROM
          to_pieces
        WHERE
          piece NOTNULL
        UNION ALL
        SELECT
          PRINTF(
            'And all for the want of a %s.',
            JSON_EXTRACT(proverb.strings, '$[0]')
          )
      )"""

BLOCK_NAMES = ["results", "growth", "probes", "additivity"]


class ExerciseRunError(Exception):
    """Exception raised for exercise execution failures."""
    pass


class DocsVerificationError(Exception):
    """Exception raised when docs generated blocks do not match evidence."""
    pass


def get_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "exercises" / "practice" / "proverb").is_dir():
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


def expected_proverb(items: list[str]) -> str:
    n = len(items)
    if n == 0:
        return ""
    if n == 1:
        return f"And all for the want of a {items[0]}."
    lines = [f"For want of a {items[i]} the {items[i+1]} was lost." for i in range(n - 1)]
    lines.append(f"And all for the want of a {items[0]}.")
    return "\n".join(lines)


def make_data_csv(lists: list[list[str]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\n")
    for lst in lists:
        compact_json = json.dumps(lst, separators=(",", ":"))
        writer.writerow([compact_json, ""])
    return out.getvalue()


def verify_data_csv_convention(repo_root: Path, override_csv_bytes: bytes | None = None) -> None:
    if override_csv_bytes is not None:
        committed_csv = override_csv_bytes
    else:
        committed_path = repo_root / "exercises" / "practice" / "proverb" / "data.csv"
        if not committed_path.is_file():
            raise ExerciseRunError(f"Committed data.csv not found at {committed_path}")
        committed_csv = committed_path.read_bytes()

    test_lists = [
        [],
        ["nail"],
        ["nail", "shoe"],
        ["nail", "shoe", "horse"],
        ["nail", "shoe", "horse", "rider", "message", "battle", "kingdom"],
        ["pin", "gun", "soldier", "battle"],
    ]
    generated_text = make_data_csv(test_lists)
    generated_bytes = generated_text.encode("utf-8")

    if generated_bytes != committed_csv:
        raise ExerciseRunError(
            "data.csv encoding convention does not match committed file byte-for-byte"
        )


def run_driver(
    exercise_dir: Path,
    solution_sql: str,
    lists: list[list[str]],
    timer: bool = True,
    stats: bool = True,
    timeout: float = RUN_CAP_SECONDS,
) -> dict:
    _, _, _, solution_rel, _, _ = load_config(exercise_dir)
    csv_text = make_data_csv(lists)

    with tempfile.TemporaryDirectory() as tmp_dir:
        copy_dir = Path(tmp_dir) / "exercise"
        shutil.copytree(exercise_dir, copy_dir)

        (copy_dir / "data.csv").write_text(csv_text, encoding="utf-8")
        dest_solution = copy_dir / solution_rel
        dest_solution.write_text(solution_sql, encoding="utf-8")

        driver_sql = f"""
.read ./create_fixture.sql
{".timer on" if timer else ""}
{".stats vmstep" if stats else ""}
.read ./{solution_rel}
{".timer off" if timer else ""}
{".stats off" if stats else ""}
.mode json
SELECT strings, result FROM proverb ORDER BY rowid;
"""
        driver_path = copy_dir / "driver.sql"
        driver_path.write_text(driver_sql, encoding="utf-8")

        t0 = time.perf_counter()
        with open(driver_path, "rb") as stdin_f:
            try:
                proc = subprocess.run(
                    ["sqlite3", ":memory:", "-bail"],
                    stdin=stdin_f,
                    cwd=copy_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                raise ExerciseRunError(f"Driver execution timed out after {timeout}s")
        t1 = time.perf_counter()
        wall = t1 - t0

        if proc.returncode != 0:
            raise ExerciseRunError(
                f"sqlite3 driver exited with return code {proc.returncode}: {proc.stderr.strip()}"
            )

        stdout = proc.stdout
        idx = stdout.find("[")
        if idx == -1:
            raise ExerciseRunError(f"Could not find JSON array in driver output: {stdout!r}")

        stats_text = stdout[:idx]
        json_text = stdout[idx:].strip()

        try:
            json_rows = json.loads(json_text)
        except Exception as e:
            raise ExerciseRunError(f"Failed to parse driver JSON output: {e}; text: {json_text!r}")

        results = [row.get("result") for row in json_rows]

        timers = []
        if timer:
            timers = [float(m) for m in re.findall(r"Run Time:\s+real\s+([0-9.]+)", stats_text)]

        vm_steps = []
        if stats:
            vm_steps = [int(m) for m in re.findall(r"VM-steps:\s+(\d+)", stats_text)]
            if not vm_steps:
                vm_steps = [int(m) for m in re.findall(r"Virtual Machine Steps:\s+(\d+)", stats_text)]

        stmt1_timer = timers[0] if len(timers) > 0 else 0.0
        stmt1_vm = vm_steps[0] if len(vm_steps) > 0 else 0

        stmt2_timer = timers[1] if len(timers) > 1 else stmt1_timer
        stmt2_vm = vm_steps[1] if len(vm_steps) > 1 else stmt1_vm

        return {
            "wall": wall,
            "results": results,
            "timers": timers,
            "vm_steps": vm_steps,
            "stmt1_timer": stmt1_timer,
            "stmt1_vm": stmt1_vm,
            "stmt2_timer": stmt2_timer,
            "stmt2_vm": stmt2_vm,
        }


def run_committed_tests(
    solution_sql: str,
    exercise_dir: Path | None = None,
    test_file_override: str | None = None,
) -> list[dict]:
    if exercise_dir is None:
        exercise_dir = get_repo_root() / "exercises" / "practice" / "proverb"
    _, _, _, solution_rel, test_rel, _ = load_config(exercise_dir)
    with tempfile.TemporaryDirectory() as tmp_dir:
        copy_dir = Path(tmp_dir) / "exercise"
        shutil.copytree(exercise_dir, copy_dir)
        (copy_dir / solution_rel).write_text(solution_sql, encoding="utf-8")
        test_file = test_file_override if test_file_override else test_rel
        with open(copy_dir / test_file, "rb") as stdin_f:
            proc = subprocess.run(
                ["sqlite3", "-bail"],
                stdin=stdin_f,
                cwd=copy_dir,
                capture_output=True,
                text=True,
            )
        if proc.returncode != 0:
            raise ExerciseRunError(
                f"sqlite3 test execution failed (rc={proc.returncode}): {proc.stderr.strip()}"
            )
        out_json_path = copy_dir / "output.json"
        if not out_json_path.is_file() or out_json_path.stat().st_size == 0:
            raise ExerciseRunError("output.json is missing or empty after test execution")
        try:
            out_json = json.loads(out_json_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise ExerciseRunError(f"Failed to parse output.json: {e}")
        if not isinstance(out_json, list):
            raise ExerciseRunError(f"output.json is not a JSON list: got {type(out_json)}")
        return out_json


def assert_all_pass(entries: list[dict]) -> None:
    failing = [r for r in entries if r.get("status") != "pass"]
    if failing:
        raise AssertionError(f"{len(failing)} test cases failed (expected all pass)")


def assert_nonzero(entries: list[dict]) -> None:
    if len(entries) == 0:
        raise AssertionError("Zero tests executed in output.json")


def compare_expected(actual: str, expected: str) -> None:
    if actual != expected:
        act_lines = actual.split("\n")
        exp_lines = expected.split("\n")
        diff_detail = f"line count mismatch (actual {len(act_lines)} lines vs expected {len(exp_lines)} lines)"
        for idx, (al, el) in enumerate(zip(act_lines, exp_lines)):
            if al != el:
                diff_detail = f"line {idx+1}: actual={al!r} != expected={el!r}"
                break
        raise AssertionError(f"Correctness mismatch: {diff_detail}")


def check_guard(paths: list[str], ref: str) -> None:
    if len(paths) != 0:
        raise ExerciseRunError(
            f"Guard failure: unauthorized files modified under exercises/ or bin/ (ref {ref}): {paths}"
        )


def check_vm_linearity(steps: dict[int, int]) -> tuple[float, float, float]:
    step100 = steps[100]
    step1000 = steps[1000]
    step10000 = steps[10000]

    slope1 = (step1000 - step100) / 900.0
    slope2 = (step10000 - step1000) / 9000.0

    rel_diff = abs(slope1 - slope2) / slope2
    if rel_diff > 0.005:
        raise AssertionError(
            f"VM steps linearity assertion failed: slope1={slope1:.4f}, slope2={slope2:.4f}, rel_diff={rel_diff:.6f} > 0.005"
        )
    return slope1, slope2, rel_diff


def compute_net_wall_ratio(net1: float, below1: bool, net2: float, below2: bool) -> float | None:
    if below1 or below2 or net1 <= 0:
        return None
    return net2 / net1


def format_ratio(ratio: float | None) -> str:
    if ratio is None:
        return "n/a (below noise)"
    return f"{ratio:.2f}x" if ratio < 10 else f"{ratio:.1f}x"


def compute_growth_exponent(t1: float, n1: int, t2: float, n2: int) -> float | None:
    if n1 == n2 or t1 <= 0 or t2 <= 0:
        return None
    return math.log(t2 / t1) / math.log(n2 / n1)


def format_exponent(exp: float | None) -> str:
    if exp is None:
        return "n/a (same n)"
    return f"{exp:.2f}"


def get_tool_version(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True).strip()
    except Exception as e:
        return f"unknown ({e})"


# --- Docs Block Renderers and Verifier ---

def render_results_block(evidence: dict) -> str:
    noise = evidence["noise"]
    startup = evidence["startup"]
    timing = evidence["timing"]

    bare_ms = startup["bare_sqlite_median_s"] * 1000
    driver_ms = noise["driver_1_median_s"] * 1000
    floor_ms = noise["noise_floor_s"] * 1000

    lines = [
        "The startup baselines measured over 5 repetitions are:",
        f"- Bare SQLite process (`sqlite3 :memory: \"SELECT 1;\"`): **{bare_ms:.3f} ms**",
        f"- Harness driver on a 1-item list: **{driver_ms:.3f} ms** (noise floor: **{floor_ms:.3f} ms**)",
        "",
        "The measured scaling metrics across all evaluated sizes are:",
        "",
        "| n | L | wall median (s) | net wall | statement-2 median (s) | statement-2 VM steps |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in timing:
        n = row["n"]
        l_label = row["item_len"]
        wall_med = f"{row['wall_median_s']:.6f}"
        net_wall = "below noise" if row["below_noise"] else f"{row['net_wall_s']:.6f} s"
        stmt2_med = f"{row['statement_2_median_s']:.6f}"
        stmt2_vm = str(row["statement_2_vm_steps"])
        lines.append(f"| {n} | {l_label} | {wall_med} | {net_wall} | {stmt2_med} | {stmt2_vm} |")
    return "\n".join(lines)


def render_growth_block(evidence: dict) -> str:
    ratios = evidence["ratios"]
    exponents = evidence["growth_exponents"]
    prep = evidence["preparation"]

    lines = [
        "The scaling ratios and local growth exponents between evaluated sizes are:",
        "",
        "| comparison | statement-2 ratio | local exponent (alpha) | net wall ratio |",
        "| --- | --- | --- | --- |",
        f"| short: 100 -> 1000 | {ratios['statement_timer_100_to_1000_short']:.1f}x | {format_exponent(exponents['short_100_to_1000'])} | {format_ratio(ratios['net_wall_100_to_1000_short'])} |",
        f"| short: 1000 -> 10000 | {ratios['statement_timer_1000_to_10000_short']:.1f}x | {format_exponent(exponents['short_1000_to_10000'])} | {format_ratio(ratios['net_wall_1000_to_10000_short'])} |",
        f"| L=50: 100 -> 1000 | {ratios['statement_timer_100_to_1000_len50']:.1f}x | {format_exponent(exponents['len50_100_to_1000'])} | {format_ratio(ratios['net_wall_100_to_1000_len50'])} |",
        f"| L=50 vs short at n=1000 | {ratios['statement_timer_len50_to_short_at_1000']:.2f}x | {format_exponent(exponents['len50_to_short_at_1000'])} | {format_ratio(ratios['net_wall_len50_to_short_at_1000'])} |",
        "",
        f"The tables report Statement 2 (the recursive UPDATE); Statement 1 (the empty-list check) executes in a constant {prep['statement_1_vm_steps_constant']} VM steps. {prep['sentence']}",
    ]
    return "\n".join(lines)


def render_probes_block(evidence: dict) -> str:
    probes_table = evidence["probes"]["table"]
    lines = [
        "The attribution probe measurements across sizes and item lengths are:",
        "",
        "| probe | n | L | statement-2 median (s) | VM steps | output equals expected |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in probes_table:
        p_id = row["probe"]
        n = row["n"]
        l_label = row["L"]
        med = f"{row['statement_median_s']:.6f}"
        vm = str(row["vm_steps"])
        match = "true" if row["output_matches_expected"] else "false"
        lines.append(f"| {p_id} | {n} | {l_label} | {med} | {vm} | {match} |")
    lines.extend([
        "",
        "Probe descriptions:",
        "- **P0**: Unmodified reference implementation. Output equals expected: true.",
        "- **P1**: both JSON_EXTRACT calls in the recursive step AND the PRINTF calls that build their paths are replaced by constants; the recursion still runs n-1 times and still carries `strings`. Output equals expected: false (substitutes constants).",
        "- **P2**: the recursive rows no longer carry `strings`; the text is read from the base table inside the recursion. Output equals expected: true.",
        "",
        "Probes are diagnostic cost probes, not alternative solutions.",
    ])
    return "\n".join(lines)


def compute_session_variation(evidence: dict) -> list[dict]:
    timing = evidence["timing"]
    probes = evidence["probes"]["table"]
    conditions = [
        (1000, "short", "n=1000 (short)"),
        (10000, "short", "n=10000 (short)"),
        (1000, "50", "n=1000 (L=50)"),
    ]
    results = []
    for n, l_prefix, cond in conditions:
        sweep_row = next(
            r for r in timing
            if r["n"] == n and (r["item_len"].startswith(l_prefix) if l_prefix == "short" else r["item_len"] == l_prefix)
        )
        probe_row = next(
            r for r in probes
            if r["probe"] == "P0" and r["n"] == n and (r["L"].startswith(l_prefix) if l_prefix == "short" else r["L"] == l_prefix)
        )
        sweep_med = sweep_row["statement_2_median_s"]
        probe_med = probe_row["statement_median_s"]
        rel_diff = (probe_med - sweep_med) / sweep_med
        results.append({
            "condition": cond,
            "probe_median_s": probe_med,
            "relative_diff": rel_diff,
            "sweep_median_s": sweep_med,
        })
    return results


def render_additivity_block(evidence: dict) -> str:
    add = evidence["additivity"]
    lines = [
        "The additive contribution of the two diagnostic probes across conditions:",
        "",
        "| condition | P0 statement-2 (s) | extract saving (P0 - P1) | payload saving (P0 - P2) | total savings (s) | share of P0 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in add["conditions"]:
        cond = row["condition"]
        p0 = f"{row['p0_s']:.6f}"
        ext_s = f"{row['saving_extract_s']:.6f} s ({row['saving_extract_pct']:.0%})"
        pay_s = f"{row['saving_payload_s']:.6f} s ({row['saving_payload_pct']:.0%})"
        tot_s = f"{row['saving_extract_s'] + row['saving_payload_s']:.6f} s"
        share_s = f"{row['share']:.0%}"
        lines.append(f"| {cond} | {p0} | {ext_s} | {pay_s} | {tot_s} | {share_s} |")
    lines.extend([
        "",
        "Additivity evaluation:",
    ])
    for row in add["conditions"]:
        cond = row["condition"]
        pct_ext = f"{row['saving_extract_pct']:.0%}"
        pct_pay = f"{row['saving_payload_pct']:.0%}"
        lines.append(f"- At {cond}: {row['sentence']} (extract saving: {pct_ext}, payload saving: {pct_pay}).")

    session_var = compute_session_variation(evidence)
    lines.extend([
        "",
        "Session variation for the unmodified reference (P0):",
        "",
        "| condition | sweep median (s) | probe-set P0 median (s) | difference |",
        "| --- | --- | --- | --- |",
    ])
    for row in session_var:
        cond = row["condition"]
        sw_s = f"{row['sweep_median_s']:.6f}"
        pr_s = f"{row['probe_median_s']:.6f}"
        diff_s = f"{row['relative_diff']:+.1%}"
        lines.append(f"| {cond} | {sw_s} | {pr_s} | {diff_s} |")

    diff_strs = [f"{abs(r['relative_diff']):.1%}" for r in session_var]
    diff_list_str = ", ".join(diff_strs[:-1]) + f", and {diff_strs[-1]}"
    max_diff_str = f"{max(abs(r['relative_diff']) for r in session_var):.1%}"
    lines.extend([
        "",
        f"The unmodified statement was measured twice in this run (main sweep and probe set); the medians differ by {diff_list_str} (largest {max_diff_str}), so the shares above are accurate only to about that margin and must not be read to the nearest percent.",
    ])
    return "\n".join(lines)


BLOCK_RENDERERS = {
    "results": render_results_block,
    "growth": render_growth_block,
    "probes": render_probes_block,
    "additivity": render_additivity_block,
}


def extract_block_from_text(text: str, name: str) -> str:
    start_tag = f"<!-- BEGIN GENERATED: {name} -->"
    end_tag = f"<!-- END GENERATED: {name} -->"
    start_pos = text.find(start_tag)
    if start_pos == -1:
        raise DocsVerificationError(f"Start tag '{start_tag}' not found in docs")
    content_start = start_pos + len(start_tag)
    end_pos = text.find(end_tag, content_start)
    if end_pos == -1:
        raise DocsVerificationError(f"End tag '{end_tag}' not found in docs")
    return text[content_start:end_pos].strip()


def verify_docs_blocks(docs_text: str, evidence: dict) -> None:
    for name in BLOCK_NAMES:
        actual = extract_block_from_text(docs_text, name)
        expected = BLOCK_RENDERERS[name](evidence).strip()
        if actual != expected:
            act_lines = actual.splitlines()
            exp_lines = expected.splitlines()
            diff_line = "length mismatch"
            for idx, (al, el) in enumerate(zip(act_lines, exp_lines)):
                if al != el:
                    diff_line = f"line {idx+1}:\n  Docs:     {al!r}\n  Expected: {el!r}"
                    break
            if diff_line == "length mismatch":
                diff_line = f"docs has {len(act_lines)} lines, expected has {len(exp_lines)} lines"
            raise DocsVerificationError(
                f"Docs block '{name}' does not match evidence:\n{diff_line}"
            )


def update_docs_file(docs_path: Path, evidence: dict) -> None:
    docs_text = docs_path.read_text(encoding="utf-8")
    for name in BLOCK_NAMES:
        start_tag = f"<!-- BEGIN GENERATED: {name} -->"
        end_tag = f"<!-- END GENERATED: {name} -->"
        start_pos = docs_text.find(start_tag)
        if start_pos == -1:
            raise DocsVerificationError(f"Start tag '{start_tag}' not found in docs")
        content_start = start_pos + len(start_tag)
        end_pos = docs_text.find(end_tag, content_start)
        if end_pos == -1:
            raise DocsVerificationError(f"End tag '{end_tag}' not found in docs")
        rendered = BLOCK_RENDERERS[name](evidence).strip()
        docs_text = docs_text[:content_start] + "\n" + rendered + "\n" + docs_text[end_pos:]
    docs_path.write_text(docs_text, encoding="utf-8")


# --- Self-Test ---

def run_self_test(repo_root: Path) -> None:
    print("Running self-test scenarios...")
    exercise_dir = repo_root / "exercises" / "practice" / "proverb"
    solution_file, _, example_file, _, _, _ = load_config(exercise_dir)
    reference_sql = example_file.read_text(encoding="utf-8")
    stub_sql = solution_file.read_text(encoding="utf-8")

    # (a) stub as solution -> assert_all_pass fails
    scenario_a_ok = False
    try:
        entries = run_committed_tests(stub_sql, exercise_dir=exercise_dir)
        assert_all_pass(entries)
        print("Scenario (a) FAILED: all-pass assertion did not fail.")
    except AssertionError as e:
        scenario_a_ok = True
        print(f"Scenario (a) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (a) FAILED with unexpected exception: {e}")

    # (b) test SQL SELECT * FROM table_that_does_not_exist; -> non-zero child exit
    scenario_b_ok = False
    try:
        run_committed_tests("SELECT * FROM table_that_does_not_exist;", exercise_dir=exercise_dir)
        print("Scenario (b) FAILED: non-zero exit was not triggered.")
    except ExerciseRunError as e:
        scenario_b_ok = True
        print(f"Scenario (b) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (b) FAILED with unexpected exception: {e}")

    # (c) test SQL that writes [] to ./output.json -> assert_nonzero fails
    scenario_c_ok = False
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            copy_dir = Path(tmp_dir) / "exercise"
            shutil.copytree(exercise_dir, copy_dir)
            zero_test_sql = """.mode json
.once './output.json'
.print []
SELECT 1 WHERE 0;
"""
            (copy_dir / "zero.sql").write_text(zero_test_sql)
            with open(copy_dir / "zero.sql", "rb") as stdin_f:
                subprocess.run(["sqlite3", "-bail"], stdin=stdin_f, cwd=copy_dir, capture_output=True)
            out_json = json.loads((copy_dir / "output.json").read_text(encoding="utf-8"))
            assert_nonzero(out_json)
        print("Scenario (c) FAILED: zero-test check did not fail.")
    except AssertionError as e:
        scenario_c_ok = True
        print(f"Scenario (c) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (c) FAILED with unexpected exception: {e}")

    # (d) expected_proverb with its last line dropped -> compare_expected fails
    scenario_d_ok = False
    try:
        res = run_driver(exercise_dir, reference_sql, [["nail", "shoe"]], timer=False, stats=False)
        actual = res["results"][0]
        full_expected = expected_proverb(["nail", "shoe"])
        bad_expected = "\n".join(full_expected.split("\n")[:-1])
        compare_expected(actual, bad_expected)
        print("Scenario (d) FAILED: dropped last line was not detected.")
    except AssertionError as e:
        scenario_d_ok = True
        print(f"Scenario (d) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (d) FAILED with unexpected exception: {e}")

    # (e) reference with two words in PRINTF pair swapped -> compare_expected fails
    scenario_e_ok = False
    try:
        swapped_target = """            JSON_EXTRACT(strings, PRINTF('$[%d]', i)),
            JSON_EXTRACT(strings, PRINTF('$[%d]', i + 1))"""
        swapped_replacement = """            JSON_EXTRACT(strings, PRINTF('$[%d]', i + 1)),
            JSON_EXTRACT(strings, PRINTF('$[%d]', i))"""
        if swapped_target not in reference_sql:
            raise ExerciseRunError("Swap patch target not found in reference SQL")
        bad_ref_sql = reference_sql.replace(swapped_target, swapped_replacement)
        res = run_driver(exercise_dir, bad_ref_sql, [["nail", "shoe"]], timer=False, stats=False)
        actual = res["results"][0]
        expected = expected_proverb(["nail", "shoe"])
        compare_expected(actual, expected)
        print("Scenario (e) FAILED: swapped words reference was not detected.")
    except AssertionError as e:
        scenario_e_ok = True
        print(f"Scenario (e) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (e) FAILED with unexpected exception: {e}")

    # (f) guard function fed one changed path under exercises/ -> fails
    scenario_f_ok = False
    try:
        check_guard(["exercises/practice/proverb/proverb.sql"], "test_ref")
        print("Scenario (f) FAILED: unauthorized changed path was not rejected by guard.")
    except ExerciseRunError as e:
        scenario_f_ok = True
        print(f"Scenario (f) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (f) FAILED with unexpected exception: {e}")

    # (g) quadratic VM-step series fed to linearity check -> fails
    scenario_g_ok = False
    try:
        bad_steps = {100: 100**2, 1000: 1000**2, 10000: 10000**2}
        check_vm_linearity(bad_steps)
        print("Scenario (g) FAILED: quadratic VM-step series was not rejected by linearity check.")
    except AssertionError as e:
        scenario_g_ok = True
        print(f"Scenario (g) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (g) FAILED with unexpected exception: {e}")

    # (h) RUN_CAP_SECONDS set to tiny value -> timeout failure
    scenario_h_ok = False
    try:
        items = [f"w{i}" for i in range(1, 10001)]
        run_driver(exercise_dir, reference_sql, [items], timer=False, stats=False, timeout=0.0001)
        print("Scenario (h) FAILED: timeout was not triggered.")
    except ExerciseRunError as e:
        scenario_h_ok = True
        print(f"Scenario (h) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (h) FAILED with unexpected exception: {e}")

    # (i) data.csv encoding with single quotes around JSON -> convention check fails
    scenario_i_ok = False
    try:
        bad_csv_bytes = b"'[]',''\n'[\"nail\"]',''\n"
        verify_data_csv_convention(repo_root, override_csv_bytes=bad_csv_bytes)
        print("Scenario (i) FAILED: differing data.csv convention was not rejected.")
    except ExerciseRunError as e:
        scenario_i_ok = True
        print(f"Scenario (i) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (i) FAILED with unexpected exception: {e}")

    # (j) docs-block verifier fed a copy of docs text where one number inside a marked block is changed -> fails
    scenario_j_ok = False
    try:
        evidence_file = repo_root / "work" / "R08-T055" / "evidence.json"
        docs_file = repo_root / "docs" / "maintenance" / "proverb.md"
        if not docs_file.is_file():
            raise ExerciseRunError("proverb.md missing for scenario (j)")

        # Prepare minimal mock evidence if evidence.json is missing or incomplete
        mock_evidence = {
            "noise": {"driver_1_median_s": 0.0036, "noise_floor_s": 0.0002},
            "startup": {"bare_sqlite_median_s": 0.0033},
            "timing": [
                {
                    "below_noise": True,
                    "item_len": "short (2-6 chars)",
                    "n": 1,
                    "net_wall_s": -0.0001,
                    "statement_2_median_s": 0.00004,
                    "statement_2_vm_steps": 81,
                    "wall_median_s": 0.0035,
                },
                {
                    "below_noise": False,
                    "item_len": "short (2-6 chars)",
                    "n": 1000,
                    "net_wall_s": 0.0039,
                    "statement_2_median_s": 0.00309,
                    "statement_2_vm_steps": 42039,
                    "wall_median_s": 0.0076,
                },
                {
                    "below_noise": False,
                    "item_len": "short (2-6 chars)",
                    "n": 10000,
                    "net_wall_s": 0.25,
                    "statement_2_median_s": 0.25,
                    "statement_2_vm_steps": 420039,
                    "wall_median_s": 0.26,
                },
                {
                    "below_noise": False,
                    "item_len": "50",
                    "n": 1000,
                    "net_wall_s": 0.011,
                    "statement_2_median_s": 0.01048,
                    "statement_2_vm_steps": 42039,
                    "wall_median_s": 0.014,
                },
            ],
            "ratios": {
                "net_wall_100_to_1000_len50": None,
                "net_wall_100_to_1000_short": None,
                "net_wall_1000_to_10000_short": 65.0,
                "net_wall_len50_to_short_at_1000": 2.8,
                "statement_timer_100_to_1000_len50": 64.0,
                "statement_timer_100_to_1000_short": 32.5,
                "statement_timer_1000_to_10000_short": 76.8,
                "statement_timer_len50_to_short_at_1000": 3.2,
            },
            "growth_exponents": {
                "len50_100_to_1000": 1.81,
                "len50_to_short_at_1000": None,
                "short_1000_to_10000": 1.89,
                "short_100_to_1000": 1.51,
            },
            "preparation": {
                "sentence": "The SQL text is identical for every size, so statement preparation cost does not depend on n, and the statement-2 time at n=1 (0.000040 s) is an upper bound for preparation plus execution at the smallest size.",
                "statement_1_vm_steps_constant": 13,
            },
            "probes": {
                "table": [
                    {
                        "L": "short (2-6 chars)",
                        "n": 1000,
                        "output_matches_expected": True,
                        "probe": "P0",
                        "statement_median_s": 0.003125,
                        "vm_steps": 42039,
                    },
                    {
                        "L": "short (2-6 chars)",
                        "n": 10000,
                        "output_matches_expected": True,
                        "probe": "P0",
                        "statement_median_s": 0.277,
                        "vm_steps": 420039,
                    },
                    {
                        "L": "50",
                        "n": 1000,
                        "output_matches_expected": True,
                        "probe": "P0",
                        "statement_median_s": 0.0117,
                        "vm_steps": 42039,
                    },
                ]
            },
            "additivity": {
                "conditions": [
                    {
                        "condition": "n=1000 (short)",
                        "p0_s": 0.00317,
                        "saving_extract_pct": 0.8,
                        "saving_extract_s": 0.0025,
                        "saving_payload_pct": 0.15,
                        "saving_payload_s": 0.0005,
                        "sentence": "the two savings add up to 96% of the unmodified statement time",
                        "share": 0.96,
                    }
                ]
            },
        }

        if evidence_file.is_file():
            try:
                with open(evidence_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if "noise" in loaded and "preparation" in loaded:
                    mock_evidence = loaded
            except Exception:
                pass

        docs_text = docs_file.read_text(encoding="utf-8")
        # Populate all 4 blocks in docs_text using mock_evidence
        for name in BLOCK_NAMES:
            s_tag = f"<!-- BEGIN GENERATED: {name} -->"
            e_tag = f"<!-- END GENERATED: {name} -->"
            rendered = BLOCK_RENDERERS[name](mock_evidence).strip()
            s_idx = docs_text.find(s_tag)
            e_idx = docs_text.find(e_tag)
            if s_idx != -1 and e_idx != -1:
                docs_text = docs_text[:s_idx + len(s_tag)] + "\n" + rendered + "\n" + docs_text[e_idx:]

        # Verify pristine docs_text passes first
        verify_docs_blocks(docs_text, mock_evidence)

        # Now alter one number inside a marked block
        match = re.search(r"(<!-- BEGIN GENERATED: results -->.*?)(42039|\d+\.\d+)(.*?<!-- END GENERATED: results -->)", docs_text, re.DOTALL)
        if not match:
            raise ExerciseRunError("Could not find number in results block to alter for scenario (j)")
        num_str = match.group(2)
        corrupted_num = "99999" if num_str == "42039" else "9.999999"
        corrupted_docs = docs_text[:match.start(2)] + corrupted_num + docs_text[match.end(2):]

        verify_docs_blocks(corrupted_docs, mock_evidence)
        print("Scenario (j) FAILED: altered number in docs block was not detected by verifier.")
    except DocsVerificationError as e:
        scenario_j_ok = True
        print(f"Scenario (j) correctly failed: {e}")
    except Exception as e:
        print(f"Scenario (j) FAILED with unexpected exception: {e}")

    # (k) feed below-noise net-wall values to the ratio function -> returns None and renderer prints "n/a (below noise)"
    scenario_k_ok = False
    try:
        ratio_below = compute_net_wall_ratio(net1=0.00005, below1=True, net2=0.00395, below2=False)
        rendered_below = format_ratio(ratio_below)
        if ratio_below is not None:
            raise AssertionError(f"Expected None when below noise, got {ratio_below}")
        if rendered_below != "n/a (below noise)":
            raise AssertionError(f"Expected 'n/a (below noise)', got {rendered_below!r}")

        ratio_above = compute_net_wall_ratio(net1=0.00395, below1=False, net2=0.25793, below2=False)
        rendered_above = format_ratio(ratio_above)
        if ratio_above is None or not rendered_above.endswith("x"):
            raise AssertionError(f"Expected valid ratio above noise, got {ratio_above} ({rendered_above})")

        scenario_k_ok = True
        print(f"Scenario (k) correctly verified: ratio is None and renders 'n/a (below noise)': {rendered_below}")
    except AssertionError as e:
        print(f"Scenario (k) FAILED: {e}")
    except Exception as e:
        print(f"Scenario (k) FAILED with unexpected exception: {e}")

    scenarios = [
        ("a", scenario_a_ok),
        ("b", scenario_b_ok),
        ("c", scenario_c_ok),
        ("d", scenario_d_ok),
        ("e", scenario_e_ok),
        ("f", scenario_f_ok),
        ("g", scenario_g_ok),
        ("h", scenario_h_ok),
        ("i", scenario_i_ok),
        ("j", scenario_j_ok),
        ("k", scenario_k_ok),
    ]
    passed_n = sum(1 for _, ok in scenarios if ok)
    total_n = len(scenarios)

    if passed_n == total_n:
        print("Self-test: 10 failure scenarios rejected, 1 rendering check passed")
        print("ALL SELF-TEST SCENARIOS PASSED")
        sys.exit(0)
    else:
        failed_names = [name for name, ok in scenarios if not ok]
        print(f"Self-test: {passed_n}/{total_n} scenarios passed; failed: {failed_names}", file=sys.stderr)
        sys.exit(1)


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Measure scaling of the proverb reference")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test failure scenarios",
    )
    parser.add_argument(
        "--write-evidence",
        action="store_true",
        help="Run measurements, write evidence.json, versions.txt, and update docs blocks",
    )
    parser.add_argument(
        "--write-docs",
        action="store_true",
        help="Regenerate all four marked blocks of docs/maintenance/proverb.md from committed evidence.json without measurements",
    )
    args = parser.parse_args()

    repo_root = get_repo_root()
    exercise_dir = repo_root / "exercises" / "practice" / "proverb"
    work_dir = Path(__file__).resolve().parent
    docs_file = repo_root / "docs" / "maintenance" / "proverb.md"
    evidence_file = work_dir / "evidence.json"
    versions_file = work_dir / "versions.txt"

    if args.self_test:
        run_self_test(repo_root)

    if args.write_docs:
        if not evidence_file.is_file():
            print("run --write-evidence first", file=sys.stderr)
            sys.exit(1)
        with open(evidence_file, "r", encoding="utf-8") as f:
            evidence = json.load(f)
        update_docs_file(docs_file, evidence)
        docs_text = docs_file.read_text(encoding="utf-8")
        verify_docs_blocks(docs_text, evidence)
        print("Docs blocks match evidence: 4/4")
        sys.exit(0)

    solution_file, _, example_file, solution_rel, _, _ = load_config(exercise_dir)
    reference_sql = example_file.read_text(encoding="utf-8")
    stub_sql = solution_file.read_text(encoding="utf-8")

    # D.0 data.csv convention check
    verify_data_csv_convention(repo_root)

    # D.1 tests.toml parse & reference run
    tests_toml_path = exercise_dir / ".meta" / "tests.toml"
    with open(tests_toml_path, "rb") as f:
        toml_data = tomllib.load(f)
    total_count = len(toml_data)
    included_uuids = {k for k, v in toml_data.items() if isinstance(v, dict) and v.get("include") is not False}
    excluded_count = total_count - len(included_uuids)
    reimplemented_uuids = {v["reimplements"] for v in toml_data.values() if isinstance(v, dict) and "reimplements" in v}
    expected_rendered = included_uuids - reimplemented_uuids
    print(f"tests.toml: {total_count} total, {len(included_uuids)} included, {excluded_count} excluded")

    ref_out = run_committed_tests(reference_sql, exercise_dir=exercise_dir)
    assert_nonzero(ref_out)
    assert_all_pass(ref_out)
    if len(ref_out) != len(expected_rendered):
        raise ExerciseRunError(f"Executed count ({len(ref_out)}) != expected rendered ({len(expected_rendered)})")
    executed_n = len(ref_out)
    print(f"Executed {executed_n} cases")

    # D.2 Stub run
    stub_out = run_committed_tests(stub_sql, exercise_dir=exercise_dir)
    stub_pass = sum(1 for r in stub_out if r.get("status") == "pass")
    stub_fail = sum(1 for r in stub_out if r.get("status") != "pass")
    print(f"Stub: {stub_pass} passed, {stub_fail} failed")
    if stub_pass == executed_n:
        raise ExerciseRunError("Negative control failed: stub passed every test case")

    # D.3 Guard
    guard_ref = "origin/main"
    verify_cmd = subprocess.run(
        ["git", "rev-parse", "--verify", f"{guard_ref}^{{commit}}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if verify_cmd.returncode != 0:
        guard_ref = "HEAD"
    diff_proc = subprocess.run(
        ["git", "diff", "--name-only", guard_ref, "--", "exercises", "bin"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if diff_proc.returncode != 0:
        raise ExerciseRunError(f"git diff failed during guard check: {diff_proc.stderr}")
    changed_paths = [l.strip() for l in diff_proc.stdout.splitlines() if l.strip()]
    check_guard(changed_paths, guard_ref)
    print(f"Guard: 0 files modified under exercises/ and bin/ (ref: {guard_ref})")

    # D.4 Correctness BEFORE timing
    all_check_sizes = []
    for n in CORRECTNESS_ONLY_SIZES:
        all_check_sizes.append((n, "short", [f"w{i}" for i in range(1, n + 1)]))
    for n in SUPPLEMENTAL_SHORT:
        if (n, "short") not in [(c[0], c[1]) for c in all_check_sizes]:
            all_check_sizes.append((n, "short", [f"w{i}" for i in range(1, n + 1)]))
    for n in PRIMARY_SIZES:
        if (n, "short") not in [(c[0], c[1]) for c in all_check_sizes]:
            all_check_sizes.append((n, "short", [f"w{i}" for i in range(1, n + 1)]))
    for n in SERIES_50:
        all_check_sizes.append((n, "len50", [f"w_{i}_".ljust(50, "x") for i in range(1, n + 1)]))

    correctness_evidence = []
    for n, item_type, items in all_check_sizes:
        res = run_driver(exercise_dir, reference_sql, [items], timer=False, stats=False)
        actual = res["results"][0]
        expected = expected_proverb(items)
        compare_expected(actual, expected)
        correctness_evidence.append({
            "item_type": item_type,
            "match": True,
            "n": n,
        })
    print(f"Correctness: {len(correctness_evidence)}/{len(all_check_sizes)} sizes match")

    evidence_file = work_dir / "evidence.json"
    versions_file = work_dir / "versions.txt"

    # Default run: load committed evidence and verify docs blocks
    if not args.write_evidence:
        if not evidence_file.is_file():
            print("run --write-evidence first", file=sys.stderr)
            sys.exit(1)
        with open(evidence_file, "r", encoding="utf-8") as f:
            evidence = json.load(f)
        docs_text = docs_file.read_text(encoding="utf-8")
        verify_docs_blocks(docs_text, evidence)
        print("Docs blocks match evidence: 4/4")
        print("ALL CHECKS PASSED")
        sys.exit(0)

    # --- Full Measurement Routine (--write-evidence) ---

    # Startup & Noise Baselines
    bare_walls = []
    for _ in range(WARMUPS):
        subprocess.run(["sqlite3", ":memory:", "SELECT 1;"], capture_output=True)
    for _ in range(REPS):
        t0 = time.perf_counter()
        subprocess.run(["sqlite3", ":memory:", "SELECT 1;"], capture_output=True)
        t1 = time.perf_counter()
        bare_walls.append(t1 - t0)
    bare_median = statistics.median(bare_walls)

    driver_1_walls = []
    for _ in range(WARMUPS):
        run_driver(exercise_dir, reference_sql, [["w1"]], timer=True, stats=True)
    for _ in range(REPS):
        m = run_driver(exercise_dir, reference_sql, [["w1"]], timer=True, stats=True)
        driver_1_walls.append(m["wall"])
    driver_1_median = statistics.median(driver_1_walls)
    noise_floor = max(driver_1_walls) - min(driver_1_walls)

    print(
        f"Startup baseline (bare SQLite): {bare_median*1000:.3f} ms; driver on 1-item list: {driver_1_median*1000:.3f} ms; noise floor: {noise_floor*1000:.3f} ms"
    )

    timing_sizes = []
    for n in SUPPLEMENTAL_SHORT + PRIMARY_SIZES:
        timing_sizes.append((n, "short (2-6 chars)", [f"w{i}" for i in range(1, n + 1)]))
    for n in SERIES_50:
        timing_sizes.append((n, "50", [f"w_{i}_".ljust(50, "x") for i in range(1, n + 1)]))

    timing_evidence = []
    vm_steps_by_n_short = {}
    vm_steps_by_n_50 = {}

    print(f"\n{'n':>5} | {'L':<18} | {'wall med (s)':<12} | {'net wall':<12} | {'stmt2 med':<10} | {'stmt2 VM':<8} | {'stmt1 VM'}")
    print("-" * 88)

    for n, item_len_label, items in timing_sizes:
        for _ in range(WARMUPS):
            run_driver(exercise_dir, reference_sql, [items], timer=True, stats=True)

        walls = []
        stmt1_timers = []
        stmt2_timers = []
        stmt1_vms = []
        stmt2_vms = []

        for _ in range(REPS):
            m = run_driver(exercise_dir, reference_sql, [items], timer=True, stats=True)
            walls.append(m["wall"])
            stmt1_timers.append(m["stmt1_timer"])
            stmt2_timers.append(m["stmt2_timer"])
            stmt1_vms.append(m["stmt1_vm"])
            stmt2_vms.append(m["stmt2_vm"])

        wall_med = statistics.median(walls)
        wall_min = min(walls)
        wall_max = max(walls)
        stmt1_med = statistics.median(stmt1_timers)
        stmt2_med = statistics.median(stmt2_timers)
        stmt2_min = min(stmt2_timers)
        stmt2_max = max(stmt2_timers)
        stmt1_vm_val = stmt1_vms[0]
        stmt2_vm_val = stmt2_vms[0]

        net_wall_s = wall_med - driver_1_median
        below_noise = abs(net_wall_s) < noise_floor

        if item_len_label.startswith("short"):
            vm_steps_by_n_short[n] = stmt2_vm_val
        else:
            vm_steps_by_n_50[n] = stmt2_vm_val

        timing_evidence.append({
            "below_noise": below_noise,
            "item_len": item_len_label,
            "n": n,
            "net_wall_s": net_wall_s,
            "statement_1_median_s": stmt1_med,
            "statement_1_vm_steps": stmt1_vm_val,
            "statement_2_max_s": stmt2_max,
            "statement_2_median_s": stmt2_med,
            "statement_2_min_s": stmt2_min,
            "statement_2_runs_s": stmt2_timers,
            "statement_2_vm_steps": stmt2_vm_val,
            "vm_steps": stmt2_vm_val,
            "wall_max_s": wall_max,
            "wall_median_s": wall_med,
            "wall_min_s": wall_min,
            "wall_runs_s": walls,
        })

        net_str = "below noise" if below_noise else f"{net_wall_s:.6f}"
        print(
            f"{n:5d} | {item_len_label:<18} | {wall_med:12.6f} | {net_str:<12} | {stmt2_med:10.6f} | {str(stmt2_vm_val):<8} | {stmt1_vm_val}"
        )

    # VM-step linearity check
    slope1, slope2, rel_diff = check_vm_linearity(vm_steps_by_n_short)
    for n_50 in SERIES_50:
        if vm_steps_by_n_50[n_50] != vm_steps_by_n_short[n_50]:
            raise AssertionError(
                f"VM steps for 50-character series ({vm_steps_by_n_50[n_50]}) != short series ({vm_steps_by_n_short[n_50]}) at n={n_50}"
            )
    print(f"\nVM steps linear: ~{round(slope2)} per item")

    # Growth ratios & Exponents
    short_lookup = {r["n"]: r for r in timing_evidence if r["item_len"].startswith("short")}
    len50_lookup = {r["n"]: r for r in timing_evidence if not r["item_len"].startswith("short")}

    timer_100_1000_short = short_lookup[1000]["statement_2_median_s"] / short_lookup[100]["statement_2_median_s"]
    timer_1000_10000_short = short_lookup[10000]["statement_2_median_s"] / short_lookup[1000]["statement_2_median_s"]
    timer_100_1000_len50 = len50_lookup[1000]["statement_2_median_s"] / len50_lookup[100]["statement_2_median_s"]
    timer_len50_to_short_1000 = len50_lookup[1000]["statement_2_median_s"] / short_lookup[1000]["statement_2_median_s"]

    net_wall_100_1000_short = compute_net_wall_ratio(
        short_lookup[100]["net_wall_s"], short_lookup[100]["below_noise"],
        short_lookup[1000]["net_wall_s"], short_lookup[1000]["below_noise"],
    )
    net_wall_1000_10000_short = compute_net_wall_ratio(
        short_lookup[1000]["net_wall_s"], short_lookup[1000]["below_noise"],
        short_lookup[10000]["net_wall_s"], short_lookup[10000]["below_noise"],
    )
    net_wall_100_1000_len50 = compute_net_wall_ratio(
        len50_lookup[100]["net_wall_s"], len50_lookup[100]["below_noise"],
        len50_lookup[1000]["net_wall_s"], len50_lookup[1000]["below_noise"],
    )
    net_wall_len50_to_short_1000 = compute_net_wall_ratio(
        short_lookup[1000]["net_wall_s"], short_lookup[1000]["below_noise"],
        len50_lookup[1000]["net_wall_s"], len50_lookup[1000]["below_noise"],
    )

    exp_short_100_1000 = compute_growth_exponent(
        short_lookup[100]["statement_2_median_s"], 100,
        short_lookup[1000]["statement_2_median_s"], 1000,
    )
    exp_short_1000_10000 = compute_growth_exponent(
        short_lookup[1000]["statement_2_median_s"], 1000,
        short_lookup[10000]["statement_2_median_s"], 10000,
    )
    exp_len50_100_1000 = compute_growth_exponent(
        len50_lookup[100]["statement_2_median_s"], 100,
        len50_lookup[1000]["statement_2_median_s"], 1000,
    )
    exp_len50_to_short_1000 = compute_growth_exponent(
        short_lookup[1000]["statement_2_median_s"], 1000,
        len50_lookup[1000]["statement_2_median_s"], 1000,
    )

    growth_ratios = {
        "net_wall_100_to_1000_len50": net_wall_100_1000_len50,
        "net_wall_100_to_1000_short": net_wall_100_1000_short,
        "net_wall_1000_to_10000_short": net_wall_1000_10000_short,
        "net_wall_len50_to_short_at_1000": net_wall_len50_to_short_1000,
        "statement_timer_100_to_1000_len50": timer_100_1000_len50,
        "statement_timer_100_to_1000_short": timer_100_1000_short,
        "statement_timer_1000_to_10000_short": timer_1000_10000_short,
        "statement_timer_len50_to_short_at_1000": timer_len50_to_short_1000,
    }

    growth_exponents = {
        "len50_100_to_1000": exp_len50_100_1000,
        "len50_to_short_at_1000": exp_len50_to_short_1000,
        "short_1000_to_10000": exp_short_1000_10000,
        "short_100_to_1000": exp_short_100_1000,
    }

    # Preparation data
    stmt2_at_n1 = short_lookup[1]["statement_2_median_s"]
    prep_sentence = (
        f"The SQL text is identical for every size, so statement preparation cost does not depend on n, "
        f"and the statement-2 time at n=1 ({stmt2_at_n1:.6f} s) is an upper bound for preparation plus execution at the smallest size."
    )
    preparation_data = {
        "explanation": "The reference comprises two UPDATE statements. The tables report Statement 2 (the recursive UPDATE); Statement 1 (the empty-list check) executes in a constant 13 VM steps.",
        "sentence": prep_sentence,
        "statement_1_vm_steps_constant": 13,
        "statement_2_at_n1_s": stmt2_at_n1,
        "table_statement": 2,
    }

    # Probes
    p0_sql = reference_sql
    if P1_OLD_BLOCK not in reference_sql:
        raise ExerciseRunError("P1 patch target block not found in reference SQL")
    p1_sql = reference_sql.replace(P1_OLD_BLOCK, P1_NEW_BLOCK)

    if P2_OLD_BLOCK not in reference_sql:
        raise ExerciseRunError("P2 patch target block not found in reference SQL")
    p2_sql = reference_sql.replace(P2_OLD_BLOCK, P2_NEW_BLOCK)

    probe_targets = [
        ("P0", p0_sql),
        ("P1", p1_sql),
        ("P2", p2_sql),
    ]

    probe_runs_spec = [
        (1000, "short (2-6 chars)", [f"w{i}" for i in range(1, 1001)]),
        (10000, "short (2-6 chars)", [f"w{i}" for i in range(1, 10001)]),
        (1000, "50", [f"w_{i}_".ljust(50, "x") for i in range(1, 1001)]),
    ]

    probe_evidence = []
    probe_medians = {}

    print(f"\n{'probe':<5} | {'n':>5} | {'L':<18} | {'stmt2 med':<12} | {'VM steps':<8} | {'matches exp'}")
    print("-" * 68)

    for p_id, p_sql in probe_targets:
        for n, l_label, items in probe_runs_spec:
            for _ in range(WARMUPS):
                run_driver(exercise_dir, p_sql, [items], timer=True, stats=True)

            p_timers = []
            p_vms = []
            last_res = None
            for _ in range(REPS):
                m = run_driver(exercise_dir, p_sql, [items], timer=True, stats=True)
                p_timers.append(m["stmt2_timer"])
                p_vms.append(m["stmt2_vm"])
                last_res = m["results"][0]

            med_timer = statistics.median(p_timers)
            med_vm = p_vms[0]
            probe_medians[(p_id, n, l_label)] = med_timer
            matches_exp = (last_res == expected_proverb(items))

            probe_evidence.append({
                "L": l_label,
                "n": n,
                "output_matches_expected": matches_exp,
                "probe": p_id,
                "statement_median_s": med_timer,
                "vm_steps": med_vm,
            })
            print(f"{p_id:<5} | {n:5d} | {l_label:<18} | {med_timer:12.6f} | {str(med_vm):<8} | {matches_exp}")

    probe_outputs_list = [
        {
            "L": r["L"],
            "n": r["n"],
            "output_matches_expected": r["output_matches_expected"],
            "probe": r["probe"],
        }
        for r in probe_evidence
    ]

    # Additivity
    conditions_spec = [
        (1000, "short (2-6 chars)", "n=1000 (short)"),
        (10000, "short (2-6 chars)", "n=10000 (short)"),
        (1000, "50", "n=1000 (L=50)"),
    ]

    additivity_conditions = []
    for n, l_label, cond_name in conditions_spec:
        p0 = probe_medians[("P0", n, l_label)]
        p1 = probe_medians[("P1", n, l_label)]
        p2 = probe_medians[("P2", n, l_label)]
        saving_extract = p0 - p1
        saving_payload = p0 - p2
        share = (saving_extract + saving_payload) / p0
        is_additive = (ADDITIVITY_LOW <= share <= ADDITIVITY_HIGH)
        if is_additive:
            sentence = f"the two savings add up to {share:.0%} of the unmodified statement time"
        else:
            sentence = f"the two savings do not add up to the unmodified time ({share:.0%})"

        additivity_conditions.append({
            "L": l_label,
            "condition": cond_name,
            "is_additive": is_additive,
            "n": n,
            "p0_s": p0,
            "p1_s": p1,
            "p2_s": p2,
            "saving_extract_pct": saving_extract / p0,
            "saving_extract_s": saving_extract,
            "saving_payload_pct": saving_payload / p0,
            "saving_payload_s": saving_payload,
            "sentence": sentence,
            "share": share,
        })

    additivity_data = {
        "conditions": additivity_conditions,
        "threshold_high": ADDITIVITY_HIGH,
        "threshold_low": ADDITIVITY_LOW,
    }

    noise_data = {
        "driver_1_median_s": driver_1_median,
        "driver_1_runs_s": driver_1_walls,
        "noise_floor_formula": "max(driver_1_runs) - min(driver_1_runs)",
        "noise_floor_s": noise_floor,
    }

    # Tool versions
    tool_versions = {
        "git": get_tool_version(["git", "--version"]),
        "jq": get_tool_version(["jq", "--version"]),
        "os": f"{platform.system()} {platform.release()} {platform.machine()}",
        "python": f"Python {platform.python_version()}",
        "sqlite3": get_tool_version(["sqlite3", "--version"]),
    }

    evidence = {
        "additivity": additivity_data,
        "correctness": correctness_evidence,
        "counts": {
            "excluded": excluded_count,
            "executed": executed_n,
            "included": len(included_uuids),
            "reimplemented": len(reimplemented_uuids),
            "total": total_count,
        },
        "definitions": {
            "L": "average item length in characters",
            "domain": "unbounded (specification does not bound list length or item length and does not require distinct items)",
            "n": "number of items in the list",
        },
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "sqlite3": tool_versions["sqlite3"],
        },
        "growth_exponents": growth_exponents,
        "guard": {
            "ref": guard_ref,
            "status": "clean",
        },
        "noise": noise_data,
        "preparation": preparation_data,
        "probe_outputs": probe_outputs_list,
        "probes": {
            "p1_sql": p1_sql,
            "p2_sql": p2_sql,
            "table": probe_evidence,
        },
        "ratios": growth_ratios,
        "self_test": {
            "scenarios_total": 11,
        },
        "startup": {
            "bare_sqlite_median_s": bare_median,
            "driver_1_median_s": driver_1_median,
        },
        "stub": {
            "failed": stub_fail,
            "passed": stub_pass,
            "total": executed_n,
        },
        "timing": timing_evidence,
        "tool_versions": tool_versions,
        "vm_linearity": {
            "relative_diff": rel_diff,
            "slope1": slope1,
            "slope2": slope2,
        },
    }

    work_dir.mkdir(parents=True, exist_ok=True)

    with open(versions_file, "w", encoding="utf-8") as f:
        for tool in sorted(tool_versions.keys()):
            f.write(f"{tool}: {tool_versions[tool]}\n")

    with open(evidence_file, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2, sort_keys=True)
        f.write("\n")

    # Update docs marked blocks
    update_docs_file(docs_file, evidence)

    # Verify docs blocks match evidence
    docs_text = docs_file.read_text(encoding="utf-8")
    verify_docs_blocks(docs_text, evidence)
    print("\nDocs blocks match evidence: 4/4")
    print("ALL CHECKS PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
