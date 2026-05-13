-- Session B, шаг 2: после COMMIT у Session A.
UPDATE counters SET val = @b_val + 1 WHERE id = 1;
SELECT 'B2 wrote val=@b_val+1 (may overwrite)' AS step, val FROM counters WHERE id = 1;

COMMIT;

SELECT 'B3 final counter' AS step, val FROM counters WHERE id = 1;
