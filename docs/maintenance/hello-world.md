# Hello-World Maintenance & Contract Documentation

## Overview

- **Exercise**: `exercises/practice/hello-world`
- **Task ID**: `R08-T050`
- **Objective**: Clarify and document the subtle contract cases for `hello-world` in SQLite, establish a decision table separating specified requirements from unspecified behaviors, and maintain strict verification standards.

---

## 1. Canonical Case Specifications

The `hello-world` exercise contains a single canonical test case from Exercism problem-specifications:

- **UUID**: `af9ffe10-dc13-42d8-a742-e7bdafac449d`
- **Description**: `Say Hi!`
- **Expected String**: `Hello, World!`
- **Configuration**: Listed in `exercises/practice/hello-world/.meta/tests.toml`

---

## 2. SQLite Execution & Relational Contract

The exercise operates on a single relational table defined in `create_fixture.sql`:
```sql
CREATE TABLE hello_world (greeting TEXT);
```

The test runner sets up the test fixture, imports the student's `hello-world.sql`, and evaluates the result with:
```sql
UPDATE tests
SET status = 'pass'
FROM (
  SELECT greeting FROM hello_world
) AS actual
WHERE actual.greeting = tests.expected;
```

### Key SQLite Evaluation Properties:
1. **Case-Sensitive Binary Equality**:
   SQLite's default collation for `TEXT` is `BINARY`. String comparison `actual.greeting = tests.expected` evaluates character codes directly. Any variation in case (e.g., `'hello, world!'` or `'HELLO, WORLD!'`) fails the check.
2. **Whitespace and Punctuation**:
   Spaces, commas, and exclamation marks are strictly checked. Omission of comma or exclamation mark (`'Hello World'`) will fail.
3. **Empty or Missing Values**:
   If the student solution does not insert any row, or inserts `NULL` or empty text `''`, the test remains at status `'fail'`.

---

## 3. Decision Table

| Input Condition | Table Content (`greeting`) | Expected Value | SQLite Comparison | Test Status | Contract Category |
|---|---|---|---|---|---|
| Canonical Solution | `'Hello, World!'` | `'Hello, World!'` | `'Hello, World!' = 'Hello, World!'` -> TRUE | `pass` | Specified requirement |
| Stub Default | `'Goodbye, Mars!'` | `'Hello, World!'` | `'Goodbye, Mars!' = 'Hello, World!'` -> FALSE | `fail` | Expected failure (unsolved) |
| Lowercase | `'hello, world!'` | `'Hello, World!'` | Binary collation mismatch -> FALSE | `fail` | Strict case requirement |
| Missing Comma | `'Hello World!'` | `'Hello, World!'` | String inequality -> FALSE | `fail` | Punctuation requirement |
| Missing Exclamation | `'Hello, World'` | `'Hello, World!'` | String inequality -> FALSE | `fail` | Punctuation requirement |
| Whitespace Padding | `' Hello, World! '` | `'Hello, World!'` | String inequality -> FALSE | `fail` | Exact whitespace requirement |
| NULL Value | `NULL` | `'Hello, World!'` | `NULL = '...'` -> NULL (falsy) | `fail` | Non-null requirement |

---

## 4. Specified vs. Unspecified Behaviors

### Specified Contract
- The student must populate `hello_world.greeting` with `'Hello, World!'`.
- All canonical tests must pass against the reference implementation (`.meta/example.sql`).
- The student starter stub must remain unsolved (`'Goodbye, Mars!'`).

### Unspecified Contract
- **Row Ordering**: With a single required greeting row, row ordering is neither defined nor checked.
- **Multiple Rows**: Inserting duplicate or extra rows where at least one contains `'Hello, World!'` satisfies the `WHERE actual.greeting = tests.expected` condition, but the canonical specification only calls for a single greeting.
- **Type Coercion & Schema Alterations**: No type conversions or schema modifications are required or expected.

---

## 5. Verification Commands

```bash
# 1. Run task verification check
python3 work/R08-T050/check.py

# 2. Run reusable focused check
python3 tools/course_checks/r08-t050.py

# 3. Run Exercism track test runner
./bin/verify-exercises exercises/practice/hello-world

# 4. Run configlet linter
./bin/configlet lint
```
