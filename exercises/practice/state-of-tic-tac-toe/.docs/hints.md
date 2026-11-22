# Hints

## Approach Selection

When determining the state of a Tic-Tac-Toe board in SQLite, two primary architectural approaches emerge, each trading off algorithmic abstraction against query simplicity.

### 1. Direct Positional Extraction (Combinatorial CASE Expressions)

This approach leverages the fixed $3 \times 3$ grid dimensions and known string layout. The input board is stored as an 11-character multiline string with three 3-character rows separated by newline characters (`\n` / `CHAR(10)`).

- **Position Extraction via `SUBSTR()`**:
  - Row 1: `SUBSTR(board, 1, 1)`, `SUBSTR(board, 2, 1)`, `SUBSTR(board, 3, 1)`
  - Row 2: `SUBSTR(board, 5, 1)`, `SUBSTR(board, 6, 1)`, `SUBSTR(board, 7, 1)` (Index 4 is newline `\n`)
  - Row 3: `SUBSTR(board, 9, 1)`, `SUBSTR(board, 10, 1)`, `SUBSTR(board, 11, 1)` (Index 8 is newline `\n`)
- **Winning Line Reconstruction**:
  - 3 Rows: `SUBSTR(board, 1, 3)`, `SUBSTR(board, 5, 3)`, `SUBSTR(board, 9, 3)`
  - 3 Columns: `c11 || c21 || c31`, `c12 || c22 || c32`, `c13 || c23 || c33`
  - 2 Diagonals: `c11 || c22 || c33`, `c31 || c22 || c13`
- **Piece Counting via Length Differences**:
  - `count(X) = LENGTH(board) - LENGTH(REPLACE(board, 'X', ''))`
  - `count(O) = LENGTH(board) - LENGTH(REPLACE(board, 'O', ''))`
  - `count(empty) = LENGTH(board) - LENGTH(REPLACE(board, ' ', ''))`
- **Evaluation**:
  - Boolean flags `x_wins` and `o_wins` test whether any of the 8 lines equal `'XXX'` or `'OOO'`.
  - A single CTE coupled with `UPDATE ... FROM ... SET error = CASE ..., result = CASE ...` updates the target table in a single pass.

### 2. Recursive CTE Board Decomposition (Normalized Set Operations)

This approach treats the board as a relational matrix by breaking the multiline text into relational rows and columns.

- **Multiline Decomposition**:
  - A recursive CTE (`split_lines`) recursively extracts row substrings delimited by `CHAR(10)`.
  - A second recursive CTE (`split_letters`) decomposes each row into individual letter tokens.
  - SQLite JSON functions (`JSON_GROUP_ARRAY()`) bundle letters into row arrays, producing a nested 2D matrix (`[["X","O","O"], ...]`).
- **Dynamic Line Aggregation**:
  - Rows are unpacked via `JSON_EACH(matrix)`.
  - Columns are projected using `JSON_EXTRACT(j.value, '$[col]')` across grouped rows.
  - Diagonals are indexed via direct coordinate access (`$[0][0]`, `$[1][1]`, `$[2][2]`, etc.).
  - All 8 candidates are unified using `UNION` and filtered against `["X","X","X"]` and `["O","O","O"]`.
- **Evaluation**:
  - Multiple sequential `UPDATE` statements evaluate matrix characteristics using subqueries with `COUNT(*) FILTER (...)`.

---

## Architectural Trade-offs

| Criterion | Approach 1: Direct Positional Extraction | Approach 2: Recursive CTE Decomposition |
| :--- | :--- | :--- |
| **Readability** | High for $3 \times 3$. Direct coordinate indexing is immediately transparent without SQL recursion. | Moderate to High in relational abstraction, but high cognitive load due to nested CTEs and JSON queries. |
| **Performance** | **Optimal $O(1)$**: Operates purely on string offsets and length calculations. Zero temp tables, zero memory allocations. | **Heavier Overhead**: Incurs multiple recursive iterations, JSON serialization/deserialization, and temporary table allocations (`matrices`). |
| **Generalizability** | Low: Hardcoded to fixed $3 \times 3$ coordinate offsets. Does not generalize easily to $N \times N$. | High: Recursive string splitting naturally scales to arbitrary $N \times M$ grids. |
| **Query Complexity** | Single CTE and single `UPDATE ... FROM` statement. | Multi-stage script: temporary table creation, column alterations, and 6 separate `UPDATE` queries. |

---

## Validation of Illegal States

Tic-Tac-Toe rules mandate detecting invalid board states and returning exact error messages. Enforcing the correct order of precedence is essential:

1. **Turn Order Violations**:
   - `Wrong turn order: O started`:
     - Because X always plays first, the count of `O` pieces can never exceed `X`.
     - Condition: `count(O) > count(X)`.
   - `Wrong turn order: X went twice`:
     - Because players alternate turns, `X` can have at most one more piece than `O`.
     - Condition: `count(X) > count(O) + 1`.

2. **Post-Win Continuation Violations**:
   - `Impossible board: game should have ended after the game was won`:
     - **Simultaneous Wins**: If both `X` and `O` have winning lines (`x_wins > 0 AND o_wins > 0`), players continued placing marks after a victor had already been decided.
     - **X Won but Counts are Equal**: If X won, X made the final move. Therefore, `count(X)` must equal `count(O) + 1`. If `count(X) = count(O)`, O played an illegal turn after X already won.
     - **O Won but X Has More Pieces**: If O won, O made the final move. Therefore, `count(X)` must equal `count(O)`. If `count(X) > count(O)`, X played an illegal turn after O already won.

3. **Status Determination (when `error IS NULL`)**:
   - `win`: If `x_wins > 0 OR o_wins > 0`. Note that a single player may simultaneously complete two winning lines (e.g. intersecting row and column or two diagonals) with their final winning piece.
   - `draw`: If no player has won and zero empty cells remain (`count(empty) = 0`).
   - `ongoing`: If no player has won and one or more empty cells remain (`count(empty) > 0`).
