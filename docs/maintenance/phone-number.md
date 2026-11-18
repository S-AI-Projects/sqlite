# phone-number isolated check

Run the reference check from the repository root:

```sh
python3 tools/course_checks/r08-t059.py
```

The runner reads the solution, test and reference paths from `exercises/practice/phone-number/.meta/config.json`. It copies the whole exercise, including dotfiles, to a temporary directory, writes `.meta/example.sql` into the configured solution path in that copy, and feeds the configured test SQL to `sqlite3 -bail` with the copy as its working directory. It then requires a non-empty `output.json`, at least one executed case, and `pass` for every status. SQLite errors, failed cases, missing results, empty selections and timeouts produce a non-zero exit.

Only the temporary copy is changed. The runner hashes every configured learner solution before and after execution and fails if a hash differs. Python removes the temporary directory on successful runs, failed assertions and child-process timeouts. The optional `--solution-sql` and `--test-sql` overrides are intended for checking failure behavior; they are also applied only inside the temporary copy.

Requirements: Python 3, SQLite CLI with JSON output support, and the `jq` utility used by the course check evidence script.
