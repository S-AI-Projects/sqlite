# Hints

## General

- The goal is to update the `yacht` table and calculate the `result` score based on the `dice_results` and `category` columns.
- The `dice_results` column contains 5 comma-separated die numbers as text (e.g., `'1, 3, 3, 2, 5'`).
- SQLite string functions like `REPLACE()`, `LENGTH()`, and mathematical expressions can be used to count occurrences of each die face (1 through 6).

## Common Pitfalls & Debugging

### Full House Requirements
- **Exact Counts**: A Full House requires **exactly three of one die face and exactly two of another die face** (e.g., three 4s and two 2s).
- **Yacht is NOT a Full House**: Five-of-a-kind (a Yacht, such as `2, 2, 2, 2, 2`) cannot be scored as a Full House and must score `0`. Avoid logic that treats having at least 3 of a kind and at least 2 of a kind without verifying that the two die values are distinct.
- **Two Pair & Four of a Kind**: Neither two pair (`2, 2, 4, 4, 5`) nor four-of-a-kind (`1, 4, 4, 4, 4`) constitutes a Full House. Ensure your query checks both the maximum count (which must be exactly 3) and that the secondary count is exactly 2.

### Four of a Kind vs. Yacht
- A roll with 5 matching dice **can** be scored as Four of a Kind (for example, `3, 3, 3, 3, 3` scored in category `four of a kind` yields `12`, which is `4 * 3`). The score is the sum of the four matching dice, **not** all five.
- Full House rolls (such as `3, 3, 3, 5, 5`) do not satisfy Four of a Kind and must score `0`.

### Straights (Little Straight & Big Straight)
- **Little Straight**: Requires exactly `1, 2, 3, 4, 5` (all unique, with 6 absent) and scores `30`. Any duplicate die or the presence of a 6 results in `0`.
- **Big Straight**: Requires exactly `2, 3, 4, 5, 6` (all unique, with 1 absent) and scores `30`. Any duplicate die or the presence of a 1 results in `0`.
- Be cautious of rolls that have minimum 1 and maximum 5 or no pairs, but are missing an intermediate number (e.g., `1, 2, 3, 4, 6` or `1, 1, 3, 4, 5`).

### Yacht Category
- All five dice must be identical to score `50` points. If any die differs, the score is `0`.

### Number Categories (Ones through Sixes)
- Scores are calculated by summing only the dice matching the specified category (e.g., `fours` sums only dice showing 4). Unmatched dice do not contribute to the score.
