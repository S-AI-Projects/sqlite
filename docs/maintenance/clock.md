# Clock Exercise Maintenance

This document provides maintenance and reference notes for the `clock` exercise in the SQLite track. It details key canonical test cases for clock creation, demonstrating how SQLite's datetime functions (`TIME()` and `STRFTIME()`) evaluate hour and minute modifiers—including date-rollover behavior at midnight—and provides standalone `sqlite3` verification commands for each scenario.

| UUID | Full test description (as in tests.toml) | Input | Expected | SQLite operation | How to verify |
| --- | --- | --- | --- | --- | --- |
| `a577bacc-106b-496e-9792-b3083ea8705e` | Create a new clock with an initial time -> on the hour | `{"hour": 8, "minute": 0}` | `08:00` | `STRFTIME('%H:%M', TIME('00:00', '8 HOUR', '0 MINUTE'))` | `sqlite3 :memory: "select strftime('%H:%M', time('00:00', '8 HOUR', '0 MINUTE'));"` |
| `b5d0c360-3b88-489b-8e84-68a1c7a4fa23` | Create a new clock with an initial time -> past the hour | `{"hour": 11, "minute": 9}` | `11:09` | `STRFTIME('%H:%M', TIME('00:00', '11 HOUR', '9 MINUTE'))` | `sqlite3 :memory: "select strftime('%H:%M', time('00:00', '11 HOUR', '9 MINUTE'));"` |
| `473223f4-65f3-46ff-a9f7-7663c7e59440` | Create a new clock with an initial time -> midnight is zero hours | `{"hour": 24, "minute": 0}` | `00:00` | `STRFTIME('%H:%M', TIME('00:00', '24 HOUR', '0 MINUTE'))`. Adding `'24 HOUR'` to `'00:00'` rolls forward to the next day, and `TIME()` drops the date portion. | `sqlite3 :memory: "select strftime('%H:%M', time('00:00', '24 HOUR', '0 MINUTE'));"` |

*Note: All 52 canonical test cases are included in `tests.toml`, and none are excluded (`include = false`).*
