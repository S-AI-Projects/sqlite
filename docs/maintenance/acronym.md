# Acronym Test Generation and Maintenance Guide

This document describes the test generation pipeline, input sources, command execution, and case-to-output mapping for the `acronym` practice exercise (`exercises/practice/acronym`).

## 1. Generation Pipeline Overview

The test suite for `acronym` is generated using the track generator script `bin/generate_tests`, which merges canonical test data from `problem-specifications` with track-specific configurations in `.meta/tests.toml`, rendering SQL test fixtures via Jinja2 templates.

### Generated vs. Hand-Maintained Files

| File | Status | Description / Maintenance Role |
|:---|:---:|:---|
| `exercises/practice/acronym/create_test_table.sql` | **Generated** | Rendered from `.meta/template.create_test_table.j2`. Drops and creates the `tests` table and inserts all enabled test cases. |
| `exercises/practice/acronym/data.csv` | **Generated** | Rendered from `.meta/template.data.j2`. Contains CSV input phrases for `create_fixture.sql`. |
| `exercises/practice/acronym/acronym_test.sql` | **Hand-Maintained** | The test harness script that reads `create_fixture.sql`, executes the solution, reads `create_test_table.sql`, evaluates results, and formats `output.json`. |
| `exercises/practice/acronym/create_fixture.sql` | **Hand-Maintained** | DDL script creating `acronym (phrase TEXT, result TEXT)` and importing `data.csv`. |
| `exercises/practice/acronym/acronym.sql` | **Hand-Maintained** | Learner stub table definition and instructions. |
| `exercises/practice/acronym/.meta/example.sql` | **Hand-Maintained** | Maintained reference implementation using recursive CTE parsing. |
| `exercises/practice/acronym/.meta/tests.toml` | **Hand-Maintained / Synced** | Track test case selection and comments managed via `configlet sync`. |

---

## 2. Test Sources and Canonical Invariants

Test cases originate from upstream Exercism problem specifications:
- **Canonical Data**: `problem-specifications/exercises/acronym/canonical-data.json`
- **Track Selection & Invariants**: Managed in `exercises/practice/acronym/.meta/tests.toml`

When regenerating or synchronizing tests via `configlet sync --tests --exercise acronym`:
1. **Recreate every `description` key/value pair**: Automatically mapped from `canonical-data.json` test case descriptions.
2. **Recreate every `reimplements` key/value pair**: Preserved where an upstream canonical case is reimplemented.
3. **Preserve any other key/value pair**: Retains any custom metadata, exclusion rules (`include = false`), or user comments (`comment = "..."`).

---

## 3. Exact Generation Command

To regenerate the `acronym` test files:

```bash
# 1. Ensure problem-specifications are cached (via configlet sync)
./bin/configlet sync --tests --exercise acronym

# 2. Run the track test generator
./bin/generate_tests --no-pull acronym
```

### Automated Reusable Check Command

To verify that generation is 100% deterministic and reproducible across clean environments:

```bash
python3 tools/course_checks/r08-t042.py
```

Options:
- `--json`: Output check results in structured JSON format.
- `--quiet`, `-q`: Quiet mode (minimal console output).

---

## 4. Case-to-Output Mapping

The table below maps each canonical test case from `canonical-data.json` and `.meta/tests.toml` to its rendered output in `create_test_table.sql` and `data.csv`:

| UUID | Description | Input `phrase` | Expected `result` | Row in `create_test_table.sql` | Row in `data.csv` |
|:---|:---|:---|:---:|:---|:---|
| `1e22cceb-c5e4-4562-9afe-aef07ad1eaf4` | basic | `'Portable Network Graphics'` | `'PNG'` | `('1e22cceb...', 'basic', 'Portable Network Graphics', 'PNG')` | `"Portable Network Graphics",""` |
| `79ae3889-a5c0-4b01-baf0-232d31180c08` | lowercase words | `'Ruby on Rails'` | `'ROR'` | `('79ae3889...', 'lowercase words', 'Ruby on Rails', 'ROR')` | `"Ruby on Rails",""` |
| `ec7000a7-3931-4a17-890e-33ca2073a548` | punctuation | `'First In, First Out'` | `'FIFO'` | `('ec7000a7...', 'punctuation', 'First In, First Out', 'FIFO')` | `"First In, First Out",""` |
| `32dd261c-0c92-469a-9c5c-b192e94a63b0` | all caps word | `'GNU Image Manipulation Program'` | `'GIMP'` | `('32dd261c...', 'all caps word', 'GNU Image Manipulation Program', 'GIMP')` | `"GNU Image Manipulation Program",""` |
| `ae2ac9fa-a606-4d05-8244-3bcc4659c1d4` | punctuation without whitespace | `'Complementary metal-oxide semiconductor'` | `'CMOS'` | `('ae2ac9fa...', 'punctuation without whitespace', 'Complementary metal-oxide semiconductor', 'CMOS')` | `"Complementary metal-oxide semiconductor",""` |
| `0e4b1e7c-1a6d-48fb-81a7-bf65eb9e69f9` | very long abbreviation | `'Rolling On The Floor Laughing So Hard That My Dogs Came Over And Licked Me'` | `'ROTFLSHTMDCOALM'` | `('0e4b1e7c...', 'very long abbreviation', 'Rolling On The Floor Laughing So Hard That My Dogs Came Over And Licked Me', 'ROTFLSHTMDCOALM')` | `"Rolling On The Floor Laughing So Hard That My Dogs Came Over And Licked Me",""` |
| `6a078f49-c68d-4b7b-89af-33a1a98c28cc` | consecutive delimiters | `'Something - I made up from thin air'` | `'SIMUFTA'` | `('6a078f49...', 'consecutive delimiters', 'Something - I made up from thin air', 'SIMUFTA')` | `"Something - I made up from thin air",""` |
| `5118b4b1-4572-434c-8d57-5b762e57973e` | apostrophes | `'Halley''s Comet'` | `'HC'` | `('5118b4b1...', 'apostrophes', 'Halley''s Comet', 'HC')` | `"Halley's Comet",""` |
| `adc12eab-ec2d-414f-b48c-66a4fc06cdef` | underscore emphasis | `'The Road _Not_ Taken'` | `'TRNT'` | `('adc12eab...', 'underscore emphasis', 'The Road _Not_ Taken', 'TRNT')` | `"The Road _Not_ Taken",""` |

---

## 5. Round-Trip Verification and Idempotency

1. **Deterministic Code Generation**: Two successive generation passes on clean temporary copies produce byte-for-byte identical output files after normalizing generation timestamps (if present in headers).
2. **Zero Case Dropping**: All 9 active canonical cases defined in `tests.toml` are preserved across the round trip without any missing or duplicated records.
3. **Reference Verification**: The maintained reference implementation (`.meta/example.sql`) passes all 9 generated test cases with 100% pass rate.

