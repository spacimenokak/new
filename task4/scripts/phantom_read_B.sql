-- Phantom read (Session B)

USE isolation;

SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

INSERT INTO items (category, price) VALUES ('book', 130);
SELECT 'B1 inserted new matching row' AS step, LAST_INSERT_ID() AS new_id;

COMMIT;

