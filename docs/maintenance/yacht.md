# Yacht Maintenance Documentation

This document describes the test suite characteristics, mutation testing results, and subtle scoring contract rules for the `yacht` practice exercise in the SQLite track.

---

## 1. Overview & Scoring Rules

The `yacht` exercise tests 12 distinct scoring categories against rolls of 5 six-sided dice:
- **Numbers (ones - sixes)**: Sum of dice matching the category number.
- **Full House**: Sum of all 5 dice if and only if there are **exactly 3 of one die face and exactly 2 of another die face**.
- **Four of a Kind**: Sum of the 4 matching dice (4 * die value) if at least 4 dice share the same face.
- **Little Straight**: 30 points if the dice are `1, 2, 3, 4, 5`.
- **Big Straight**: 30 points if the dice are `2, 3, 4, 5, 6`.
- **Choice**: Sum of all dice.
- **Yacht**: 50 points if all 5 dice are identical.

---

## 2. Reference Mutant Analysis: Full House

### The Pitfall
In dice games, a common misconception or flawed implementation occurs when evaluating a **Full House**:
1. Conflating 5-of-a-kind (Yacht) with Full House by reasoning that 5 matching dice include "at least 3 of a kind and at least 2 of a kind".
2. Failing to verify that the distinct group count equals 2 (or checking `MAX(counts) == 3`), instead checking `MAX(counts) IN (3, 5)` or `count >= 3`.

Under standard Yacht rules, **a Yacht is NOT a Full House**. Five identical dice must score `0` in the `full house` category.

### Mutant Implementation Diff

The reference mutant replaces the strict Full House condition:

```sql
--- Reference Solution (example.sql)
+++ Mutant Solution (mutant.sql)
@@ -37,16 +37,16 @@
         WHEN 'full house' THEN CASE
-          WHEN MAX(ones, twos, threes, fours, fives, sixes) == 3
+          WHEN MAX(ones, twos, threes, fours, fives, sixes) IN (3, 5)
           AND (
-            ones == 3
-            OR twos == 3
-            OR threes == 3
-            OR fours == 3
-            OR fives == 3
-            OR sixes == 3
+            ones IN (3, 5)
+            OR twos IN (3, 5)
+            OR threes IN (3, 5)
+            OR fours IN (3, 5)
+            OR fives IN (3, 5)
+            OR sixes IN (3, 5)
           ) THEN total
           ELSE 0
         END
```

---

## 3. Mutant Detection: Rejecting Test Case

The mutant passes 28 out of 29 test cases, but is caught and rejected by the canonical test case specifically designed for this edge case:

| Field | Value |
| :--- | :--- |
| **UUID** | `32a3f4ee-9142-4edf-ba70-6c0f96eb4b0c` |
| **Test Description (`tests.toml`)** | `Yacht is not a full house` |
| **Category** | `full house` |
| **Dice Results** | `'2, 2, 2, 2, 2'` |
| **Expected Score** | `0` |
| **Actual Mutant Score** | `10` |
| **Error Message** | `Result for 2, 2, 2, 2, 2 as full house is <10> but should be <0>` |

### Significance
Without test `32a3f4ee-9142-4edf-ba70-6c0f96eb4b0c`, a solution that erroneously classifies 5-of-a-kind as a Full House would pass all test suites undetected. This mutation verification confirms that the test suite is mutation-resistant for this critical contract rule.
