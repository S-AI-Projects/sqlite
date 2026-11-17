# Hints

The reference stores the eight bit values in a table and uses a bitwise
containment test: `(score & code) = code`. A different way to organize the
same contract is an inline `codes(item, code)` CTE used by one update. For a
score of `34`, the rows for peanuts (`2`) and chocolate (`32`) are selected, so
the list is `peanuts, chocolate`; a score of `257` still selects only eggs
because the unknown `256` bit has no row in `codes`.

The CTE keeps the mapping local to the statement and makes the worked example
easy to see, but it repeats the mapping whenever the statement is prepared and
can be less convenient to inspect than a named table. Whichever representation
you choose, preserve the item order and ignore bits that are outside the eight
specified allergens.
