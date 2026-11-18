# Hints

## SQLite

The reference keeps color names as `TEXT` and their band values as `INT` in a lookup table. For each input row, a scalar subquery selects the matching quoted `"index"` from `colors` and assigns it to `color_code.result`.

| Tested input | Required result | Test case |
| --- | ---: | --- |
| `black` | 0 | Color codes -> Black |
| `white` | 9 | Color codes -> White |
| `orange` | 3 | Color codes -> Orange |

These are the three enabled cases in `.meta/tests.toml`; each assertion compares the input color and its integer result. The metadata also contains a `Colors` case with `include = false`, so it is not part of this test run. The exercise instructions define the full band mapping, while these cases check the black, white and orange entries.

There is no list ordering or error response requirement in these selected assertions: each test checks one color-to-number pair. The exercise does not specify what an unknown color must return. In SQLite, the reference's scalar subquery returns `NULL` when it finds no matching row, but that implementation detail is not an exercise promise and should not be turned into a new validation rule.
