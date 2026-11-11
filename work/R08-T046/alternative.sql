-- Alternative Implementation for Meetup: Recursive Calendar Expansion (CTE Technique)
-- Instead of closed-form date modifier arithmetic, this approach dynamically generates
-- all calendar days of the month, annotates each with its weekday name, and selects
-- the desired meetup day using ordinal filtering and window functions.

UPDATE meetup
SET
  result = (
    WITH RECURSIVE
      calendar (cal_date, day_num, weekday_name) AS (
        SELECT
          date(printf('%d-%02d-01', meetup.year, meetup.month)),
          1,
          CASE strftime('%w', printf('%d-%02d-01', meetup.year, meetup.month))
            WHEN '0' THEN 'Sunday'
            WHEN '1' THEN 'Monday'
            WHEN '2' THEN 'Tuesday'
            WHEN '3' THEN 'Wednesday'
            WHEN '4' THEN 'Thursday'
            WHEN '5' THEN 'Friday'
            WHEN '6' THEN 'Saturday'
          END
        UNION ALL
        SELECT
          date(cal_date, '+1 day'),
          day_num + 1,
          CASE strftime('%w', date(cal_date, '+1 day'))
            WHEN '0' THEN 'Sunday'
            WHEN '1' THEN 'Monday'
            WHEN '2' THEN 'Tuesday'
            WHEN '3' THEN 'Wednesday'
            WHEN '4' THEN 'Thursday'
            WHEN '5' THEN 'Friday'
            WHEN '6' THEN 'Saturday'
          END
        FROM
          calendar
        WHERE
          strftime('%m', date(cal_date, '+1 day')) = printf('%02d', meetup.month)
      ),
      matching_days AS (
        SELECT
          cal_date,
          day_num,
          ROW_NUMBER() OVER (ORDER BY day_num ASC) AS occ
        FROM
          calendar
        WHERE
          weekday_name = meetup.dayofweek
      )
    SELECT
      cal_date
    FROM
      matching_days
    WHERE
      (meetup.week = 'first' AND occ = 1)
      OR (meetup.week = 'second' AND occ = 2)
      OR (meetup.week = 'third' AND occ = 3)
      OR (meetup.week = 'fourth' AND occ = 4)
      OR (meetup.week = 'teenth' AND day_num BETWEEN 13 AND 19)
      OR (meetup.week = 'last' AND occ = (SELECT MAX(occ) FROM matching_days))
  );
