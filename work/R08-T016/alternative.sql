-- Alternative Solution for state-of-tic-tac-toe
-- Approach 1: Direct Positional Extraction using SUBSTR() with combinatorial CASE expressions.

WITH parsed AS (
  SELECT
    board,
    -- Extract rows
    SUBSTR(board, 1, 3) AS r1,
    SUBSTR(board, 5, 3) AS r2,
    SUBSTR(board, 9, 3) AS r3,
    -- Extract columns (indices 4 and 8 are newline characters)
    SUBSTR(board, 1, 1) || SUBSTR(board, 5, 1) || SUBSTR(board, 9, 1) AS c1,
    SUBSTR(board, 2, 1) || SUBSTR(board, 6, 1) || SUBSTR(board, 10, 1) AS c2,
    SUBSTR(board, 3, 1) || SUBSTR(board, 7, 1) || SUBSTR(board, 11, 1) AS c3,
    -- Extract diagonals
    SUBSTR(board, 1, 1) || SUBSTR(board, 6, 1) || SUBSTR(board, 11, 1) AS d1,
    SUBSTR(board, 9, 1) || SUBSTR(board, 6, 1) || SUBSTR(board, 3, 1) AS d2,
    -- Count piece occurrences
    LENGTH(board) - LENGTH(REPLACE(board, 'X', '')) AS nx,
    LENGTH(board) - LENGTH(REPLACE(board, 'O', '')) AS no,
    LENGTH(board) - LENGTH(REPLACE(board, ' ', '')) AS n_empty
  FROM "state-of-tic-tac-toe"
),
evaluated AS (
  SELECT
    board,
    nx,
    no,
    n_empty,
    (r1 = 'XXX' OR r2 = 'XXX' OR r3 = 'XXX' OR c1 = 'XXX' OR c2 = 'XXX' OR c3 = 'XXX' OR d1 = 'XXX' OR d2 = 'XXX') AS x_wins,
    (r1 = 'OOO' OR r2 = 'OOO' OR r3 = 'OOO' OR c1 = 'OOO' OR c2 = 'OOO' OR c3 = 'OOO' OR d1 = 'OOO' OR d2 = 'OOO') AS o_wins
  FROM parsed
)
UPDATE "state-of-tic-tac-toe" AS t
SET
  error = CASE
    WHEN e.no > e.nx THEN 'Wrong turn order: O started'
    WHEN e.nx > e.no + 1 THEN 'Wrong turn order: X went twice'
    WHEN (e.x_wins AND e.o_wins) OR (e.x_wins AND e.nx = e.no) OR (e.o_wins AND e.nx > e.no)
      THEN 'Impossible board: game should have ended after the game was won'
    ELSE NULL
  END,
  result = CASE
    WHEN e.no > e.nx OR e.nx > e.no + 1 OR (e.x_wins AND e.o_wins) OR (e.x_wins AND e.nx = e.no) OR (e.o_wins AND e.nx > e.no)
      THEN NULL
    WHEN e.x_wins OR e.o_wins THEN 'win'
    WHEN e.n_empty = 0 THEN 'draw'
    ELSE 'ongoing'
  END
FROM evaluated AS e
WHERE t.board = e.board;
