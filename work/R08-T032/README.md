# Grains Exercise Test Generation Review and Verification (Task R08-T032)

This directory contains the verification script, canonical case review, reproducibility evidence, and test execution results for the Grains exercise (`exercises/practice/grains`).

## Contents

- `check.py`: Automated verification script using Python's `subprocess` module and temporary directories.
- `evidence.json`: Complete machine-readable evidence recording environment info, generator info, canonical cases review, reproducibility comparison, input values, and expected vs actual results.
- `verification_output.txt`: Human-readable console log and table output from test execution.
- `canonical_cases_review.md`: Detailed review of the three canonical case requirements, generated vs manually maintained files, and reproducibility analysis.
- `sql_comparison.diff`: Comparison diff between two independent test generation environments.

## How to Reproduce the Verification

Run the verification script from the repository root:

```bash
python3 work/R08-T032/check.py
```

The script will:
1. Parse and validate `exercises/practice/grains/.meta/tests.toml`.
2. Perform two independent test generation / preparation runs in isolated temporary directories.
3. Compare `grains_test.sql` from both runs (normalizing timestamps if applicable) and assert zero differences and zero silently dropped cases.
4. Execute the equivalent of `sqlite3 -bail < grains_test.sql` against the reference implementation (`.meta/example.sql`) in a temporary directory.
5. Parse `output.json` and assert 100% of executed tests pass.
6. Verify that the learner stub (`exercises/practice/grains/grains.sql`) remains completely unmodified in the working tree.
7. Save full evidence to `work/R08-T032/evidence.json` and `work/R08-T032/verification_output.txt`.

## Summary of Findings

- **Canonical Cases Total**: 11
- **Included Cases**: 8 (all pass against reference implementation)
- **Excluded Cases**: 3 (`include = false`, error testing omitted on purpose)
- **Generation Reproducibility**: 100% identical between independent runs; 0 silently dropped cases.
- **Learner Stub**: Preserved, unsolved, and untouched.
