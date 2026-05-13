-- Session A, шаг 2: после шагов Session B — откат и финальное чтение.
ROLLBACK;

SELECT 'A3 after ROLLBACK' AS step, owner, balance FROM accounts WHERE owner = 'alice';
