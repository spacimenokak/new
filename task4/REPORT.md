# Отчёт: аномалии изоляции в SQL (MySQL 8 / InnoDB)

## 0. Что выбрано

Показаны 4 аномалии изоляции:

- **dirty read**
- **non-repeatable read**
- **phantom read**
- **lost update**

## 1. Как запустить стенд

В `task4/`:

1) Поднять БД:

`docker compose up -d`

После изменения `docker-compose.yml` (например, добавили монтирование `scripts`) пересоздайте контейнер, чтобы подхватились тома:

`docker compose up -d --force-recreate`

2) Открыть **две параллельные сессии** MySQL (A и B)

В Cursor / VS Code: откройте встроенный терминал (**Ctrl+`**) и добавьте второй терминал кнопкой **+** рядом с выпадающим списком терминалов или через меню терминала («Split Terminal» / разделить). В первом окне будет сессия A, во втором — B.

В **каждом** терминале выполните одну и ту же команду подключения (это два независимых клиента к одному контейнеру):

`docker exec -it isolation_mysql mysql -uroot -proot isolation`

3) Как выполнять SQL из файлов **внутри** `mysql>`

Строка вида `scripts/dirty_read_A.sql` в приглашении `mysql>` — это **не** SQL и не путь к файлу на хосте: клиент ждёт операторы SQL или служебные команды клиента.

Скрипты смонтированы в контейнере в каталог **`/scripts`**. В сессии `mysql>` используйте:

`source /scripts/имя_файла.sql`

(альтернатива: `\. /scripts/имя_файла.sql`)

Для демонстраций, где нужно **остановиться** между шагами (dirty read, non-repeatable, phantom, lost update), добавлены файлы `*_part1.sql` / `*_part2.sql` — выполняйте их по порядку, как указано в разделах ниже.

Если нужно быстро «сбросить» данные к исходным:

- `docker compose down -v`
- `docker compose up -d`

Схема и тестовые данные создаются файлом `init.sql`.

## 2. Dirty read (грязное чтение)

### 2.1 Скрипты

- `scripts/dirty_read_A.sql`, `scripts/dirty_read_B.sql` (полный текст для копирования)
- пошагово в `mysql>`: `dirty_read_A_part1.sql` / `dirty_read_A_part2.sql`, `dirty_read_B_part1.sql` / `dirty_read_B_part2.sql`

### 2.2 Шаги воспроизведения

1) Session A: `source /scripts/dirty_read_A_part1.sql` — после этого транзакция открыта, есть несохранённый `UPDATE`.
2) Session B: `source /scripts/dirty_read_B_part1.sql` — на шаге `B1` может прочитаться значение, которое **ещё не закоммичено**.
3) Session A: `source /scripts/dirty_read_A_part2.sql` — `ROLLBACK` и `A3`.
4) Session B: `source /scripts/dirty_read_B_part2.sql` — `B2` после отката A.

Полный сценарий в одном файле по-прежнему в `dirty_read_A.sql` / `dirty_read_B.sql` (удобно копировать блоками из редактора).

### 2.3 Результат

- В шаге `B1` можно увидеть “промежуточный” баланс Alice (который потом исчезает после `ROLLBACK` у A).

### 2.4 Как избежать

- **Не использовать `READ UNCOMMITTED`**. Минимально — `READ COMMITTED` (грязные чтения запретит).

### 2.5 Скриншоты

они короче вон в структуре проекта лежат

## 3. Non-repeatable read (неповторяемое чтение)

### 3.1 Скрипты

- `scripts/non_repeatable_read_A.sql`, `scripts/non_repeatable_read_B.sql`
- пошагово: `non_repeatable_read_A_part1.sql` / `non_repeatable_read_A_part2.sql`

### 3.2 Шаги воспроизведения

1) Session A: `source /scripts/non_repeatable_read_A_part1.sql` — оставить транзакцию открытой после `A1`.
2) Session B: `source /scripts/non_repeatable_read_B.sql` — обновит `bob.balance` и закоммитит.
3) Session A: `source /scripts/non_repeatable_read_A_part2.sql` — `A2` и `COMMIT`.

### 3.3 Результат

- В рамках одной транзакции A два `SELECT` одного и того же ряда могут вернуть **разные значения** (первое и второе чтение отличаются).

### 3.4 Как избежать

- Поднять уровень изоляции до **`REPEATABLE READ`** или **`SERIALIZABLE`**.
- Либо применять блокировки чтения по месту: `SELECT ... FOR UPDATE` (когда это бизнес-логически оправдано).

### 3.5 Скриншоты

вон они там вот вот

## 4. Phantom read (фантомное чтение)

### 4.1 Скрипты

- `scripts/phantom_read_A.sql`, `scripts/phantom_read_B.sql`
- пошагово: `phantom_read_A_part1.sql` / `phantom_read_A_part2.sql`

### 4.2 Шаги воспроизведения

1) Session A: `source /scripts/phantom_read_A_part1.sql` — после `A1` транзакция остаётся открытой.
2) Session B: `source /scripts/phantom_read_B.sql` — добавит строку в `items` и закоммитит.
3) Session A: `source /scripts/phantom_read_A_part2.sql` — `A2` и `COMMIT`.

### 4.3 Результат

- Два одинаковых запроса с условием (`WHERE category='book' AND price>=100`) внутри транзакции A могут вернуть **разное количество строк** (в счётчик “приходит фантом”).

### 4.4 Как избежать

- Повысить уровень изоляции до **`REPEATABLE READ`** / **`SERIALIZABLE`**.
- В “проверил-что-нет-строки → вставил” сценариях использовать:
  - уникальные ограничения + обработку конфликтов, или
  - явные блокировки диапазона (в MySQL это обычно получается через `SELECT ... FOR UPDATE` по индексируемому предикату).

### 4.5 Скриншоты

вооон там, видите?

## 5. Lost update (потерянное обновление)

### 5.1 Скрипты

- `scripts/lost_update_A.sql`, `scripts/lost_update_B.sql`
- пошагово: `lost_update_reset.sql`, `lost_update_A_part1.sql` / `lost_update_A_part2.sql`, `lost_update_B_part1.sql` / `lost_update_B_part2.sql`

### 5.2 Шаги воспроизведения

Подготовка (в любой сессии, один раз):

`source /scripts/lost_update_reset.sql`

Дальше:

1) Session A: `source /scripts/lost_update_A_part1.sql` — шаг `A1`, переменная `@a_val`.
2) Session B: `source /scripts/lost_update_B_part1.sql` — шаг `B1`, переменная `@b_val`.
3) Session A: `source /scripts/lost_update_A_part2.sql` — `UPDATE`, `COMMIT`.
4) Session B: `source /scripts/lost_update_B_part2.sql` — `UPDATE`, `COMMIT`, финальный `B3`.

### 5.3 Результат

- Ожидаемо “логически” два инкремента должны дать \(0 \rightarrow 2\), но при lost update получится \(0 \rightarrow 1\): одно обновление **затирает** другое.

### 5.4 Как избежать

- Делать атомарное изменение без read-modify-write на клиенте:
  - `UPDATE counters SET val = val + 1 WHERE id = 1;`
- Или использовать блокировку строки:
  - `SELECT val FROM counters WHERE id=1 FOR UPDATE;` + затем `UPDATE` (в той же транзакции)
- Или оптимистическую блокировку (версия):
  - `UPDATE ... SET val=?, version=version+1 WHERE id=? AND version=?` и повтор при `0 rows affected`.

### 5.5 Скриншоты

оно там тоже есть клянусь

---

## 6. Список сданных файлов

- SQL для создания схемы и данных: `task4/init.sql`
- SQL-скрипты для сессий A/B: `task4/scripts/*.sql` (в т.ч. пошаговые `*_part1.sql`, `*_part2.sql`, `lost_update_reset.sql`)
- Отчет: `task4/REPORT.md`

