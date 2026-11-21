# Diamond Exercise Test Review and Verification (Task R08-T031)

This directory contains the verification script, canonical case review, test evidence, and execution outputs for the Diamond exercise (`exercises/practice/diamond`).

## Directory Structure

- `check.py`: Verification script implementing automated testing in an isolated temporary directory using Python's `subprocess` module.
- `evidence.json`: Full machine-readable evidence recording SQLite/Python versions, test pass/fail results, input letters, expected vs actual outputs, before/after inclusion counts, and execution metadata.
- `verification_output.txt`: Human-readable console log and table output from the verification test run.
- `rationales.md`: Documented, independently verifiable rationales for the three required UUIDs (`202fb4cc-6a38-4883-9193-a29d5cb92076`, `bd6a6d78-9302-42e9-8f60-ac1461e9abae`, and `af8efb49-14ed-447f-8944-4cc59ce3fd76`), citing relevant SQLite operations and language/test considerations.

## Summary of Findings

1. **Canonical Cases & Inclusions**:
   - Total canonical cases: 5
   - Included before: 5, Excluded before: 0
   - Included after: 5, Excluded after: 0
   - All 5 cases are valid, supported by SQLite operations, and pass 100% against the reference implementation (`.meta/example.sql`).
   - No include values needed modification.

2. **Test Execution**:
   - Environment: SQLite 3.54.0, Python 3.9.6
   - Executed tests: 5
   - Passed tests: 5 (100% passing)
   - Learner solution (`diamond.sql`) remains completely unchanged and unsolved.

3. **Verification Command**:
   ```bash
   python3 work/R08-T031/check.py
   ```
