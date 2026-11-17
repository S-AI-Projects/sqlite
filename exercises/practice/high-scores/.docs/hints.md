# Hints

For `personalTopThree`, “highest” is part of the contract, not just a limit
on the number of rows. Keep the scores in descending numeric order before
aggregating the first three values. A small diagnostic input is `20,10,30`:
the required result is `30,20,10`. An ascending sort produces `10,20,30`, so a
test that checks both membership and order can distinguish the mistake.

The reference also uses `rowid` to preserve insertion order for the `scores`
property and to identify the latest score. Those are separate contracts; do
not replace either with an arbitrary sort.
