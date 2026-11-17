# SQLite-specific hint

The reference walks the input with a recursive CTE and then uses
`GROUP_CONCAT(..., '')` to join the transformed characters. The seed row has
`chr = NULL`; the final `WHERE chr NOTNULL` removes that seed before
aggregation. `GROUP_CONCAT` ignores NULL values, but it preserves duplicate
non-NULL rows, which matters when a message repeats a letter. Replacing it with
a distinct set operation would silently lose characters.

This standalone example makes the distinction explicit:

```sql
WITH letters(ord, ch) AS (VALUES (1, 'a'), (2, 'b'), (3, 'a'))
SELECT
  (SELECT group_concat(ch, '') FROM (SELECT ch FROM letters ORDER BY ord)) AS kept,
  (SELECT group_concat(ch) FROM (SELECT DISTINCT ch FROM letters ORDER BY ch)) AS collapsed;
```

It returns `aba|a,b`: the ordered stream keeps both `a` rows, while `DISTINCT`
collapses them. In the exercise, the recursive traversal supplies one row per
input character; if a future change needs a formal aggregate-order guarantee,
feed `GROUP_CONCAT` an explicitly ordered subquery rather than relying on an
incidental scan order.
