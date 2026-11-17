# Sieve generation evidence

The focused run used the public Exercism problem-specifications repository in a
fresh cache and executed:

```bash
XDG_CACHE_HOME=/tmp/exercism-spec-cache python3 bin/generate_tests --no-pull sieve
```

Two fresh repository copies produced byte-identical
`exercises/practice/sieve/create_test_table.sql` files. The generated file also
matched the committed repository version, and all five generated UUIDs were
present in the isolated SQLite run.
