# Отчёт: сравнение cache-aside, write-through и write-back

## 1. Описание тестов

- **Система**: HTTP KV-сервис (`GET /items/{key}`, `PUT /items/{key}`), Redis как кеш, SQLite как БД.
- **Единый генератор нагрузки**: `load_generator.py` перед каждым прогоном вызывает `POST /admin/reset` с одинаковым числом строк (`seed_rows`, по умолчанию 10 000 ключей `0..9999`, значения `seed-{i}`).
- **Параметры нагрузки** (в актуальном прогоне ниже):
  - после каждого `reset`: **прогрев** **15 с** тем же профилем, затем **`POST /admin/reset-counters`**;
  - замер: **30 с**, **40** воркеров;
  - **локальность ключей**: **88%** запросов в диапазон **0..799**, **12%** — равномерно по **0..9999** (`--focus-pool 800 --focus-share 0.88`);
  - `seed_rows` / `key_space` = **10 000**.
- **Три профиля** (одинаковые для всех стратегий):
  - **read_heavy**: 80% `GET`, 20% `PUT`;
  - **balanced**: 50% / 50%;
  - **write_heavy**: 20% `GET`, 80% `PUT`.
- **Три стратегии**: три экземпляра приложения (например порты **8001 / 8002 / 8003** в `docker-compose.yml`), отличаются только `CACHE_STRATEGY` и изолированными префиксами Redis + отдельными файлами SQLite.

Метрики:

| Метрика | Как получена |
|---------|----------------|
| **Throughput (req/s)** | `total_requests / duration` на клиенте |
| **Средняя задержка** | среднее время HTTP-запроса на клиенте (`avg_latency_ms`) |
| **Обращения к БД** | счётчики `db_reads`, `db_writes` в `GET /metrics` |
| **Hit rate кеша** | `cache_hits / (cache_hits + cache_misses)` на сервере |
| **Write-back и накопление записей** | в логах генератора и в `GET /metrics`: `write_back_dirty_keys_pending` (сколько ключей ещё не сброшено в БД в момент запроса метрик), `write_back_dirty_keys_flushed_total` (сколько ключей уже слили фоновые/ручные flush) |

После полного прогона `run_benchmarks.py` создаются файлы **`benchmark_results.json`** и **`benchmark_table.md`** — их можно вставить в таблицу ниже.

## 2. Таблица результатов

Прогон на этой машине: `docker compose up -d --build`, затем рекомендуемая команда:

`python run_benchmarks.py --cache-aside http://127.0.0.1:8001 --write-through http://127.0.0.1:8002 --write-back http://127.0.0.1:8003 --duration 30 --concurrency 40 --warmup-seconds 15 --focus-pool 800 --focus-share 0.88`

Полные JSON-метрики: `benchmark_results.json` и `benchmark_table.md` в корне `task3`.

| strategy | profile | read% | rps | avg_ms | db_reads | db_writes | hit_rate | wb_dirty | wb_flushed |
|----------|---------|-------|-----|--------|----------|-----------|----------|----------|------------|
| cache_aside | read_heavy | 80 | 147.6 | 271.73 | 1035 | 911 | 0.706 | 0 | 0 |
| write_through | read_heavy | 80 | 148.9 | 269.26 | 453 | 890 | 0.873 | 0 | 0 |
| write_back | read_heavy | 80 | 144.3 | 278.25 | 385 | 851 | 0.889 | 12 | 851 |
| cache_aside | balanced | 50 | 133.0 | 301.67 | 1108 | 1978 | 0.450 | 0 | 0 |
| write_through | balanced | 50 | 127.8 | 314.65 | 266 | 1877 | 0.864 | 0 | 0 |
| write_back | balanced | 50 | 122.6 | 327.39 | 231 | 1816 | 0.872 | 40 | 1838 |
| cache_aside | write_heavy | 20 | 104.7 | 384.87 | 502 | 2531 | 0.177 | 0 | 0 |
| write_through | write_heavy | 20 | 63.6 | 633.65 | 89 | 1520 | 0.770 | 0 | 0 |
| write_back | write_heavy | 20 | 63.1 | 637.83 | 82 | 1494 | 0.781 | 36 | 1494 |

## 3. Скриншоты

лежит тут где-то он в структуре

## 4. Выводы

Сопоставление с таблицей выше (**прогрев 15 с**, **локальность 88% в 800 ключах**, затем замер **30 с**). Hit rate вырос по сравнению с равномерным доступом ко всем 10 000 ключам без прогрева.

- **Для чтения (read-heavy)**  
  **Write-through** и **write-back** дали **hit rate ~0.87–0.89** и заметно меньше **`db_reads`**, чем **cache-aside** (~0.71 и 1035 чтений БД): при записи cache-aside **инвалидирует** Redis, после чего снова идут промахи до прогрева строк. **Write-through** чуть выше по **rps** (148.9 vs 147.6 / 144.3). У **write-back** виден хвост **`wb_dirty`** и **`wb_flushed`**.

- **Для записи (write-heavy)**  
  **Cache-aside** держит **~105 rps** при низком hit rate (**~0.18**): много записей в БД и сброс кеша. **Write-through** и **write-back** (~64 rps) просели по throughput, но **сильно сократили `db_reads`** (89 / 82 против 502) и дали **hit rate ~0.77–0.78** за счёт горячего набора ключей в Redis.

- **Для смешанной нагрузки (balanced)**  
  **Cache-aside** выше по **rps** (133), но с **большим числом обращений к БД** (`db_r`/`db_w`). **Write-through** и **write-back** снижают **`db_reads`** (266 / 231) при высоком hit rate (**~0.86–0.87**), ценой чуть более высокой **avg_ms** и меньшего rps в этом замере.

---

**Воспроизводимость:** `docker compose` (порты 8001–8003), команда из раздела 2; `seed_rows` / `key_space` = 10 000. К разделу 3 приложите скрин консоли с выводом `run_benchmarks.py`.
