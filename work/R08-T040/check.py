import json, hashlib, os, pathlib, shutil, subprocess, sys, tempfile

def file_hash(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

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
exercise_dir = repo_root / "exercises" / "practice" / "largest-series-product"
config_path = exercise_dir / ".meta" / "config.json"
if not config_path.is_file():
    sys.exit(f"Config not found: {config_path}")
with open(config_path, "r", encoding="utf-8") as f:
    cfg = json.load(f)
files_cfg = cfg.get("files", {})
if not files_cfg:
    sys.exit("No files section in config")
# Resolve paths
resolved = {}
for role, rels in files_cfg.items():
    resolved[role] = []
    for rel in rels:
        path = resolve_path(exercise_dir, rel)
        if not path.is_file():
            sys.exit(f"Declared {role} file does not exist: {rel}")
        resolved[role].append(path)
# Ensure required roles
for r in ("solution", "test", "example"):
    if r not in resolved:
        sys.exit(f"Missing {r} declaration")
solution_path = resolved["solution"][0]
example_path = resolved["example"][0]
test_path = resolved["test"][0]
# Hash learner solution before run
pre_hash = file_hash(solution_path)
# Temporary copy and test execution
with tempfile.TemporaryDirectory() as tmpdir:
    work_dir = pathlib.Path(tmpdir)
    shutil.copytree(exercise_dir, work_dir, dirs_exist_ok=True)
    # Replace learner solution with reference implementation
    rel_solution = solution_path.relative_to(exercise_dir)
    dest_solution = work_dir / rel_solution
    shutil.copyfile(example_path, dest_solution)
    # Determine test path inside temporary copy
    test_rel = test_path.relative_to(exercise_dir)
    test_copy = work_dir / test_rel
    # Run sqlite3 tests
    proc = subprocess.run(["sqlite3", "-bail", str(test_copy)], cwd=work_dir, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        sys.exit("Test runner failed")
    out_json = work_dir / "output.json"
    if not out_json.is_file():
        sys.exit("output.json missing")
    with open(out_json, "r", encoding="utf-8") as f:
        results = json.load(f)
    if not results:
        sys.exit("Zero tests executed")
    for entry in results:
        if entry.get("status") != "pass":
            sys.exit(f"Test failed: {entry.get('description')}")
    print("All checks passed")
    print(f"Test count: {len(results)}")
    # Save evidence
    evidence_dir = repo_root / "work" / "R08-T040"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(out_json, evidence_dir / "reference_output.json")
    # Record tool versions
    sqlite_ver = subprocess.run(["sqlite3", "--version"], capture_output=True, text=True).stdout.strip()
    jq_ver = subprocess.run(["jq", "--version"], capture_output=True, text=True).stdout.strip()
    python_ver = sys.version.split()[0]
    with open(evidence_dir / "versions.txt", "w") as f:
        f.write(f"python {python_ver}\nsqlite3 {sqlite_ver}\njq {jq_ver}\n")
# Verify learner stub unchanged
post_hash = file_hash(solution_path)
if pre_hash != post_hash:
    sys.exit("Learner solution file was modified")
