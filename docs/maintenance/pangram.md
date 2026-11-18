# Maintenance Guide: Pangram Reference Scaling and Structural Comparison

## 1. Purpose

Compare the reference technique with one independently written alternative for the same pangram contract. The contribution is an architectural explanation and measurement study, not a solved learner stub. Both approaches, the test suites, structural properties, and scaling characteristics are verified by `work/R08-T056/check.py`.

## 2. The Specification

### What the Instructions Say
The exercise instructions in `exercises/practice/pangram/.docs/instructions.md` define a pangram and the required contract with the following statements:
> "It is case insensitive, so it doesn't matter if a letter is lower-case (e.g. `k`) or upper-case (e.g. `K`)."
> "For this exercise, a sentence is a pangram if it contains each of the 26 letters in the English alphabet."

The instructions do not mention non-alphabetic characters, numbers, punctuation symbols, whitespace, or non-ASCII characters.

### How This Page Treats Other Characters
How this page treats other characters (assumption: the independent expectation counts only ASCII letters; digits, punctuation, whitespace and non-ASCII characters never count as letters). Non-letter characters neither count toward satisfying the 26 English letters nor invalidate the presence of other valid letters in the sentence.

The canonical test suite defined in `exercises/practice/pangram/.meta/tests.toml` and instantiated in `exercises/practice/pangram/create_test_table.sql` contains ten active test cases, plus one excluded case that is reimplemented by a more comprehensive case:

<!-- BEGIN GENERATED: cases -->
| UUID | Description | Expected | Reference | Alternative | Agree |
| :--- | :--- | :---: | :---: | :---: | :---: |
| 64f61791 | empty sentence | False | False | False | Yes |
| 74858f80 | perfect lower case | True | True | True | Yes |
| 61288860 | only lower case | True | True | True | Yes |
| 6564267d | missing the letter 'x' | False | False | False | Yes |
| c79af1be | missing the letter 'h' (named) | False | False | False | Yes |
| d835ec38 | with underscores | True | True | True | Yes |
| 8cc1e080 | with numbers | True | True | True | Yes |
| bed96b1c | missing letters replaced by numbers | False | False | False | Yes |
| 938bd5d8 | mixed case and punctuation (named) | True | True | True | Yes |
| 7138e389 | a-m and A-M are 26 different characters but not a pangram (named) | False | False | False | Yes |

Excluded case: `2577bf54` (case insensitive), reimplemented by `7138e389` (a-m and A-M are 26 different characters but not a pangram).
<!-- END GENERATED: cases -->

## 3. The Reference Approach

The reference implementation in `exercises/practice/pangram/.meta/example.sql` uses a central representation consisting of 26 scalar conditions joined by `AND` operators within a single `UPDATE` assignment, with no intermediate tabular data structure:

```sql
INSTR(LOWER(sentence), 'a')
AND INSTR(LOWER(sentence), 'b')
-- ... repeated for each letter through 'z'
```

When evaluating an input string, `LOWER(sentence)` maps uppercase ASCII characters to lowercase equivalents. For each of the 26 target letters from `'a'` to `'z'`, `INSTR` scans the lowercased sentence and returns the 1-based character position of the first occurrence, or 0 if the letter is absent. The 25 boolean `AND` operators combine these 26 integer results into a single boolean result.

## 4. The Second Approach

The second approach in `ALT_SQL` adopts a relational model where the target alphabet is represented as a 26-row table generated dynamically by a recursive common table expression (`WITH RECURSIVE alphabet`), followed by a set cardinality count:

```sql
WITH RECURSIVE alphabet(letter, i) AS (...)
SELECT COUNT(*) = 26 FROM alphabet
WHERE INSTR(LOWER(pangram.sentence), letter) > 0
```

This is not a renaming of the reference. The reference evaluates an unrolled chain of 26 scalar expressions relying on 26 hardcoded letter literals and 25 boolean conjunctions. In contrast, the second approach defines an in-memory relation over the alphabet using arithmetic recursion (`CHAR(97 + i)`), filters that relation using a `WHERE` clause, and determines coverage through relational aggregation (`COUNT(*) = 26`). The differences in SQL keywords, functions, and static bytecode opcodes are summarized below:

<!-- BEGIN GENERATED: structure -->
- **Structural Facts**:
  - Reference: 26 single-letter literals matching `'[a-z]'`, 25 `AND` operators, no `RECURSIVE`, no `COUNT(`.
  - Alternative: 1 single-letter literal matching `'[a-z]'`, 0 `AND` operators, contains `RECURSIVE` and `COUNT(`.
- **Distinct SQL Keywords**:
  - Reference: `AND`, `SET`, `UPDATE`
  - Alternative: `ALL`, `AS`, `FROM`, `RECURSIVE`, `SELECT`, `SET`, `UNION`, `UPDATE`, `WHERE`, `WITH`
  - Set difference (Reference \ Alternative): `AND`
  - Set difference (Alternative \ Reference): `ALL`, `AS`, `FROM`, `RECURSIVE`, `SELECT`, `UNION`, `WHERE`, `WITH`
- **Distinct Function Names**:
  - Reference: `INSTR`, `LOWER`
  - Alternative: `CHAR`, `COUNT`, `INSTR`, `LOWER`
  - Set difference (Reference \ Alternative): *(none)*
  - Set difference (Alternative \ Reference): `CHAR`, `COUNT`
- **Static Opcode Counts (from `EXPLAIN`; these are static bytecode counts, not runtime counts)**:
  - Reference: 144 total opcodes, 26 `Function` opcodes invoking `lower`, 0 `OpenEphemeral` opcodes.
  - Alternative: 66 total opcodes, 1 `Function` opcodes invoking `lower`, 1 `OpenEphemeral` opcodes.
<!-- END GENERATED: structure -->

## 5. Worked Example (Hint)

### Reference Approach
- Converts the candidate sentence to lowercase and searches for each letter from `'a'` to `'z'` using `INSTR`.
- For `"The quick brown fox jumps over the lazy dog"`, all 26 searches return non-zero character offsets.
- The 25 conjunctions combine 26 positive integers, yielding 1 (True).
- For `"The quick brown fox jumps over the lazy do"`, searches for `'a'` through `'f'` succeed with non-zero offsets.
- The search for `'g'` returns 0 because `'g'` is absent from the input.
- In SQLite boolean semantics, 0 is false, so the conjunction evaluates to 0 (False).

### Second Approach
- Generates a 26-row relation containing letters `'a'` through `'z'` and tests row presence in the lowercased sentence.
- For `"The quick brown fox jumps over the lazy dog"`, every letter satisfies `INSTR > 0`.
- The aggregate query computes `COUNT(*) = 26`, and the comparison `26 = 26` evaluates to 1 (True).
- For `"The quick brown fox jumps over the lazy do"`, the row for letter `'g'` yields 0 and is excluded by the filter.
- Exactly 25 alphabet rows pass the `WHERE` condition, so `COUNT(*)` returns 25.
- The comparison `25 = 26` evaluates to 0 (False).

## 6. Trade-offs

The alternative approach can be considered clearer because the alphabet domain is defined once programmatically via character code arithmetic rather than through 26 distinct manual string literals; a typo in a literal list cannot go unnoticed. However, describing one technique as clearer is a subjective design judgment, not a physical measurement.

In terms of overhead, the alternative contains one OpenEphemeral opcode in its static bytecode (see the structure block). Across all tested sentence lengths, measured virtual machine steps remained strictly identical between True and False inputs within each approach, demonstrating that no early exit was observed in the query execution. Statement time grows with sentence length, which is consistent with LOWER and INSTR scanning the whole text; this page does not isolate that cause.

<!-- BEGIN GENERATED: results -->
The startup baselines measured over 5 repetitions are:
- Bare SQLite process (`sqlite3 :memory: "SELECT 1;"`): **2.556 ms** median
- 1-row harness driver: **2.749 ms** median (noise floor: **1.706 ms**)

| Approach | Length | Expected | Wall Median (s) | Timer Median (s) | Timer Min (s) | Timer Max (s) | VM Steps |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Reference | 26 | True | 0.002753 | 0.000023 | 0.000022 | 0.000026 | 144 |
| Reference | 26 | False | 0.002704 | 0.000022 | 0.000021 | 0.000026 | 144 |
| Reference | 1000 | True | 0.002760 | 0.000032 | 0.000029 | 0.000037 | 144 |
| Reference | 1000 | False | 0.002745 | 0.000031 | 0.000030 | 0.000042 | 144 |
| Reference | 100000 | True | 0.004921 | 0.000768 | 0.000755 | 0.000779 | 144 |
| Reference | 100000 | False | 0.004965 | 0.000799 | 0.000796 | 0.000815 | 144 |
| Alternative | 26 | True | 0.002762 | 0.000036 | 0.000034 | 0.000040 | 709 |
| Alternative | 26 | False | 0.002745 | 0.000034 | 0.000032 | 0.000034 | 709 |
| Alternative | 1000 | True | 0.002740 | 0.000041 | 0.000040 | 0.000042 | 709 |
| Alternative | 1000 | False | 0.002722 | 0.000042 | 0.000040 | 0.000043 | 709 |
| Alternative | 100000 | True | 0.004895 | 0.000716 | 0.000715 | 0.000746 | 709 |
| Alternative | 100000 | False | 0.004942 | 0.000759 | 0.000758 | 0.000769 | 709 |

VM steps constant per approach: reference 144, alternative 709 (identical for True and False inputs).

Statement times are printed by SQLite with six decimals (resolution 1e-6 s), so the smallest values in the table carry only two significant digits.

- At length 26, the alternative statement-time median is 1.57x the reference median for valid inputs (intervals do not overlap) and 1.55x for invalid inputs (intervals do not overlap).
- At length 1000, the alternative statement-time median is 1.28x the reference median for valid inputs (intervals do not overlap) and 1.35x for invalid inputs (intervals overlap).
- At length 100000, the alternative statement-time median is 0.93x the reference median for valid inputs (intervals do not overlap) and 0.95x for invalid inputs (intervals do not overlap).
<!-- END GENERATED: results -->

## 7. Equivalence and the ASCII Boundary

Both techniques yield identical boolean results across the test suite and an expanded battery of inputs testing punctuation, whitespace, numbers, casing permutations, and non-ASCII characters:

<!-- BEGIN GENERATED: equivalence -->
| # | Input | Length | Expected | Reference | Alternative | Agree | Missing ASCII letters |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | len=0: `` | 0 | False | False | False | Yes | abcdefghij... (26 missing) |
| 2 | len=26: `abcdefghijklmnopqrstuvwxyz` | 26 | True | True | True | Yes | none |
| 3 | len=26: `ABCDEFGHIJKLMNOPQRSTUVWXYZ` | 26 | True | True | True | Yes | none |
| 4 | len=25: `abcdefghijklmnopqrstuvwxy` | 25 | False | False | False | Yes | z |
| 5 | len=25: `bcdefghijklmnopqrstuvwxyz` | 25 | False | False | False | Yes | a |
| 6 | len=43: `The quick brown fox jumps over t...` | 43 | True | True | True | Yes | none |
| 7 | len=42: `The quick brown fox jumps over t...` | 42 | False | False | False | Yes | g |
| 8 | len=42: `Pack my box with 5 dozen liquor ...` | 42 | False | False | False | Yes | fv |
| 9 | len=37: `a1b2c3d4e5f6g7h8i9j0 klmnopqrstu...` | 37 | True | True | True | Yes | none |
| 10 | len=27: `abcdefghijklm ABCDEFGHIJKLM` | 27 | False | False | False | Yes | nopqrstuvw... (13 missing) |
| 11 | len=51: `a_b_c_d_e_f_g_h_i_j_k_l_m_n_o_p_...` | 51 | True | True | True | Yes | none |
| 12 | len=34: `abc\tdef\nghi jkl mno pqr stu vw...` | 34 | True | True | True | Yes | none |
| 13 | len=47: `The quick brown fox jumps over t...` | 47 | True | True | True | Yes | none |
| 14 | len=46: `The quick brown fox jumps over t...` | 46 | False | False | False | Yes | g |
| 15 | len=55: `\u0421\u044a\u0435\u0448\u044c ...` | 55 | False | False | False | Yes | abcdefghij... (26 missing) |
| 16 | len=32: `abcdefghijklmnopqrstuvwxyz ...` | 32 | True | True | True | Yes | none |
| 17 | len=43: `Th\u00e9 quick brown fox jumps o...` | 43 | False | False | False | Yes | e |
| 18 | len=43: `The quic\u212a brown fox jumps o...` | 43 | False | False | False | Yes | k |
| 19 | len=32: `aaaaaaaaaa bbbbbbbbbb cccccccccc` | 32 | False | False | False | Yes | defghijklm... (23 missing) |
| 20 | len=5: `     ` | 5 | False | False | False | Yes | abcdefghij... (26 missing) |
| 21 | len=1: `a` | 1 | False | False | False | Yes | bcdefghijk... (25 missing) |
| 22 | len=33: `   abcdefghijklmnopqrstuvwxyz   \n` | 33 | True | True | True | Yes | none |

Round-trip check: all 22 extra inputs read back byte-for-byte identically from the fixture table.
Non-ASCII behaviour: upper(U+00e4) -> U+00e4, lower(U+00c4) -> U+00c4, lower(U+212a) -> U+212a (hex E284AA) (standard 7-bit ASCII case folding; non-ASCII letters remain unchanged).
<!-- END GENERATED: equivalence -->

The Kelvin sign input (U+212a) illustrates the specification boundary. In Unicode case-folding tables, U+212a normalizes to lowercase `'k'`, meaning Python's built-in `str.lower()` would mistakenly satisfy the requirement for `'k'` (this Python fact is recorded in the evidence under `python_facts`). However, the exercise specification restricts the alphabet strictly to the 26 English ASCII letters. The independent test expectation filters characters using ASCII letter membership, correctly classifying U+212a as a non-ASCII symbol rather than an English letter. In the SQLite build recorded in the evidence, LOWER does not fold non-ASCII letters (see the measured line above), so both SQL implementations correctly identify the sentence as missing the letter `'k'` and return False.

## 8. What This Page Does Not Claim

- Neither approach is declared unconditionally superior or faster overall; trade-offs exist between scalar simplicity and relational modeling.
- Static bytecode opcode counts reflect query structure at preparation time, not dynamic loop iteration counts at runtime.
- Absolute timing figures depend on the host operating system, hardware platform, and SQLite compile flags.
- The learner exercise stub `exercises/practice/pangram/pangram.sql` remains unsolved in this repository.

## 9. Note on Issue #56

The Goal, Steps, and "Done when" text in issue #56 contain garbled fragments where named test cases were expected to be listed. In response, three canonical test cases from `exercises/practice/pangram/.meta/tests.toml` were selected as the formal named cases to cover standard negative, mixed-case positive, and case-boundary negative behaviors. The collapsed "Additional task guidance" section was not read; it was not available when this page was written (assumption).

## 10. How to Run

The verification script `work/R08-T056/check.py` supports the following execution modes:
- **Default mode** (`python3 work/R08-T056/check.py`): Re-runs canonical test suites, guard checks, equivalence sweeps, and checks that the generated documentation blocks match `work/R08-T056/evidence.json` without modifying any file.
- **Evidence generation mode** (`python3 work/R08-T056/check.py --write-evidence`): Executes complete timing sweeps, writes `work/R08-T056/evidence.json` and `work/R08-T056/versions.txt`, and updates the generated blocks in `docs/maintenance/pangram.md`.
- **Documentation refresh mode** (`python3 work/R08-T056/check.py --write-docs`): Rebuilds the generated blocks in `docs/maintenance/pangram.md` directly from the existing `work/R08-T056/evidence.json` without re-running timing measurements.
- **Self-test mode** (`python3 work/R08-T056/check.py --self-test`): Evaluates thirteen intentional failure scenarios across all shared verification routines, requiring all thirteen to be rejected.
