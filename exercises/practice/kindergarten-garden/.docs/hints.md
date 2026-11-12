# Hints

## General

- Each student is responsible for four cups: two adjacent cups on the top row and two adjacent cups directly beneath them on the bottom row.
- Students are assigned cups alphabetically based on their names (`Alice` at index 0, `Bob` at index 1, ..., `Larry` at index 11).

## Cup Traversal Order & Row-Major Contract

- Pay close attention to the order in which plants must be reported.
- The contract requires **row-major** traversal:
  1. Top row, student's left cup
  2. Top row, student's right cup
  3. Bottom row, student's left cup
  4. Bottom row, student's right cup
- A common mistake is traversing in **column-major** order (top-left, bottom-left, top-right, bottom-right).

## Diagnostic Example

Consider the smallest garden with a single student (`Alice`):
```text
RC
GG
```
- **Top row**: `R` (radishes), `C` (clover)
- **Bottom row**: `G` (grass), `G` (grass)
- **Expected result**: `radishes,clover,grass,grass`
- **Diagnostic check**: If your query produces `radishes,grass,clover,grass`, your traversal order is collecting column-by-column rather than row-by-row. Ensure both plants from the first row are listed before the plants from the second row.
