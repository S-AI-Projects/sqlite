# Diamond Exercise: Canonical Test Case Rationales
**Assignment Task:** R08-T031  
**Exercise:** `exercises/practice/diamond`

---

## Executive Summary
This document reviews the 5 canonical test cases in `exercises/practice/diamond/.meta/tests.toml`, with an in-depth investigation into three specific test case UUIDs:
1. `202fb4cc-6a38-4883-9193-a29d5cb92076`
2. `bd6a6d78-9302-42e9-8f60-ac1461e9abae`
3. `af8efb49-14ed-447f-8944-4cc59ce3fd76`

Current canonical test counts:
- Total canonical cases: **5**
- Included cases before: **5**
- Excluded cases before: **0**
- Included cases after: **5**
- Excluded cases after: **0**

All existing include values remain unchanged because all canonical cases are fully supported by SQLite, correctly handled by the maintained reference implementation (`.meta/example.sql`), and 100% passing.

---

## Detailed Case Investigations

### 1. UUID: `202fb4cc-6a38-4883-9193-a29d5cb92076`

- **Test Name (Description):**
  - `tests.toml`: `"Degenerate case with a single 'A' row"`
  - `create_test_table.sql`: `"Degenerate case with a single \"A\" row"`
- **Input:**
  - `letter = 'A'`
- **Expected Behavior:**
  - `result = 'A'` (a 1x1 grid containing just the single character `'A'` with no padding spaces and no trailing newlines).
- **Trace to Reference Implementation (`.meta/example.sql`):**
  - **`lengths` CTE:**
    `GENERATE_SERIES(UNICODE('A'), UNICODE('A'))` generates exactly one row with `value = 65`.
    `ROW_NUMBER() OVER () - 1` computes 0. `len = 0 * 2 = 0`, and `chr = CHAR(65) = 'A'`.
  - **`lines` CTE:**
    `IIF(chr = 'A', chr, PRINTF('%-*c%c', len, chr, chr))` evaluates the `IIF` predicate `chr = 'A'`. Since `chr = 'A'`, the branch directly evaluates to `'A'`.
  - **`padding` CTE:**
    The subquery `SELECT MAX(LENGTH(line)) FROM lines` yields `1`.
    The padding calculation `((1) - 1) / 2` yields `0`.
    `PRINTF('%*s%s%-*s', 0, '', 'A', 0, '')` evaluates to `'A'`.
    `ROW_NUMBER() OVER ()` assigns `rn = 1`.
  - **`top` CTE:**
    Returns 1 row: `'A'` with `rn = 1`.
  - **`bottom` CTE:**
    Filtered by `WHERE rn < (SELECT MAX(rn) FROM padding)`. With `MAX(rn) = 1`, `1 < 1` evaluates to `FALSE`, producing 0 rows.
  - **`top UNION ALL bottom` & Aggregation:**
    Union contains only `'A'`. `GROUP_CONCAT(line, CHAR(10))` emits `'A'`.
- **Comparison with SQLite Capabilities:**
  - Relevant SQLite operations:
    - `GENERATE_SERIES(start, stop)` table-valued extension function: handles `start == stop` cleanly by returning a single-row sequence.
    - `IIF(expr, then, else)`: correctly shortcuts evaluation for `'A'`.
    - `PRINTF('%*s...', 0, ...)`: correctly emits zero spaces for 0-width padding.
    - `GROUP_CONCAT(col, separator)`: returns the single value without adding spurious delimiters.
  - There are no language or engine limitations in SQLite preventing execution of this degenerate single-character case.
- **Decision:**
  - **INCLUDED** (`include = true` / implicit inclusion).
- **Verifiable Rationale:**
  - The degenerate case with letter `'A'` tests the fundamental base case of diamond construction (a single 1x1 character). SQLite fully supports single-row generation and aggregation via `GENERATE_SERIES`, `IIF`, and `GROUP_CONCAT`. The test executes and passes without error against the reference implementation.

---

### 2. UUID: `bd6a6d78-9302-42e9-8f60-ac1461e9abae`

- **Test Name (Description):**
  - `tests.toml`: `"Degenerate case with no row containing 3 distinct groups of spaces"`
  - `create_test_table.sql`: `"Degenerate case with no row containing 3 distinct groups of spaces"`
- **Input:**
  - `letter = 'B'`
- **Expected Behavior:**
  - `result = ' A \nB B\n A '` (newlines represented as `CHAR(10)`).
  - Row 1: `" A "` (1 leading space, `'A'`, 1 trailing space; width = 3).
  - Row 2: `"B B"` (0 leading spaces, `'B'`, 1 middle space, `'B'`, 0 trailing spaces; width = 3).
  - Row 3: `" A "` (1 leading space, `'A'`, 1 trailing space; width = 3).
- **Trace to Reference Implementation (`.meta/example.sql`):**
  - **`lengths` CTE:**
    `GENERATE_SERIES(UNICODE('A'), UNICODE('B'))` outputs two rows:
    - `rn = 1`: `len = 0`, `chr = 'A'`
    - `rn = 2`: `len = 2`, `chr = 'B'`
  - **`lines` CTE:**
    - For `'A'`: `IIF` returns `'A'`.
    - For `'B'`: `PRINTF('%-*c%c', 2, 'B', 'B')`. The specifier `%-*c` formats character `'B'` left-justified within width 2, giving `'B '`. The trailing `%c` appends `'B'`, yielding `'B B'` (length 3).
  - **`padding` CTE:**
    - `MAX(LENGTH(line))` across lines is 3 (from `'B B'`).
    - For `'A'`: `pad = (3 - 1) / 2 = 1`. `PRINTF('%*s%s%-*s', 1, '', 'A', 1, '')` produces `" A "`.
    - For `'B B'`: `pad = (3 - 3) / 2 = 0`. `PRINTF('%*s%s%-*s', 0, '', 'B B', 0, '')` produces `"B B"`.
  - **`top` and `bottom` CTEs:**
    - `top` yields `" A "` (`rn = 1`) followed by `"B B"` (`rn = 2`).
    - `bottom` (`rn < 2`) yields `" A "` (`rn = 1`).
  - **Aggregation:**
    `UNION ALL` and `GROUP_CONCAT(line, CHAR(10))` produce `" A \nB B\n A "`.
- **Comparison with SQLite Capabilities:**
  - Relevant SQLite operations:
    - `PRINTF('%-*c%c', len, chr, chr)`: SQLite supports dynamic field width `*` passed as a parameter and character conversions `%c`.
    - `PRINTF('%*s%s%-*s', pad, '', line, pad, '')`: Dynamically generates balanced leading and trailing whitespace.
    - `UNION ALL` preserves order and duplicates across vertical reflection.
    - `CHAR(10)` creates exact LF newline characters matching canonical line separators.
  - In certain other language tracks, letter `'B'` is sometimes flagged because middle rows have 0 leading spaces (no row contains 3 distinct groups of spaces: leading, interior, trailing). In SQLite, however, width arithmetic `(3 - 3) / 2 = 0` requires no branching and works seamlessly.
- **Decision:**
  - **INCLUDED** (`include = true` / implicit inclusion).
- **Verifiable Rationale:**
  - The case tests the transition from single-character rows to dual-character rows and zero outer padding. SQLite standard formatting operations (`PRINTF`, `LENGTH`, `CHAR`) handle zero padding and interior spacing without issue. The test passes cleanly against the reference implementation.

---

### 3. UUID: `af8efb49-14ed-447f-8944-4cc59ce3fd76`

- **Test Name (Description):**
  - `tests.toml`: `"Smallest non-degenerate case with odd diamond side length"`
  - `create_test_table.sql`: `"Smallest non-degenerate case with odd diamond side length"`
- **Input:**
  - `letter = 'C'`
- **Expected Behavior:**
  - `result = '  A  \n B B \nC   C\n B B \n  A  '` (width = 5, height = 5).
  - Row 1: `"  A  "` (2 leading, `'A'`, 2 trailing)
  - Row 2: `" B B "` (1 leading, `'B'`, 1 interior, `'B'`, 1 trailing)
  - Row 3: `"C   C"` (0 leading, `'C'`, 3 interior, `'C'`, 0 trailing)
  - Row 4: `" B B "` (1 leading, `'B'`, 1 interior, `'B'`, 1 trailing)
  - Row 5: `"  A  "` (2 leading, `'A'`, 2 trailing)
- **Trace to Reference Implementation (`.meta/example.sql`):**
  - **`lengths` CTE:**
    `GENERATE_SERIES(UNICODE('A'), UNICODE('C'))` yields 3 rows:
    - `rn = 1`: `len = 0`, `chr = 'A'`
    - `rn = 2`: `len = 2`, `chr = 'B'`
    - `rn = 3`: `len = 4`, `chr = 'C'`
  - **`lines` CTE:**
    - `'A'` -> `'A'` (length 1)
    - `'B'` -> `PRINTF('%-*c%c', 2, 'B', 'B')` -> `'B B'` (length 3)
    - `'C'` -> `PRINTF('%-*c%c', 4, 'C', 'C')` -> `'C   C'` (length 5)
  - **`padding` CTE:**
    `MAX(LENGTH(line))` is 5.
    - `'A'`: `pad = (5 - 1) / 2 = 2` -> `"  A  "`
    - `'B'`: `pad = (5 - 3) / 2 = 1` -> `" B B "`
    - `'C'`: `pad = (5 - 5) / 2 = 0` -> `"C   C"`
  - **`top` and `bottom` Reflection:**
    - `top`: rows 1, 2, 3 (`"  A  "`, `" B B "`, `"C   C"`)
    - `bottom`: rows 2, 1 (`" B B "`, `"  A  "`) ordered by `rn DESC`.
  - **Aggregation:**
    `GROUP_CONCAT` joins all 5 rows with `CHAR(10)`.
- **Comparison with SQLite Capabilities:**
  - Relevant SQLite operations:
    - Integer division in SQLite: `(5 - 1) / 2 = 2`, `(5 - 3) / 2 = 1`, `(5 - 5) / 2 = 0`. With odd side length (side length = 3), total grid width is `2 * 3 - 1 = 5` (odd), and subtracting line lengths (which are all odd numbers: 1, 3, 5) always yields an even number, ensuring integer division by 2 is exact and symmetrical.
    - `ORDER BY rn DESC` in CTE query: correctly inverts the sequence for bottom-half reflection.
    - `GROUP_CONCAT(line, CHAR(10))`: aggregates rows preserving explicit CTE ordering.
- **Decision:**
  - **INCLUDED** (`include = true` / implicit inclusion).
- **Verifiable Rationale:**
  - Letter `'C'` is the first fully non-degenerate diamond containing leading, interior, and trailing spaces across intermediate rows. SQLite's integer division, dynamic string formatting with `PRINTF`, window functions, and `GROUP_CONCAT` implement this behavior with complete numerical and formatting precision. The test passes 100% against the reference implementation.

---

## Remaining Canonical Cases (Summary)
- **`e0c19a95-9888-4d05-86a0-fa81b9e70d1d`** (`'D'`):
  - Description: `"Smallest non-degenerate case with even diamond side length"`
  - Status: **INCLUDED** (Passes against reference implementation).
- **`82ea9aa9-4c0e-442a-b07e-40204e925944`** (`'Z'`):
  - Description: `"Largest possible diamond"`
  - Status: **INCLUDED** (Passes against reference implementation).

## Conclusion
All 5 canonical test cases are valid, well-formed, and completely supported by SQLite 3.38+ and the reference solution. No cases need to be excluded. The inclusion count remains 5 before and after this review.
