# Transpose Maintenance Documentation

This document maintains test coverage mappings, SQLite operations, and maintenance rationale for the `transpose` exercise in the SQLite track of Exercism.

## Overview

The `transpose` exercise requires transposing an input string consisting of rows and columns of characters into its matrix transpose. In SQLite, this involves:
1. Splitting input lines using recursive Common Table Expressions (CTEs) or character search functions (`INSTR`, `SUBSTR`, `CHAR(10)`).
2. Parsing strings into per-character cells and determining the maximum row length using `MAX(LENGTH(line))` and `PRINTF` for space padding.
3. Transposing rows into columns using JSON aggregation functions (`JSON_GROUP_ARRAY`, `JSON_EXTRACT`, `JSON_EACH`) or recursive column index extraction.
4. Aggregating transposed characters into lines using `GROUP_CONCAT` and string concatenation (`||`), and applying trailing space trimming rules via `RTRIM`.

## Canonical Test Cases & SQLite Operation Mapping Table

| UUID | Description | SQLite Operation Used | Coverage Status |
| :--- | :--- | :--- | :--- |
| `404b7262-c050-4df0-a2a2-0cb06cd6a821` | empty string | Recursive CTE recursion termination at length 0 / `UPDATE ... WHERE lines = ''` producing an empty result set | Covered (pass) |
| `a89ce8a3-c940-4703-a688-3ea39412fbcb` | two characters in a row | `SUBSTR()` for character extraction, single-row recursive CTE expansion into 2 column rows | Covered (pass) |
| `855bb6ae-4180-457c-abd0-ce489803ce98` | two characters in a column | `GROUP_CONCAT()` or string concatenation `\|\|` across row entities into a single output row | Covered (pass) |
| `5ceda1c0-f940-441c-a244-0ced197769c8` | simple | Recursive CTEs, `JSON_GROUP_ARRAY()`, `JSON_EXTRACT()`, `GROUP_CONCAT()` | Covered (pass) |
| `a54675dd-ae7d-4a58-a9c4-0c20e99a7c1f` | single line | Single-line splitting, `SUBSTR()`, `JSON_GROUP_ARRAY()`, `GROUP_CONCAT()` | Covered (pass) |
| `0dc2ec0b-549d-4047-aeeb-8029fec8d5c5` | first line longer than second line | `PRINTF()` space-padding, `MAX(LENGTH())`, `RTRIM()`, `GROUP_CONCAT()` | Covered (pass) |
| `984e2ec3-b3d3-4b53-8bd6-96f5ef404102` | second line longer than first line | `PRINTF()` space-padding, `MAX(LENGTH())`, `RTRIM()`, `GROUP_CONCAT()` | Covered (pass) |
| `eccd3784-45f0-4a3f-865a-360cb323d314` | mixed line length | `PRINTF()` space-padding, `MAX(LENGTH())`, `RTRIM()`, `GROUP_CONCAT()` | Covered (pass) |
| `85b96b3f-d00c-4f80-8ca2-c8a5c9216c2d` | square | Symmetric NxN matrix transposition, `JSON_GROUP_ARRAY()`, `GROUP_CONCAT()` | Covered (pass) |
| `b9257625-7a53-4748-8863-e08e9d27071d` | rectangle | Asymmetric MxN matrix transposition, `JSON_GROUP_ARRAY()`, `GROUP_CONCAT()` | Covered (pass) |
| `b80badc9-057e-4543-bd07-ce1296a1ea2c` | triangle | Uneven line lengths, `PRINTF()` padding, selective whitespace preservation | Covered (pass) |
| `76acfd50-5596-4d05-89f1-5116328a7dd9` | jagged triangle | Complex trailing whitespace trimming with `RTRIM()`, placeholder preservation | Covered (pass) |

## Key UUID Rationale

### 1. `404b7262-c050-4df0-a2a2-0cb06cd6a821` (empty string)
- **Behavior**: Input text is completely empty `""`.
- **SQLite Operation**: SQLite CTE recursion terminates immediately at length 0, producing an empty result set (or handled via `UPDATE transpose SET result = '' WHERE lines = ''`).
- **Significance**: Ensures base-case recursion termination without infinite loops or producing `NULL` outputs.

### 2. `a89ce8a3-c940-4703-a688-3ea39412fbcb` (two characters in a row)
- **Behavior**: Input contains 1 row with 2 columns (`"A1"`), transposing into 2 rows of 1 column each (`"A\n1"`).
- **SQLite Operation**: Character extraction using `SUBSTR(string, 1, 1)` and `SUBSTR(string, 2)` inside recursive CTE `to_letter`.
- **Significance**: Verifies horizontal line splitting into individual character tokens in SQLite.

### 3. `855bb6ae-4180-457c-abd0-ce489803ce98` (two characters in a column)
- **Behavior**: Input contains 2 rows with 1 column each (`"A\n1"`), transposing into 1 row of 2 columns (`"A1"`).
- **SQLite Operation**: String aggregation using `GROUP_CONCAT(letter, '')` or string concatenation `||`.
- **Significance**: Validates vertical aggregation across row boundaries in SQLite without extraneous separators.
