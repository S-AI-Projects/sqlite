import json, os, subprocess, shutil, tempfile, sys

def load_config(path):
    """Load the JSON config file for the exercise."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def copy_exercise(src, dst):
    """Recursively copy the whole exercise directory (including hidden files)."""
    shutil.copytree(src, dst, dirs_exist_ok=True)

def run_sqlite(test_sql_path, cwd):
    """Run `sqlite3 -bail` feeding the test SQL via stdin.
    Returns the CompletedProcess object.
    """
    with open(test_sql_path, "r", encoding="utf-8") as f:
        test_sql = f.read()
    # Use argument list, no shell
    return subprocess.run(["sqlite3", "-bail"], input=test_sql, cwd=cwd, capture_output=True, text=True)
    """Run `sqlite3 -bail` feeding the test SQL via stdin.
    Returns the CompletedProcess object.
    """
    with open(test_sql_path, "r", encoding="utf-8") as f:
        test_sql = f.read()
    # Use argument list, no shell
    return subprocess.run(["sqlite3", "-bail"], input=test_sql, cwd=cwd, capture_output=True, text=True)

def parse_output_json(dir_path):
    out_path = os.path.join(dir_path, "output.json")
    if not os.path.isfile(out_path):
        return None
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None

def all_pass(results):
    if not results:
        return False, 0
    for entry in results:
        if entry.get("status") != "pass":
            return False, len(results)
    return True, len(results)

def mutate_reference(example_path):
    """Read the maintained reference implementation, remove the NOTNULL filter,
    and write the mutated version back. Returns the mutated SQL text.
    """
    with open(example_path, "r", encoding="utf-8") as f:
        content = f.read()
    # The exact clause we expect to appear once
    target = "AND j.value NOTNULL"
    occurrences = content.count(target)
    if occurrences != 1:
        print(f"Expected exactly one occurrence of '{target}' in {example_path}, found {occurrences}")
        sys.exit(1)
    mutated = content.replace(target, "")
    # Clean up possible double spaces or stray whitespace
    mutated = "\n".join(line.rstrip() for line in mutated.splitlines() if line.strip() != "")
    with open(example_path, "w", encoding="utf-8") as f:
        f.write(mutated)
    return mutated

def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    ex_dir = os.path.join(repo_root, "exercises", "practice", "flatten-array")
    cfg = load_config(os.path.join(ex_dir, ".meta", "config.json"))
    sol_file = cfg["files"]["solution"][0]
    test_file = cfg["files"]["test"][0]
    example_file = cfg["files"]["example"][0]

    sol_path = os.path.join(ex_dir, sol_file)
    test_path = os.path.join(ex_dir, test_file)
    example_path = os.path.join(ex_dir, example_file)

    # ---------- Original reference run ----------
    with tempfile.TemporaryDirectory() as tmp_orig:
        copy_exercise(ex_dir, tmp_orig)
        # Overwrite learner solution with the maintained reference implementation
        shutil.copy2(example_path, os.path.join(tmp_orig, sol_file))
        res = run_sqlite(os.path.join(tmp_orig, test_file), cwd=tmp_orig)
        if res.returncode != 0:
            print("Original run failed: sqlite exit code", res.returncode)
            sys.exit(1)
        out_orig = parse_output_json(tmp_orig)
        ok, count = all_pass(out_orig)
        if not ok:
            print("Original run: not all tests passed. Count", count)
            sys.exit(1)
        print("Original reference: all", count, "tests passed")

    # ---------- Mutated reference run ----------
    with tempfile.TemporaryDirectory() as tmp_mut:
        copy_exercise(ex_dir, tmp_mut)
        # Mutate the maintained reference implementation inside the temporary copy
        mutated_example_path = os.path.join(tmp_mut, example_file)
        mutated_sql = mutate_reference(mutated_example_path)
        # Overwrite the learner solution with the mutated reference
        shutil.copy2(mutated_example_path, os.path.join(tmp_mut, sol_file))
        res = run_sqlite(os.path.join(tmp_mut, test_file), cwd=tmp_mut)
        if res.returncode != 0:
            print("Mutated run failed: sqlite exit code", res.returncode)
            sys.exit(1)
        out_mut = parse_output_json(tmp_mut)
        ok_mut, count_mut = all_pass(out_mut)
        if ok_mut:
            print("Mutated run unexpectedly passed all", count_mut, "tests")
            sys.exit(1)
        # Identify first failing test (should be the null‑omission case)
        failing_uuid = None
        failing_desc = None
        for entry in out_mut:
            if entry.get("status") != "pass":
                failing_uuid = entry.get("uuid")
                failing_desc = entry.get("description")
                break
        expected_uuid = "0705a8e5-dc86-4cec-8909-150c5e54fa9c"
        if failing_uuid != expected_uuid:
            print(f"Unexpected failing test UUID: {failing_uuid} (expected {expected_uuid})")
            sys.exit(1)
        print("Mutated reference: failure detected as expected")
        print("Failing test UUID:", failing_uuid)
        print("Description:", failing_desc)
        print("Executed", count_mut, "tests")
        # Save evidence
        ev_dir = os.path.abspath(os.path.join(repo_root, "work", "R08-T033"))
        os.makedirs(ev_dir, exist_ok=True)
        with open(os.path.join(ev_dir, "original_output.json"), "w", encoding="utf-8") as f:
            json.dump(out_orig, f, indent=2)
        with open(os.path.join(ev_dir, "mutated_output.json"), "w", encoding="utf-8") as f:
            json.dump(out_mut, f, indent=2)
        with open(os.path.join(ev_dir, "mutated_example.sql"), "w", encoding="utf-8") as f:
            f.write(mutated_sql)
        with open(os.path.join(ev_dir, "versions.txt"), "w", encoding="utf-8") as f:
            f.write(f"Python: {sys.version}\n")
            sqlite_ver = subprocess.run(["sqlite3", "--version"], capture_output=True, text=True).stdout.strip()
            f.write(f"SQLite: {sqlite_ver}\n")

if __name__ == "__main__":
    main()
