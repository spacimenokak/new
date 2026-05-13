-- Session B, шаг 1: пока A держит транзакцию после UPDATE.
USE isolation;

SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
START TRANSACTION;

SELECT 'B1 read alice (dirty possible)' AS step, owner, balance
FROM accounts
WHERE owner = 'alice';

COMMIT;
