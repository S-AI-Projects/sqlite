-- Invariant Contract & Valid Input Specification:
-- 1. Valid Input Range:
--    0 <= number <= 999,999,999,999 (from zero up to 10^12 - 1).
--    Numbers < 0 or >= 1,000,000,000,000 (1e12) are out of range and must set error = 'input out of range'.
-- 2. Hyphenation Rules:
--    Compound two-digit numbers between 21 and 99 (except exact multiples of 10) must be
--    hyphenated with a single hyphen (e.g., 'twenty-two', 'ninety-nine').
-- 3. Chunk Decomposition:
--    Numbers are partitioned into 3-digit chunks corresponding to magnitude scale factors:
--    - 10^9: billions
--    - 10^6: millions
--    - 10^3: thousands
--    - 10^0: units (hundreds, tens, and ones)
-- 4. Text Assembly:
--    Chunks are formatted and assembled from highest to lowest magnitude, separated by single spaces.
--    Zero chunks are omitted unless the input is exactly 0 ('zero').

-- ============================================================================
-- Stage 1: Base Case & Input Range Validation
-- ============================================================================

-- Boundary Case: Exactly 0
UPDATE say
SET
  result = 'zero'
WHERE
  number = 0;

-- Invariant Enforcement: Validate range [0, 999,999,999,999]
UPDATE say
SET
  error = 'input out of range'
WHERE
  number < 0
  OR number >= 1e12;

-- ============================================================================
-- Stage 2: Base Unit Lookups (0-19) and Tens Lookups (20, 30, ... 90)
-- ============================================================================

DROP TABLE IF EXISTS dict;

CREATE TEMPORARY TABLE dict (digits INTEGER PRIMARY KEY, words TEXT NOT NULL);

-- Seed base single units and teens (0-19) along with exact multiples of ten (20-90)
INSERT INTO
  dict (digits, words)
VALUES
  (0, 'zero'),
  (1, 'one'),
  (2, 'two'),
  (3, 'three'),
  (4, 'four'),
  (5, 'five'),
  (6, 'six'),
  (7, 'seven'),
  (8, 'eight'),
  (9, 'nine'),
  (10, 'ten'),
  (11, 'eleven'),
  (12, 'twelve'),
  (13, 'thirteen'),
  (14, 'fourteen'),
  (15, 'fifteen'),
  (16, 'sixteen'),
  (17, 'seventeen'),
  (18, 'eighteen'),
  (19, 'nineteen'),
  (20, 'twenty'),
  (30, 'thirty'),
  (40, 'forty'),
  (50, 'fifty'),
  (60, 'sixty'),
  (70, 'seventy'),
  (80, 'eighty'),
  (90, 'ninety');

-- ============================================================================
-- Stage 3: Hyphenated Compound Numbers (21-99) & Hundreds (100-900)
-- ============================================================================

-- Recursive CTE generating hyphenated compound dozens (e.g., 'twenty-one' ... 'ninety-nine')
WITH
  dozens (jarray) AS (
    SELECT
      (
        WITH RECURSIVE
          rcte (base, unit, dozen, string) AS (
            VALUES
              (digits, 1, NULL, NULL)
            UNION ALL
            SELECT
              digits,
              unit + 1,
              base + unit,
              PRINTF(
                '%s-%s',
                (
                  SELECT
                    words
                  FROM
                    dict
                  WHERE
                    digits = base
                ),
                (
                  SELECT
                    words
                  FROM
                    dict
                  WHERE
                    digits = unit
                )
              )
            FROM
              rcte
            WHERE
              unit < 10
          )
        SELECT
          JSON_GROUP_ARRAY(JSON_ARRAY(dozen, string))
        FROM
          rcte
        WHERE
          dozen NOT NULL
      )
    FROM
      dict
    WHERE
      digits BETWEEN 20 AND 90
  )
INSERT INTO
  dict (digits, words)
SELECT
  JSON_EXTRACT(j.VALUE, '$[0]'),
  JSON_EXTRACT(j.VALUE, '$[1]')
FROM
  dozens,
  JSON_EACH(jarray) j;

-- Generate hundreds multiples (100, 200, ... 900)
INSERT INTO
  dict
SELECT
  value * 100,
  (
    SELECT
      words
    FROM
      dict
    WHERE
      digits = VALUE
  ) || ' hundred'
FROM
  GENERATE_SERIES (1, 9);

-- ============================================================================
-- Stage 4: Magnitude Scale Positions (thousands, millions, billions)
-- ============================================================================

DROP TABLE IF EXISTS positions;

CREATE TEMPORARY TABLE positions (pos INTEGER PRIMARY KEY, words TEXT NOT NULL);

INSERT INTO
  positions (pos, words)
VALUES
  (2, 'thousand'),       -- 10^3
  (3, 'million'),        -- 10^6
  (4, 'billion'),        -- 10^9
  (5, 'trillion'),       -- 10^12
  (6, 'quadrillion'),    -- 10^15
  (7, 'quintillion'),    -- 10^18
  (8, 'sextillion'),
  (9, 'septillion'),
  (10, 'octillion'),
  (11, 'nonillion'),
  (12, 'decillion'),
  (13, 'undecillion'),
  (14, 'duodecillion'),
  (15, 'tredecillion'),
  (16, 'quattuordecillion'),
  (17, 'quindecillion'),
  (18, 'sexdecillion'),
  (19, 'septendecillion'),
  (20, 'octodecillion'),
  (21, 'novemdecillion'),
  (22, 'vigintillion');

-- ============================================================================
-- Stage 5: 3-Digit Chunk Decomposition & Final Text Assembly
-- ============================================================================

UPDATE say
SET
  result = (
    WITH
      -- Stage 5.1: 3-digit chunk decomposition (units, 10^3 thousands, 10^6 millions, 10^9 billions)
      decompositor (num, thousands, thpos) AS (
        WITH RECURSIVE
          decompositor (num, thousands, thpos) AS (
            VALUES
              (number, NULL, 0)
            UNION ALL
            SELECT
              num / 1000,
              JSON_ARRAY(num % 1000 - num % 100, (num % 1000) % 100),
              thpos + 1
            FROM
              decompositor
            WHERE
              num > 0
          )
        SELECT
          *
        FROM
          decompositor
      ),
      -- Stage 5.2: Map decomposed hundreds and tens/units to words and attach scale suffixes
      to_strings (thpos, hundred, dozen, pos_str) AS (
        SELECT
          thpos,
          (
            SELECT
              words
            FROM
              dict
            WHERE
              digits = NULLIF(JSON_EXTRACT(thousands, '$[0]'), 0)
          ),
          (
            SELECT
              words
            FROM
              dict
            WHERE
              digits = NULLIF(JSON_EXTRACT(thousands, '$[1]'), 0)
          ),
          IIF(
            JSON_EXTRACT(thousands, '$[0]') + JSON_EXTRACT(thousands, '$[1]') > 0,
            (
              SELECT
                words
              FROM
                positions
              WHERE
                pos = thpos
            ),
            NULL
          )
        FROM
          decompositor
        WHERE
          thpos > 0
      ),
      -- Stage 5.3: Format each chunk with scale label and order descending by magnitude
      to_format (thpos, string) AS (
        SELECT
          thpos,
          TRIM(PRINTF('%s %s %s', hundred, dozen, pos_str))
        FROM
          to_strings
        ORDER BY
          thpos DESC
      )
    -- Stage 5.4: Final text assembly (concatenate non-empty chunks separated by single spaces)
    SELECT
      TRIM(GROUP_CONCAT(string, ' '))
    FROM
      to_format
  )
WHERE
  error IS NULL
  AND number > 0;
