import json, os, shutil, subprocess, sys, pathlib
try:
    import tomllib as toml
except ImportError:
    import toml

# Helper to resolve paths safely
def resolve_path(base_dir: pathlib.Path, rel: str) -> pathlib.Path:
    p = pathlib.Path(rel)
    if p.is_absolute():
        raise ValueError(f"Absolute path not allowed: {rel}")
    resolved = (base_dir / p).resolve()
    try:
        resolved.relative_to(base_dir.resolve())
    except Exception:
        raise ValueError(f"Path escapes exercise directory: {rel}")
    return resolved

repo_root = pathlib.Path(__file__).resolve().parents[2]
exercise_dir = repo_root / "exercises" / "practice" / "scrabble-score"
config_path = exercise_dir / ".meta" / "config.json"
if not config_path.is_file():
    sys.exit(f"Config file not found: {config_path}")
with open(config_path, "r", encoding="utf-8") as f:
    cfg = json.load(f)
files_cfg = cfg.get("files", {})
if not files_cfg:
    sys.exit("No 'files' section in config")
# Validate declared files and collect absolute paths
resolved = {}
for role, rel_paths in files_cfg.items():
    resolved[role] = []
    for rel in rel_paths:
        try:
            abs_path = resolve_path(exercise_dir, rel)
        except ValueError as e:
            sys.exit(str(e))
        if not abs_path.is_file():
            sys.exit(f"Declared {role} file does not exist: {rel}")
        resolved[role].append(abs_path)
# Prepare clean working copy (temp directory)
work_dir = repo_root / "work" / "R08-T038"
if work_dir.is_dir():
    shutil.rmtree(work_dir)
shutil.copytree(exercise_dir, work_dir, dirs_exist_ok=False)  # copy all, including hidden files
# Substitute learner solution with reference implementation
if "solution" not in resolved or "example" not in resolved:
    sys.exit("Missing solution or example declaration")
solution_rel = resolved["solution"][0].relative_to(exercise_dir)
example_rel = resolved["example"][0].relative_to(exercise_dir)
solution_path = work_dir / solution_rel
example_path = work_dir / example_rel
shutil.copyfile(example_path, solution_path)
# Run the test suite using sqlite3
if "test" not in resolved:
    sys.exit("Missing test declaration")
test_rel = resolved["test"][0].relative_to(exercise_dir)
test_path = work_dir / test_rel
proc = subprocess.run(["sqlite3", "-bail", str(test_path)], cwd=work_dir, capture_output=True, text=True)
if proc.returncode != 0:
    print(proc.stderr, file=sys.stderr)
    sys.exit("Test runner failed (reference implementation)")
# Parse output.json and assert every test passed
output_json = work_dir / "output.json"
if not output_json.is_file():
    sys.exit("output.json missing after test run")
with open(output_json, "r", encoding="utf-8") as f:
    results = json.load(f)
if not results:
    sys.exit("No test results found")
for entry in results:
    if entry.get("status") != "pass":
        sys.exit(f"Test failed (reference): {entry.get('description')}")
# Save evidence files
shutil.copy(output_json, work_dir / "reference_output.json")
ver = subprocess.run(["sqlite3", "--version"], capture_output=True, text=True).stdout.strip()
with open(work_dir / "versions.txt", "w", encoding="utf-8") as f:
    f.write(f"sqlite3 {ver}\n")
# Verify learner stub still fails (run without substitution)
stub_dir = repo_root / "tmp_stub_check"
if stub_dir.is_dir():
    shutil.rmtree(stub_dir)
shutil.copytree(exercise_dir, stub_dir, dirs_exist_ok=False)
# Run tests on stub (no substitution)
stub_test_path = stub_dir / test_rel
stub_proc = subprocess.run(["sqlite3", "-bail", str(stub_test_path)], cwd=stub_dir, capture_output=True, text=True)
if stub_proc.returncode == 0:
    stub_out = stub_dir / "output.json"
    if stub_out.is_file():
        with open(stub_out) as f:
            stub_res = json.load(f)
        if all(e.get("status") == "pass" for e in stub_res):
            sys.exit("Learner stub unexpectedly passes all tests")
    else:
        sys.exit("Learner stub unexpectedly passed (no output.json)")
# Verify test descriptions match tests.toml
tests_toml_path = exercise_dir / ".meta" / "tests.toml"
if tests_toml_path.is_file():
    with open(tests_toml_path, "rb") as f:
        toml_data = tomllib.load(f)
    toml_desc = {case.get("description") for case in toml_data.get("cases", []) if "description" in case}
    result_desc = {entry.get("description") for entry in results if "description" in entry}
    missing = toml_desc - result_desc
    if missing:
        sys.exit(f"Missing test descriptions in results: {missing}")
else:
    sys.exit("tests.toml not found")
print("All checks passed")
print(f"Test count: {len(results)}")
# ---------- Negative fixture checks ----------

def run_fixture(name: str, cfg_override: dict, should_fail: bool, expected_msg: str):
    try:
        for role, rels in cfg_override.get("files", {}).items():
            for rel in rels:
                resolve_path(exercise_dir, rel)
                if not (exercise_dir / rel).exists():
                    raise FileNotFoundError(f"Declared {role} file does not exist: {rel}")
        if should_fail:
            print(f"[FAIL] Fixture {name} should have failed but passed")
            sys.exit(1)
    except Exception as e:
        if should_fail and expected_msg in str(e):
            print(f"[PASS] Fixture {name} failed as expected: {e}")
        else:
            print(f"[FAIL] Fixture {name} unexpected error: {e}")
            sys.exit(1)
# 1. Missing reference file
missing_ref_cfg = {"files": {"solution": ["scrabble-score.sql"], "test": ["scrabble-score_test.sql"], "example": [".meta/nonexistent.sql"]}}
run_fixture("missing reference", missing_ref_cfg, True, "does not exist")
# 2. Missing test file
missing_test_cfg = {"files": {"solution": ["scrabble-score.sql"], "test": ["nonexistent_test.sql"], "example": [".meta/example.sql"]}}
run_fixture("missing test", missing_test_cfg, True, "does not exist")
# 3. Path escaping exercise directory
escape_cfg = {"files": {"solution": ["../outside.sql"], "test": ["scrabble-score_test.sql"], "example": [".meta/example.sql"]}}
run_fixture("escape path", escape_cfg, True, "escapes exercise directory")
