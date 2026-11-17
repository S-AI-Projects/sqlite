# Luhn exercise file map

The path declarations in `exercises/practice/luhn/.meta/config.json` are
relative to the exercise directory and are resolved by the track tooling as
follows:

| Role | Config path | Maintained file | Purpose |
| --- | --- | --- | --- |
| solution | `luhn.sql` | `exercises/practice/luhn/luhn.sql` | Unsolved learner starter file. |
| test | `luhn_test.sql` | `exercises/practice/luhn/luhn_test.sql` | Loads the fixture, inserts canonical cases, and reports status. |
| example | `.meta/example.sql` | `exercises/practice/luhn/.meta/example.sql` | Maintained reference used for verification; it is not copied into the learner file in the working tree. |
| editor | `data.csv` | `exercises/practice/luhn/data.csv` | Editor data exposed to the exercise runner. |

The test entry point is therefore:

```bash
cd exercises/practice/luhn
sqlite3 -bail < luhn_test.sql
```

For a reference check without touching `luhn.sql`, run:

```bash
python3 work/R08-T008/check.py
```

The checker parses the `files` object instead of guessing filenames, rejects
missing or escaping paths, copies the full exercise including dotfiles to a
temporary directory, and substitutes the reference only in that copy.
