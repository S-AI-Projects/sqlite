# Collatz Conjecture – maintenance guide

## Runner command
```bash
python3 work/R08-T039/check.py
```
The command validates the exercise `exercises/practice/collatz-conjecture` by:
1. Parsing `.meta/config.json` for the declared **solution**, **test**, and **example** files.
2. Copying the entire exercise (including hidden files) into a temporary directory.
3. Substituting the learner’s stub with the reference implementation (`.meta/example.sql`).
4. Executing `sqlite3 -bail <collatz-conjecture_test.sql>` inside the temporary copy.
5. Ensuring the generated `output.json` reports **pass** for every test case.
6. Verifying the learner stub file hash before and after the run to guarantee it remains unchanged.
7. Storing evidence (`reference_output.json`, `versions.txt`) under `work/R08-T039/`.

## Tool requirements
- **SQLite CLI** with JSON support (used for the test runner).
- **jq** (optional for post‑processing JSON output, not required by the script).
- **bash** (for any shell‑level scripting surrounding the runner).
- **Python 3** (standard library only; `hashlib`, `tempfile`, `subprocess`, `json`, `pathlib`, `shutil`).

## Files involved
| Role | Path |
|------|------|
| Learner stub (unsolved) | `exercises/practice/collatz-conjecture/collatz-conjecture.sql` |
| Reference implementation | `.meta/example.sql` |
| Test suite | `collatz-conjecture_test.sql` |
| Config metadata | `.meta/config.json` |
| Generated evidence | `work/R08-T039/reference_output.json`, `work/R08-T039/versions.txt` |

The runner never modifies the learner stub in the repository; all changes happen inside the temporary copy.
