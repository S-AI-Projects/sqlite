# Hints

## 1. Start with one cell

A saddle point must satisfy two conditions at once: it is as large as every
other value in its row, and as small as every other value in its column.
Keep every matching cell; ties can produce multiple saddle points.

## 2. Work through a small matrix

In the instructions' matrix, row 2 is `[5, 3, 2, 4]`. Its largest value is 5,
at column 1. Column 1 is `[9, 5, 6]`, whose smallest value is also 5. So the
matrix has a saddle point at row 2, column 1.

## 3. Keep track of coordinates

As you read the nested JSON arrays, keep the row and column indexes alongside
each value. JSON array indexes start at zero, while the exercise's returned
coordinates start at one; convert them when you build the result.

## 4. Two ways to find candidates

One approach finds each row's maximum and each column's minimum separately,
then keeps the cells that appear in both groups. This makes the two
comparisons explicit, but requires joining the candidate groups back to the
cells. A JSON path can encode the coordinates, though extracting indexes from
that path takes care.

Another approach checks each cell directly: look for any larger value in its
row and any smaller value in its column. If neither exists, the cell qualifies.
This follows the definition closely and can stop a search when a counterexample
is found, but may scan rows and columns repeatedly.

An empty matrix has no candidate cells, so its result should be an empty array.
