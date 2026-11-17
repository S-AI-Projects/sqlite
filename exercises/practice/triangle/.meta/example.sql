-- Compute validity once so every classification below starts from the same
-- triangle-inequality invariant.
WITH triangle_validity AS (
  SELECT
    rowid,
    side_a > 0
    AND side_b > 0
    AND side_c > 0
    AND side_a + side_b >= side_c
    AND side_b + side_c >= side_a
    AND side_a + side_c >= side_b AS is_valid
  FROM triangle
)
UPDATE triangle
SET
  result = FALSE
WHERE rowid IN (
  SELECT rowid
  FROM triangle_validity
  WHERE NOT is_valid
);

UPDATE triangle
SET
  result = (
    side_a = side_b
    AND side_a = side_c
  )
WHERE
  property = 'equilateral'
  AND result ISNULL;

UPDATE triangle
SET
  result = (
    side_a = side_b
    OR side_a = side_c
    OR side_b = side_c
  )
WHERE
  property = 'isosceles'
  AND result ISNULL;

UPDATE triangle
SET
  result = (
    side_a != side_b
    AND side_a != side_c
    AND side_b != side_c
  )
WHERE
  property = 'scalene'
  AND result ISNULL;
