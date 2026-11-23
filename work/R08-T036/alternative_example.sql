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
