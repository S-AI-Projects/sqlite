# Bob Exercise Maintenance

This document records maintenance and verification for the `exercises/practice/bob` exercise in the SQLite track. Its purpose is to document a single targeted readability improvement to the reference solution in `exercises/practice/bob/.meta/example.sql` by clarifying an identifier collision around the SQL keyword `AS`. The change preserves exact behavioral equivalence across the entire committed test suite and additional edge cases, verified by `work/R08-T054/check.py`.

## Bob's Rules and Precedence

Based on `exercises/practice/bob/.docs/instructions.md`, Bob only ever answers one of five things:

- **Silence** (`Fine. Be that way!`): This is how he responds to silence. The convention used for silence is nothing, or various combinations of whitespace characters.
- **Forceful Question** (`Calm down, I know what I'm doing!`): This is what he says if you yell a question at him.
- **Shouting / Yelling** (`Whoa, chill out!`): This is his answer if you yell at him. The convention used for yelling is ALL CAPITAL LETTERS.
- **Question** (`Sure.`): This is his response if you ask him a question, such as "How are you?" The convention used for questions is that it ends with a question mark.
- **Anything else** (`Whatever.`): This is what he answers to anything else.

The reference implementation trims the characters `CHAR(32, 9, 10, 13)` (space, tab, line feed, carriage return) before deciding.

## Test Suite Organisation

The test suite for `exercises/practice/bob` is structured as follows:

- **Total Cases**: 27 test cases defined in `exercises/practice/bob/.meta/tests.toml`.
- **Enabled Cases**: Exactly 26 cases are included in execution.
- **Excluded Case**: `66953780-165b-4e7e-8ce3-4bcb80b6385a` (`multiple line question`, marked `include = false`).
- **Reimplemented Case**: `2c7278ac-f955-4eb4-bf8f-e33eb4116a15` carries `reimplements = "66953780-165b-4e7e-8ce3-4bcb80b6385a"` and the original is `include = false`.
- **Expected Values**: Hardcoded directly inside `exercises/practice/bob/bob_test.sql` in the `INSERT INTO tests (uuid, name, input, expected)` statement.
- **Fixture Data**: Populated in `exercises/practice/bob/create_fixture.sql` by importing `exercises/practice/bob/data.csv` into table `bob(input, reply)`. `data.csv` is the fixture file, `.meta/template.data.j2` exists, and `bin/generate_tests` renders templates under `.meta/`. The generator was NOT re-run for this task.
- **Test Harness**: `exercises/practice/bob/test_setup.sql` initializes table `tests`, `exercises/practice/bob/bob_test.sql` runs the solution and checks `(actual.input, actual.reply) = (tests.input, tests.expected)` to set `status = 'pass'`, and `exercises/practice/bob/test_reporter.sql` formats error diagnostics and writes `output.json`.

## Reading of "AS"

Issue #54 specifies to "Focus on AS". Because the issue does not formally define the term, this maintenance documentation reads "AS" as the SQL keyword (an assumption; the issue does not define it).

In `exercises/practice/bob/.meta/example.sql`, the whole-word token `AS` occurs exactly 6 times:

| line | kind | what it names | where it is used later |
| --- | --- | --- | --- |
| `2` | `cte_definition` | `trimmed_inputs` (CTE table name) | Line `17` (`FROM trimmed_inputs`) |
| `5` | `column_alias` | `trimmed` (whitespace-stripped string) | Lines `12`, `13`, `14`, `15` (`trimmed = ''`, `trimmed LIKE '%?'`, `trimmed GLOB ...`, `UPPER(trimmed)`) |
| `9` | `cte_definition` | `bools` (CTE table of classification flags) | Lines `22`, `23`, `24`, `25`, `26`, `30`, `32` (`bools.is_silence`, `bools.is_yelling`, `bools.is_question`, `FROM bools`, `bools.input`) |
| `12` | `column_alias` | `is_silence` (boolean silence flag) | Line `22` (`WHEN bools.is_silence THEN ...`) |
| `13` | `column_alias` | `is_question` (boolean question flag) | Lines `24`, `26` (`AND bools.is_question`, `WHEN bools.is_question THEN ...`) |
| `15` | `column_alias` | `is_yelling` (boolean shouting flag) | Lines `23`, `25` (`WHEN bools.is_yelling`, `WHEN bools.is_yelling THEN ...`) |

## Local State and Trace of Named Cases

The outcome is determined by four intermediate column values computed in the CTEs:

- `trimmed`: The string resulting from `TRIM(input, CHAR(32, 9, 10, 13))`.
- `is_silence`: `trimmed = ''` (1 if input is empty or whitespace-only, 0 otherwise).
- `is_question`: `trimmed LIKE '%?'` (1 if input ends with `?`, 0 otherwise).
- `is_yelling`: `trimmed GLOB '*[a-zA-Z]*' AND trimmed = UPPER(trimmed)` (1 if input contains letters and all letters are uppercase, 0 otherwise).

These flags evaluate through the prioritized `CASE` statement:
`is_silence` -> `is_yelling AND is_question` -> `is_yelling` -> `is_question` -> `ELSE 'Whatever.'`.

The three named cases produce the following trace:

Control characters in inputs are shown as escape sequences (`\t`, `\n`).

| UUID | name | input | trimmed | is_silence | is_question | is_yelling | reply | branch |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `a5193c61` | forceful question | `WHAT'S GOING ON?` | `WHAT'S GOING ON?` | 0 | 1 | 1 | `Calm down, I know what I'm doing!` | `WHEN bools.is_yelling AND bools.is_question THEN 'Calm down, I know what I''m doing!'` |
| `4428f28d` | alternate silence | `\t\t\t\t\t\t\t\t\t\t` | `""` | 1 | 0 | 0 | `Fine. Be that way!` | `WHEN bools.is_silence THEN 'Fine. Be that way!'` |
| `2c7278ac` | multiple line question | `\nDoes this cryogenic chamber make\n me look fat?` | `Does this cryogenic chamber make\n me look fat?` | 0 | 1 | 0 | `Sure.` | `WHEN bools.is_question THEN 'Sure.'` |

## The Change

The single readability change renames the first CTE from `trimmed` to `trimmed_inputs`:

```diff
--- .meta/example.sql
+++ .meta/example.sql
@@ -1,5 +1,5 @@
 WITH
-  trimmed AS (
+  trimmed_inputs AS (
     SELECT
       input,
       TRIM(input, CHAR(32, 9, 10, 13)) AS trimmed
@@ -14,7 +14,7 @@
       trimmed GLOB '*[a-zA-Z]*'
       AND trimmed = UPPER(trimmed) AS is_yelling
     FROM
-      trimmed
+      trimmed_inputs
   )
 UPDATE bob
 SET
```

### Why It Helps

Previously, the same identifier `trimmed` appeared on both sides of `AS` in close proximity: line 2 defined the CTE table as `trimmed AS (`, while line 5 defined the projected column as `... AS trimmed`. In the downstream CTE, `FROM trimmed` referenced the table while `trimmed = ''` referenced the column. Renaming the CTE to `trimmed_inputs` gives the relation a distinct plural name indicating a set of rows (`trimmed_inputs`), while `trimmed` remains unambiguously as the column name.

### What Did Not Change

The column alias `AS trimmed`, all four downstream column references (`trimmed = ''`, `trimmed LIKE '%?'`, `trimmed GLOB ...`, `UPPER(trimmed)`), the second CTE `bools`, the `UPDATE` query, and the `CASE` logic were left completely unchanged. Specifically:
- **Return values**: Agrees on 26/26 enabled cases and 10/10 extra inputs.
- **Ordering**: the statement has no `ORDER BY`, and the rename does not touch how rows are selected or joined. The 26 enabled cases are compared per UUID and the extra inputs by row position.
- **Error behaviour**: No function, operator, or statement was added or removed. AFTER replacing `trimmed_inputs` with `trimmed` equals BEFORE byte for byte.

## Behaviour Preserved

- **Enabled Suite**: Before and after implementations produce identical results on 26/26 enabled test cases.
- **Extra Inputs**: Before and after implementations produce identical results on 10/10 custom edge-case inputs (empty string, spaces only, uppercase question, yelled question, trailing spaces, tabs and newlines, lowercase question, digits and punctuation, CRLF newline, and numbers with exclamation).
- **Rename-Only Proof**: Reversing `trimmed_inputs` -> `trimmed` in the after source recovers the before source verbatim. The identifier `trimmed_inputs` occurs exactly 2 times in the after source and 0 times in the before source. Both before and after sources contain exactly 6 whole-word occurrences of `AS` on lines 2, 5, 9, 12, 13, and 15.
- **Repository Guard**: Exactly one file under `exercises/` and `bin/` was modified relative to commit `4f26956df8ac8c261803011db8bc6a066e2b295c`: `exercises/practice/bob/.meta/example.sql`.

## Alternatives Considered and Not Applied

Two alternative refactorings were considered, evaluated, and verified by `python3 work/R08-T054/check.py`, but not applied:

1. **A1: Extract the `CASE` into an `answers` CTE**:
   - **Diff stats**: +16 lines added, -10 lines removed.
   - **Verification**: Passes 26/26 enabled cases and agrees on 10/10 extra inputs.
   - **Reason not applied**: The issue asks for one readability improvement; this alternative adds more change than the rename (+16/-10 lines vs +2/-2 lines for the rename).

2. **A2: Drop redundant `bools.` qualifiers in the `CASE`**:
   - **Diff stats**: +5 lines added, -5 lines removed.
   - **Verification**: Passes 26/26 enabled cases and agrees on 10/10 extra inputs.
   - **Reason not applied**: Removes qualifiers whose safety depends on `bob` never having a column named like a flag; not needed to clarify `AS`.

Both alternatives are reproduced and verified against the BEFORE source by `python3 work/R08-T054/check.py`.

## Note on Issue #54

The description for issue #54 contains standard track maintenance boilerplate where specific named test cases would normally be listed. Accordingly, three representative cases covering each of the three active boolean flags (`is_yelling AND is_question`, `is_silence`, and `is_question`) were traced: `a5193c61-4a92-4f68-93e2-f554eb385ec6`, `4428f28d-4100-4d85-a902-e5a78cb0ecd3`, and `2c7278ac-f955-4eb4-bf8f-e33eb4116a15`. The term "AS" is read as the SQL keyword.

## How to Run

To run the verification suite:
```bash
python3 work/R08-T054/check.py
```

To run the failure self-test suite:
```bash
python3 work/R08-T054/check.py --self-test
```
