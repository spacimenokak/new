-- Phantom read (Session A)
-- Намеренно ставим READ COMMITTED, чтобы фантомы проявились проще.

USE isolation;

SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT 'A1 count books price>=100 (first)' AS step, COUNT(*) AS cnt
FROM items
WHERE category = 'book' AND price >= 100;

-- Пока транзакция открыта, Session B добавляет подходящую строку и коммитит.

SELECT 'A2 count books price>=100 (second, phantom possible)' AS step, COUNT(*) AS cnt
FROM items
WHERE category = 'book' AND price >= 100;

COMMIT;

