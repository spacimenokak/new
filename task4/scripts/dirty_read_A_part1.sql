-- Session A, шаг 1: открыта транзакция с UPDATE без COMMIT/ROLLBACK.
USE isolation;

SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
START TRANSACTION;

SELECT 'A1 initial' AS step, owner, balance FROM accounts WHERE owner = 'alice';

UPDATE accounts SET balance = balance - 50 WHERE owner = 'alice';
SELECT 'A2 after UPDATE (not committed)' AS step, owner, balance FROM accounts WHERE owner = 'alice';
