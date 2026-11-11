# Hints

## General

- Review the problem requirements: you need to find all contiguous substrings of length `n` in the order they appear.
- Be careful with error conditions: slice length zero, negative slice length, empty series, and slice length greater than input length.

## Language-Specific Guidance: Duplicate-Preserving Operations (`UNION ALL`)

When generating slices across iterations in SQLite (such as within a recursive Common Table Expression using `WITH RECURSIVE`), you need to combine rows produced across successive evaluation steps.

### Chosen Construct: `UNION ALL`

In `example.sql`, the recursive query uses the `UNION ALL` operator:

```sql
WITH RECURSIVE
  to_series (digits, serie) AS (
    VALUES
      (input, NULL)
    UNION ALL
    SELECT
      SUBSTR(digits, 2),
      SUBSTR(digits, 1, slice_length)
    FROM
      to_series
    WHERE
      digits <> ''
  )
```

SQLite supports two primary compound query operators for combining rows:
- **`UNION ALL` (Duplicate-Preserving)**: Appends result sets without discarding duplicate rows.
- **`UNION` (Set Union)**: Appends result sets and discards duplicate rows (treating results as a mathematical set).

### Relevance to Series

In the `series` exercise, strings often contain repeating characters or duplicate subsequences. For example, in the test case `slices can include duplicates` with input `"777777"` and slice length `3`, the expected slices are four identical `"777"` entries (`"777\n777\n777\n777"`).

Because `UNION ALL` preserves duplicate rows, all identical slices are preserved in the order they were produced.

### Executable Micro-Example 1: Duplicate-Preserving with `UNION ALL`

To demonstrate preserving duplicate slices:

```sql
SELECT '777' AS slice
UNION ALL
SELECT '777' AS slice;
```

**Expected Output:**
```text
777
777
```

Both occurrences of `'777'` are retained.

### Executable Micro-Example 2 (Contrasting Pitfall): Set Union with `UNION`

If `UNION` is used instead:

```sql
SELECT '777' AS slice
UNION
SELECT '777' AS slice;
```

**Expected Output:**
```text
777
```

### Why the Outcomes Differ

The outcomes differ because `UNION` performs set deduplication and eliminates duplicate rows across queries. In contrast, `UNION ALL` is duplicate-preserving and concatenates rows directly without removing duplicates. When extracting slices from a series, using `UNION` causes duplicate slices to collapse into a single row, resulting in missing slices and test failures.

### References

- [SQLite Compound SELECT Operators (`UNION ALL` vs `UNION`)](https://www.sqlite.org/lang_select.html#compound)
- [SQLite Recursive Common Table Expressions (`WITH RECURSIVE`)](https://www.sqlite.org/lang_with.html)
