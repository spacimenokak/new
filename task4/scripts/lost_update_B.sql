-- Lost update (Session B)
-- Запустить параллельно с Session A так, чтобы оба прочитали val=0.

USE isolation;

SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT 'B1 read counter' AS step, val FROM counters WHERE id = 1;
SELECT val INTO @b_val FROM counters WHERE id = 1;

-- После того как A закоммитил, мы всё равно пишем "на основе старого прочтения",
-- тем самым затираем инкремент A (если оба начинали с 0, оба запишут 1).
UPDATE counters SET val = @b_val + 1 WHERE id = 1;
SELECT 'B2 wrote val=@b_val+1 (may overwrite)' AS step, val FROM counters WHERE id = 1;

COMMIT;

SELECT 'B3 final counter' AS step, val FROM counters WHERE id = 1;

