-- Session A, шаг 1: первый COUNT, транзакция открыта.
USE isolation;

SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT 'A1 count books price>=100 (first)' AS step, COUNT(*) AS cnt
FROM items
WHERE category = 'book' AND price >= 100;
