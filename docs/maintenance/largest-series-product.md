# Maintenance – Largest Series Product

## Overview
The **Largest Series Product** exercise verifies a learner’s solution by running the SQLite test suite in an isolated temporary copy of the exercise.

## Command
Run the isolated checker:

```bash
python3 work/R08-T040/check.py
```

The command:

1. Reads `exercises/practice/largest-series-product/.meta/config.json` to locate the solution, reference (`example.sql`), test suite, and editor files.
2. Copies the entire exercise (including hidden dot‑files) into a temporary directory.
3. Substitutes the learner’s stub (`largest-series-product.sql`) with the reference implementation.
4. Executes the test suite with `sqlite3 -bail < largest-series-product_test.sql`.
5. Parses `output.json` and asserts **every** enabled case has `"status":"pass"`.
6. Records evidence (`reference_output.json`, `versions.txt`) under `work/R08‑T040/`.
7. Verifies that the learner stub’s SHA‑256 hash is unchanged before and after the run.

If any step fails (non‑zero exit, zero tests, failing case, or hash mismatch) the script exits non‑zero.

## Prerequisites
- **SQLite CLI** with JSON support (`sqlite3 --version` ≥ 3.38).
- **jq** (for JSON processing, version printed in `versions.txt`).
- **Bash** (standard macOS shell).
- **Python 3** (standard library only).

## File‑role mapping (from `.meta/config.json`)

| Role     | File (relative to exercise)                |
|----------|--------------------------------------------|
| solution | `largest-series-product.sql`               |
| test     | `largest-series-product_test.sql`          |
| example  | `.meta/example.sql` (reference implementation) |
| editor   | *(optional – not used for this exercise)* |

## Evidence
Running the checker produces:

- `work/R08-T040/reference_output.json` – full JSON output of the test run.
- `work/R08-T040/versions.txt` – versions of Python, SQLite, and jq.

These files are committed alongside the checker to provide reproducible proof of correctness.
