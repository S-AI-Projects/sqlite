UPDATE "reverse-string"
SET
  -- Each recursive row removes one trailing character. For input length n,
  -- the CTE visits n+1 states and copies shrinking prefixes, so SQL work is
  -- quadratic in n; sqlite3 process startup is outside this algorithm cost.
  result = (
    WITH RECURSIVE
      reverse_char (string, char) AS (
        VALUES
          (input, '')
        UNION ALL
        SELECT
          SUBSTRING(string, 1, LENGTH(string) - 1),
          SUBSTRING(string, -1)
        FROM
          reverse_char
        WHERE
          string <> ''
      )
    SELECT
      GROUP_CONCAT(char, '')
    FROM
      reverse_char
  );
