# Rationales for Transpose Canonical Test UUIDs

This document details the rationales and SQLite operational behaviors for three foundational canonical test cases in `exercises/practice/transpose`.

---

## 1. UUID: `404b7262-c050-4df0-a2a2-0cb06cd6a821`
- **Description**: `empty string`
- **Input**: `""`
- **Expected Output**: `""`
- **Explanatory Rationale**:
  * Input text is empty.
  * SQLite CTE recursion terminates at length 0, producing an empty result set.
  * In the reference implementation (`example.sql`), an explicit `UPDATE transpose SET result = '' WHERE lines = '';` or recursive base termination condition ensures that no `NULL` value or empty line artifact is generated.
  * Verifying this case ensures that recursive SQL statements do not enter infinite loops when scanning zero-length strings.

---

## 2. UUID: `a89ce8a3-c940-4703-a688-3ea39412fbcb`
- **Description**: `two characters in a row`
- **Input**: `"A1"`
- **Expected Output**: `"A
1"`
- **Explanatory Rationale**:
  * 1 row with 2 columns transposes into 2 rows of 1 column each.
  * SQLite character extraction uses `SUBSTR()` (specifically `SUBSTR(string, 1, 1)` to extract the current character and `SUBSTR(string, 2)` to step the recursive remainder).
  * This case confirms that single-line horizontal string decomposition works properly in SQLite before multi-line aggregation.

---

## 3. UUID: `855bb6ae-4180-457c-abd0-ce489803ce98`
- **Description**: `two characters in a column`
- **Input**: `"A
1"`
- **Expected Output**: `"A1"`
- **Explanatory Rationale**:
  * 2 rows with 1 column each transpose into 1 row of 2 columns.
  * String aggregation in SQLite uses `GROUP_CONCAT()` (with an empty separator `GROUP_CONCAT(..., '')`) or the string concatenation operator `||`.
  * This validates that character tokens extracted from separate vertical rows can be aggregated horizontally into a single transposed output row.
