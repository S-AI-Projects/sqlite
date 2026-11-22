# Hints

## General

A queen in chess can move any number of unoccupied squares along a row, column, or diagonal. Thus, two queens can attack each other if they share:
- The same row: `white_row = black_row`
- The same column: `white_col = black_col`
- The same diagonal

---

## SQLite-Specific Guidance

### 1. Board Boundary Validation

The chessboard is an $8 \times 8$ grid indexed from `0` to `7` (both ranks and files). In SQLite, you can validate that a coordinate lies within valid boundaries using the `BETWEEN` operator:

```sql
row BETWEEN 0 AND 7 AND col BETWEEN 0 AND 7
```

When validating coordinates in a `CASE` expression, the canonical tests require specific error descriptions matching coordinate bounds in order of precedence:

- `row < 0`: `'row not positive'`
- `row > 7`: `'row not on board'`
- `col < 0`: `'column not positive'`
- `col > 7`: `'column not on board'`

For example:
```sql
UPDATE "queen-attack"
SET error = CASE
  WHEN white_row < 0 OR black_row < 0 THEN 'row not positive'
  WHEN white_row > 7 OR black_row > 7 THEN 'row not on board'
  WHEN white_col < 0 OR black_col < 0 THEN 'column not positive'
  WHEN white_col > 7 OR black_col > 7 THEN 'column not on board'
  ELSE NULL
END;
```

---

### 2. Same-Square Validation

In standard chess, two pieces cannot simultaneously occupy the exact same square. When validating piece placement, you can check whether the white queen and black queen have identical coordinates:

```sql
white_row = black_row AND white_col = black_col
```

Depending on the track test requirements, placing two pieces on the exact same square may either trigger an error or evaluate as an attack (since distance is zero). Ensure error conditions are evaluated before computing the attack outcome.

---

### 3. Diagonal Check Using SQLite's `ABS()` Function

Determining whether two pieces share a diagonal does not require generating series of positions (`GENERATE_SERIES` or recursive Common Table Expressions). Instead, two pieces lie on the same diagonal if and only if the absolute vertical distance equals the absolute horizontal distance:

$$\lvert r_1 - r_2 \rvert = \lvert c_1 - c_2 \rvert$$

SQLite provides the built-in mathematical function `ABS()`:

```sql
ABS(white_row - black_row) = ABS(white_col - black_col)
```

- **Efficiency**: Calculating `ABS(white_row - black_row) = ABS(white_col - black_col)` runs in $O(1)$ constant time with minimal CPU instructions, avoiding recursive CTE overhead and temporary row allocations.
- **Direction Invariance**: Because the distance is taken as an absolute magnitude, this single condition simultaneously checks all four diagonal directions (rising, falling, forward, and backward).

---

### 4. Boolean Result Representation in SQLite

SQLite does not have a separate boolean storage class:
- Boolean values are represented as integers: `1` for **true** and `0` for **false**.
- Comparison operations and boolean logic expressions in SQLite automatically evaluate to `1` or `0`:

```sql
UPDATE "queen-attack"
SET result = (
  white_row = black_row
  OR white_col = black_col
  OR ABS(white_row - black_row) = ABS(white_col - black_col)
)
WHERE error IS NULL;
```

Alternatively, SQLite accepts the literal keywords `TRUE` and `FALSE`, which internally map directly to integer constants `1` and `0`.
