# Contributing

If you have not contributed previously to one of the Exercism tracks, we strongly recommend discussing any changes on [the forum][forum] _before_ creating any PR.

## Formatting

All `.sql` files in this repo should be formatted using [the `sql-formatter` tool][sql-formatter].
This provides a single, consistent way to format SQL.

The `sql-formatter` does not properly handle [SQLite dot commands][dot-commands].
The following `bash` script can be used to wrap `sql-formatter` without breaking on dot commands by temporarily turning them into comments.

```bash
#!/bin/env bash
sed -i 's/^\./--T./' "$@"
sql-formatter --fix -l sqlite "$@"
sed -i 's/^--T\././' "$@"
```

## Test Maintenance and Canonical Test Synchronization

Exercises in this repository are maintained and synchronized against Exercism's canonical problem specifications (`problem-specifications`).

### 1. Synchronizing Canonical Test Cases (`configlet sync`)

To synchronize an exercise's `.meta/tests.toml` against upstream canonical data:

```bash
./bin/fetch-configlet
./bin/configlet sync --tests --exercise <slug>
```

When regenerating `.meta/tests.toml`, `configlet sync`:
- **Recreates every `description` key/value pair** from canonical data in `problem-specifications/exercises/<slug>/canonical-data.json`.
- **Recreates every `reimplements` key/value pair**, where they exist in `problem-specifications` (identifies superseded canonical tests). If no tests are reimplemented for an exercise (such as `grains`), no `reimplements` keys are created.
- **Preserves any other key/value pair** present in `.meta/tests.toml` (e.g., track-specific exclusions like `include = false` and explanatory `comment = "..."` annotations).

### 2. Test Generation (`bin/generate_tests`)

To generate exercise test fixtures from templates:

```bash
./bin/generate_tests <slug>
# Or without pulling updates to the local problem-specifications cache:
./bin/generate_tests --no-pull <slug>
```

### 3. Generated vs. Manually Maintained Files

The repository distinguishes between generated assets and manually maintained files:

- **Generated files**:
  - `.meta/tests.toml`: Synchronized via `bin/configlet sync --tests --exercise <slug>`.
  - `data.csv`: Generated from `.meta/template.data.j2` by `bin/generate_tests <slug>`.
  - `create_test_table.sql`: Generated from `.meta/template.create_test_table.j2` by `bin/generate_tests <slug>` (for exercises utilizing separate test table templates).
- **Manually maintained files**:
  - `<slug>_test.sql` (e.g., `exercises/practice/grains/grains_test.sql`): In exercises where test table creation, test inputs, and runner hooks are consolidated, `<slug>_test.sql` is maintained manually without a per-exercise Jinja template.
  - `test_setup.sql`, `test_reporter.sql`, `create_fixture.sql`: Shared test harness components maintained manually.
  - `<slug>.sql`: Student starter stub, maintained manually.
  - `.meta/example.sql`: Track reference solution, maintained manually.
  - `.meta/config.json`: Exercise metadata configuration.

## Creating a new exercise

(These instructions may become the seed of a exercise-generate script.)

The steps below walk you through creating a new "bob" exercise.
They provide most the steps needed to create a new practice exercise.

1. create the directory structure:

    ```sh
    bin/fetch-configlet
    slug=bob
    bin/configlet create --practice-exercise "$slug"
    ```

1. create the data.csv file from canonical data

    ```sh
    cd "exercises/practice/$slug"
    cp "${XDG_CACHE_DIR:-$HOME/.cache}/exercism/configlet/problem-specifications/exercises/$slug/canonical-data.json" .

    # This needs to be custom crafted per exercise.
    # for exaple, for "bob"
    jq -r '.cases[] | [.input.heyBob, ""] | @csv' canonical-data.json > data.csv

    # and for "high-scores", the canonical data has nested cases
    jq -r '
      ( .cases
        | map(select(has("uuid")))
        + map(select(has("cases")) | .cases)[]
      )[]
      | .uuid as $u
      | .input.scores[]
      | [$u, .]
      | @csv
    ' canonical-data.json > data.csv
    ```

1. create the `create_test_table.sql` from canonical data

    ```sh
    #!/usr/bin/env bash
    {
    cat << '--END-SQL--'
    DROP TABLE IF EXISTS tests;
    CREATE TABLE IF NOT EXISTS tests (
        -- uuid and description are taken from the test.toml file
        uuid TEXT PRIMARY KEY,
        description TEXT NOT NULL,
        -- The following section is needed by the online test-runner
        status TEXT DEFAULT 'fail',
        message TEXT,
        output TEXT,
        test_code TEXT,
        task_id INTEGER DEFAULT NULL,
        -- Here are columns for the actual tests
        property TEST NOT NULL,
        input INT NOT NULL,
        expected TEXT NOT NULL
    );

    -- Note: the strings below _may_ contain literal tab, newline, or carriage returns.

    INSERT INTO tests (uuid, description, property, input, expected)
        VALUES
    --END-SQL--

    # The following may need to be custom crafted per exercise (this is high-scores)
    jq -r --arg q "'" '
        ( .cases
          | map(select(has("uuid")))
          + map(select(has("cases")) | .cases)[]
        )[]
        | [
            .uuid,
            .description,
            .property,
            (.input.scores | join(",")),
            (.expected | if type == "array" then join(",") else . end)
        ]
        | @csv
        | gsub($q; $q+$q)
        | gsub("\""; $q)
        | "        (" + . + "),"
    ' canonical-data.json | sed -E '$s/,$/;/'
    } > create_test_table.sql
    ```

1. create the `create_fixture.sql` file
1. create the `${slug}_test.sql` file based on the test script from another exercise.
1. create `.meta/example.sql`
1. set the stub file.
1. test it.

[forum]: https://forum.exercism.org/c/programming/sqlite/430
[sql-formatter]: https://github.com/sql-formatter-org/sql-formatter
[dot-commands]: https://www.sqlite.org/cli.html#special_commands_to_sqlite3_dot_commands_
