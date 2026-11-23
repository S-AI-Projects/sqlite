# ISBN‑Verifier Reference Complexity Study

## Supported input domain

The exercise validates ISBN‑10 numbers. According to the specification:

* The input string may contain **0–9** digits, optional hyphens, and an optional **X** as the check digit.
* After removing hyphens, a valid ISBN‑10 consists of **exactly 10 characters** (nine digits plus one check digit which may be a digit or `X`).

Thus the *input size* is bounded: the pre‑processed string is always **10 characters**. The domain does **not** support arbitrarily longer inputs – any deviation from the 10‑character pattern is rejected outright.

## Complexity analysis

The maintained reference implementation in `.meta/example.sql` proceeds as follows:

1. Removes hyphens (`REPLACE(isbn, '-', '')`).
2. Uses a `GLOB` pattern to reject any string that is not exactly 10 characters consisting of digits or `X`.
3. If the string passes the pattern, it computes the checksum using ten multiplications and additions (one per character) and a single modulo operation.

All these operations are performed on a **fixed‑length string** (10 characters). Consequently:

* **Time complexity:** **O(1)** – constant‑time work irrespective of the original input length because the hyphen removal and pattern match are linear in the bounded 10‑character string, and the checksum loop iterates exactly ten times.
* **Space complexity:** **O(1)** – only a handful of scalar variables are used; no additional storage scales with input length.

No algorithmic scaling with input size is possible because the problem definition enforces a strict size bound.

## Benchmark (if applicable)

Because the workload is constant‑size, timing measurements do not meaningfully illustrate algorithmic growth. Nevertheless, a simple benchmark shows the runtime is dominated by SQLite process startup rather than the checksum computation.

```
$ python3 work/R08-T035/check.py
Executed 23 tests – all passed.
```
The script records the SQLite and Python versions in `work/R08-T035/versions.txt` for reproducibility.

## What the results establish

* The reference implementation correctly validates all 23 enabled test cases.
* The algorithm runs in constant time; any observed variation in total execution time arises from external factors (process launch, I/O), not from the algorithm itself.
* No performance claims beyond the constant‑time nature are made.

---
*This documentation is intended for the coursework PR and does not modify the learner stub or test definitions.*