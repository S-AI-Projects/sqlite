# Hints

## General

- Carefully review the six week categories: `first`, `second`, `third`, `fourth`, `teenth`, and `last`.
- Recall that the "teenth" days in any month are always days 13 through 19 inclusive (13th, 14th, 15th, 16th, 17th, 18th, and 19th). There is exactly one of each weekday in that 7-day range.
- SQLite provides built-in date functions such as `date()` and `strftime()`, as well as support for recursive Common Table Expressions (`WITH RECURSIVE`).

## Approach Selection

There are two primary paradigms for solving the meetup date calculation in SQLite:

### Approach 1: Closed-Form Date Modifiers (Reference Technique)

- **Data Representation**: Works directly on scalar ISO date strings (`YYYY-MM-DD`) using SQLite's built-in date arithmetic.
- **Mechanism**:
  - Maps weekday names to numbers (0 = Sunday, 1 = Monday, ..., 6 = Saturday).
  - Uses fixed anchor dates for each week category:
    - `first`: starts on the 1st (`YYYY-MM-01`).
    - `second`: starts on the 8th (`YYYY-MM-08`).
    - `third`: starts on the 15th (`YYYY-MM-15`).
    - `fourth`: starts on the 22nd (`YYYY-MM-22`).
    - `teenth`: starts on the 13th (`YYYY-MM-13`).
    - `last`: starts on the 1st of the next month, minus 7 days (`date('YYYY-MM-01', '+1 month', '-7 days')`).
  - Employs SQLite's `'weekday N'` modifier: `date(anchor_date, 'weekday ' || dayofweek_num)`. In SQLite, `'weekday N'` advances the date forward to the next occurrence of that weekday (or leaves it unchanged if the anchor is already on that weekday).
- **Trade-offs**:
  - **Memory & Work**: $O(1)$ operations per record with minimal CPU overhead and zero temporary table allocations.
  - **Portability**: Relies on SQLite-specific `'weekday N'` date modifier semantics, which are not standard in other SQL dialects.

### Approach 2: Recursive Calendar Expansion (CTE Technique)

- **Data Representation**: Represents the month as a relational table of daily tuples `(cal_date, day_num, weekday_name)` generated dynamically.
- **Mechanism**:
  - Uses `WITH RECURSIVE` to generate all 28–31 calendar days of the month starting from day 1.
  - Determines each candidate day's weekday with `strftime('%w', cal_date)`.
  - Filters rows matching the requested weekday name.
  - Selects the target date using ordinal ranking (e.g. `ROW_NUMBER() OVER (ORDER BY day_num)` for 1st–4th occurrences, `BETWEEN 13 AND 19` for teenth, or max occurrence for last).
- **Trade-offs**:
  - **Memory & Work**: Generates 28–31 intermediate rows per input row, incurring additional CPU, sorting, and transient working memory.
  - **Clarity & Portability**: Highly transparent and inspectable; uses standard SQL CTE and window function logic that easily translates to other relational database systems.

### Worked Example: "teenth Saturday of August 1953"

Input parameters:
- `year = 1953`
- `month = 8`
- `week = 'teenth'`
- `dayofweek = 'Saturday'` (weekday number 6)

1. **Under Approach 1 (Date Modifier)**:
   - The teenth anchor date is the 13th: `'1953-08-13'`.
   - In 1953, August 13 fell on Thursday (weekday 4).
   - Evaluating `date('1953-08-13', 'weekday 6')` steps forward to the next Saturday: August 15, 1953 (`'1953-08-15'`).

2. **Under Approach 2 (Calendar Expansion)**:
   - The recursive CTE produces all dates from `1953-08-01` to `1953-08-31`.
   - Filtering for `weekday_name = 'Saturday'` yields candidate dates:
     - `1953-08-01` (day 1)
     - `1953-08-08` (day 8)
     - `1953-08-15` (day 15)
     - `1953-08-22` (day 22)
     - `1953-08-29` (day 29)
   - Applying the teenth filter (`day_num BETWEEN 13 AND 19`) isolates day 15 (`'1953-08-15'`).
