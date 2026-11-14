# SQLite-specific instructions

## JSON documentation

[JSON Functions And Operators][json-docs]

[json-docs]: https://www.sqlite.org/json1.html

## `UNION` and `UNION ALL` in recursive searches

`UNION` removes duplicate complete rows, while `UNION ALL` keeps them. For
example:

```sql
WITH
  deduplicated(value) AS (
    SELECT 7
    UNION
    SELECT 7
  ),
  duplicate_preserving(value) AS (
    SELECT 7
    UNION ALL
    SELECT 7
  )
SELECT
  (SELECT COUNT(*) FROM deduplicated) AS union_rows,
  (SELECT COUNT(*) FROM duplicate_preserving) AS union_all_rows;
```

The result is `1|2`: the first CTE contains one row and the second contains
two. This distinction applies to whole rows, not to individual values inside
a JSON array.

The binary-search reference uses `UNION` in its recursive CTE. Each CTE row is
a search state: the remaining candidate list and the target. Its list stores
each value together with its original index, so equal values at different
positions remain distinct entries. The search narrows that list at each step;
`UNION` would discard an identical repeated state, not remove equal values
from the list.

Binary search also depends on the input array being sorted: only then does the
middle value tell you which half can be discarded. The reference returns a
zero-based index when it finds the target. When it does not, the result is SQL
`NULL` and the error is `value not in array`; do not use `0` to mean “not
found,” because index zero is valid.
