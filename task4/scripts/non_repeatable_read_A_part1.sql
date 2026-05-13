-- Session A, шаг 1: первое чтение, транзакция остаётся открытой.
USE isolation;

SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT 'A1 first read' AS step, owner, balance FROM accounts WHERE owner = 'bob';
