-- Anagram Invariant:
-- A candidate word is an anagram of the subject word if and only if:
-- 1. Matching letter signatures: both words have identical sorted ASCII letters when case-normalized (subject_sorted = candidate_sorted).
-- 2. Non-identical words: a word is not an anagram of itself (LOWER(subject) <> LOWER(candidate)).

DROP TABLE IF EXISTS word_signatures;

-- Build a temporary dictionary of all distinct lowercase words from subjects and candidate lists.
CREATE TEMPORARY TABLE word_signatures AS
SELECT
  CAST(word AS TEXT) AS word
FROM
  (
    SELECT
      LOWER(subject) AS word
    FROM
      anagram
    UNION
    SELECT
      LOWER(j.VALUE)
    FROM
      anagram,
      JSON_EACH(candidates) AS j
  );

ALTER TABLE word_signatures
ADD sorted_letters TEXT;

-- Compute the sorted letter signature for each distinct word:
-- Splits the word character-by-character via recursive CTE, sorts ASCII letters, and concatenates them.
UPDATE word_signatures
SET
  sorted_letters = (
    WITH RECURSIVE
      split_characters (remainder, char) AS (
        VALUES
          (word, '')
        UNION ALL
        SELECT
          SUBSTR(remainder, 2),
          SUBSTR(remainder, 1, 1)
        FROM
          split_characters
        WHERE
          LENGTH(remainder) > 0
      )
    SELECT
      GROUP_CONCAT(char, '')
    FROM
      (
        SELECT
          char
        FROM
          split_characters
        WHERE
          UNICODE(char) BETWEEN UNICODE('a') AND UNICODE('z')
        ORDER BY
          char
      )
  );

-- For each row in anagram, evaluate each candidate against the subject using their precomputed signatures.
UPDATE anagram
SET
  result = (
    SELECT
      JSON_GROUP_ARRAY(candidate)
    FROM
      (
        SELECT
          subject,
          candidate,
          (
            SELECT
              sorted_letters
            FROM
              word_signatures
            WHERE
              LOWER(subject) = word
          ) AS subject_sorted,
          (
            SELECT
              sorted_letters
            FROM
              word_signatures
            WHERE
              LOWER(candidate) = word
          ) AS candidate_sorted
        FROM
          (
            SELECT
              subject,
              j.VALUE AS candidate
            FROM
              JSON_EACH(candidates) AS j
          )
      )
    WHERE
      subject_sorted = candidate_sorted
      AND LOWER(subject) <> LOWER(candidate)
  );
