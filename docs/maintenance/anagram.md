# Anagram Maintenance Documentation

## Overview

- **Exercise**: `exercises/practice/anagram`
- **Task ID**: `R08-T044`
- **Objective**: Improve the readability and maintainability of the reference implementation in `exercises/practice/anagram/.meta/example.sql` while preserving the exact anagram interface, canonical case behavior, and learner starter template.

---

## 1. Domain & Exercise Invariant

In SQLite, determining whether a candidate string is an anagram of a target subject requires two fundamental rules:
1. **Identical Normalized Letter Signatures**: The sorted multiset of letters in the candidate and target subject must match when evaluated case-insensitively (`subject_sorted = candidate_sorted`).
2. **Non-Identical Words**: A word is not an anagram of itself. Any candidate that matches the subject case-insensitively must be rejected (`LOWER(subject) <> LOWER(candidate)`).

---

## 2. Readability Refactoring Summary

The original reference implementation in `.meta/example.sql` relied on ambiguous table names, single-letter column names, and cryptic subquery aliases. The refactoring addresses these ambiguities directly without altering the relational schema, dependencies, or external contract.

| Scope | Original Identifier | Refactored Identifier | Rationale |
|---|---|---|---|
| Temporary Table | `tmp` | `word_signatures` | Clarifies that this table serves as a dictionary cache storing distinct lowercase words and their sorted letter signatures. |
| Signature Column | `s` | `sorted_letters` | Replaces the single-letter column name with a descriptive name indicating the alphabetical sequence of letters. |
| Recursive CTE | `rcte (word, c)` | `split_characters (remainder, char)` | Makes the recursive string-splitting logic self-documenting by distinguishing the tail remainder from the head character. |
| Subject Alias | `a` | `subject_sorted` | Replaces single-letter alias with explicit reference to the sorted letter signature of the subject. |
| Candidate Alias | `b` | `candidate_sorted` | Replaces single-letter alias with explicit reference to the sorted letter signature of the candidate. |
| Header Invariant | *None* | Explicit invariant comments | Documents the two core rules of the anagram problem directly in the reference SQL file. |

---

## 3. Canonical Case Mapping Table

All 16 active canonical test cases from `tests.toml` and `create_test_table.sql` were verified against both the pre-refactor reference and post-refactor reference implementation. Outputs are strictly byte-identical.

| # | UUID | Description | Subject | Candidates | Expected Result | Status |
|---|---|---|---|---|---|---|
| 1 | `dd40c4d2-3c8b-44e5-992a-f42b393ec373` | no matches | `diaper` | `["hello","world","zombies","pants"]` | `[]` | PASS |
| 2 | `03eb9bbe-8906-4ea0-84fa-ffe711b52c8b` | detects two anagrams | `solemn` | `["lemons","cherry","melons"]` | `["lemons","melons"]` | PASS |
| 3 | `a27558ee-9ba0-4552-96b1-ecf665b06556` | does not detect anagram subsets | `good` | `["dog","goody"]` | `[]` | PASS |
| 4 | `64cd4584-fc15-4781-b633-3d814c4941a4` | detects anagram | `listen` | `["enlists","google","inlets","banana"]` | `["inlets"]` | PASS |
| 5 | `99c91beb-838f-4ccd-b123-935139917283` | detects three anagrams | `allergy` | `["gallery","ballerina","regally","clergy","largely","leading"]` | `["gallery","regally","largely"]` | PASS |
| 6 | `78487770-e258-4e1f-a646-8ece10950d90` | detects multiple anagrams with different case | `nose` | `["Eons","ONES"]` | `["Eons","ONES"]` | PASS |
| 7 | `1d0ab8aa-362f-49b7-9902-3d0c668d557b` | does not detect non-anagrams with identical checksum | `mass` | `["last"]` | `[]` | PASS |
| 8 | `9e632c0b-c0b1-4804-8cc1-e295dea6d8a8` | detects anagrams case-insensitively | `Orchestra` | `["cashregister","Carthorse","radishes"]` | `["Carthorse"]` | PASS |
| 9 | `b248e49f-0905-48d2-9c8d-bd02d8c3e392` | detects anagrams using case-insensitive subject | `Orchestra` | `["cashregister","carthorse","radishes"]` | `["carthorse"]` | PASS |
| 10 | `f367325c-78ec-411c-be76-e79047f4bd54` | detects anagrams using case-insensitive possible matches | `orchestra` | `["cashregister","Carthorse","radishes"]` | `["Carthorse"]` | PASS |
| 11 | `630abb71-a94e-4715-8395-179ec1df9f91` | does not detect an anagram if the original word is repeated | `go` | `["goGoGO"]` | `[]` | PASS |
| 12 | `9878a1c9-d6ea-4235-ae51-3ea2befd6842` | anagrams must use all letters exactly once | `tapper` | `["patter"]` | `[]` | PASS |
| 13 | `68934ed0-010b-4ef9-857a-20c9012d1ebf` | words are not anagrams of themselves | `BANANA` | `["BANANA"]` | `[]` | PASS |
| 14 | `589384f3-4c8a-4e7d-9edc-51c3e5f0c90e` | words are not anagrams of themselves even if letter case is partially different | `BANANA` | `["Banana"]` | `[]` | PASS |
| 15 | `ba53e423-7e02-41ee-9ae2-71f91e6d18e6` | words are not anagrams of themselves even if letter case is completely different | `BANANA` | `["banana"]` | `[]` | PASS |
| 16 | `33d3f67e-fbb9-49d3-a90e-0beb00861da7` | words other than themselves can be anagrams | `LISTEN` | `["LISTEN","Silent"]` | `["Silent"]` | PASS |

---

## 4. Verification Procedures

To run automated checks:
```bash
# 1. Run course verification check
python3 work/R08-T044/check.py

# 2. Run reusable focused check
python3 tools/course_checks/r08-t044.py

# 3. Run track test runner
./bin/verify-exercises exercises/practice/anagram

# 4. Run configlet linter
./bin/configlet lint
```
