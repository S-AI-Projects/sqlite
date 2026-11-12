# Resistor-Color-Duo Maintenance & File-Role Metadata Mapping

## Overview

- **Exercise**: `exercises/practice/resistor-color-duo`
- **Task ID**: `R08-T048`
- **Objective**: Establish a clear, verifiable file-role map for `exercises/practice/resistor-color-duo/.meta/config.json`, explain how the Exercism test runner locates and verifies exercise files, and implement an automated configuration validation tool that tests both valid paths and invalid metadata fixtures.

---

## 1. Exercise-Specific File-Role Map

The following table categorizes all files associated with `resistor-color-duo`, indicating whether each is a maintained source asset or a generated artifact:

| File Path | Config Role | Artifact Category | Purpose & Description |
|---|---|---|---|
| `resistor-color-duo.sql` | `files.solution` | Maintained Source | Learner starter stub containing table schema and empty student placeholder query. |
| `resistor-color-duo_test.sql` | `files.test` | Maintained Source | Test suite runner inserting canonical cases and evaluating student query results. |
| `.meta/example.sql` | `files.example` | Maintained Source | Reference implementation passing all canonical test cases; used by automated test verification. |
| `data.csv` | `files.editor` | Generated Artifact | Input dataset loaded into the SQLite `color_code` table during fixture setup. |
| `create_fixture.sql` | *N/A (harness)* | Maintained Source | Drops and recreates the `color_code` table and imports `data.csv`. |
| `test_setup.sql` | *N/A (harness)* | Maintained Source | Prepares `tests` tracking table, sets output formatting, and reads student solution. |
| `test_reporter.sql` | *N/A (harness)* | Maintained Source | Formats failed assertions and writes JSON output to `./output.json` for Exercism runner. |
| `.meta/config.json` | *N/A (metadata)* | Maintained Source | Declares exercise authors, contributors, blurb, and file mappings. |
| `.meta/tests.toml` | *N/A (metadata)* | Maintained Source | Tracks canonical test UUIDs, descriptions, inclusions, and exclusion comments. |
| `.meta/template.data.j2` | *N/A (generator)* | Maintained Source | Jinja2 template used by `bin/generate_tests` to generate `data.csv`. |
| `.docs/instructions.md` | *N/A (docs)* | Upstream Synced | Problem description and rules provided to the learner. |

---

## 2. Test Runner Execution & File Discovery

The Exercism SQLite track uses two shell scripts to run exercise verification: `bin/verify-exercises` and `bin/verify-exercise-example`.

### Discovery Mechanism
1. **Locating Example Solution**:
   `bin/verify-exercises` parses `.meta/config.json` using `jq`:
   ```bash
   example=$(jq -r '.files | (.example? + .exemplar?)[0]' "${dir}/.meta/config.json")
   ```
   For `resistor-color-duo`, this resolves directly to `.meta/example.sql`.
2. **Staging Solution**:
   The script creates a backup of `resistor-color-duo.sql` (`resistor-color-duo_backup.sql`) and copies `.meta/example.sql` into `resistor-color-duo.sql`.
3. **Executing Test Runner**:
   `bin/verify-exercise-example` receives the slug (`resistor-color-duo`) and directory path, changes into the exercise directory, and invokes SQLite non-interactively:
   ```bash
   sqlite3 '' --init "resistor-color-duo_test.sql" -bail '.exit'
   ```
4. **Internal Test Harness Loading**:
   - `resistor-color-duo_test.sql` invokes `.read ./test_setup.sql`, which in turn executes `.read ./create_fixture.sql` and `.read ./resistor-color-duo.sql`.
   - Test cases are inserted into `tests`.
   - Student results in `color_code` are compared with `tests.expected`, setting `status = 'pass'` for matches.
   - `.read ./test_reporter.sql` formats messages and exports summary data to `./output.json`.
5. **Teardown**:
   `bin/verify-exercises` restores `resistor-color-duo_backup.sql` back to `resistor-color-duo.sql`, ensuring learner stubs remain unsolved in the repository.

---

## 3. Metadata Validation Rules & Deliberate Invalid Fixtures

The path checker `tools/course_checks/r08-t048.py` enforces three strict validation rules:
1. **Object Structure**: `config.json` must contain a valid `files` dictionary mapping roles to non-empty lists of relative file paths.
2. **Directory Isolation (No Traversal)**: Every path must resolve strictly inside the exercise directory (`exercises/practice/resistor-color-duo/`). Parent directory traversal (such as `../`) is rejected.
3. **File Existence**: Every declared file must exist on disk.

### Deliberate Invalid Fixtures Evaluated:
- **`missing-reference`**: `files.example` set to `[".meta/missing_example.sql"]`.
  - *Result*: Correctly rejected with `FileNotFoundError`.
- **`missing-test`**: `files.test` set to `["missing_test.sql"]`.
  - *Result*: Correctly rejected with `FileNotFoundError`.
- **`outside-exercise`**: `files.example` set to `["../outside.sql"]`.
  - *Result*: Correctly rejected with `ValueError` for directory traversal violation.
- **Real Metadata**: Evaluated without modification and confirmed 100% valid.

---

## 4. Canonical Case Mapping Table

| # | UUID | Description | Color 1 | Color 2 | Expected Value | Status |
|---|---|---|---|---|---|---|
| 1 | `ce11995a-5b93-4950-a5e9-93423693b2fc` | Brown and black | `brown` | `black` | 10 | PASS |
| 2 | `7bf82f7a-af23-48ba-a97d-38d59406a920` | Blue and grey | `blue` | `grey` | 68 | PASS |
| 3 | `f1886361-fdfd-4693-acf8-46726fe24e0c` | Yellow and violet | `yellow` | `violet` | 47 | PASS |
| 4 | `b7a6cbd2-ae3c-470a-93eb-56670b305640` | White and red | `white` | `red` | 92 | PASS |
| 5 | `77a8293d-2a83-4016-b1af-991acc12b9fe` | Orange and orange | `orange` | `orange` | 33 | PASS |
| 6 | `4a8ceec5-0ab4-4904-88a4-daf953a5e818` | Black and brown, one-digit | `black` | `brown` | 1 | PASS |
| - | `0c4fb44f-db7c-4d03-afa8-054350f156a8` | Ignore additional colors | *N/A* | *N/A* | *N/A* | Excluded (`include = false`: "not passing in an array of colors") |

---

## 5. Reproducible Validation Commands

```bash
# 1. Run task verification harness
python3 work/R08-T048/check.py

# 2. Run reusable metadata path checker
python3 tools/course_checks/r08-t048.py

# 3. Run Exercism track test runner
./bin/verify-exercises exercises/practice/resistor-color-duo

# 4. Run configlet linter
./bin/configlet lint
```

