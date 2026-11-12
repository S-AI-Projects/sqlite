# REST-API Maintenance Documentation & Canonical Case Rationales

## Overview

- **Exercise**: `exercises/practice/rest-api`
- **Task ID**: `R08-T041`
- **Objective**: Review the 9 canonical case entries in `exercises/practice/rest-api/.meta/tests.toml`, document the rationale and SQLite behavior for the three selected canonical cases (`5be01ffb-a814-47a8-a19f-490a5622ba07`, `382b70cc-9f6c-486d-9bee-fda2df81c803`, `d624e5e5-1abb-4f18-95b3-45d55c818dc3`), and establish an automated verification harness.

---

## 1. Selected Canonical Case Rationales & SQLite Behavior

The canonical suite specifies 9 cases across two test groups: `user management` and `iou`. All 9 cases are actively included in the SQLite track (0 exclusions). Below are the specific rationales and relational operations for the selected user management cases:

### 1. `5be01ffb-a814-47a8-a19f-490a5622ba07`: `user management -> no users`
- **Endpoint / Method**: GET `/users`
- **Input State**: `database: {"users": []}`, `payload: {}`
- **Expected Result**: `{"users": []}`
- **SQLite Relational Operation**:
  - The query executes a `LEFT JOIN` on `json_each(RA.database, '$.users')`.
  - When the database user list is empty, `json_each` returns 0 rows.
  - The expression `IIF(json_type(DB.value) IS NULL, json_array(), json_array(json(DB.value)))` detects the null table join and safely outputs an empty JSON array (`[]`) rather than failing or producing a SQL `NULL`.
  - Wrapped via `json_object('users', ...)` to match the canonical envelope.
- **Inclusion Decision**: Included. Validates baseline empty array handling in SQLite JSON1 functions.

### 2. `382b70cc-9f6c-486d-9bee-fda2df81c803`: `user management -> add user`
- **Endpoint / Method**: POST `/add`
- **Input State**: `database: {"users": []}`, `payload: {"user": "Adam"}`
- **Expected Result**: `{"name": "Adam", "owes": {}, "owed_by": {}, "balance": 0.0}`
- **SQLite Relational Operation**:
  - Directly extracts the new username via `json_extract(payload, '$.user')`.
  - Constructs the new User object using `json_object('name', ..., 'owes', json_object(), 'owed_by', json_object(), 'balance', 0)`.
  - Note: Unlike GET requests which return a wrapped `{"users": [...]}`, POST `/add` returns an unwrapped individual User object.
- **Inclusion Decision**: Included. Validates schema construction for newly registered users.

### 3. `d624e5e5-1abb-4f18-95b3-45d55c818dc3`: `user management -> get single user`
- **Endpoint / Method**: GET `/users`
- **Input State**: `database: {"users": [Adam, Bob]}`, `payload: {"users": ["Bob"]}`
- **Expected Result**: `{"users": [{"name": "Bob", "owes": {}, "owed_by": {}, "balance": 0.0}]}`
- **SQLite Relational Operation**:
  - Performs a relational join between two table-valued JSON functions:
    ```sql
    LEFT JOIN json_each(RA.payload, '$.users') AS PL ON RA.payload = PL.json
    LEFT JOIN json_each(RA.database, '$.users') AS DB ON RA.database = DB.json
      AND json_extract(DB.value, '$.name') = PL.value
    ```
  - Filters out unrequested users (e.g., Adam) and preserves only the user matching the payload filter array.
- **Inclusion Decision**: Included. Validates filtered querying and multi-collection JSON joining in SQLite.

---

## 2. Canonical Case Mapping Table

All 9 canonical test cases are supported and verified against the reference implementation:

| # | UUID | Description | Method | URL | Input Summary | Expected Summary | Status |
|---|---|---|---|---|---|---|---|
| 1 | `5be01ffb-a814-47a8-a19f-490a5622ba07` | no users | GET | `/users` | Empty DB, empty payload | `{"users":[]}` | Included (PASS) |
| 2 | `382b70cc-9f6c-486d-9bee-fda2df81c803` | add user | POST | `/add` | Empty DB, user: Adam | Bare user object (balance 0) | Included (PASS) |
| 3 | `d624e5e5-1abb-4f18-95b3-45d55c818dc3` | get single user | GET | `/users` | Users: Adam, Bob; filter: Bob | `{"users":[Bob]}` | Included (PASS) |
| 4 | `7a81b82c-7276-433e-8fce-29ce983a7c56` | both users have 0 balance | POST | `/iou` | Adam loans Bob 3.0 | Both users updated with 3.0 debt | Included (PASS) |
| 5 | `1c61f957-cf8c-48ba-9e77-b221ab068803` | borrower has negative balance | POST | `/iou` | Adam loans Bob 3.0 (Bob owes Chuck) | Bob owes Adam 3.0, Chuck 3.0 | Included (PASS) |
| 6 | `8a8567b3-c097-468a-9541-6bb17d5afc85` | lender has negative balance | POST | `/iou` | Bob loans Adam 3.0 (Bob owes Chuck) | Bob balance updated to 0.0 | Included (PASS) |
| 7 | `29fb7c12-7099-4a85-a7c4-9c290d2dc01a` | lender owes borrower | POST | `/iou` | Adam loans Bob 2.0 (Adam owes Bob 3.0) | Adam debt reduced to 1.0 | Included (PASS) |
| 8 | `ce969e70-163c-4135-a4a6-2c3a5da286f5` | lender owes borrower less than new loan | POST | `/iou` | Adam loans Bob 4.0 (Adam owes Bob 3.0) | Direction flips: Bob owes Adam 1.0 | Included (PASS) |
| 9 | `7f4aafd9-ae9b-4e15-a406-87a87bdf47a4` | lender owes borrower same as new loan | POST | `/iou` | Adam loans Bob 3.0 (Adam owes Bob 3.0) | Both balances return to 0.0 | Included (PASS) |

---

## 3. Inclusion & Exclusion Tracking

- **Pre-Task State**:
  - Total canonical entries: 9
  - Included: 9
  - Excluded: 0
- **Post-Task State**:
  - Total canonical entries: 9
  - Included: 9
  - Excluded: 0
- **Net Inclusions / Exclusions Changed**: 0 (all 9 canonical cases remain fully supported, tested, and passing against reference).

---

## 4. Verification Commands

```bash
# 1. Run course verification harness
python3 work/R08-T041/check.py

# 2. Run reusable focused check
python3 tools/course_checks/r08-t041.py

# 3. Run Exercism track test runner
./bin/verify-exercises exercises/practice/rest-api

# 4. Run configlet linter
./bin/configlet lint
```
