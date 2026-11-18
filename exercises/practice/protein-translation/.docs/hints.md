# Hints

## SQLite

The reference uses a recursive common table expression with `UNION ALL` to consume the RNA strand three characters at a time. `UNION ALL` keeps every row; ordinary `UNION` removes duplicate rows. Keeping repeated codons matters: the test input `UUUUUU` contains two `UUU` codons and should produce `Phenylalanine, Phenylalanine`.

This small query shows the set-versus-duplicate-preserving difference without implementing the exercise:

```sql
SELECT GROUP_CONCAT(amino_acid, ', ')
FROM (
  SELECT 'Phenylalanine' AS amino_acid
  UNION ALL
  SELECT 'Phenylalanine'
);

SELECT GROUP_CONCAT(amino_acid, ', ')
FROM (
  SELECT 'Phenylalanine' AS amino_acid
  UNION
  SELECT 'Phenylalanine'
);
```

Expected output:

```text
Phenylalanine, Phenylalanine
Phenylalanine
```

The second query collapses equal rows before `GROUP_CONCAT`. In the reference's recursive CTE, each step also carries the remaining strand, so its state rows represent successive positions. Avoid applying `DISTINCT` to the translated amino acids: different codons can legitimately produce the same amino acid more than once.

The dictionary lookup in the reference is a scalar subquery. If a codon has no matching dictionary row, that expression evaluates to `NULL`; the reference detects this with `ISNULL` and reports `Invalid codon`. Its initial recursive row uses an empty string, which is not `NULL` and is not an amino acid.

The exercise expects amino acids in codon order. SQL does not guarantee row order without an explicit `ORDER BY`, and aggregate input order should not be inferred from incidental query execution. Keep sequence position available when ordering translated results.

See SQLite's [WITH clause documentation](https://www.sqlite.org/lang_with.html) for recursive CTEs and compound SELECT operators.
