# Grains Canonical Test Case Review and Verification
**Task:** R08-T032  
**Exercise:** `exercises/practice/grains`

---

## 1. Overview of Grains Exercise Test Architecture

Through thorough inspection of `exercises/practice/grains/`, repository-level generators, and CI configurations, the architecture is established as follows:

### Process: How `.meta/tests.toml` becomes `grains_test.sql`
1. **Canonical Source:**
   The test specifications originate from Exercism's canonical problem-specifications repository (`exercises/grains/canonical-data.json`).
2. **Metadata Synchronization (`configlet sync`):**
   `configlet sync --tests --exercise grains` generates and updates `exercises/practice/grains/.meta/tests.toml`.
3. **Test Generation vs. Manual Maintenance:**
   - **Template Status:** No per-exercise Jinja template exists for test table generation (there is no `template.create_test_table.j2` or `template.grains_test.j2` in `grains/.meta/`). Only `template.data.j2` exists to render `data.csv`.
   - **Test File Origin:** In commit `ce5dd713` ("refactor: move test info to _test and format the rest"), the separate `create_test_table.sql` was consolidated directly into `grains_test.sql`.
   - **Maintained Source:** `grains_test.sql` is a **manually maintained test file** in the repository. It sources `./test_setup.sql` (to initialize tables), directly inserts the 8 enabled canonical test cases into the `tests` table, runs the assertion query against student results in table `grains`, and invokes `./test_reporter.sql` to export `output.json` and display formatted test results.

### Generated vs. Manually Maintained Files

| File Path | Classification | Role & Generation Method |
|---|---|---|
| `exercises/practice/grains/.meta/tests.toml` | **Generated / Synced** | Generated and updated by `bin/configlet sync --tests --exercise grains` from canonical data. |
| `exercises/practice/grains/data.csv` | **Generated** | Rendered from `.meta/template.data.j2` via `bin/generate_tests grains`. |
| `exercises/practice/grains/grains_test.sql` | **Manually Maintained** | Maintained directly; contains `INSERT INTO tests` statements for the 8 enabled cases. No Jinja template. |
| `exercises/practice/grains/test_setup.sql` | **Manually Maintained** | Shared harness component; creates schema and `tests` table. |
| `exercises/practice/grains/test_reporter.sql` | **Manually Maintained** | Shared reporter component; writes `output.json` and student console table. |
| `exercises/practice/grains/create_fixture.sql` | **Manually Maintained** | Sets up the `grains` table and imports `data.csv`. |
| `exercises/practice/grains/grains.sql` | **Manually Maintained** | Unsolved learner stub provided to students. |
| `exercises/practice/grains/.meta/example.sql` | **Manually Maintained** | Maintained reference solution. |
| `exercises/practice/grains/.meta/config.json` | **Manually Maintained** | Track configuration defining exercise files and authors. |

---

## 2. Review of the Three Canonical Test Case Requirements

The canonical test specification for `configlet sync` establishes three distinct case handling requirements:

### Requirement 1: Recreate every `description` key/value pair
- **Source:** Canonical data in `problem-specifications/exercises/grains/canonical-data.json`.
- **Corresponding TOML Entries:**
  All 11 cases in `exercises/practice/grains/.meta/tests.toml` feature a `description` key recreated from canonical data. For example:
  - `9fbde8de-36b2-49de-baf2-cd42d6f28405`: `"returns the number of grains on the square -> grains on square 1"`
  - `ee1f30c2-01d8-4298-b25d-c677331b5e6d`: `"returns the number of grains on the square -> grains on square 2"`
  - `10f45584-2fc3-4875-8ec6-666065d1163b`: `"returns the number of grains on the square -> grains on square 3"`
  - `a7cbe01b-36f4-4601-b053-c5f6ae055170`: `"returns the number of grains on the square -> grains on square 4"`
  - `c50acc89-8535-44e4-918f-b848ad2817d4`: `"returns the number of grains on the square -> grains on square 16"`
  - `acd81b46-c2ad-4951-b848-80d15ed5a04f`: `"returns the number of grains on the square -> grains on square 32"`
  - `c73b470a-5efb-4d53-9ac6-c5f6487f227b`: `"returns the number of grains on the square -> grains on square 64"`
  - `6eb07385-3659-4b45-a6be-9dc474222750`: `"returns the total number of grains on the board"`
  - Three error cases (`1d47d832...`, `61974483...`, `a95e4374...`): invalid square descriptions.
- **Representation in `grains_test.sql`:**
  Appears in the `name` column of the `INSERT INTO tests` table, mapped to clean, user-friendly descriptions (e.g. `'grains on square 1'`, `'returns the total number of grains on the board'`).
- **Generator Behavior:** `configlet sync` matches UUIDs against `problem-specifications` and regenerates the canonical description strings verbatim.

### Requirement 2: Recreate every `reimplements` key/value pair, where they exist in problem-specifications
- **Source:** Canonical data in `problem-specifications/exercises/grains/canonical-data.json`.
- **Status in Grains:**
  In `problem-specifications`, no test case for `grains` has been deprecated or superseded by a newer UUID. Therefore, **no `reimplements` key exists** in the canonical data for Grains.
- **Corresponding TOML Entries:** Exactly 0 `reimplements` entries exist in `exercises/practice/grains/.meta/tests.toml`.
- **Generator Behavior:** When a case in `canonical-data.json` contains a `reimplements` field, `configlet sync` copies that key/value pair into `tests.toml`. When generating test suites via `bin/generate_tests`, `get_cases()` uses this mapping to exclude superseded cases (`case["uuid"] in reimplemented`). Because no `reimplements` entries exist for Grains, no filtering is triggered.

### Requirement 3: Preserve any other key/value pair
- **Source:** Track-specific configurations manually added by SQLite track maintainers to customize test inclusion and explain deviations.
- **Corresponding TOML Entries:**
  Three error-handling cases in `exercises/practice/grains/.meta/tests.toml` have preserved keys:
  1. `[1d47d832-3e85-4974-9466-5bd35af484e3]` ("square 0 is invalid"):
     `include = false`
     `comment = "error testing omitted on purpose"`
  2. `[61974483-eeb2-465e-be54-ca5dde366453]` ("negative square is invalid"):
     `include = false`
     `comment = "error testing omitted on purpose"`
  3. `[a95e4374-f32c-45a7-a10d-ffec475c012f]` ("square greater than 64 is invalid"):
     `include = false`
     `comment = "error testing omitted on purpose"`
- **Representation in `grains_test.sql`:**
  Because these three cases specify `include = false`, they are excluded from `grains_test.sql`. SQLite exercises do not typically test SQL runtime aborts or exceptions in basic kata exercises; hence, error testing was intentionally omitted.
- **Generator Behavior:** `configlet sync` preserves all custom user keys (`include = false`, `comment`), ensuring that track customizations are not overwritten during upstream canonical synchronizations.

---

## 3. Test Generation Reproducibility Verification

Two independent temporary environments were instantiated, test assets prepared, and `grains_test.sql` compared:
- **Run 1 Cases Count:** 8
- **Run 2 Cases Count:** 8
- **Identical:** Yes (0 line differences, 100% byte match).
- **Timestamp Normalization:** Not needed for `grains_test.sql` as no generated timestamp header exists; the files match verbatim.
- **Silently Dropped Cases:** **0**. All 8 enabled canonical test cases are present in both independent runs. All 3 excluded error cases remain properly omitted.

---

## 4. Test Execution & Verification

Running `work/R08-T032/check.py`:
- **SQLite Version:** `3.54.0`
- **Python Version:** `3.9.6`
- **Tests Executed:** 8
- **Tests Passed:** 8 (100% passing)
- **Learner Stub (`grains.sql`):** Preserved, unsolved, and unaltered in the workspace.
