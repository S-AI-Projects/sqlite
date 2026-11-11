# Leap Exercise Maintenance and Verification

This document describes the maintenance tooling, execution procedure, and tool requirements for the `leap` practice exercise (`exercises/practice/leap`).

## Overview

The `leap` exercise provides an isolated test runner, `tools/course_checks/r08-t049.py`, designed to verify the maintained reference implementation (`.meta/example.sql`) without modifying or overwriting the unsolved learner starter files (`leap.sql`) in the working tree.

## Prerequisites and Tool Requirements

The isolated test runner requires the following tools:

| Tool | Minimum Version / Requirement | Purpose |
|------|--------------------------------|---------|
| **Python 3** | Python 3.8+ | Test runner script execution and assertion verification |
| **SQLite 3** | SQLite 3.33+ (with JSON support) | Database engine executing `leap_test.sql` |
| **Bash** | GNU Bash 3.2+ | Shell environment for test execution |
| **jq** | jq 1.6+ | JSON processing for Exercism track test runners |
| **Configlet** | Configlet 4.0+ (`./bin/fetch-configlet`) | Exercism track linting and test syncing |

## Usage and Command Line Interface

Run the isolated runner from the repository root:

```bash
python3 tools/course_checks/r08-t049.py
```

### Command-Line Options

- `--solution-file <PATH>`: Test an alternate solution SQL file (e.g. for testing student solutions or regression tests) instead of the default reference (`.meta/example.sql`).
- `--empty-tests`: Simulate a zero-test run to verify error propagation and exit status when no tests are executed.
- `--json`: Output test results and execution metadata in JSON format.
- `--quiet`, `-q`: Suppress human-readable output and only exit with the corresponding status code.

### Examples

**Default execution (reference implementation):**
```bash
python3 tools/course_checks/r08-t049.py
```

**JSON output mode:**
```bash
python3 tools/course_checks/r08-t049.py --json
```

**Test a custom or failing solution:**
```bash
python3 tools/course_checks/r08-t049.py --solution-file /path/to/solution.sql
```

**Verify failure on zero-test selection:**
```bash
python3 tools/course_checks/r08-t049.py --empty-tests
```

## Exit Status Codes

The runner exits with distinct return codes depending on the outcome:

| Exit Code | Meaning | Description |
|-----------|---------|-------------|
| `0` | Success | All test cases executed and passed against the reference. |
| `1` | Assertion Failure | One or more test cases failed against the provided solution. |
| `2` | Zero-Test Run | No test cases were executed (empty test selection). |
| `3` | Process Error | SQLite child process failed or exited with a non-zero status. |
| `4` | Configuration Error | Missing configuration file, missing solution file, or invalid JSON. |

## Isolation Mechanism

1. **Working Tree Protection**: Before and after running tests, the runner computes SHA256 hashes of all learner starter and fixture files (`leap.sql`, `leap_test.sql`, `create_fixture.sql`, `data.csv`, `test_setup.sql`, `test_reporter.sql`). If any hash differs after execution, the runner throws an error.
2. **Temporary Directory**: The exercise files (including `.meta/` and `.docs/`) are copied to an isolated temporary directory created via `tempfile.TemporaryDirectory`.
3. **Reference Substitution**: The reference solution (`.meta/example.sql`) is substituted for `leap.sql` only inside the temporary copy.
4. **Guaranteed Cleanup**: Temporary directories and generated test artifacts (`output.json`, `user_output.md`) are automatically purged upon process termination.
