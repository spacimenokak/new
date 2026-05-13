-- Dirty read (Session B)
-- ВАЖНО: запускать пока Session A находится между UPDATE и ROLLBACK.

USE isolation;

SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
START TRANSACTION;

SELECT 'B1 read alice (dirty possible)' AS step, owner, balance
FROM accounts
WHERE owner = 'alice';

COMMIT;

-- После того как A сделает ROLLBACK, повторяем чтение уже вне транзакции.
SELECT 'B2 read after A rollback' AS step, owner, balance
FROM accounts
WHERE owner = 'alice';

