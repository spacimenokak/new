-- Lost update (Session A)
-- Демонстрация "потерянного обновления" через read-modify-write на стороне клиента.

USE isolation;

SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT 'A1 read counter' AS step, val FROM counters WHERE id = 1;
SELECT val INTO @a_val FROM counters WHERE id = 1;

-- Не выполняйте UPDATE сразу: сначала дайте Session B тоже прочитать старое значение.
UPDATE counters SET val = @a_val + 1 WHERE id = 1;
SELECT 'A2 wrote val=@a_val+1' AS step, val FROM counters WHERE id = 1;

COMMIT;

