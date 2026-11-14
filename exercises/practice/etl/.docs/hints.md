# Hints

## 1. Understand the input

Each JSON property is a score, and its value is a list of letters with that
score. The output needs to reverse this arrangement: each letter becomes a
property whose value is its score.

## 2. Work with the nested JSON

SQLite's JSON table-valued functions can walk through the input and expose its
leaf values. For each letter, keep track of the score from the property that
contains it. The score starts as text in a JSON path, so make sure the output
value is numeric.

## 3. Normalize the letters

The output uses lowercase letters even though the input uses uppercase ones.
Convert each letter as you build the letter-to-score rows, before creating the
result object.

## 4. Check the ordering

The result object's keys must be alphabetical. Sort the rows by the letter
before aggregating them into the JSON object. Try a short input first and
inspect the resulting JSON to check both the key order and value types.
