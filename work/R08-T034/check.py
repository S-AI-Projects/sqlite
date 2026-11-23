import json, os, subprocess, shutil, tempfile, sys

def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def copy_exercise(src, dst):
    shutil.copytree(src, dst, dirs_exist_ok=True)

def run_sqlite(test_sql_path, cwd):
    with open(test_sql_path, "r", encoding="utf-8") as f:
        sql = f.read()
    return subprocess.run(["sqlite3", "-bail"], input=sql, cwd=cwd,
                          capture_output=True, text=True)

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
    for r in results:
        if r.get("status") != "pass":
            return False, len(results)
    return True, len(results)

def get_original_sql(ref_path):
    with open(ref_path, "r", encoding="utf-8") as f:
        txt = f.read()
    # revert the readability rename for baseline
    return txt.replace("vowel_mask", "no_vowel")

def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    ex_dir = os.path.join(repo_root, "exercises", "practice", "pig-latin")
    cfg = load_config(os.path.join(ex_dir, ".meta", "config.json"))
    sol_file = cfg["files"]["solution"][0]
    test_file = cfg["files"]["test"][0]
    example_file = cfg["files"]["example"][0]

    example_path = os.path.join(ex_dir, example_file)
    original_sql = get_original_sql(example_path)

    # ---------- Original reference (baseline) ----------
    with tempfile.TemporaryDirectory() as tmp_orig:
        copy_exercise(ex_dir, tmp_orig)
        # write baseline sql to example file in temporary copy
        tmp_example = os.path.join(tmp_orig, example_file)
        with open(tmp_example, "w", encoding="utf-8") as f:
            f.write(original_sql)
        # overwrite learner solution with this baseline reference
        shutil.copy2(tmp_example, os.path.join(tmp_orig, sol_file))
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

    # ---------- Refactored reference (with comment) ----------
    with tempfile.TemporaryDirectory() as tmp_ref:
        copy_exercise(ex_dir, tmp_ref)
        # example file already contains refactored version
        # copy it over learner solution
        shutil.copy2(os.path.join(tmp_ref, example_file), os.path.join(tmp_ref, sol_file))
        res = run_sqlite(os.path.join(tmp_ref, test_file), cwd=tmp_ref)
        if res.returncode != 0:
            print("Refactored run failed: sqlite exit code", res.returncode)
            sys.exit(1)
        out_ref = parse_output_json(tmp_ref)
        ok, count_ref = all_pass(out_ref)
        if not ok:
            print("Refactored run: not all tests passed. Count", count_ref)
            sys.exit(1)
        print("Refactored reference: all", count_ref, "tests passed")

    if count != count_ref:
        print("Mismatch in test count between runs")
        sys.exit(1)
    if out_orig != out_ref:
        print("Outputs differ between original and refactored implementation")
        sys.exit(1)
    print("Before/after outputs identical;", count, "tests executed")

    # Save evidence
    ev_dir = os.path.abspath(os.path.join(repo_root, "work", "R08-T034"))
    os.makedirs(ev_dir, exist_ok=True)
    with open(os.path.join(ev_dir, "original_output.json"), "w", encoding="utf-8") as f:
        json.dump(out_orig, f, indent=2)
    with open(os.path.join(ev_dir, "refactored_output.json"), "w", encoding="utf-8") as f:
        json.dump(out_ref, f, indent=2)
    with open(os.path.join(ev_dir, "refactored_example.sql"), "w", encoding="utf-8") as f:
        with open(example_path, "r", encoding="utf-8") as src:
            f.write(src.read())
    with open(os.path.join(ev_dir, "versions.txt"), "w", encoding="utf-8") as f:
        f.write(f"Python: {sys.version}\n")
        sqlite_ver = subprocess.run(["sqlite3", "--version"], capture_output=True, text=True).stdout.strip()
        f.write(f"SQLite: {sqlite_ver}\n")

if __name__ == "__main__":
    main()
