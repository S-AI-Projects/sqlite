# Hints

## General

- The goal of this exercise is to write an `INSERT` statement into the existing `hello_world` table so that it contains the expected greeting.
- Inspect `create_fixture.sql` to review the table definition:
  ```sql
  CREATE TABLE hello_world (greeting TEXT);
  ```

## Case Walkthrough: "Say Hi!"

- **UUID**: `af9ffe10-dc13-42d8-a742-e7bdafac449d`
- **Description**: `Say Hi!`
- **Expected String**: `'Hello, World!'`
- **SQLite Representation**:
  - The greeting must be inserted as a string literal:
    ```sql
    INSERT INTO hello_world (greeting) VALUES ('Hello, World!');
    ```
- **Evaluation Mechanism**:
  - The test suite compares `actual.greeting` to `tests.expected` using strict equality (`=`):
    ```sql
    WHERE actual.greeting = tests.expected;
    ```
  - Because SQLite string comparison defaults to binary collation (case-sensitive), variants such as `'hello, world!'`, `'Hello World'`, or `'Hello, World'` (missing punctuation or whitespace differences) will fail.

## Decision Table

| Input Condition | Table State / Value | Expected Result | Evaluation Status | Contract Category |
|---|---|---|---|---|
| Target string provided | `'Hello, World!'` | `'Hello, World!'` | `pass` | Specified canonical contract |
| Incorrect case | `'hello, world!'` | `'Hello, World!'` | `fail` | Case-sensitive binary comparison |
| Missing punctuation | `'Hello World'` | `'Hello, World!'` | `fail` | Exact string match required |
| Stub default value | `'Goodbye, Mars!'` | `'Hello, World!'` | `fail` | Unsolved learner stub |
| NULL or empty | `NULL` / `''` | `'Hello, World!'` | `fail` | Non-matching value |

## Specified vs. Unspecified Contract Behavior

- **Specified Behavior**:
  - The table `hello_world` must contain the string `'Hello, World!'` in the `greeting` column.
  - The string must match character-by-character, including capitalization, comma, space, and exclamation point.
- **Unspecified Behavior**:
  - **Row Ordering**: Only a single row is expected, so ordering is neither specified nor tested.
  - **Multiple Rows**: Inserting multiple rows where at least one matches is not formally specified; solutions should insert exactly one row.
  - **Type Coercion / Error Handling**: No type coercion, error-throwing, or custom constraints are imposed by the track specification.
