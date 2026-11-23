import json, os, shutil, subprocess, sys, tempfile

# Load exercise configuration
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
exercise_dir = os.path.join(repo_root, 'exercises', 'practice', 'house')
config_path = os.path.join(exercise_dir, '.meta', 'config.json')
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

solution_file = config['files']['solution'][0]
example_file = config['files']['example'][0]
test_file = config['files']['test'][0]

# Create a permanent work directory for this task
work_dir = os.path.abspath(os.path.join(repo_root, 'work', 'R08-T037'))
# Ensure clean – we will recreate contents each run
if os.path.isdir(os.path.join(work_dir, 'exercise')):
    shutil.rmtree(os.path.join(work_dir, 'exercise'))

exercise_tmp = os.path.join(work_dir, 'exercise')
shutil.copytree(exercise_dir, exercise_tmp, dirs_exist_ok=True)

# Replace learner solution with reference implementation (example.sql)
shutil.copyfile(os.path.join(exercise_tmp, example_file),
                os.path.join(exercise_tmp, solution_file))

# Run the official test suite
test_sql_path = os.path.join(exercise_tmp, test_file)
proc = subprocess.run(['sqlite3', '-bail', test_sql_path], cwd=exercise_tmp,
                      capture_output=True, text=True)
if proc.returncode != 0:
    print('Test runner failed', file=sys.stderr)
    print(proc.stderr, file=sys.stderr)
    sys.exit(1)

# Verify output.json exists and parse it
output_json_path = os.path.join(exercise_tmp, 'output.json')
if not os.path.isfile(output_json_path):
    print('output.json missing', file=sys.stderr)
    sys.exit(1)
with open(output_json_path, 'r', encoding='utf-8') as f:
    results = json.load(f)

# Ensure there is at least one enabled test and all pass
if not results:
    print('No enabled tests', file=sys.stderr)
    sys.exit(1)
for entry in results:
    if entry.get('status') != 'pass':
        print('Test failed:', entry.get('description'), file=sys.stderr)
        sys.exit(1)

# Save evidence files
shutil.copy(output_json_path, os.path.join(work_dir, 'reference_output.json'))


# Micro‑example execution (write a temporary script with .separator, then run sqlite3)
micro_sql = """
.separator |
WITH cte(idx, sentence) AS (
  VALUES
    (1, 'first'),
    (2, 'second')
)
SELECT
  (SELECT GROUP_CONCAT(sentence, ' ') FROM (SELECT sentence FROM cte ORDER BY idx DESC)) AS ordered,
  (SELECT GROUP_CONCAT(sentence, ' ') FROM cte) AS unordered;
"""
# Write to a temporary file
micro_path = os.path.join(work_dir, 'micro_example.sql')
with open(micro_path, 'w') as f:
    f.write(micro_sql)
# Execute micro‑example using sqlite3 without extra separator flag (handled in script)
proc_micro = subprocess.run(['sqlite3', '-batch', '-noheader', micro_path], capture_output=True, text=True)
if proc_micro.returncode != 0:
    print('Micro example failed', file=sys.stderr)
    sys.exit(1)
micro_output = proc_micro.stdout.strip()
expected_micro = 'second first|first second'
if micro_output != expected_micro:
    print('Micro‑example output mismatch', file=sys.stderr)
    print('Got:', micro_output, file=sys.stderr)
    sys.exit(1)
with open(os.path.join(work_dir, 'micro_output.txt'), 'w') as f:
    f.write(micro_output)

# Versions evidence
ver = subprocess.run(['sqlite3', '--version'], capture_output=True, text=True).stdout.strip()
with open(os.path.join(work_dir, 'versions.txt'), 'w') as f:
    f.write('sqlite3 ' + ver + '\n')

print('All checks passed')
print('Test count:', len(results))
