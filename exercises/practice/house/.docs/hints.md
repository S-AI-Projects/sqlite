# SQLite Hint – Window Function Ordering

The reference implementation for the *House* exercise builds each verse using a **window function**:

```sql
GROUP_CONCAT(sentence, ' ') OVER (
  ORDER BY idx DESC ROWS BETWEEN 0 PRECEDING AND 12 FOLLOWING
)
```

### What it does
- `GROUP_CONCAT` concatenates the `sentence` values into a single string.
- The `OVER (…)` clause creates a *window* that orders rows by `idx DESC` (reverse order) and includes the current row plus the next twelve rows. This guarantees that for any verse we concatenate the current line and all later lines, preserving the correct reverse‑order of the rhyme.
- Without the explicit `ORDER BY idx DESC` the order of concatenation would be undefined, leading to nondeterministic verse text.

### Small executable micro‑example
```sql
WITH cte(idx, sentence) AS (
  VALUES
    (1, 'first'),
    (2, 'second')
)
SELECT
  GROUP_CONCAT(sentence, ' ') OVER (ORDER BY idx DESC) AS ordered,
  GROUP_CONCAT(sentence, ' ') OVER ()                AS unordered;
```

**Expected output** (run with `sqlite3 -batch -separator '|' -noheader`):
```
second first|first second
```

### Why the ordering matters
If the `ORDER BY idx DESC` is omitted, the `ordered` column could produce `first second` instead of the deterministic `second first`. The *House* exercise relies on a **stable reverse ordering** to correctly build each verse from the bottom up.

For more details see the SQLite documentation on **window functions** and **GROUP_CONCAT**:
https://www.sqlite.org/windowfunctions.html
