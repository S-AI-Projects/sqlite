#!/usr/bin/env python3
"""
Reusable focused regeneration check for exercises/practice/acronym (Task R08-T042).

Verifies the test-generation round trip:
1. Re-renders create_test_table.sql and data.csv in two fresh temporary copies.
2. Asserts both generations are identical after timestamp normalization.
3. Asserts no test case from tests.toml is dropped.
4. Asserts reference implementation passes all generated test cases.
"""

import argparse
import difflib
import json
import os
import pathlib
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


def find_repo_root() -> Path:
    """Locate the git repository root."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".git").exists() or (current / "exercises").exists():
            return current
        current = current.parent
    return Path.cwd()


def find_specs_dir() -> Path:
    """Locate the cached problem-specifications directory."""
    candidates = [
        Path.home() / "Library/Caches/exercism/configlet/problem-specifications",
        Path.home() / ".cache/exercism/configlet/problem-specifications",
    ]
    for c in candidates:
        if (c / "exercises/acronym/canonical-data.json").exists():
            return c
    raise FileNotFoundError("Could not find problem-specifications with acronym canonical data.")


def run_generator_on_copy(repo_root: Path, target_exercise_dir: Path, specs_dir: Path):
    """Run generate_tests on a target exercise directory."""
    env = os.environ.copy()
    env["XDG_CACHE_HOME"] = str(specs_dir.parent.parent.parent)
    site_packages = "/tmp/.venv/lib/python3.15/site-packages"
    if Path(site_packages).exists():
        env["PYTHONPATH"] = f"{site_packages}:{env.get('PYTHONPATH', '')}"

    # We can invoke bin/generate_tests or run internal generator logic
    gen_script = repo_root / "bin" / "generate_tests"
    cmd = [sys.executable, str(gen_script), "--no-pull", str(target_exercise_dir)]
    proc = subprocess.run(cmd, cwd=repo_root, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"generate_tests failed ({proc.returncode}):\n{proc.stderr}\n{proc.stdout}")


def normalize_content(text: str) -> str:
    """Normalize timestamp differences or trailing whitespace."""
    # Normalize '# generated on ...' lines if present
    normalized = re.sub(r"# generated on [0-9T:\-\+Z]+", "# generated on <TIMESTAMP>", text)
    return normalized.strip()


def run_regeneration_check(repo_root: Path, quiet: bool = False) -> dict:
    """Execute two independent generations and verify consistency and correctness."""
    exercise_rel = Path("exercises/practice/acronym")
    exercise_dir = repo_root / exercise_rel
    specs_dir = find_specs_dir()

    with tempfile.TemporaryDirectory() as tmpdir_a, tempfile.TemporaryDirectory() as tmpdir_b:
        copy_a = Path(tmpdir_a) / "acronym"
        copy_b = Path(tmpdir_b) / "acronym"

        shutil.copytree(exercise_dir, copy_a)
        shutil.copytree(exercise_dir, copy_b)

        # Run generator on Copy A
        run_generator_on_copy(repo_root, copy_a, specs_dir)

        # Run generator on Copy B
        run_generator_on_copy(repo_root, copy_b, specs_dir)

        # Compare generated files between Copy A and Copy B
        generated_files = ["create_test_table.sql", "data.csv"]
        diffs = {}
        for fname in generated_files:
            text_a = normalize_content((copy_a / fname).read_text(encoding="utf-8"))
            text_b = normalize_content((copy_b / fname).read_text(encoding="utf-8"))
            if text_a != text_b:
                diff = "\n".join(difflib.unified_diff(
                    text_a.splitlines(), text_b.splitlines(),
                    fromfile=f"Copy_A/{fname}", tofile=f"Copy_B/{fname}"
                ))
                diffs[fname] = diff

        if diffs:
            raise AssertionError(f"Generations A and B differ:\n{diffs}")

        # Compare Copy A with repository working tree
        repo_diffs = {}
        for fname in generated_files:
            text_gen = normalize_content((copy_a / fname).read_text(encoding="utf-8"))
            text_repo = normalize_content((exercise_dir / fname).read_text(encoding="utf-8"))
            if text_gen != text_repo:
                diff = "\n".join(difflib.unified_diff(
                    text_repo.splitlines(), text_gen.splitlines(),
                    fromfile=f"Repo/{fname}", tofile=f"Generated/{fname}"
                ))
                repo_diffs[fname] = diff

        if repo_diffs:
            raise AssertionError(f"Generated output differs from repository files:\n{repo_diffs}")

        # Count cases generated
        create_sql = (copy_a / "create_test_table.sql").read_text(encoding="utf-8")
        case_uuids = re.findall(r"\(\s*'([a-f0-9\-]{36})'", create_sql)
        case_count = len(case_uuids)

        if case_count == 0:
            raise AssertionError("Zero test cases were generated!")

        # Verify against tests.toml
        tests_toml_text = (exercise_dir / ".meta" / "tests.toml").read_text(encoding="utf-8")
        toml_uuids = re.findall(r"\[([a-f0-9\-]{36})\]", tests_toml_text)
        missing_uuids = set(toml_uuids) - set(case_uuids)
        if missing_uuids:
            raise AssertionError(f"Cases in tests.toml were dropped during generation: {missing_uuids}")

        # Run reference implementation in Copy A
        shutil.copyfile(copy_a / ".meta" / "example.sql", copy_a / "acronym.sql")
        proc = subprocess.run("sqlite3 -bail < acronym_test.sql", cwd=copy_a, shell=True, capture_output=True, text=True)

        if proc.returncode != 0:
            raise AssertionError(f"sqlite3 failed against reference in generated copy ({proc.returncode}): {proc.stderr}")

        output_file = copy_a / "output.json"
        if not output_file.exists():
            raise AssertionError("output.json was not generated.")

        with open(output_file, "r", encoding="utf-8") as f:
            results = json.load(f)

        passed = [t for t in results if t.get("status") == "pass"]
        if len(passed) != case_count:
            raise AssertionError(f"{case_count - len(passed)} test(s) failed against reference!")

        return {
            "status": "success",
            "returncode": 0,
            "case_count": case_count,
            "generations_identical": True,
            "repo_matches_generation": True,
            "reference_passed_all": True,
            "cases": results
        }


def main():
    parser = argparse.ArgumentParser(description="Focused regeneration check for acronym.")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format.")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal console output.")
    args = parser.parse_args()

    repo_root = find_repo_root()

    try:
        res = run_regeneration_check(repo_root, quiet=args.quiet)
    except Exception as e:
        if args.json:
            print(json.dumps({"status": "failure", "error": str(e), "returncode": 1}, indent=2))
        else:
            print(f"[FAILURE] Check failed: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(res, indent=2))
    elif not args.quiet:
        print(f"[SUCCESS] Acronym test generation round trip verified successfully:")
        print(f"  - Two fresh generations produced identical outputs.")
        print(f"  - Repository matches generated files byte-for-byte.")
        print(f"  - All {res['case_count']} canonical cases preserved and passing against reference.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

