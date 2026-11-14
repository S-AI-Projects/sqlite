UPDATE "saddle-points"
SET
  result = (
    WITH
      cells AS (
        SELECT
          CAST(row_entry.key AS INTEGER) row_index,
          CAST(cell_entry.key AS INTEGER) column_index,
          cell_entry.value value
        FROM
          JSON_EACH(matrix) row_entry
          JOIN JSON_EACH(row_entry.value) cell_entry
        WHERE
          cell_entry.type = 'integer'
      ),
      saddle_points AS (
        SELECT
          candidate.row_index,
          candidate.column_index
        FROM
          cells candidate
        WHERE
          NOT EXISTS (
            SELECT
              1
            FROM
              cells row_cell
            WHERE
              row_cell.row_index = candidate.row_index
              AND row_cell.value > candidate.value
          )
          AND NOT EXISTS (
            SELECT
              1
            FROM
              cells column_cell
            WHERE
              column_cell.column_index = candidate.column_index
              AND column_cell.value < candidate.value
          )
      )
    SELECT
      JSON_GROUP_ARRAY(
        JSON_OBJECT(
          'row',
          row_index + 1,
          'column',
          column_index + 1
        )
      )
    FROM
      (
        SELECT
          row_index,
          column_index
        FROM
          saddle_points
        ORDER BY
          row_index,
          column_index
      )
  );
