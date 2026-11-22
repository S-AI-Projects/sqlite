# Atbash Cipher Maintenance & Test Runner Documentation

This document describes the automated course check runner, execution options, system prerequisites, and isolation guarantees for the `atbash-cipher` exercise in the SQLite track of Exercism.

---

## 1. Test Runner Command

The standardized test runner script is located at `tools/course_checks/r08-t019.py` and can be executed via Python 3:

```bash
python3 tools/course_checks/r08-t019.py [OPTIONS]
```

### CLI Options

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--json` | Flag | `False` | Emits comprehensive, machine-readable JSON results to `stdout` for CI/CD auditing. |
| `--solution <path>` | String | `.meta/example.sql` | Specifies an alternative solution file to test (useful for mutant testing or learner evaluation). |
| `--timeout <seconds>` | Float | `15.0` | Execution timeout in seconds for the `sqlite3` subprocess. |
| `--exercise-dir <path>` | String | Auto-detected | Explicit path to the `atbash-cipher` exercise folder. |

### Usage Examples

- **Default Execution (Verify Reference Implementation)**:
  ```bash
  python3 tools/course_checks/r08-t019.py
  ```

- **Machine-Readable JSON Output**:
  ```bash
  python3 tools/course_checks/r08-t019.py --json
  ```

- **Evaluate Custom or Experimental Solution**:
  ```bash
  python3 tools/course_checks/r08-t019.py --solution /path/to/solution.sql
  ```

---

## 2. Prerequisites

1. **Python Runtime**:
   - Python 3.10+ (utilizes standard library modules: `argparse`, `hashlib`, `json`, `os`, `pathlib`, `shutil`, `subprocess`, `sys`, `tempfile`).
   - No external third-party dependencies required.

2. **SQLite3 Command-Line Interface**:
   - `sqlite3` CLI must be present in the system `PATH`.
   - Requires SQLite version 3.35.0 or later (supporting Recursive CTEs, `IIF()`, `CHAR()`, `UNICODE()`, and `GROUP_CONCAT()`).

3. **Repository Directory Layout**:
   - Exercise files must reside at `exercises/practice/atbash-cipher/`.
   - Required assets:
     - `create_fixture.sql`
     - `create_test_table.sql`
     - `atbash-cipher_test.sql`
     - `data.csv`
     - `.meta/config.json`
     - `.meta/example.sql`

---

## 3. Isolation Guarantees

The test runner enforces strict isolation and immutability guarantees to prevent accidental state contamination or student file degradation:

1. **Workspace Immutability**:
   - The learner starter stub (`exercises/practice/atbash-cipher/atbash-cipher.sql`) is never modified or overwritten during execution.
   - A cryptographic SHA-256 hash is computed immediately prior to execution and verified against a post-execution hash. If any alteration occurs, the runner aborts with a failure exit code.

2. **Ephemeral Sandbox Environment**:
   - All database creation, table migrations, test insertions, and file writes (`output.json`, `user_output.md`) occur inside a temporary directory managed by `tempfile.TemporaryDirectory()`.
   - The operating system cleans up and deletes all temporary files and directories upon script completion, ensuring zero leftover state on disk.

3. **Subprocess Boundary & Timeout Safety**:
   - The test harness is executed in an isolated child process (`sqlite3 -bail`).
   - Execution is bounded by a configurable timeout (`--timeout`), preventing potential infinite recursion loops (e.g. malformed recursive Common Table Expressions) from hanging the audit pipeline.
