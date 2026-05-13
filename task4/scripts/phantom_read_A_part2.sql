-- Session A, шаг 2: после INSERT от Session B.
SELECT 'A2 count books price>=100 (second, phantom possible)' AS step, COUNT(*) AS cnt
FROM items
WHERE category = 'book' AND price >= 100;

COMMIT;
