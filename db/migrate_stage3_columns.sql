-- Добавляет колонки, которые есть в models.py, но могли отсутствовать в старых БД (create_all не меняет существующие таблицы).
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS interests VARCHAR(500);
ALTER TABLE ratings ADD COLUMN IF NOT EXISTS initiated_chats INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ratings ADD COLUMN IF NOT EXISTS referral_bonus DOUBLE PRECISION NOT NULL DEFAULT 0.0;

-- Уникальность пары (actor, target) — только если дубликатов ещё нет
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'uq_interactions_actor_target'
  ) THEN
    ALTER TABLE interactions ADD CONSTRAINT uq_interactions_actor_target UNIQUE (actor_id, target_id);
  END IF;
END $$;
