# Robot-Simulator Exercise Maintenance

This document provides maintenance and verification documentation for the `exercises/practice/robot-simulator` exercise in the SQLite track. Its purpose is to verify that the committed test suite distinguishes deliberately incorrect implementations (mutants) from the reference solution, confirming test suite sensitivity and regression protection without asserting or implying that either the reference solution or the test cases are defective.

## The Contract

Based on a direct reading of `exercises/practice/robot-simulator/.docs/instructions.md` and `exercises/practice/robot-simulator/.docs/instructions.append.md`, the robot simulator operates under the following explicit specification:

- **Robot State**:
  - The robot has a position represented by integer coordinates `{x, y}` on a 2D Cartesian plane.
  - The robot has a heading pointing in one of four cardinal directions: `north`, `east`, `south`, or `west`.
- **Coordinate Axes**:
  - Coordinates increase toward the north along the y-axis (`+y`).
  - Coordinates increase toward the east along the x-axis (`+x`).
- **Movement Semantics**:
  - `R` (Turn Right): Rotates the robot 90 degrees clockwise (`north` -> `east` -> `south` -> `west` -> `north`). The coordinates `{x, y}` remain unchanged.
  - `L` (Turn Left): Rotates the robot 90 degrees counter-clockwise (`north` -> `west` -> `south` -> `east` -> `north`). The coordinates `{x, y}` remain unchanged.
  - `A` (Advance): Moves the robot 1 unit forward in its current heading:
    - Facing `north`: increments `y` by 1.
    - Facing `south`: decrements `y` by 1.
    - Facing `east`: increments `x` by 1.
    - Facing `west`: decrements `x` by 1.
- **Infinite Grid**:
  - Robots navigate an infinite grid; no boundary limits or grid borders are defined.
- **Unspecified Behaviors**:
  - The specification does not define error handling or state transitions for unknown instruction letters (characters other than `R`, `L`, `A`).
  - The specification does not specify special handling for empty instruction strings `""` beyond the natural rule that receiving no movement instructions leaves the robot at its initial `{position, direction}`.

## The Suite in Numbers

The test suite in `exercises/practice/robot-simulator/.meta/tests.toml` and `exercises/practice/robot-simulator/create_test_table.sql` contains exactly 18 test cases with 0 excluded entries:

- `create` (2 cases): Tests robot placement at the origin facing `north` and at negative coordinates facing `south`.
- Rotation (8 cases): Tests all four 90-degree clockwise turns and all four 90-degree counter-clockwise turns.
- Advance (4 cases): Tests single-step forward movement in each of the four cardinal directions (`north`, `east`, `south`, `west`).
- Sequence (4 cases): Tests multi-step instruction streams combining turns and advances across multiple quadrants.

## Documented Mutant M5 (Reverse Processing)

Mutant M5 alters `exercises/practice/robot-simulator/.meta/example.sql` so that instruction characters are extracted from right to left instead of left to right.

### Diff
```diff
--- .meta/example.sql
+++ robot-simulator.sql
@@ -39,8 +39,8 @@
             (JSON_EXTRACT(input, '$.instructions'), NULL)
           UNION ALL
           SELECT
-            SUBSTR(string, 2),
-            SUBSTR(string, 1, 1)
+            SUBSTR(string, 1, LENGTH(string) - 1),
+            SUBSTR(string, -1)
           FROM
             rcte
           WHERE
```

### Test Outcome
- Reference solution: 18/18 passed.
- Mutant M5: 14/18 passed, 4/18 failed.

### Named Assertion
The named assertion from the README example is `e34ac672-4ed4-4be3-a0b8-d9af259cbaa1` (`moving east and north from README`):
- **Input**: `{"position":{"x":7,"y":3},"direction":"north","instructions":"RAALAL"}`
- **Expected**: `{"position":{"x":9,"y":4},"direction":"west"}`
- **Mutant Actual**: `{"position":{"x":6,"y":1},"direction":"west"}`

### Other Rejecting Cases
The other three multi-step test cases also reject Mutant M5:
- `f30e4955-4b47-4aa3-8b39-ae98cfbd515b` (`moving west and north`): input `{"position":{"x":0,"y":0},"direction":"north","instructions":"LAAARALA"}`, expected `{"position":{"x":-4,"y":1},"direction":"west"}`, actual `{"position":{"x":-1,"y":4},"direction":"west"}`.
- `3e466bf6-20ab-4d79-8b51-264165182fca` (`moving west and south`): input `{"position":{"x":2,"y":-7},"direction":"east","instructions":"RRAAAAALA"}`, expected `{"position":{"x":-3,"y":-8},"direction":"south"}`, actual `{"position":{"x":3,"y":-2},"direction":"south"}`.
- `41f0bb96-c617-4e6b-acff-a4b279d44514` (`moving east and north`): input `{"position":{"x":8,"y":4},"direction":"south","instructions":"LAAARRRALLLL"}`, expected `{"position":{"x":11,"y":5},"direction":"north"}`, actual `{"position":{"x":11,"y":3},"direction":"north"}`.

### Reduction to Minimal Diagnostic Inputs
The existing test suite already firmly rejects Mutant M5, so no new test case is proposed for the repository. For diagnostic and explanatory purposes, the minimal input sequence to demonstrate non-commutativity consists of two instructions from the origin `{"position":{"x":0,"y":0},"direction":"north"}`:
- Input `RA`: Original reference produces `{"position":{"x":1,"y":0},"direction":"east"}`; Mutant M5 produces `{"position":{"x":0,"y":1},"direction":"east"}` (executed as `AR`).
- Input `AR`: Original reference produces `{"position":{"x":0,"y":1},"direction":"east"}`; Mutant M5 produces `{"position":{"x":1,"y":0},"direction":"east"}` (executed as `RA`).

## Mutation Matrix

| mutant | change | failing count | failing UUIDs | smallest rejecting existing case |
| --- | --- | --- | --- | --- |
| `M1` | Swap `L` (-90) and `R` (+90) turn angles | 12 | `8cbd0086` (north->east), `8abc87fc` (east->south), `3cfe1b85` (south->west), `5ea9fb99` (west->north), `fa0c40f5` (north->west), `da33d734` (west->south), `bd1ca4b9` (south->east), `2de27b67` (east->north), `e34ac672` (README), `f30e4955` (west & north), `3e466bf6` (west & south), `41f0bb96` (east & north) | `8cbd0086` (`R`, len 1) |
| `M2` | Invert west advance increment from `-1` to `+1` | 3 | `bb69c4a7` (west decrements X), `f30e4955` (west & north), `3e466bf6` (west & south) | `bb69c4a7` (`A`, len 1) |
| `M4` | Replace recursive instruction tail with empty array `[]` | 4 | `e34ac672` (README), `f30e4955` (west & north), `3e466bf6` (west & south), `41f0bb96` (east & north) | `e34ac672` (`RAALAL`, len 6) |
| `M5` | Extract characters from right end of instruction string | 4 | `e34ac672` (README), `f30e4955` (west & north), `3e466bf6` (west & south), `41f0bb96` (east & north) | `e34ac672` (`RAALAL`, len 6) |

## Formatting-Only Changes Are Not Mutations

To prevent superficial or cosmetic modifications from passing as valid mutation benchmarks, `work/R08-T053/check.py` enforces two strict validation rules:
1. **Normalized Source Divergence**: The proposed mutant source code must differ from the reference source after stripping all SQL comment lines (lines starting with `--`) and collapsing all contiguous whitespace.
2. **Behavioral Divergence**: The mutant must cause at least one test case that passed under the reference implementation to fail.

If a proposed mutant violates either condition, the validation suite raises `NotAValidMutation("formatting-only changes are not mutations")`. This safeguard is verified by self-test scenario `(d)`.

## Learner Hint

When implementing the robot simulator:
- Instructions are evaluated strictly in sequential order from left to right. Each command executes on the state left behind by the preceding command.
- Turn commands (`R` and `L`) modify only the robot's heading direction; they never alter the `{x, y}` coordinates.
- The advance command (`A`) modifies exactly one coordinate by 1 unit, along the axis corresponding to the robot's current heading direction at the moment of execution.
- Diagnostic check: Starting from `{"position":{"x":0,"y":0},"direction":"north"}`, executing `RA` must arrive at `{"position":{"x":1,"y":0},"direction":"east"}`, whereas executing `AR` must arrive at `{"position":{"x":0,"y":1},"direction":"east"}`. If your implementation produces the same coordinate result for both sequences, instructions are not being applied in proper sequence.

## Observation on Unspecified Characters

The committed test suite in `exercises/practice/robot-simulator` never supplies instruction characters other than `R`, `L`, and `A`. Furthermore, the problem specification does not define how unhandled characters should be treated. Consequently, a mutant that alters only unhandled character behavior is not rejected by any committed test case.

This observation is reproduced by `python3 work/R08-T053/check.py` (Observation M6). The exact patch alters the CASE fallback in `exercises/practice/robot-simulator/.meta/example.sql`:
- Target string: `ELSE jobject`
- Replacement string: `ELSE NULL`

When executed against the committed test suite, Observation M6 passes all 18 cases (0 failing, 18 passing) and survives. When tested against the unknown instruction letter `X` with input `{"position":{"x":0,"y":0},"direction":"north","instructions":"X"}`:
- Original reference output: `{"position":{"x":0,"y":0},"direction":"north"}`
- Mutant M6 output: `null` (SQL `NULL`)

The measured outputs confirm that implementation behavior diverges on unhandled characters. This survival is not a defect in the reference solution or the test suite, and no test case is proposed because the behaviour is not part of the specification.

## Note on Issue #53

The description for issue #53 contains standard track maintenance boilerplate where specific named test cases would normally be listed. Accordingly, the rejecting case of documented mutant M5 (`e34ac672-4ed4-4be3-a0b8-d9af259cbaa1`, `moving east and north from README`) is treated as the named assertion.

We operate under two explicit assumptions:
1. The issue does not say where "the hint" should live, so it is published in the "Learner Hint" section of this maintenance page and the learner-facing exercise files are left unchanged.
2. The rejecting case of the documented mutant (`e34ac672-4ed4-4be3-a0b8-d9af259cbaa1`, `moving east and north from README`) is used as the named assertion.

## How to Run

To execute the verification suite:
```bash
python3 work/R08-T053/check.py
```

To run the failure self-test suite:
```bash
python3 work/R08-T053/check.py --self-test
```
