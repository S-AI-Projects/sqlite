# High-scores mutation check

The reference sorts the temporary `personalTopThree` rows by `score DESC`
before taking the first three rows. This is the deliberate mutant used by the
course check:

```diff
- ORDER BY scores.game_id ASC, score DESC;
+ ORDER BY scores.game_id ASC, score ASC;
```

The existing canonical case `1084ecb5-3eb4-46fe-a816-e40331a4e83a`,
“Personal top highest to lowest”, supplies scores `20,10,30` and expects
`30,20,10`. The original reference passes it; the mutant returns `10,20,30`
and is rejected. This is a contract failure in ordering, not a formatting-only
change. The same check also exercises ties, fewer-than-three scores, and the
independent `scores`, `latest`, and `personalBest` properties.

Run the isolated verification from the repository root:

```bash
python3 work/R08-T003/check.py
```
