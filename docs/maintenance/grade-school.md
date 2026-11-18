# grade-school exercise files

Run the focused path check from the repository root:

```sh
python3 tools/course_checks/r08-t058.py
```

The checker parses `exercises/practice/grade-school/.meta/config.json` and validates every path declared under `files`. The `solution` role points to the learner stub `exercises/practice/grade-school/grade-school.sql`; `test` points to `exercises/practice/grade-school/grade-school_test.sql`; and `example` points to the maintained reference `exercises/practice/grade-school/.meta/example.sql`. This exercise does not currently declare an `editor` role. If one is added, the checker applies the same existence and containment checks to it.

The config file tells the track tooling which learner, test and reference files belong to this exercise. It does not list every support file. The configured test script starts with `create_fixture.sql`, runs the learner solution, and then reads `./create_test_table.sql` with SQLite's `.read` command. That table is generated from `.meta/tests.toml` by the track's configlet sync process; edit the TOML source rather than hand-editing the generated SQL.

The reference is separate from the learner stub. The course check copies the complete exercise, including dotfiles, to a temporary directory, installs `.meta/example.sql` into the configured solution path in that copy, and runs the configured test script there. It asserts that `output.json` exists, contains a non-zero number of cases, and reports `pass` for every case. The checker does not write to the learner files.
