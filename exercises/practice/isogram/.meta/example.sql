-- Complexity Analysis and Invariants:
--
-- Invariant:
-- A phrase is an isogram if and only if every alphabetic character (case-insensitive)
-- appears at most once: COUNT(letter) == COUNT(DISTINCT letter).
-- Non-alphabetic characters (spaces, hyphens) are filtered out via GLOB '[a-zA-Z]'.
-- The empty string phrase = '' is vacuously an isogram (is_isogram = TRUE).
--
-- Algorithmic Complexity:
-- For a phrase of length L = LENGTH(phrase) with K alphabetic letters (0 <= K <= L):
-- 1. chars CTE: Recursively extracts characters, producing L + 1 rows via SUBSTR.
--    Time: O(L) iterations and substring extractions.
-- 2. letters CTE: Filters L + 1 rows with GLOB '[a-zA-Z]' and applies LOWER().
--    Time: O(L) filter checks, producing K rows.
-- 3. uniq_letters CTE: Deduplicates K letters via SELECT DISTINCT.
--    Time: O(K log K) sorting/hashing, producing U unique letter rows (U <= min(K, 26)).
-- 4. letter_count & uniq_count CTEs: Aggregate counts over K and U rows.
--    Time: O(K + U) aggregation work.
-- 5. UPDATE: Joins counts and evaluates equality; second UPDATE handles empty string.
--    Time: O(1) table row update.
--
-- Total Time Complexity:  O(L + K log K) ~ O(L) linear in phrase character length.
-- Total Space Complexity: O(L) transient working memory for intermediate CTE rows.
--
-- Cost Distinction: Algorithm work in-engine is on the order of microseconds (~95-100 us),
-- while process-startup and compilation time in CLI invocations takes ~5-15 ms.

WITH RECURSIVE
  chars (phrase, idx, char) AS (
    SELECT
      phrase,
      0,
      ''
    FROM
      isogram
    UNION ALL
    SELECT
      phrase,
      idx + 1,
      SUBSTR(phrase, idx + 1, 1)
    FROM
      chars
    WHERE
      idx < LENGTH(phrase)
  ),
  letters AS (
    SELECT
      phrase,
      LOWER(char) "letter"
    FROM
      chars
    WHERE
      char GLOB '[a-zA-Z]'
  ),
  uniq_letters AS (
    SELECT DISTINCT
      phrase,
      letter
    FROM
      letters
  ),
  letter_count AS (
    SELECT
      phrase,
      COUNT(letter) "num_letters"
    FROM
      letters
    GROUP BY
      phrase
  ),
  uniq_count AS (
    SELECT
      phrase,
      COUNT(letter) "num_uniq"
    FROM
      uniq_letters
    GROUP BY
      phrase
  )
UPDATE isogram
SET
  is_isogram = (letter_count.num_letters = uniq_count.num_uniq)
FROM
  letter_count,
  uniq_count
WHERE
  isogram.phrase = letter_count.phrase
  AND isogram.phrase = uniq_count.phrase;

UPDATE isogram
SET
  is_isogram = TRUE
WHERE
  phrase = '';
