# Hints

- Remember that the contract specifies **null‑like values must be omitted** from the flattened result.
- The reference implementation filters out `NULL` values when aggregating the JSON tree. If that filter is missing, the result will contain `null` entries and the corresponding tests will fail.
- Check the `WHERE` clause of the `UPDATE` statement in `.meta/example.sql`; it should include a condition that excludes `NULL` values (`AND j.value NOTNULL`).