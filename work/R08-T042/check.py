#!/usr/bin/env python3
"""
Verification check for Task R08-T042 (exercises/practice/acronym).

Requirements verified:
1. Learner stub in working tree remains unsolved.
2. Maintained reference implementation passes all 9 enabled test cases in an isolated temporary copy.
3. Test generation round trip produces identical outputs across two fresh generations (after timestamp normalization).
4. All active cases from tests.toml are preserved with zero cases dropped.
5. Generated files match the repository working tree files.
6. Documentation in docs/maintenance/acronym.md contains generation commands, input files, and case-to-output mapping.
7. Reusable check tools/course_checks/r08-t042.py is executed and verified.
8. Execution evidence is saved in work/R08-T042/.
"""

import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Add possible site-packages paths for jinja2
for p in [
    "/tmp/.venv/lib/python3.15/site-packages",
    str(Path.home() / "Library/Python/3.15/lib/python/site-packages")
]:
    if p not in sys.path and Path(p).exists():
        sys.path.insert(0, p)


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


def parse_create_test_table_sql(create_test_path: Path) -> list:
    """Extract test case definitions from create_test_table.sql."""
    with open(create_test_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(
        r"\(\s*'([a-f0-9\-]+)',\s*'([^']+)',\s*'((?:''|[^'])*)',\s*'((?:''|[^'])*)'\s*\)",
        re.MULTILINE
    )
    cases = []
    for m in pattern.finditer(content):
        uuid, desc, phrase, expected = m.groups()
        cases.append({
            "uuid": uuid,
            "description": desc,
            "phrase": phrase.replace("''", "'"),
            "expected": expected.replace("''", "'")
        })
    return cases


def verify_learner_stub(repo_root: Path, exercise_rel_path: Path, config: dict):
    """Verify that learner stub in working tree is unsolved."""
    exercise_dir = repo_root / exercise_rel_path
    solution_file = config["files"]["solution"][0]
    test_file = config["files"]["test"][0]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        temp_exercise = tmp_path / "acronym"
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
        temp_exercise = tmp_path / "acronym"
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
    table_cases = parse_create_test_table_sql(exercise_dir / "create_test_table.sql")
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
            "expected": c_info.get("expected")
        })

    with open(work_dir / "test_results.json", "w", encoding="utf-8") as f:
        json.dump(detailed_results, f, indent=2)

    print(f"[OK] Reference implementation passed all {test_count} executed test cases.")
    return {"test_count": test_count, "results": detailed_results}


def normalize_content(text: str) -> str:
    """Normalize timestamp differences or trailing whitespace."""
    normalized = re.sub(r"# generated on [0-9T:\-\+Z]+", "# generated on <TIMESTAMP>", text)
    return normalized.strip()


def verify_test_generation_round_trip(repo_root: Path, work_dir: Path) -> dict:
    """Regenerate tests in two fresh temporary copies and verify determinism and completeness."""
    exercise_dir = repo_root / "exercises" / "practice" / "acronym"
    gen_script = repo_root / "bin" / "generate_tests"

    specs_candidates = [
        Path.home() / "Library/Caches/exercism/configlet/problem-specifications",
        Path.home() / ".cache/exercism/configlet/problem-specifications"
    ]
    specs_dir = next((c for c in specs_candidates if (c / "exercises/acronym/canonical-data.json").exists()), None)
    if not specs_dir:
        raise FileNotFoundError("Could not find problem-specifications with acronym canonical data.")

    env = os.environ.copy()
    env["XDG_CACHE_HOME"] = str(specs_dir.parent.parent.parent)
    site_packages = "/tmp/.venv/lib/python3.15/site-packages"
    if Path(site_packages).exists():
        env["PYTHONPATH"] = f"{site_packages}:{env.get('PYTHONPATH', '')}"

    with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
        copy_a = Path(tmp_a) / "acronym"
        copy_b = Path(tmp_b) / "acronym"
        shutil.copytree(exercise_dir, copy_a)
        shutil.copytree(exercise_dir, copy_b)

        # Run generator on Copy A
        cmd_a = [sys.executable, str(gen_script), "--no-pull", str(copy_a)]
        proc_a = subprocess.run(cmd_a, cwd=repo_root, env=env, capture_output=True, text=True)
        if proc_a.returncode != 0:
            raise RuntimeError(f"Generation on copy A failed ({proc_a.returncode}): {proc_a.stderr}")

        # Run generator on Copy B
        cmd_b = [sys.executable, str(gen_script), "--no-pull", str(copy_b)]
        proc_b = subprocess.run(cmd_b, cwd=repo_root, env=env, capture_output=True, text=True)
        if proc_b.returncode != 0:
            raise RuntimeError(f"Generation on copy B failed ({proc_b.returncode}): {proc_b.stderr}")

        # Verify Copy A == Copy B
        files_to_check = ["create_test_table.sql", "data.csv"]
        diffs_between_copies = {}
        for fname in files_to_check:
            content_a = normalize_content((copy_a / fname).read_text(encoding="utf-8"))
            content_b = normalize_content((copy_b / fname).read_text(encoding="utf-8"))
            if content_a != content_b:
                diffs_between_copies[fname] = "\n".join(difflib.unified_diff(
                    content_a.splitlines(), content_b.splitlines(),
                    fromfile=f"Copy_A/{fname}", tofile=f"Copy_B/{fname}"
                ))

        if diffs_between_copies:
            raise AssertionError(f"Differences found between Copy A and Copy B generations: {diffs_between_copies}")

        # Verify Copy A == Repository Working Tree
        repo_diffs = {}
        for fname in files_to_check:
            content_gen = normalize_content((copy_a / fname).read_text(encoding="utf-8"))
            content_repo = normalize_content((exercise_dir / fname).read_text(encoding="utf-8"))
            if content_gen != content_repo:
                repo_diffs[fname] = "\n".join(difflib.unified_diff(
                    content_repo.splitlines(), content_gen.splitlines(),
                    fromfile=f"Repo/{fname}", tofile=f"Generated/{fname}"
                ))

        if repo_diffs:
            raise AssertionError(f"Differences between generated output and repo files: {repo_diffs}")

        # Check case preservation
        gen_cases = parse_create_test_table_sql(copy_a / "create_test_table.sql")
        toml_cases = parse_tests_toml(exercise_dir / ".meta" / "tests.toml")

        gen_uuids = [c["uuid"] for c in gen_cases]
        toml_uuids = [c["uuid"] for c in toml_cases]

        if len(gen_uuids) != len(toml_uuids):
            raise AssertionError(f"Case count mismatch: {len(gen_uuids)} generated vs {len(toml_uuids)} in tests.toml")

        dropped = set(toml_uuids) - set(gen_uuids)
        if dropped:
            raise AssertionError(f"Cases dropped during generation: {dropped}")

        round_trip_info = {
            "canonical_cases_count": len(gen_cases),
            "generated_files": files_to_check,
            "generations_identical": True,
            "repo_matches_generation": True,
            "dropped_cases_count": 0,
            "cases": gen_cases
        }

        with open(work_dir / "generation_round_trip.json", "w", encoding="utf-8") as f:
            json.dump(round_trip_info, f, indent=2)

        print(f"[OK] Generation round trip verified: 2 clean generations produced identical {len(gen_cases)} cases with 0 dropped.")
        return round_trip_info


def verify_maintenance_documentation(repo_root: Path):
    """Verify docs/maintenance/acronym.md exists and contains required sections."""
    doc_path = repo_root / "docs" / "maintenance" / "acronym.md"
    if not doc_path.exists():
        raise AssertionError(f"Documentation file {doc_path} does not exist!")

    text = doc_path.read_text(encoding="utf-8")

    required_tokens = [
        "bin/generate_tests --no-pull acronym",
        "create_test_table.sql",
        "data.csv",
        "template.create_test_table.j2",
        "tests.toml",
        "tools/course_checks/r08-t042.py",
        "Case-to-Output Mapping",
        "reimplements"
    ]
    for token in required_tokens:
        if token.lower() not in text.lower():
            raise AssertionError(f"acronym.md missing required section/token: '{token}'")

    print(f"[OK] Maintenance documentation in {doc_path} verified.")


def verify_reusable_check_tool(repo_root: Path):
    """Run tools/course_checks/r08-t042.py to verify it functions cleanly."""
    tool_path = repo_root / "tools" / "course_checks" / "r08-t042.py"
    if not tool_path.exists():
        raise AssertionError(f"Reusable check tool {tool_path} does not exist!")

    proc = subprocess.run([sys.executable, str(tool_path), "--json"], capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"{tool_path} failed with exit code {proc.returncode}:\n{proc.stderr}")

    out = json.loads(proc.stdout)
    if out.get("status") != "success" or out.get("case_count") != 9:
        raise AssertionError(f"Unexpected output from {tool_path}: {out}")

    print(f"[OK] Reusable check tool {tool_path} verified: returned success for 9 cases.")


def main():
    repo_root = Path(__file__).resolve().parent.parent.parent
    work_dir = repo_root / "work" / "R08-T042"
    work_dir.mkdir(parents=True, exist_ok=True)

    exercise_rel = Path("exercises/practice/acronym")

    print("=== Running Checks for Task R08-T042 ===")
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

    # 5. Verify test generation round trip
    rt_res = verify_test_generation_round_trip(repo_root, work_dir)

    # 6. Verify maintenance documentation
    verify_maintenance_documentation(repo_root)

    # 7. Verify reusable check tool
    verify_reusable_check_tool(repo_root)

    # Save summary
    summary = {
        "task": "R08-T042",
        "exercise": "exercises/practice/acronym",
        "reusable_tool": "tools/course_checks/r08-t042.py",
        "documentation": "docs/maintenance/acronym.md",
        "executed_test_cases": ref_res["test_count"],
        "reference_all_passed": True,
        "learner_stub_unsolved": True,
        "round_trip_verified": True,
        "generations_identical": True,
        "dropped_cases_count": 0,
        "maintenance_docs_verified": True,
        "reusable_tool_verified": True
    }
    with open(work_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n=== ALL CHECKS PASSED SUCCESSFULLY ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
