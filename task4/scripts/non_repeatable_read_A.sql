-- Non-repeatable read (Session A)
-- REPEATABLE READ предотвращает это, поэтому намеренно ставим READ COMMITTED.

USE isolation;

SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT 'A1 first read' AS step, owner, balance FROM accounts WHERE owner = 'bob';

-- Пока транзакция открыта, Session B меняет bob.balance и коммитит.

SELECT 'A2 second read (may differ)' AS step, owner, balance FROM accounts WHERE owner = 'bob';

COMMIT;

