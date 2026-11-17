# Proverb Reference Scaling Analysis

## 1. Purpose

This document explains the computational cost and scaling characteristics of the reference solution in `exercises/practice/proverb/.meta/example.sql` for the `proverb` exercise in the SQLite track. It documents empirical measurements, algorithmic cost models, attribution probes, and baseline comparisons across varying input sizes and item lengths, verified by `work/R08-T055/check.py`.

## 2. Specification

Based on `exercises/practice/proverb/.docs/instructions.md` and `exercises/practice/proverb/.docs/instructions.append.md`:

- **Input**: A list of inputs provided as a JSON array of strings.
- **Output format**: Lines of text separated by single line feeds (`\n`).
  - **0 items**: Produces an empty string `""` (no lines).
  - **1 item (`[w1]`)**: Produces only the final rhyme line: `And all for the want of a w1.`
  - **2 items (`[w1, w2]`)**: Produces 2 lines:
    ```text
    For want of a w1 the w2 was lost.
    And all for the want of a w1.
    ```
  - **Many items (`[w1, w2, ..., wn]`)**: Produces exactly `n` lines. For each consecutive pair `(wi, wi+1)` where `i` ranges from 1 to `n - 1`: `For want of a <wi> the <wi+1> was lost.`
  - **The last line**: For any non-empty list, the final line always references the first element of the list: `And all for the want of a <w1>.`
- **Domain unboundedness**:
  - The specification explicitly notes: *"the list of inputs may vary; your solution should be able to handle lists of arbitrary length and content."*
  - The specification does not bound the list length `n` or the item length `L`.
  - The specification does not require items to be distinct.
  - The input domain is unbounded.

## 3. Input Size and Derived Operation Counts

Input size is defined along two orthogonal dimensions:
- `n`: The number of items in the list.
- `L`: The average item length in characters.

Because the input domain is unbounded, a measured size sweep across primary sizes `[100, 1000, 10000]` is evaluated rather than a fixed-size operation table.

The following table summarizes derived operation counts based on the SQL structure of the reference query across the three primary sizes (labelled as derived structural counts, not measured CPU operations):

| operation | derivation formula | n = 100 | n = 1000 | n = 10000 |
| --- | --- | --- | --- | --- |
| recursive CTE rows | `n - 1` | 99 | 999 | 9999 |
| `JSON_EXTRACT` calls in recursion | `2 * (n - 1)` | 198 | 1998 | 19998 |
| `JSON_EXTRACT` calls for final line | `1` | 1 | 1 | 1 |
| output lines formatted and concatenated | `n` | 100 | 1000 | 10000 |

## 4. The Reference Implementation

The reference solution in `exercises/practice/proverb/.meta/example.sql` comprises two `UPDATE` statements:

1. **Zero-length handling**:
   An initial `UPDATE` statement handles empty arrays:
   ```sql
   UPDATE proverb
   SET result = ''
   WHERE JSON(strings) = '[]';
   ```
   This canonicalizes the input using the `JSON` scalar function and assigns `result = ''` if the list is empty.

2. **Recursive generation and aggregation**:
   A second `UPDATE` statement executes a correlated scalar subquery for non-empty lists (`WHERE result ISNULL`):
   - Computes the index of the last item (n - 1) using `JSON_ARRAY_LENGTH(strings) - 1`.
   - Generates intermediate rhymes using a recursive common table expression (`WITH RECURSIVE to_pieces`).
   - In each recursive step, formats the next rhyme line using `PRINTF('For want of a %s the %s was lost.', ...)` with two dynamic `JSON_EXTRACT` calls: `JSON_EXTRACT(strings, PRINTF('$[%d]', i))` and `JSON_EXTRACT(strings, PRINTF('$[%d]', i + 1))`.
   - Appends the closing line using `UNION ALL SELECT PRINTF('And all for the want of a %s.', JSON_EXTRACT(strings, '$[0]'))`.
   - Aggregates all pieces into a single newline-separated text block via `group_concat(piece, CHAR(10))`.

## 5. Measurement Protocol

All measurements adhere to the following protocol:
- **Environment**: Measured on macOS Darwin arm64 with SQLite.
- **Isolation**: Executed in temporary, isolated directories copying the entire exercise workspace.
- **Repetitions**: 1 discarded warm-up run followed by 5 timed repetitions per size, holding input data and environment constant.
- **Metrics reported**:
  - Whole-process wall clock (measured around the `sqlite3` child process with `time.perf_counter`).
  - Net wall clock (whole-process wall clock minus the median driver-on-1-item startup baseline; reported only when above the noise floor).
  - SQLite statement execution time (captured via `.timer on` and reported as statement-2 median).
  - SQLite Virtual Machine instruction steps (captured via `.stats vmstep`).
- **Correctness assertion**: Independent Python expectation function `expected_proverb` verifies exact string equality before any timing runs. Timings are recorded for characterization and are never asserted as pass/fail.

## 6. Measurement Results

<!-- BEGIN GENERATED: results -->
The startup baselines measured over 5 repetitions are:
- Bare SQLite process (`sqlite3 :memory: "SELECT 1;"`): **2.896 ms**
- Harness driver on a 1-item list: **3.141 ms** (noise floor: **0.462 ms**)

The measured scaling metrics across all evaluated sizes are:

| n | L | wall median (s) | net wall | statement-2 median (s) | statement-2 VM steps |
| --- | --- | --- | --- | --- | --- |
| 1 | short (2-6 chars) | 0.003193 | below noise | 0.000035 | 81 |
| 10 | short (2-6 chars) | 0.002832 | below noise | 0.000041 | 459 |
| 100 | short (2-6 chars) | 0.003188 | below noise | 0.000105 | 4239 |
| 1000 | short (2-6 chars) | 0.006310 | 0.003169 s | 0.003090 | 42039 |
| 10000 | short (2-6 chars) | 0.257008 | 0.253867 s | 0.250704 | 420039 |
| 10 | 50 | 0.002928 | below noise | 0.000040 | 459 |
| 100 | 50 | 0.003122 | below noise | 0.000165 | 4239 |
| 1000 | 50 | 0.014561 | 0.011420 s | 0.010480 | 42039 |
<!-- END GENERATED: results -->

## 7. Cost Statement and Growth

### Three Views of Cost

1. **Process Startup**:
   Process startup and fixture initialization impose a constant baseline overhead. For small inputs (`n <= 100`), this fixed overhead dominates whole-process wall time, placing net wall times within the driver noise floor (see the results table above).
2. **Virtual Machine Steps**:
   The SQLite bytecode instruction count is strictly linear: 42 per item at every measured size (42n + 39 for n = 1, 10, 100, 1000, 10000, short and 50-character items alike). Furthermore, VM step counts are completely independent of item length `L` (see the results table above).
3. **Statement Execution Time**:
   In contrast to the strictly linear VM-step count, statement execution time grows faster than the VM-step count, exhibiting super-linear growth as reflected in the local growth exponents (see the growth block below):

<!-- BEGIN GENERATED: growth -->
The scaling ratios and local growth exponents between evaluated sizes are:

| comparison | statement-2 ratio | local exponent (alpha) | net wall ratio |
| --- | --- | --- | --- |
| short: 100 -> 1000 | 29.4x | 1.47 | n/a (below noise) |
| short: 1000 -> 10000 | 81.1x | 1.91 | 80.1x |
| L=50: 100 -> 1000 | 63.5x | 1.80 | n/a (below noise) |
| L=50 vs short at n=1000 | 3.39x | n/a (same n) | 3.60x |

The tables report Statement 2 (the recursive UPDATE); Statement 1 (the empty-list check) executes in a constant 13 VM steps. The SQL text is identical for every size, so statement preparation cost does not depend on n, and the statement-2 time at n=1 (0.000035 s) is an upper bound for preparation plus execution at the smallest size.
<!-- END GENERATED: growth -->

## 8. Diagnostic Attribution Probes

To investigate the root cause of this super-linear growth, two diagnostic probes were evaluated:

<!-- BEGIN GENERATED: probes -->
The attribution probe measurements across sizes and item lengths are:

| probe | n | L | statement-2 median (s) | VM steps | output equals expected |
| --- | --- | --- | --- | --- | --- |
| P0 | 1000 | short (2-6 chars) | 0.003125 | 42039 | true |
| P0 | 10000 | short (2-6 chars) | 0.277141 | 420039 | true |
| P0 | 1000 | 50 | 0.011794 | 42039 | true |
| P1 | 1000 | short (2-6 chars) | 0.000668 | 34048 | false |
| P1 | 10000 | short (2-6 chars) | 0.097151 | 340048 | false |
| P1 | 1000 | 50 | 0.006560 | 34048 | false |
| P2 | 1000 | short (2-6 chars) | 0.002914 | 40039 | true |
| P2 | 10000 | short (2-6 chars) | 0.185762 | 400039 | true |
| P2 | 1000 | 50 | 0.005469 | 40039 | true |

Probe descriptions:
- **P0**: Unmodified reference implementation. Output equals expected: true.
- **P1**: both JSON_EXTRACT calls in the recursive step AND the PRINTF calls that build their paths are replaced by constants; the recursion still runs n-1 times and still carries `strings`. Output equals expected: false (substitutes constants).
- **P2**: the recursive rows no longer carry `strings`; the text is read from the base table inside the recursion. Output equals expected: true.

Probes are diagnostic cost probes, not alternative solutions.
<!-- END GENERATED: probes -->

## 9. Additivity and Hypotheses

<!-- BEGIN GENERATED: additivity -->
The additive contribution of the two diagnostic probes across conditions:

| condition | P0 statement-2 (s) | extract saving (P0 - P1) | payload saving (P0 - P2) | total savings (s) | share of P0 |
| --- | --- | --- | --- | --- | --- |
| n=1000 (short) | 0.003125 | 0.002457 s (79%) | 0.000211 s (7%) | 0.002668 s | 85% |
| n=10000 (short) | 0.277141 | 0.179990 s (65%) | 0.091379 s (33%) | 0.271369 s | 98% |
| n=1000 (L=50) | 0.011794 | 0.005234 s (44%) | 0.006325 s (54%) | 0.011559 s | 98% |

Additivity evaluation:
- At n=1000 (short): the two savings add up to 85% of the unmodified statement time (extract saving: 79%, payload saving: 7%).
- At n=10000 (short): the two savings add up to 98% of the unmodified statement time (extract saving: 65%, payload saving: 33%).
- At n=1000 (L=50): the two savings add up to 98% of the unmodified statement time (extract saving: 44%, payload saving: 54%).

Session variation for the unmodified reference (P0):

| condition | sweep median (s) | probe-set P0 median (s) | difference |
| --- | --- | --- | --- |
| n=1000 (short) | 0.003090 | 0.003125 | +1.1% |
| n=10000 (short) | 0.250704 | 0.277141 | +10.5% |
| n=1000 (L=50) | 0.010480 | 0.011794 | +12.5% |

The unmodified statement was measured twice in this run (main sweep and probe set); the medians differ by 1.1%, 10.5%, and 12.5% (largest 12.5%), so the shares above are accurate only to about that margin and must not be read to the nearest percent.
<!-- END GENERATED: additivity -->

The probes are consistent with both mechanisms contributing (see the additivity evaluation above), without claiming a proven mechanism:
- **Hypothesis 1 (Index lookups into the JSON text)**: In SQLite, index-based `JSON_EXTRACT(strings, '$[i]')` on a `TEXT` column scans from the start of the JSON array on each invocation. Summed over `n` iterations, this generates `O(n^2 * L)` character scans in C code.
- **Hypothesis 2 (Copying the strings text into every recursive row)**: In the unmodified reference, each recursive row carries the `strings` column. For larger payloads, ephemeral row materialization allocates and copies string buffers across recursive steps.

## 10. What This Page Does Not Claim

- **No speedup claimed**: No modification or optimization of the reference solution is proposed or claimed.
- **Reference unchanged**: `exercises/practice/proverb/.meta/example.sql` remains completely untouched.
- **Environment specificity**: Timings and execution durations are specific to this machine architecture and SQLite version.

## 11. Note on Issue #55

The issue description for #55 contained track maintenance template boilerplate where specific named test cases would normally appear. The definition of "input size" is taken as the number of list items `n` (an assumption based on the exercise domain).

## 12. How to Run

- `python3 work/R08-T055/check.py` (re-runs the committed tests, guard, correctness and the docs-versus-evidence comparison; does not re-measure timings; modifies nothing)
- `--write-evidence` (re-measures everything and overwrites evidence.json, versions.txt and the generated blocks; timings change from run to run)
- `--self-test` (eleven scenarios: ten failure scenarios and one rendering check; exit 0 only if all behave as expected)
