-- Session A, шаг 2: после того как B закоммитил изменение bob.
SELECT 'A2 second read (may differ)' AS step, owner, balance FROM accounts WHERE owner = 'bob';

COMMIT;
