-- Один раз в любой сессии перед демонстрацией lost update.
USE isolation;

UPDATE counters SET val = 0 WHERE id = 1;
SELECT 'counter reset' AS step, val FROM counters WHERE id = 1;
