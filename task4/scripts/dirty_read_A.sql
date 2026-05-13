-- Dirty read (Session A)
-- ВАЖНО: выполнить в отдельной сессии A, параллельно с Session B.

USE isolation;

SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
START TRANSACTION;

SELECT 'A1 initial' AS step, owner, balance FROM accounts WHERE owner = 'alice';

UPDATE accounts SET balance = balance - 50 WHERE owner = 'alice';
SELECT 'A2 after UPDATE (not committed)' AS step, owner, balance FROM accounts WHERE owner = 'alice';

-- Держим транзакцию открытой, чтобы B смог прочитать "грязные" данные.
-- После шагов B — откатываем.
ROLLBACK;

SELECT 'A3 after ROLLBACK' AS step, owner, balance FROM accounts WHERE owner = 'alice';

