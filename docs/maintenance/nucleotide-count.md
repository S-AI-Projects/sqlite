# Nucleotide Count test mapping

The `.meta/example.sql` file configured in the exercise's `.meta/config.json` is
the maintained reference implementation. The checker in
[`work/R08-T021/check.py`](../../work/R08-T021/check.py) copies the exercise to a
temporary directory and uses that example there; the learner's solution is not
replaced.

| UUID | Canonical test description | Metadata | Behavior covered | Inclusion or exclusion rationale |
| --- | --- | --- | --- | --- |
| `3e5c30a8-87e2-4845-a815-a49671ade970` | empty strand | Included | Counts all four nucleotides as zero for an empty DNA string. | Included because the exercise requires counts for every valid string, including the empty string. |
| `a0ea42a6-06d9-4ac6-828c-7ccaccf98fec` | can count one nucleotide in single-character input | Included | Counts one `G` and zero `A`, `C`, and `T`. | Included because it checks a smallest non-empty valid input and the per-nucleotide result. |
| `eca0d565-ed8c-43e7-9033-6cefbf5115b5` | strand with repeated nucleotide | Included | Counts seven repeated `G` nucleotides. | Included because it verifies repeated occurrences contribute to the count. |
| `40a45eac-c83f-4740-901a-20b22d15a39f` | strand with multiple nucleotides | Included | Counts each nucleotide in a longer mixed DNA string. | Included because it checks all four counts together on representative input. |
| `b4c47851-ee9e-4b0a-be70-a86e343bd851` | strand with invalid nucleotides | Excluded (`include = false`) | The canonical case expects an error for `AGXXACT`. Separately, the SQL harness attempts to insert that input: it marks the test failed if an `AFTER INSERT` trigger runs, while the example's `CHECK` constraint rejects characters outside `A`, `C`, `G`, and `T`. | Keep excluded from canonical metadata-driven tests because this SQL exercise enforces invalid input as a rejected row insertion, rather than producing a result row. The local SQL harness independently checks that database constraint. The metadata exclusion and local SQL-level test cover different interfaces and are not contradictory. |

`nucleotide-count_test.sql` includes all five rows, regardless of the canonical
metadata exclusion. In `test_reporter.sql`, expected-error rows are initially
marked as passing; the subsequent `INSERT OR IGNORE` is rejected by the
reference example's `CHECK` constraint. If invalid input were accepted, the
`AFTER INSERT` trigger would instead change that row to `fail`. This is a
database constraint test, not evidence that the canonical `include = false`
setting should be removed.
