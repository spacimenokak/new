-- Session B, шаг 1: прочитать то же «старое» значение, что и A.
USE isolation;

SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT 'B1 read counter' AS step, val FROM counters WHERE id = 1;
SELECT val INTO @b_val FROM counters WHERE id = 1;
