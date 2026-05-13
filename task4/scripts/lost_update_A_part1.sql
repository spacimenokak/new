-- Session A, шаг 1: прочитать val и @a_val; не выполнять UPDATE, пока B не прочитал.
USE isolation;

SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT 'A1 read counter' AS step, val FROM counters WHERE id = 1;
SELECT val INTO @a_val FROM counters WHERE id = 1;
