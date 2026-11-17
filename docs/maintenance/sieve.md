# Sieve test-generation maintenance

The generated test table for Sieve is produced from three maintained inputs:

1. `exercises/practice/sieve/.meta/tests.toml` supplies the UUID and
   description for each included canonical case.
2. Exercism problem specifications supply the canonical inputs and expected
   values through `canonical-data.json`.
3. `exercises/practice/sieve/.meta/template.create_test_table.j2` renders the
   rows into `create_test_table.sql`.

The repository entry point is `bin/generate_tests`. With the
`problem-specifications` cache available, the reproducible command is:

```bash
python3 bin/generate_tests --no-pull sieve
```

The command writes `exercises/practice/sieve/create_test_table.sql` (and, for
this exercise, `data.csv`). It does not edit `sieve_test.sql`; that script reads
the generated table, runs the learner/reference SQL, and records the results.

## Current case map

| UUID | Description | Limit | Expected result |
| --- | --- | ---: | --- |
| `88529125-c4ce-43cc-bb36-1eb4ddd7b44f` | no primes under two | 1 | empty string |
| `4afe9474-c705-4477-9923-840e1024cc2b` | find first prime | 2 | `2` |
| `974945d8-8cd9-4f00-9463-7d813c7f17b7` | find primes up to 10 | 10 | `2, 3, 5, 7` |
| `2e2417b7-3f3a-452a-8594-b9af08af6d82` | limit is prime | 13 | `2, 3, 5, 7, 11, 13` |
| `92102a05-4c7c-47de-9ed0-b7d5fcd00f21` | find primes up to 1000 | 1000 | all primes from 2 through 997 |

The first row is intentionally retained: an upper bound below 2 has no prime
output. The last row is the larger regression case; it protects both the
ordering and the complete set of generated values.

## Focused verification

```bash
python3 work/R08-T002/check.py
```

The checker validates the config-resolved reference run, confirms all five
generated rows are present, exercises the broken-reference and zero-test
paths, and compares two fresh generation copies. If the external
problem-specifications cache is unavailable, it reports that fact and still
performs the deterministic maintained-file replay; it never silently drops a
case.
