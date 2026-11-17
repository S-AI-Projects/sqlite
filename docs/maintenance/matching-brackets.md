# Matching-brackets isolated runner

The maintained reference is
`exercises/practice/matching-brackets/.meta/example.sql`; the learner stub is
`matching-brackets.sql`, and the canonical runner is
`matching-brackets_test.sql`. The course check resolves these roles from
`.meta/config.json`, copies the complete exercise including dotfiles to a
temporary directory, substitutes the reference only in that copy, and runs:

```bash
sqlite3 -bail < matching-brackets_test.sql
```

The check requires a non-empty JSON report and a `pass` status for every case.
It also proves that a deliberately failing or syntactically invalid reference
is reported as failure, that a zero-test report is rejected, and that the
learner file hash is unchanged before and after every run. Temporary copies
are owned by `TemporaryDirectory` and are removed when each run ends.

Run it from the repository root:

```bash
python3 work/R08-T009/check.py
```
