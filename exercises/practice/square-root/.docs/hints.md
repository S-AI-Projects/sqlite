# Approach‑selection hints for Square‑Root

The exercise asks for an **integer square root** – given a positive whole number that is a perfect square, return its square‑root as a whole number.

## Reference implementation (Newton / Heron method)
```sql
UPDATE "square-root"
SET
  result = (
    WITH RECURSIVE
      isqrt (number, approx) AS (
        VALUES
          (radicand, radicand)
        UNION ALL
        SELECT
          number,
          (number / approx + approx) / 2
        FROM
          isqrt
        WHERE
          approx * approx != NUMBER
          AND approx > 1
      )
    SELECT
      approx AS sqrt
    FROM
      isqrt
    ORDER BY
      approx ASC
    LIMIT
      1
  );
```
* **State representation:** a recursive CTE `isqrt` holds the current approximation (`approx`).
* **Operation:** each iteration applies Newton’s formula `(n/approx + approx)/2` until `approx*approx == n`.
* **Complexity:** iterations converge quadratically; for the numbers used in the test suite (max 65025) only a handful of rows are produced.
* **Why it’s clear:** the mathematical recurrence is explicit in the query, making the algorithm easy to recognise for anyone familiar with Newton’s method.

---
## Alternative implementation (linear scan)
```sql
UPDATE "square-root"
SET
  result = (
    WITH RECURSIVE
      seq(i) AS (
        SELECT 1
        UNION ALL
        SELECT i+1 FROM seq WHERE i*i < radicand
      )
    SELECT i FROM seq WHERE i*i = radicand
  );
```
* **State representation:** a recursive CTE `seq` enumerates candidate integers `i` starting at 1.
* **Operation:** the CTE grows `i` until `i*i` reaches the radicand; the matching `i` is the integer square‑root.
* **Complexity:** **O(√n)** – the loop runs once per integer up to the true root. For the biggest test (`65025 → 255`) this means 255 iterations, which is still trivial.
* **When useful:** the linear scan is conceptually the simplest possible algorithm – no arithmetic tricks, just counting. It is helpful when teaching recursion or when the input size is guaranteed to be tiny.
* **Trade‑off:** it creates more intermediate rows than Newton’s method and therefore uses slightly more memory and CPU, but the code is shorter and arguably easier for beginners to follow.

---
## Worked example (radicand = 196)
1. **Reference (Newton)** – starts with `approx = 196`. After the first iteration it becomes `(196/196 + 196)/2 = 98.5` (floored to 98 by integer division), then `≈ 49`, `≈ 25`, `≈ 17`, `≈ 14` and finally converges to `14`.
2. **Alternative (linear scan)** – generates `i = 1, 2, …, 14`. When `i = 14`, `i*i = 196` matches the radicand, so the update stores `14`.

Both yield the same correct result for all enabled tests.

---
### Why the alternative is genuinely different
The reference uses a **numerical‑method recurrence** (Newton) that halves the error each step. The alternative uses a **pure enumeration** of candidates, advancing by 1 each step. The control flow, state variables and number of generated rows are completely distinct, satisfying the requirement for a meaningfully different algorithm.

---
*This hint is intended for learners – it explains the two approaches without revealing the full learner stub.*