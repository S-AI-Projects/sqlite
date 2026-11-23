# Hints for *Largest Series Product*

The exercise asks for the largest product of a contiguous substring of digits of length **n**.

Below is a concise walkthrough of each test case defined in `largest-series-product_test.sql`.  Use these hints to understand the expected behaviour.

| Test case description | Input (digits, span) | Expected output |
|-----------------------|----------------------|-----------------|
| finds the largest product if span equals length | `"12345"`, span = 5 | `120` |
| can find the largest product of 2 with numbers in order | `"12345"`, span = 2 | `20` |
| can find the largest product of 2 | `"576"`, span = 2 | `42` |
| can find the largest product of 3 with numbers in order | `"123456"`, span = 3 | `120` |
| can find the largest product of 3 | `"5768"`, span = 3 | `336` |
| can find the largest product of 5 with numbers in order | `"12345678"`, span = 5 | `6720` |
| can get the largest product of a big number | `"12345678901234567890"`, span = 13 | `23514624000` |
| reports zero if the only digits are zero | `"00000"`, span = 3 | `0` |
| reports zero if all spans include zero | `"1020304050"`, span = 2 | `0` |
| rejects span longer than string length (first occurrence) | `"123"`, span = 5 | *error* |
| rejects span longer than string length (duplicate entry) | `"123"`, span = 5 | *error* |
| reports 1 for empty string and empty product (0 span) | `""`, span = 0 | `1` |
| reports 1 for non‑empty string and empty product (0 span) | `"123"`, span = 0 | `1` |
| rejects empty string and non‑zero span (first occurrence) | `""`, span = 2 | *error* |
| rejects empty string and non‑zero span (duplicate) | `""`, span = 2 | *error* |
| rejects invalid character in digits | `"12a34"`, span = 2 | *error* |
| rejects negative span (first occurrence) | `"123"`, span = ‑1 | *error* |
| rejects negative span (duplicate) | `"123"`, span = ‑1 | *error* |

* `*error*` means the runner should produce a JSON entry with `"status":"error"` and a helpful message.

These hints mirror the spec in `.meta/tests.toml` and can be used by learners for debugging.