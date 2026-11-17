# Pascal's triangle maintenance

The canonical cases in `.meta/tests.toml` exercise the maintained reference in
`.meta/example.sql`. The reference uses two recursive CTEs: an outer counter
enumerates rows, and an inner counter derives each row from the previous value
with `s * k / idx - s`. `group_concat` joins values within a row and joins rows
with a newline.

| UUID | Case | SQLite rationale |
| --- | --- | --- |
| `9920ce55-9629-46d5-85d6-4201f4a4234d` | zero rows | The outer `k < input` predicate emits no row for `input = 0`; the final update explicitly stores `''`. |
| `70d643ce-a46d-4e93-af58-12d88dd01f21` | single row | The inner CTE seed is `(idx=1, s=1)`, so the one-row result is `1`. |
| `a6e5a2a2-fc9a-4b47-9f4f-ed9ad9fbe4bd` | two rows | The second inner step computes `1 * 2 / 1 - 1 = 1`, producing `1 1`. |
| `97206a99-79ba-4b04-b1c5-3c0fa1e16925` | three rows | The recurrence yields `1`, `1 1`, and `1 2 1`. |
| `565a0431-c797-417c-a2c8-2935e01ce306` | four rows | The same recurrence extends the middle row to `1 3 3 1`. |
| `06f9ea50-9f51-4eb2-b9a9-c00975686c27` | five rows | The generated rows include `1 4 6 4 1`. |
| `c3912965-ddb4-46a9-848e-3363e6b00b13` | six rows | The generated rows include `1 5 10 10 5 1`. |
| `6cb26c66-7b57-4161-962c-81ec8c99f16b` | ten rows | The reference is checked through the tenth row, including `1 9 36 84 126 126 84 36 9 1`. |

The metadata contains eight included cases and no exclusions. Regeneration may
rewrite descriptions, but the `comment` values above are the durable rationale
for the three selected UUIDs.

## Reproducible check

From the repository root, run:

```bash
python3 work/R08-T001/check.py
```

The checker resolves paths from `.meta/config.json`, copies the complete
exercise (including dotfiles) to a temporary directory, substitutes the
reference only in that copy, runs `sqlite3 -bail`, and validates every JSON
result. It also records the included/excluded counts and confirms the learner
stub is not modified.
