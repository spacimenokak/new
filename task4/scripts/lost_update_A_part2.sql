-- Session A, шаг 2: после того как B тоже прочитал старое значение.
UPDATE counters SET val = @a_val + 1 WHERE id = 1;
SELECT 'A2 wrote val=@a_val+1' AS step, val FROM counters WHERE id = 1;

COMMIT;
