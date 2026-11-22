-- Complexity Analysis & Implementation Strategy:
--
-- 1. Closed-Form Algebraic Solutions:
--    - Time Complexity: O(1) per row.
--      Each evaluation involves a fixed, bounded number of basic arithmetic operations
--      (additions, multiplications, and integer division) that execute in constant time,
--      regardless of the magnitude of `number` (n). In SQLite's bytecode engine (VDBE),
--      this compiles to a fixed sequence of ~16-20 opcodes with no loops.
--    - Space Complexity: O(1).
--      Computations are performed entirely in CPU/VDBE registers without allocating
--      intermediate tables, recursive stacks, or memory buffers.
--
-- 2. Comparison with Recursive CTE Generation:
--    - A recursive CTE approach (e.g. generating rows 1..n via UNION ALL) would require:
--      * Time Complexity: O(n) row iterations, repeated additions/multiplications, and context switches.
--      * Space Complexity: O(n) memory to maintain recursive stack frames or temporary B-tree storage.
--      * Potential recursion stack exhaustion (exceeding SQLite's SQLITE_LIMIT_RECURSIVE_DEPTH = 1000).
--
-- 3. Algebraic Formulas Applied:
--    - squareOfSum:       (n * (n + 1) / 2)^2 = n^2 * (n + 1)^2 / 4
--    - sumOfSquares:      n * (n + 1) * (2n + 1) / 6
--    - differenceOfSquares: squareOfSum - sumOfSquares = n * (n + 1) * (3n + 2) * (n - 1) / 12

-- Calculate Square of Sum: O(1) time, O(1) space
UPDATE 'difference-of-squares'
SET
  result = number * number * (number + 1) * (number + 1) / 4
WHERE
  property = 'squareOfSum';

-- Calculate Sum of Squares: O(1) time, O(1) space
UPDATE 'difference-of-squares'
SET
  result = number * (number + 1) * (2 * number + 1) / 6
WHERE
  property = 'sumOfSquares';

-- Calculate Difference of Squares: O(1) time, O(1) space
UPDATE 'difference-of-squares'
SET
  result = number * (number + 1) * (3 * number + 2) * (number - 1) / 12
WHERE
  property = 'differenceOfSquares';
