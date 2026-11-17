# Reverse-string complexity note

The reference uses a recursive CTE. It starts with the complete input and an
empty output character, then removes one trailing character per recursive row
until the input is empty. For an input of length `n`, the CTE visits `n + 1`
states. Because each step also copies a shrinking prefix with `SUBSTRING`, the
SQL work is quadratic in the number of characters (`O(n^2)`), while the final
`GROUP_CONCAT` is linear in the produced output. This is an algorithmic
statement; wall-clock timings from separate `sqlite3` processes also include
process startup and shell overhead.

The focused check uses valid inputs of lengths 1, 5, and 32, runs each size five
times, asserts the reversed output before recording timing, and stores the
median in `work/R08-T005/results.json`. The operation-count evidence is stable
across machines:

| Input length | Recursive states (`n + 1`) | Expected output |
| ---: | ---: | --- |
| 1 | 2 | `a` |
| 5 | 6 | `aaaaa` |
| 32 | 33 | 32 `a` characters |

On the verification run, the five-process medians were 5.555 ms, 5.013 ms,
and 5.324 ms respectively. Those values are diagnostic only: the samples are
small and the process-startup component dominates, so the complexity statement
relies on the recursive-state and shrinking-prefix analysis above.

No speedup claim is made from these small timings. They demonstrate the
reference's fixed recursive work for the tested sizes and preserve the
exercise's learner stub.

Run the check from the repository root:

```bash
python3 work/R08-T005/check.py
```
