-- Non-repeatable read (Session B)

USE isolation;

SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

UPDATE accounts SET balance = balance + 30 WHERE owner = 'bob';
SELECT 'B1 updated bob' AS step, owner, balance FROM accounts WHERE owner = 'bob';

COMMIT;

