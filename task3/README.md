# Практика: сравнение типов кеширования (task3)

Одна KV-система (`GET/PUT` по строковому ключу) в трёх вариантах:

| Стратегия | Чтение | Запись |
|-----------|--------|--------|
| **Cache-aside (lazy)** | Redis → при miss SQLite → запись в Redis | Сразу SQLite, ключ в Redis инвалидируется |
| **Write-through** | Как cache-aside | SQLite + Redis синхронно |
| **Write-back** | Как cache-aside | Сначала Redis + множество «грязных» ключей; фоновая сливка в SQLite |

Стек: **FastAPI**, **Redis**, **SQLite** (WAL). Нагрузка: **единый** скрипт `load_generator.py` / оркестратор `run_benchmarks.py`.

## Быстрый старт

1. Поднять Redis и три приложения:

```bash
cd task3
docker compose up -d --build
```

2. Дождаться готовности (`/health` на портах 8001–8003), затем прогнать все сценарии:

```bash
python -m pip install -r requirements.txt
python run_benchmarks.py ^
  --cache-aside http://127.0.0.1:8001 ^
  --write-through http://127.0.0.1:8002 ^
  --write-back http://127.0.0.1:8003 ^
  --duration 30 --concurrency 40
```

На Linux/macOS замените `^` на `\` для переноса строк.

3. Результаты: `benchmark_results.json`, `benchmark_table.md`. Логи прогона — в консоли (stderr): throughput, db_reads/db_writes, hit rate; для write-back — `dirty_pending` и накопленный `flushed_total`.

**Прогрев и локальность ключей** (выше hit rate, нагляднее сравнение стратегий):

```bash
python run_benchmarks.py --cache-aside http://127.0.0.1:8001 --write-through http://127.0.0.1:8002 --write-back http://127.0.0.1:8003 --duration 30 --concurrency 40 --warmup-seconds 15 --focus-pool 800 --focus-share 0.88
```

После прогрева вызывается `POST /admin/reset-counters` — сбрасываются только серверные счётчики, Redis/SQLite не очищаются.


## Одиночный прогон (тот же тест)

```bash
python load_generator.py --url http://127.0.0.1:8001 --read-ratio 0.8 --duration 30
```

Перед каждым прогоном вызывается `POST /admin/reset` с одинаковым `seed_rows` (по умолчанию 10 000 ключей `0..9999`).

## API

- `GET /items/{key}` — чтение через кеш (логика зависит от `CACHE_STRATEGY`)
- `PUT /items/{key}` + JSON `{"value":"..."}` — запись
- `GET /metrics` — throughput на стороне клиента считает генератор; на сервере: `db_reads`, `db_writes`, `cache_hits`/`cache_misses`, `cache_hit_rate`, для write-back — `write_back_dirty_keys_pending`, `write_back_dirty_keys_flushed_total`
- `POST /admin/reset` — очистка Redis+SQLite и одинаковый сид данных
- `POST /admin/reset-counters` — сброс только метрик (для фазы замера после warmup)
- `POST /admin/flush` — только write-back: немедленная сливка грязных ключей в БД

## Локальный запуск одного варианта (без Compose)

```bash
docker run -d -p 6379:6379 redis:7-alpine
set CACHE_STRATEGY=write_through
set REDIS_URL=redis://127.0.0.1:6379/0
set DB_PATH=./data/local.db
python -m uvicorn app.main:app --reload --port 8000
```

## Git

Папка `task3` должна быть закоммичена вместе с остальным репозиторием. Отчёт — `REPORT.md` (таблица после прогона, выводы, скриншоты консоли добавьте вручную в отчёт или рядом в репозитории по договорённости с преподавателем).
