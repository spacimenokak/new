# Документация проекта: Dating Telegram Bot

## 1. Описание проекта

Dating Telegram Bot — это бот-знакомств, с которым пользователь взаимодействует в Telegram.  
Пользователь регистрируется, заполняет анкету, получает ленту анкет других людей, ставит лайки/скипы и получает мэтчи при взаимной симпатии.

Цель проекта: реализовать учебное dating-приложение с рейтинговой системой в формате Telegram-бота, используя очереди, кэширование, фоновые задачи и S3-хранилище.

***

## Быстрый запуск (как есть в этом репозитории)

1. Скопируй `.env.example` в `.env` и заполни `BOT_TOKEN`.
2. Подними инфраструктуру:

```bash
docker compose up -d
```

3. Запусти бота:

```bash
python -m bot.main
```

Примечание: если сеть/провайдер блокирует доступ к `api.telegram.org`, polling не сможет стартовать — в этом случае нужен VPN/прокси на машине, где запускается бот.

***

## 2. Архитектура системы

Архитектура — **логически модульная, физически монолит + фоновые воркеры**:  
- один веб-сервис (FastAPI) с модулями: Users, Profiles, Matching, Rating, Admin;  
- отдельный Celery-воркер для фоновых задач;  
- Telegram-бот как отдельный процесс, который обращается к API.

### 2.1 Компоненты

1. **Telegram Bot Service**  
   - Принимает сообщения от пользователей через Telegram Bot API.  
   - Отправляет запросы в Backend API (регистрация, анкеты, лайки, получение следующей анкеты).

2. **Backend API (Application Service)**  
   - Реализует REST API.  
   - Модули:  
     - Auth/Users — идентификация по `telegram_id`.  
     - Profiles — CRUD анкет, загрузка фото.  
     - Matching — выдача следующей анкеты, фиксация лайков/скипов, генерация мэтчей.  
     - Rating — чтение и обновление рейтингов.

3. **База данных (PostgreSQL)**  
   - Хранит пользователей, анкеты, рейтинги, мэтчи, историю взаимодействий.

4. **Кэш (Redis)**  
   - Хранит:  
     - предварительно отранжированные списки анкет для пользователя (`feed`); 

5. **Очередь сообщений (MQ)**  
   - Redis. Используется для потоковой обработки событий взаимодействия с анкетами (лайк/скип/мэтч) между Backend и Celery-воркером.

6. **Celery Worker**  
   - Обрабатывает события взаимодействий (like/skip/match) асинхронно.  
   - Регулярно пересчитывает рейтинги (primary/behavioral/combined).  
   - Обновляет таблицу рейтингов и кэш в Redis.

7. **S3-хранилище (Minio)**  
   - Хранит изображения анкет.  
   - API-приложение хранит в БД только ключи/URL.

***

## 3. Логические потоки

### 3.1 Регистрация и профиль

1. Пользователь пишет `/start` боту.  
2. Бот отправляет запрос в `POST /users/telegram-register` с `telegram_id` и базовыми данными.  
3. Backend создаёт пользователя, возвращает статус.  
4. Бот по шагам собирает данные анкеты и отправляет их в `POST /profiles`.

### 3.2 Выдача анкет (Matching)

1. Пользователь нажимает «Следующая анкета» / «Лайк» / «Скип».  
2. Бот обращается к `GET /matching/next` или `POST /matching/like|skip`.  
3. Backend:  
   - пытается взять id следующей анкеты из Redis (`feed:{user_id}`);  
   - если кэш пуст — генерирует новый список анкет из БД по комбинированному рейтингу и предпочтениям, кладёт в Redis.

### 3.3 События и пересчёт рейтинга

1. При лайке/скипе Backend:  
   - пишет запись в таблицу `interactions`;  
   - отправляет событие в MQ (`interaction_event`).  
2. Celery-воркер читает события:  
   - обновляет агрегаты в таблице `ratings` (likes, skips, matches, initiated_chats);  
   - помечает пользователей для пересчёта комбинированного рейтинга.
3. Периодически (каждые 5–15 минут, в зависимости от нагрузки) Celery запускает задачу:  
   - пересчитывает `primary_score`, `behavioral_score`, `combined_score`;  
   - обновляет кэш в Redis (списки анкет по рейтингу).

***

## 4. Схема данных (БД)

### 4.1 Таблица `users`

```sql
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 4.2 Таблица `profiles`

```sql
CREATE TABLE profiles (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    age INT CHECK (age >= 18 AND age <= 100),
    gender VARCHAR(20) CHECK (gender IN ('male', 'female')),
    city VARCHAR(255),
    bio TEXT,
    preferred_gender VARCHAR(20),
    preferred_age_from INT,
    preferred_age_to INT,
    preferred_city VARCHAR(255),
    photos JSONB DEFAULT '[]',
    is_filled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 4.3 Таблица `ratings`

```sql
CREATE TABLE ratings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    primary_score   DECIMAL(5,2) DEFAULT 0.0,
    behavioral_score DECIMAL(5,2) DEFAULT 0.0,
    combined_score  DECIMAL(5,2) DEFAULT 0.0,
    total_likes     INT DEFAULT 0,
    total_skips     INT DEFAULT 0,
    total_matches   INT DEFAULT 0,
    initiated_chats INT DEFAULT 0,
    referrals_count INT DEFAULT 0,
    is_new          BOOLEAN DEFAULT TRUE,
    new_user_boost  DECIMAL(5,2) DEFAULT 1.0,
    last_calculated_at TIMESTAMP DEFAULT NOW()
);

```

### 4.4 Таблица `interactions`

```sql
CREATE TABLE interactions (
    id BIGSERIAL PRIMARY KEY,
    actor_id BIGINT NOT NULL REFERENCES users(id),
    target_id BIGINT NOT NULL REFERENCES users(id),
    type VARCHAR(10) CHECK (type IN ('like', 'skip')),
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 4.5 Таблица `matches`

```sql
CREATE TABLE matches (
    id BIGSERIAL PRIMARY KEY,
    user1_id BIGINT NOT NULL REFERENCES users(id),
    user2_id BIGINT NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'active',
    CHECK (user1_id < user2_id)
);
```

### 4.6 Таблица `referrals`

```sql
CREATE TABLE referrals (
    id BIGSERIAL PRIMARY KEY,
    inviter_id BIGINT NOT NULL REFERENCES users(id),
    invited_id BIGINT NOT NULL REFERENCES users(id),
    invited_bonus DECIMAL(5,2) DEFAULT 0.1,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (invited_id)
);
```

***

## 5. Алгоритм рейтинга

Рейтинг состоит из трёх уровней (как в ТЗ).

### 5.1 Уровень 1: Первичный рейтинг

Используем данные анкеты и заполненность.

- Факторы:  
  - полнота анкеты (`is_filled`, количество фото);  
  - соответствие базовым требованиям (возраст, город, пол);  
  - корректность заполнения (нет пустых критичных полей).  

Пример расчёта:

- `completeness` от 0 до 1:  
  - +0.4 за заполненные `name`, `age`, `gender`, `city`;  
  - +0.3 за наличие `bio`;  
  - +0.3 за 3+ фото.  
- `preferences_match` от 0 до 1:  
  - учитывает, насколько профиль подходит по возрасту, полу и городу для других пользователей.

Псевдоформула:  
- `primary_score = 0.5 * completeness + 0.5 * preferences_match`.

### 5.2 Уровень 2: Поведенческий рейтинг

Фокус на активности и реакции других пользователей.

Факторы:

- `likes_ratio = total_likes / (total_likes + total_skips)` (при `total_likes + total_skips > 0`).  
- `match_rate = total_matches / NULLIF(total_likes, 0)`.  
- `initiation_rate = initiated_chats / NULLIF(total_matches, 0)`.  
- активность по времени суток (можно вести простую статистику и повышать рейтинг активных в прайм-тайм).

Псевдоформула:  
- `behavioral_score = 0.4 * likes_ratio + 0.3 * match_rate + 0.3 * initiation_rate`.

### 5.3 Уровень 3: Комбинированный рейтинг

Объединяем первичный и поведенческий рейтинг и добавляем реферальные бонусы.

- Для обычных пользователей (`is_new = FALSE`):
  `combined_score = 0.4 * primary_score + 0.6 * behavioral_score + referrals_bonus`

- Для новых пользователей (`is_new = TRUE`):
  `combined_score = primary_score + new_user_boost + invited_bonus`

Пользователь считается «новым», пока у него `total_likes + total_skips < 10`. После достижения порога `is_new` переводится в `FALSE`, `new_user_boost` больше не применяется, и рейтинг считается по обычной формуле.

- `referrals_bonus = min(referrals_count * 0.05, 0.3)`.
- `invited_bonus` берётся из таблицы `referrals` (по `invited_id`), по умолчанию `0.1`.

***

## 6. Применение Redis, Celery, MQ, S3, логов и метрик

### 6.1 Redis

Используется для:  
- кэширования очереди анкет: ключ `feed:{user_id}` → список `profile_id` в порядке `combined_score`;  

Обоснование:  
- уменьшает количество тяжёлых запросов с сортировкой и фильтрацией в БД;  
- ускоряет выдачу следующей анкеты до O(1) (pop из списка).

### 6.2 Celery + MQ

- MQ: Redis, используется как брокер задач Celery (`interaction_event`, `match_event`).  
- Celery:
  - обрабатывает каждое событие, обновляя агрегаты в `ratings`;
  - запускает плановые задачи: пересчёт рейтингов каждые 5–15 минут, обновление кэша;
  - при пересчёте рейтингов определяет `is_new` на основе `total_likes` и `total_skips`.

Обоснование:  
- долгие операции не блокируют ответы API/бота;  
- можно масштабировать воркеры независимо от основного приложения.


### 6.3 S3 (Minio)

- При загрузке фото бот отправляет файл на Backend.  
- Backend загружает изображение в Minio и сохраняет ключ/URL в `profiles.photos`.

Обоснование:  
- удобная работа с файлами, бэкапами и масштабированием;  
- не засоряем файловую систему или базу.

### 6.4 Логирование и метрики

- Логирование: структурированные JSON-логи, уровни INFO/ERROR.  
- Метрики (Prometheus или простые счётчики/таймеры):  
  - время ответа `GET /matching/next`,  
  - количество событий лайк/скип,  
  - hit/miss Redis по фиду.

***

## 7. Основные API эндпоинты

Базовый URL: `/api/v1`.

### 7.1 Users

- `POST /users/telegram-register`  
  - Вход: `{ telegram_id, username }`  
  - Результат: создание/получение user.

### 7.2 Profiles

- `POST /profiles`  
  - Создание/обновление анкеты пользователя.  
- `GET /profiles/me?telegram_id=...`  
  - Получение своей анкеты.  
- `POST /profiles/photo`  
  - Вход: file;  
  - Действие: загрузка в Minio, добавление ключа в `photos`.

### 7.3 Matching

- `GET /matching/next?telegram_id=...`  
  - Возвращает следующую подходящую анкету (из Redis, при необходимости заполняет Redis из БД).  
- `POST /matching/like`  
  - Вход: `{ telegram_id, target_profile_id }`.  
  - Действие: создаёт `interaction`, отправляет событие в MQ, при взаимном лайке создаёт `match`.  
- `POST /matching/skip`  
  - Аналогично лайку, но type = `skip`.

### 7.4 Rating

- `GET /rating/me?telegram_id=...`  
  - Возвращает текущий `primary_score`, `behavioral_score`, `combined_score`.  
- `POST /rating/recalculate`  
  - Закрытый эндпоинт для запуска пересчёта (для дебага/админки).

### 7.5 Referrals

- `POST /referrals/use`  
  - Вход: `{ telegram_id, referral_code }`.  
- `GET /referrals/me?telegram_id=...`  
  - Список приглашённых пользователей.

***
## 8. Технологический стек

- Язык: Python 3.10+.
- Бот: **aiogram 3.x**.
- Backend: **FastAPI**.
- БД: PostgreSQL.
- Кэш: Redis.
- Очередь (MQ): Redis (брокер задач Celery).
- Фоновые задачи: Celery.
- Хранилище файлов: Minio (S3-совместимое).
- Логирование: `loguru`.
- Метрики: `prometheus_client` (опционально).

***

## 9. CI/CD (минимальный вариант)

- CI (GitHub Actions):  
  - запуск тестов;  
  - линтер;  
  - сборка Docker-образа. 
- CD:
  - деплой через `docker-compose` на один сервер:
    - сервис backend;
    - сервис bot;
    - postgres;
    - redis (кэш + брокер Celery);
    - minio;
    - worker (celery).


***