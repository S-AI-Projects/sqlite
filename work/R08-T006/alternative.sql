-- Alternative for the experiment: keep the code mapping in a statement-local
-- CTE and handle both requested operations in one update.
WITH codes(item, code) AS (
  VALUES
    ('eggs', 1),
    ('peanuts', 2),
    ('shellfish', 4),
    ('strawberries', 8),
    ('tomatoes', 16),
    ('chocolate', 32),
    ('pollen', 64),
    ('cats', 128)
)
UPDATE allergies
SET
  result = CASE task
    WHEN 'allergicTo' THEN (
      SELECT CASE WHEN (allergies.score & codes.code) = codes.code THEN 'true' ELSE 'false' END
      FROM codes
      WHERE codes.item = allergies.item
    )
    WHEN 'list' THEN (
      SELECT CASE
        WHEN allergies.score = 0 THEN ''
        ELSE GROUP_CONCAT(codes.item, ', ')
      END
      FROM codes
      WHERE (allergies.score & codes.code) = codes.code
    )
  END;
