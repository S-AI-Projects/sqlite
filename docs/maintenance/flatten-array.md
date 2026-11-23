# Flatten‑Array – Maintenance Documentation

## 1. Contract
The flatten‑array exercise requires that **null‑like values are omitted** from the flattened result. The maintained reference implementation enforces this with the predicate `AND j.value NOTNULL` in the `UPDATE` statement.

## 2. Maintained reference (`.meta/example.sql`)
```sql
UPDATE "flatten-array"
SET
  result = (
    SELECT
      JSON_GROUP_ARRAY(j.value)
    FROM
      JSON_TREE(JSON(array)) j
    WHERE
      j.type <> 'array'
      AND j.value NOTNULL
  );
```
*The `AND j.value NOTNULL` clause is the only place where null values are filtered out.*

## 3. Deliberate mutation
The mutation removes the `NOTNULL` filter:
```sql
UPDATE "flatten-array"
SET
  result = (
    SELECT
      JSON_GROUP_ARRAY(j.value)
    FROM
      JSON_TREE(JSON(array)) j
    WHERE
      j.type <> 'array'
  );
```
This change is **only applied inside a temporary copy** of the exercise during verification; the repository’s reference file remains untouched.

## 4. Expected failure
The canonical test that asserts null omission has the UUID:
```
0705a8e5-dc86-4cec-8909-150c5e54fa9c
```
**Minimal input that triggers the regression**
```json
[1,2,null]
```
- **Expected output** (with correct reference): `[1,2]`
- **Actual output** (with mutation): `[1,2,null]`
The test message produced by the mutated run is:
```
Result for "[1,2,null]" is <[1,2,null]> but should be <[1,2]>
```

## 5. Verification script (`work/R08-T033/check.py`)
The script:
1. Loads `exercises/practice/flatten-array/.meta/config.json` to resolve the solution, test and example file names.
2. Copies the entire exercise (including hidden files) into a temporary directory.
3. Runs the original reference (by copying `.meta/example.sql` over the learner stub) – all 11 tests must pass.
4. Mutates the copied reference: it verifies the exact occurrence of `AND j.value NOTNULL`, removes it, and writes the mutated SQL back.
5. Executes the mutated reference – the run must **fail** and the first failing entry must have the UUID above; otherwise the script exits with a non‑zero status.
6. Saves reproducible evidence in `work/R08-T033/`:
   - `original_output.json`
   - `mutated_output.json`
   - `mutated_example.sql`
   - `versions.txt` (Python and SQLite versions)

The script can be run independently with:
```
python3 work/R08-T033/check.py
```
It prints the number of executed tests and confirms the expected failure.

## 6. Reproducing the evidence manually
```bash
# 1. Original run (should pass all tests)
cp exercises/practice/flatten-array/.meta/example.sql exercises/practice/flatten-array/flatten-array.sql
sqlite3 -bail < exercises/practice/flatten-array/flatten-array_test.sql
# check that output.json contains only "status": "pass"

# 2. Mutated run (should fail the null‑omission test)
# Edit the example.sql and remove the NOTNULL clause (or apply the script mutation)
sed -i '' 's/AND j.value NOTNULL//g' exercises/practice/flatten-array/.meta/example.sql
cp exercises/practice/flatten-array/.meta/example.sql exercises/practice/flatten-array/flatten-array.sql
sqlite3 -bail < exercises/practice/flatten-array/flatten-array_test.sql
# The resulting output.json will show the failing UUID and message listed above.
```
These steps mirror exactly what `check.py` automates.
