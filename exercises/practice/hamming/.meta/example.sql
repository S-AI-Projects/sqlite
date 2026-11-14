UPDATE hamming
SET
  error = 'strands must be of equal length'
WHERE
  LENGTH(strand1) != LENGTH(strand2);

UPDATE hamming
SET
  result = (
    WITH RECURSIVE
      rcte (remaining1, remaining2, nucleotide1, nucleotide2) AS (
        VALUES
          (strand1, strand2, '', '')
        UNION ALL
        SELECT
          SUBSTRING(remaining1, 2),
          SUBSTRING(remaining2, 2),
          SUBSTRING(remaining1, 1, 1),
          SUBSTRING(remaining2, 1, 1)
        FROM
          rcte
        WHERE
          remaining1 <> ''
      )
    SELECT
      COUNT(*)
    FROM
      rcte
    WHERE
      nucleotide1 != nucleotide2
  )
WHERE
  LENGTH(strand1) = LENGTH(strand2);
