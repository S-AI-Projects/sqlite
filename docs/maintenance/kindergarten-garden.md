# Kindergarten-Garden Maintenance & Mutation Analysis

## Overview

- **Exercise**: `exercises/practice/kindergarten-garden`
- **Task ID**: `R08-T043`
- **Objective**: Create a deliberate mutant of the reference implementation to probe the specification contract, identify the minimal test case rejecting the mutant, and document the regression findings along with debugging hints.

---

## 1. Underlying Contract & Traversal Invariant

In `kindergarten-garden`, students are assigned plants in a 2xN grid where the two rows are separated by a newline character (`\n` / `char(10)`).

Each student is responsible for four cups (two on the top row, two on the bottom row). The canonical specification mandates **row-major traversal**:
1. Top row, student's left cup
2. Top row, student's right cup
3. Bottom row, student's left cup
4. Bottom row, student's right cup

---

## 2. Deliberate Mutation: Column-Major Cup Traversal

A frequent misunderstanding in 2D grid processing is traversing column-by-column rather than row-by-row (e.g., top-left, bottom-left, top-right, bottom-right).

### Reference vs. Mutant Implementation

```sql
-- Original Reference (Row-Major):
WITH plants (p) AS (
  VALUES
    (1),
    (2),
    (1 + instr(diagram, char(10))),
    (2 + instr(diagram, char(10)))
)

-- Mutated Implementation (Column-Major):
WITH plants (p) AS (
  VALUES
    (1),
    (1 + instr(diagram, char(10))),
    (2),
    (2 + instr(diagram, char(10)))
)
```

---

## 3. Minimal Rejecting Test Case

The mutation is detected and rejected by the smallest input allowed by the specification:

- **Test Name**: `garden with single student`
- **UUID**: `1fc316ed-17ab-4fba-88ef-3ae78296b692`
- **Input Diagram**:
  ```text
  RC
  GG
  ```
- **Student**: `Alice`
- **Expected Result**: `radishes,clover,grass,grass`
- **Mutant Result**: `radishes,grass,clover,grass`
- **Assertion Failure**:
  ```text
  Result for "RC\nGG" and "Alice" is <radishes,grass,clover,grass> but should be <radishes,clover,grass,grass>
  ```

### Why This Case Is Minimal
This test represents the absolute minimum input domain allowed by the exercise:
1. Exactly one student (`Alice`, index 0).
2. Exactly two columns and two rows (4 cups total, 1 plant per cup).
3. The smallest diagram string length (5 characters including `\n`).

---

## 4. Canonical Case Mapping Table

All 17 canonical test cases from `tests.toml` and `kindergarten-garden_test.sql` were evaluated against both the reference implementation and the mutant:

| # | UUID | Description | Student | Diagram Summary | Reference Status | Mutant Status |
|---|---|---|---|---|---|---|
| 1 | `1fc316ed-17ab-4fba-88ef-3ae78296b692` | garden with single student | Alice | `RC\nGG` | PASS | FAIL (Minimal Rejecting Case) |
| 2 | `acd19dc1-2200-4317-bc2a-08f021276b40` | different garden with single student | Alice | `VC\nRC` | PASS | FAIL |
| 3 | `c376fcc8-349c-446c-94b0-903947315757` | garden with two students | Bob | `VVCG\nVVRC` | PASS | FAIL |
| 4 | `2d620f45-9617-4924-9d27-751c80d17db9` | second student's garden | Bob | `VVCCGG\nVVCCGG` | PASS | PASS (Symmetric plants) |
| 5 | `57712331-4896-4364-89f8-576421d69c44` | third student's garden | Charlie | `VVCCGG\nVVCCGG` | PASS | PASS (Symmetric plants) |
| 6 | `149b4290-58e1-40f2-8ae4-8b87c46e765b` | for Alice, first student's garden | Alice | Full class garden | PASS | FAIL |
| 7 | `ba25dbbc-10bd-4a37-b18e-f89ecd098a5e` | for Bob, second student's garden | Bob | Full class garden | PASS | FAIL |
| 8 | `566b621b-f18e-4c5f-873e-be30544b838c` | for Charlie | Charlie | Full class garden | PASS | FAIL |
| 9 | `3ad3df57-dd98-46fc-9269-1877abf612aa` | for David | David | Full class garden | PASS | FAIL |
| 10 | `0f0a55d1-9710-46ed-a0eb-399ba8c72db2` | for Eve | Eve | Full class garden | PASS | FAIL |
| 11 | `a7e80c90-b140-4ea1-aee3-f4625365c9a4` | for Fred | Fred | Full class garden | PASS | FAIL |
| 12 | `9d94b273-2933-471b-86e8-dba68694c615` | for Ginny | Ginny | Full class garden | PASS | FAIL |
| 13 | `f55bc6c2-ade8-4844-87c4-87196f1b7258` | for Harriet | Harriet | Full class garden | PASS | FAIL |
| 14 | `759070a3-1bb1-4dd4-be2c-7cce1d7679ae` | for Ileana | Ileana | Full class garden | PASS | FAIL |
| 15 | `78578123-2755-4d4a-9c7d-e985b8dda1c6` | for Joseph | Joseph | Full class garden | PASS | FAIL |
| 16 | `6bb66df7-f433-41ab-aec2-3ead6e99f65b` | for Kincaid | Kincaid | Full class garden | PASS | PASS (Symmetric plants) |
| 17 | `d7edec11-6488-418a-94e6-ed509e0fa7eb` | for Larry, last student's garden | Larry | Full class garden | PASS | FAIL |

---

## 5. Verification Commands

```bash
# 1. Run task verification harness
python3 work/R08-T043/check.py

# 2. Run reusable focused check
python3 tools/course_checks/r08-t043.py

# 3. Run Exercism track test runner
./bin/verify-exercises exercises/practice/kindergarten-garden

# 4. Run configlet linter
./bin/configlet lint
```
