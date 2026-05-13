-- Session B, шаг 2: после ROLLBACK у Session A.
SELECT 'B2 read after A rollback' AS step, owner, balance
FROM accounts
WHERE owner = 'alice';
