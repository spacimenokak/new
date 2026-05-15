# Соответствие проекта `okak` системе оценивания

Документ для преподавателя: по каждому пункту из файла «Система оценивания» указано, **что реализовано**, **зачем** и **где в репозитории** это лежит. Под ТЗ понимается документ «Практика-Дэйтинг-Бот».

Основной сдаваемый контур: `bot/`, `db/`, `worker/`, `cache/`, `rating/`, `mq/`, `metrics/`, `storage/`, `monitoring/`, `docker-compose.yml`. Папки `task1`–`task4` — отдельные учебные лабораторные, в runtime dating-бота не участвуют.

Шкала оценок: **3** — от 17 баллов, **4** — от 24, **5** — от 30 (максимум по таблице — 33 балла без дополнительных согласований с преподавателем).

---

## Пункт 1. Рейтинг (0–3 балла)

По таблице: 1 балл — хотя бы один подпункт из каждого уровня; 2 — два подпункта из каждого уровня; 3 — все подпункты из каждого уровня. Ниже — как закрыт каждый подпункт из ТЗ практики.

### Уровень 1 — первичный рейтинг

**Данные анкеты (возраст, пол, интересы, географическое положение).**  
Реализовано в `rating/rating_service.py`, метод `calculate_primary_score`: баллы начисляются за имя, возраст, город (география), пол, био, интересы и число фото. Данные берутся из модели `Profile` в `db/models.py`, заполняются при регистрации и редактировании в `bot/handlers.py` и `bot/profile_handlers.py`.

**Полнота анкеты и количество фотографий.**  
Там же: отдельные веса за длину bio и interests, метод `photo_count` считает фото из JSON-списка URL или строки. При регистрации пользователь может загрузить до трёх фото в MinIO (`bot/handlers.py`, шаг `RegisterForm.photos`, `bot/photo_utils.py`).

**Первичные предпочтения (возрастной диапазон, пол; в ТЗ также город).**  
В анкете хранятся `preferred_gender`, `preferred_age_from`, `preferred_age_to` (`db/models.py`). Они участвуют в первичном балле и в **фильтрации ленты** — функция `_viewer_filters` и `get_next_profile` в `db/crud.py` отсекают кандидатов по полу и возрасту. Отдельного поля «ищу только в городе X» в фильтре ленты нет — город учтён как поле своей анкеты в первичном рейтинге.

### Уровень 2 — поведенческий рейтинг

**Количество лайков анкеты.**  
Счётчик `total_likes` в таблице `ratings` (`db/models.py`), увеличивается в `create_interaction` при типе `like` (`db/crud.py`).

**Соотношение лайков и пропусков.**  
В `calculate_behavioral_score` считается `likes_ratio` по `total_likes` и `total_skips`.

**Частота взаимных лайков (мэтчей).**  
`total_matches` обновляется в `check_match` (`db/crud.py`); в формуле — `match_rate`.

**Частота инициирования диалогов после мэтча.**  
Поле `initiated_chats`, кнопка «Я написал(а) первым(ой)» после мэтча (`bot/keyboards.py`, callback `chat_init:` в `bot/handlers.py`).

**Активность в определённое время суток.**  
В `ratings` хранится JSON `activity_by_hour`. При событиях лайк/скип/мэтч бот пишет в Redis Stream (`bot/events.py`, `mq/publisher.py`), consumer `worker/event_consumer.py` вызывает `record_activity_hour` (`db/crud.py`). В рейтинге — метод `activity_time_score` и вклад 15% в `calculate_behavioral_score` (`rating/rating_service.py`).

### Уровень 3 — комбинированный рейтинг

**Интеграция первичного и поведенческого по весам.**  
`calculate_combined`: `0.4 * primary + 0.6 * behavioral` (`rating/rating_service.py`).

**Реферальная система (приглашение друзей).**  
Таблица `referrals`, поля `referral_code`, `invited_by_id`, `referral_bonus` (`db/models.py`). Логика начисления — `apply_referral_on_register`, `sync_referral_bonus` (`db/crud.py`). В боте: `/invite`, deep-link `/start ref_КОД` (`bot/referral_handlers.py`, `bot/handlers.py`).

### Дополнительно по ТЗ практики (рейтинг)

**Отдельная таблица рейтингов и пересчёт через Celery.**  
Модель `Rating`, пересчёт при взаимодействиях в `db/crud.py`, фоновый полный пересчёт — задачи `recalculate_all_ratings` / `recalculate_user_rating` в `worker/tasks.py`, расписание в `worker/celery_app.py` (beat). Админ: `/admin_recalc`, `/admin_recalc_all` (`bot/admin_handlers.py`).

**Выдача ленты по рейтингу.**  
`get_next_profile` сортирует по `combined_score` по убыванию (`db/crud.py`).

---

## Пункт 2. Использование Redis (0–2 балла)

По пояснению: если Redis используется **только** как транспорт для Celery — максимум 1 балл. В проекте Redis применяется в **трёх разных ролях** на одном сервере, разные logical DB — это обоснованное использование сверх «только Celery».

**Кэш предварительно отранжированной ленты (ТЗ: ~10 анкет в Redis).**  
Зачем: не ходить в PostgreSQL на каждый «следующий профиль».  
Где: `cache/redis_client.py` — ключи `feed:{user_id}`, `rpush`/`lpop`, TTL 3600 с. Использование в `show_next_profile` (`bot/handlers.py`): первая анкета из БД, остальные id — в очереди Redis; при опустошении очереди — новая порция из `get_next_profile(..., limit=10)`.

**Брокер и backend Celery.**  
Зачем: вынести тяжёлый периодический пересчёт рейтингов из процесса бота.  
Где: `CELERY_BROKER_URL=redis://.../1`, `CELERY_RESULT_BACKEND=redis://.../2` в `docker-compose.yml` и `.env.example`; конфигурация `worker/celery_app.py`.

**Поток доменных событий (MQ на Redis, не только Celery).**  
Зачем: асинхронная обработка лайков/скипов/мэтчей для активности по часам и метрик без блокировки ответа пользователю.  
Где: stream `dating:events` в DB `3` — публикация `mq/publisher.py`, вызов из `bot/events.py` после действий в `bot/handlers.py`; consumer — `worker/event_consumer.py`, обработка `worker/event_handlers.py`.

---

## Пункт 3. Использование Celery (0–2 балла)

Зачем: полный пересчёт всех рейтингов по расписанию (тысячи анкет) не должен выполняться в момент нажатия кнопки в Telegram.

Где: пакет `worker/` — `celery_app.py` (приложение, beat раз в `CELERY_BEAT_RECALC_SEC`, по умолчанию 3600 с), `tasks.py` (асинхронный пересчёт через SQLAlchemy). В compose — сервисы `celery_worker` и `celery_beat` (`docker-compose.yml`).

Точечный пересчёт по команде админа — `recalculate_user_rating.delay()` / `recalculate_all_ratings.delay()` (`bot/admin_handlers.py`).

Синхронный пересчёт при каждом лайке в `db/crud.py` оставлен для актуальности ленты сразу; Celery дополняет это **массовым** и **периодическим** пересчётом — так использование обосновано, а не «Celery ради Celery».

---

## Пункт 4. Применение MQ-брокера (0–2 балла)

По пояснению: брокер **только** под Celery — 1 балл; отдельная шина событий — до 2 баллов.

В проекте по README и реализации MQ — **Redis Stream** (альтернатива Kafka/RabbitMQ из ТЗ).

Зачем: потоковая обработка событий взаимодействия с анкетами (лайк, скип, мэтч, инициация чата) между ботом и фоновым обработчиком.

Где: после `commit` в PostgreSQL бот публикует JSON в stream (`mq/publisher.py`, `XADD`); отдельный процесс `event_consumer` в compose читает через consumer group (`worker/event_consumer.py`), обновляет `activity_by_hour`, счётчики Prometheus и пересчитывает рейтинг (`worker/event_handlers.py`).

RabbitMQ в основном `docker-compose.yml` **не используется** — единый Redis, как в описании архитектуры проекта.

---

## Пункт 5. Метрики и логирование (0–2 балла)

Зачем: наблюдать нагрузку и ошибки при демонстрации и отладке; не логировать «каждый чих» в консоль.

**Метрики (Prometheus).**  
Счётчики в `metrics/prometheus_metrics.py` (`dating_likes_total`, `dating_skips_total`, `dating_matches_total`, `dating_feed_requests_total`, события Redis, рефералы, S3, ошибки хендлеров). HTTP-сервер — `metrics/http_server.py`: эндпоинты `/metrics` и `/health` на порту `9100` (запуск из `bot/main.py`).

**Графики (Grafana).**  
Зачем: наглядная демонстрация на зачёте, не только сырой текст метрик.  
Где: `monitoring/prometheus.yml` (scrape с `host.docker.internal:9100` для бота на хосте и `bot:9100` для бота в Docker), `monitoring/grafana/` — provisioning и дашборд `dashboards/dating-bot.json`; сервисы `prometheus` и `grafana` в `docker-compose.yml`. Открыть: http://localhost:3000 (логин `admin`, пароль `dating`).

**Логирование.**  
Модуль `logging` с форматом и уровнем INFO в `bot/main.py`. В хендлерах — осмысленные сообщения с `user_id` и контекстом, например `logger.exception("show_next_profile failed for user %s", user_id)` в `bot/handlers.py`, а не безликое «Error happened».

---

## Пункт 6. S3-хранилище (0–2 балла)

Зачем: хранить бинарные фото отдельно от PostgreSQL; в БД — только URL (как в ТЗ с MinIO).

Где: S3-совместимый **MinIO** в `docker-compose.yml` (сервисы `minio`, `minio_init` — bucket `dating-photos`). Клиент — `storage/s3_client.py` (`upload_bytes`, `ensure_bucket`). Загрузка из Telegram при регистрации и в редактировании поля «Фото» — `bot/photo_utils.py`, `bot/handlers.py`, `bot/profile_handlers.py`. В профиле URL сохраняются в `profiles.photo_urls` (`db/models.py`).

Публичные ссылки для отображения задаются через `S3_PUBLIC_BASE` в `.env.example`.

---

## Пункт 7. Настройка CI/CD для бота (0–1 балл)

Зачем: автоматическая проверка при push/PR, что код собирается и тесты проходят.

Где: `.github/workflows/ci.yml` — workflow **CI** на GitHub Actions:

- job **test** — Python 3.12, `pip install -r requirements.txt`, `pytest` (в т.ч. `tests/test_rating_service.py`);
- job **docker** — сборка образа из `Dockerfile`, проверка `docker compose config`.

Триггеры: ветки `main` и `master`. CD (автодеплой на сервер) не настроен — для практики достаточно CI; деплой локально через `docker compose up`.

---

## Пункт 8. Другое (0–2 балла за каждый согласованный пункт)

Дополнительные решения, которые можно показать преподавателю как «сверх таблицы» или в рамках п.8:

**Пауза знакомств.**  
Кнопка «Устал знакомиться» ставит `profiles.is_active = false` (`set_profile_active` в `db/crud.py`, `bot/handlers.py`). Анкета не попадает в чужую ленту (`get_next_profile` фильтрует `is_active == True`), **мэтчи и история не удаляются**. Возврат — «Снова знакомиться». Зачем: реальный UX dating-приложения.

**Grafana + Prometheus** — см. п.5; отдельная связка для мониторинга.

**Реферальные ссылки** — см. рейтинг, уровень 3.

**Индексы БД** под ленту и взаимодействия — `_STAGE4_INDEX_DDL` в `db/database.py`, применяются в `init_db` (сервис `migrate` в compose). Зачем: ускорение выдачи анкет при росте данных (этап 4 ТЗ — оптимизация БД).

---

## Пункт 9. Этапы продукта (12+ баллов по подпунктам)

Каждый подпункт ниже соответствует строке из таблицы «Этапы продукта» (0–3 балла каждый, JMeter — 0–1).

### 9.1. Планирование и проектирование (первый этап ТЗ)

Реализовано описанием сервисов и схемой развёртывания: `docker-compose.yml` (postgres, redis, minio, bot, event_consumer, celery_worker, celery_beat, prometheus, grafana), `README.md` (архитектура, потоки, Redis как MQ). Схема данных — модели SQLAlchemy `db/models.py` (`users`, `profiles`, `ratings`, `interactions`, `matches`, `referrals`), инициализация `db/database.py`, `init_db.py`. Репозиторий под git для отслеживания прогресса.

Замечание: в README часть текста описывает идеальную схему с REST API; фактически сдаётся **Telegram-бот (aiogram)** с прямым доступом к БД — на зачёте ориентироваться на этот документ и актуальный compose.

### 9.2. Разработка базовой функциональности (второй этап ТЗ)

Telegram Bot API через **aiogram 3**: точка входа `bot/main.py`, роутеры `bot/handlers.py`, `bot/profile_handlers.py`, `bot/admin_handlers.py`, `bot/referral_handlers.py`. Регистрация по `telegram_id` на `/start`, пошаговый FSM (`RegisterForm` в `bot/handlers.py`), сохранение пользователя в `users` (`db/models.py`).

### 9.3. Система анкет и ранжирования (первые два пункта третьего этапа ТЗ)

**CRUD анкет:** создание при регистрации, редактирование и удаление — `bot/profile_handlers.py`, `bot/profile_menu.py`, функции в `db/crud.py` (`create_profile`, `update_profile`, `delete_profile`).

**Алгоритм ранжирования:** три уровня рейтинга — пакет `rating/`, см. пункт 1; выдача ленты по `combined_score`.

### 9.4. База данных

PostgreSQL 15 в `docker-compose.yml`. Async доступ: SQLAlchemy 2 + asyncpg (`db/database.py`). Схема создаётся и мигрируется при старте (`init_db`, ALTER для новых колонок). Данные: пользователи, анкеты, рейтинги, взаимодействия, мэтчи, рефералы.

### 9.5. Бот работает, ручные тесты

Сценарии для проверки на зачёте: `/start` и регистрация; лента («Следующая анкета» / `/next`); лайк и скип; мэтч и уведомления; `/profile`, редактирование; `/invite`; пауза «Устал знакомиться»; метрики и Grafana.

Запуск: `docker compose up -d` для инфраструктуры; бот с VPN часто удобнее на хосте — `python -m bot.main` (`.env` с `BOT_TOKEN`, `DATABASE_URL` на `localhost`). Метрики: http://localhost:9100/health , Grafana http://localhost:3000 .

### 9.6. Нагрузочное тестирование (JMeter)

План `tests/jmeter/dating_bot_load.jmx` — нагрузка на `/health` и `/metrics` бота (порт 9100). Зачем: проверить устойчивость эндпоинтов мониторинга под нагрузкой; альтернативные форматы по согласованию с преподавателем.

### 9.7. Другие этапы (по согласованию)

Можно отнести к доп. этапам ТЗ / п.8:

- **Интеграция через MQ** — Redis Stream, см. пункт 4.
- **Кэширование анкет в Redis** — см. пункт 2.
- **Отложенные задачи Celery** — см. пункт 3.
- **Оптимизация БД** — индексы в `db/database.py`.
- **Тестирование** — `tests/test_rating_service.py`, `pytest.ini`, CI.
- **Деплой** — `Dockerfile`, `docker compose up` локально или на сервере.

---

## Кратко: что показать на зачёте

1. Бот в Telegram: регистрация, лента, лайк/скип, мэтч.  
2. Redis: объяснить кэш ленты + stream событий + Celery (три роли).  
3. Celery beat в логах `celery_beat`.  
4. MinIO / загрузка фото.  
5. http://localhost:9100/metrics и дашборд Grafana.  
6. GitHub Actions — зелёный CI.  
7. Опционально: пауза «Устал знакомиться», `/invite`.

---

*Документ соответствует структуре «Система оценивания.docx»; пути — относительно корня репозитория `okak`.*
