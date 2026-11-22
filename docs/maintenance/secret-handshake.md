# Secret Handshake Maintenance Documentation

This document describes the test generation pipeline, canonical test case mappings, and SQLite implementation mechanics for the `secret-handshake` exercise in the SQLite track of Exercism.

---

## 1. Test Generation Path

The test table for `secret-handshake` is generated programmatically using Exercism problem specifications, track configuration, and Jinja2 templating.

### Pipeline Overview

```
problem-specifications (canonical-data.json)
                   │
                   ▼
  .meta/tests.toml (tracks active UUIDs & descriptions)
                   │
                   ▼
  bin/generate_tests (filters cases & binds Jinja2 context)
                   │
                   ▼
  .meta/template.create_test_table.j2 (Jinja2 template)
                   │
                   ▼
  create_test_table.sql (executable SQLite fixture)
```

### Generation Components & Mechanism

1. **Canonical Specifications (`canonical-data.json`)**:
   - Upstream repository `problem-specifications/exercises/secret-handshake/canonical-data.json` contains the source of truth for canonical test cases, defining the `uuid`, `description`, `property`, `input.number`, and `expected` array of strings.

2. **Track Filter Configuration (`.meta/tests.toml`)**:
   - `exercises/practice/secret-handshake/.meta/tests.toml` tracks all canonical UUIDs and controls whether a test case is included or excluded:
     ```toml
     [b8496fbd-6778-468c-8054-648d03c4bb23]
     description = "wink for 1"
     ```
   - Cases marked with `include = false` are filtered out during test generation.

3. **Generator Script (`bin/generate_tests`)**:
   - Python script utilizing `tomllib` and `jinja2`.
   - Locates `canonical-data.json` and parses `tests.toml`.
   - Filters canonical cases using `get_cases()`, matching UUIDs and verifying `tests[uuid].get("include", True)`.
   - Injects custom filters into the Jinja2 environment (`quote`, `tojson`, `tocsv`, `repr`, `camel_to_snake`, `format_list`).
   - Renders templates matching `template.<target>.j2`.

4. **Jinja2 Template (`.meta/template.create_test_table.j2`)**:
   - Defines schema and insertion syntax for the `tests` table:
     ```jinja2
     DROP TABLE IF EXISTS tests;

     CREATE TABLE IF NOT EXISTS tests (
       uuid TEXT PRIMARY KEY,
       description TEXT NOT NULL,
       status TEXT DEFAULT 'fail',
       message TEXT,
       output TEXT,
       test_code TEXT,
       task_id INTEGER DEFAULT NULL,
       number INTEGER NOT NULL,
       expected TEXT NOT NULL
     );

     INSERT INTO
       tests (uuid, description, number, expected)
     VALUES
     {%- for case in cases %}
       (
         '{{ case["uuid"] }}',
         '{{ case["description"] }}',
         {{ case["input"]["number"] }},
         '{{ case["expected"] | join(", ") }}'
     {%- if loop.last %}
       );
     {%- else %}
       ),
     {%- endif %}
     {%- endfor %}
     ```
   - Formats the expected output array as a comma-separated string using `'{{ case["expected"] | join(", ") }}'`.

5. **Output Fixture (`create_test_table.sql`)**:
   - Renders 11 canonical test records inserted into the `tests` table for automated execution by `secret-handshake_test.sql`.

---

## 2. Canonical Test Case & Binary Flag Mapping Table

The `secret-handshake` exercise relies on binary bitwise operations where each bit represents a specific hand action or order modifier:
- **Bit 0 (`1` / `0b00001`)**: `wink`
- **Bit 1 (`2` / `0b00010`)**: `double blink`
- **Bit 2 (`4` / `0b00100`)**: `close your eyes`
- **Bit 3 (`8` / `0b01000`)**: `jump`
- **Bit 4 (`16` / `0b10000`)**: `reverse` (reverses the sequence of actions)

The following table maps all 11 canonical test cases:

| UUID | Description | Input (Dec) | Binary (5-bit) | Active Flags Breakdown | Expected Output String | Expected Array (`canonical-data`) |
| :--- | :--- | :---: | :---: | :--- | :--- | :--- |
| `b8496fbd-6778-468c-8054-648d03c4bb23` | wink for 1 | `1` | `00001` | `1` (wink) | `'wink'` | `["wink"]` |
| `83ec6c58-81a9-4fd1-bfaf-0160514fc0e3` | double blink for 10 | `2` | `00010` | `2` (double blink) | `'double blink'` | `["double blink"]` |
| `0e20e466-3519-4134-8082-5639d85fef71` | close your eyes for 100 | `4` | `00100` | `4` (close your eyes) | `'close your eyes'` | `["close your eyes"]` |
| `b339ddbb-88b7-4b7d-9b19-4134030d9ac0` | jump for 1000 | `8` | `01000` | `8` (jump) | `'jump'` | `["jump"]` |
| `40499fb4-e60c-43d7-8b98-0de3ca44e0eb` | combine two actions | `3` | `00011` | `1` + `2` (wink, double blink) | `'wink, double blink'` | `["wink", "double blink"]` |
| `9730cdd5-ef27-494b-afd3-5c91ad6c3d9d` | reverse two actions | `19` | `10011` | `1` + `2` + `16` (reverse wink, double blink) | `'double blink, wink'` | `["double blink", "wink"]` |
| `0b828205-51ca-45cd-90d5-f2506013f25f` | reversing one action gives the same action | `24` | `11000` | `8` + `16` (reverse jump) | `'jump'` | `["jump"]` |
| `9949e2ac-6c9c-4330-b685-2089ab28b05f` | reversing no actions still gives no actions | `16` | `10000` | `16` (reverse empty) | `''` | `[]` |
| `23fdca98-676b-4848-970d-cfed7be39f81` | all possible actions | `15` | `01111` | `1` + `2` + `4` + `8` (all 4 actions) | `'wink, double blink, close your eyes, jump'` | `["wink", "double blink", "close your eyes", "jump"]` |
| `ae8fe006-d910-4d6f-be00-54b7c3799e79` | reverse all possible actions | `31` | `11111` | `1` + `2` + `4` + `8` + `16` (all 4 actions reversed) | `'jump, close your eyes, double blink, wink'` | `["jump", "close your eyes", "double blink", "wink"]` |
| `3d36da37-b31f-4cdb-a396-d93a2ee1c4a5` | do nothing for zero | `0` | `00000` | None | `''` | `[]` |

---

## 3. SQLite Implementation Mechanics

The canonical solution in `.meta/example.sql` implements the logic through:
1. **Bitwise Inspection**:
   - `(number >> bit_pos) & 1`: Shifts the bit at `bit_pos` to the least significant bit and checks if it equals 1.
2. **Conditional Action Ordering**:
   - If the reverse bit `(number >> 4) & 1` is `1`:
     - Builds array `JSON_ARRAY(jump, close your eyes, double blink, wink)` (descending bit order).
   - If the reverse bit `(number >> 4) & 1` is `0`:
     - Builds array `JSON_ARRAY(wink, double blink, close your eyes, jump)` (ascending bit order).
3. **Array Flattening and Filtering**:
   - `JSON_EACH(commands) j WHERE j.value NOTNULL`: Unpacks array elements and automatically omits `NULL` values (untriggered flags).
4. **String Aggregation**:
   - `COALESCE(GROUP_CONCAT(j.value, ', '), '')`: Joins elements with a comma and space separator, ensuring an empty string `''` rather than `NULL` when no actions are active.
