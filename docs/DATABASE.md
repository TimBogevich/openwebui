# База данных — схема и справочник

## Обзор

PostgreSQL 16 с расширениями `pgvector`, `pg_trgm` и `pgcrypto`. Все числовые показатели хранятся в типизированных колонках (schema v2, без JSONB).

## Расширения

```sql
CREATE EXTENSION pgcrypto;     -- gen_random_uuid()
CREATE EXTENSION pg_trgm;      -- триграмный нечёткий поиск
CREATE EXTENSION vector;       -- векторные эмбеддинги (pgvector)
```

## ER-диаграмма (основные таблицы)

```
reports (1) ──→ report_sheets (N) ──→ metrics (N)
                                   ├─→ investment_metrics (N)
                                   └─→ report_comments (N)

dept_codes (справочник, JOIN: metrics.responsible = dept_codes.code)

Все spravki_* таблицы связываются через report_date
```

## Таблицы

### `reports` — доклады ГЦУ

Одна строка на каждый загруженный .xlsx файл.

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid PK | Идентификатор |
| `filename` | varchar(512) | Имя файла |
| `report_date` | date | Дата доклада |
| `baseline_year` | int2 | Год сравнения для `*_to_prev_year` (Март 2022 → 2021, Апрель 2026 → 2025) |
| `sha256` | varchar(64) UNIQUE | Хеш файла (дедупликация) |
| `sheets_count` | int4 | Количество листов |
| `metrics_count` | int4 | Количество показателей |
| `red_count` | int4 | Красная зона (критично) |
| `yellow_count` | int4 | Жёлтая зона |
| `green_count` | int4 | Зелёная зона (норма) |
| `created_at` | timestamptz | Время создания |

### `report_sheets` — листы доклада

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid PK | Идентификатор |
| `report_id` | uuid FK→reports | Ссылка на доклад |
| `sheet_name` | varchar(256) | Название листа |
| `sheet_index` | int4 | Порядковый номер |
| `row_count` | int4 | Число строк |
| `has_text_cols` | bool | Есть ли текстовые колонки |

### `metrics` — оперативные показатели (20 355 строк)

Основная таблица. Листы «Доклад Ц ЦЗ» и «Срок доставки». Все числа в `float8`.

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid PK | Идентификатор |
| `report_id` | uuid FK→reports | Ссылка на доклад |
| `sheet_id` | uuid FK→report_sheets | Ссылка на лист |
| `indicator_number` | varchar(255) | Номер показателя («1.1.7») |
| `parent_indicator` | varchar(255) | Родительский номер («1.1») |
| `is_priority` | bool | Приоритетный (флаг «*» в источнике) |
| `section_roman` | varchar(16) | Раздел («I», «II»…) |
| `name` | varchar(512) | Наименование показателя |
| `category` | varchar(256) | Тема («1. ГРУЗОВЫЕ ПЕРЕВОЗКИ») |
| `road` | varchar(64) | Дорога (NULL для сводных строк) |
| `unit` | varchar(64) | Единица измерения |
| `responsible` | varchar(64) | Код ответственного (ЦД, ЦТ, ЦФТО…) |
| `zone` | int2 | 0=зелёная, 1=жёлтая, 2=красная, 4=особая |
| `day_fact` | float8 | Факт за сутки |
| `day_to_plan` | float8 | Отклонение от плана за сутки (доля, -0.097 = -9.7%) |
| `day_to_prev_year` | float8 | Отклонение к прошлому году за сутки |
| `month_fact` | float8 | Факт за месяц (нарастающим итогом) |
| `month_to_plan` | float8 | Отклонение от плана за месяц |
| `month_to_prev_yr` | float8 | Отклонение к прошлому году за месяц |
| `year_fact` | float8 | Факт за год (нарастающим итогом) |
| `year_to_plan` | float8 | Отклонение от плана за год |
| `year_to_prev_yr` | float8 | Отклонение к прошлому году за год |
| `populates` | varchar(8) | Период заполнения: daily/monthly/yearly/mixed/none |
| `cell_ref` | varchar(32) | Ссылка на ячейку («B14») |

**Отклонения хранятся как доли:** `-0.0979 = -9.79%`, `0.335 = +0.335 п.п.` (для показателей с `unit='%'`).

**Особые индексы:**
- `idx_metrics_problem` — частичный индекс `WHERE zone IN (1,2)` для быстрых запросов «красное+жёлтое на дату»
- `idx_metrics_name_trgm` — GIN-триграмный индекс для `name % 'запрос'` (нечёткий поиск с учётом сокращений)
- `idx_metrics_name_search` — GIN для полнотекстового поиска по-русски

### `investment_metrics` — инвестиционная программа (10 033 строки)

Листы «Инвест» и «Инвест Факт». Отдельная таблица из-за другой структуры.

| Колонка | Тип | Описание |
|---|---|---|
| `code_spiui` | varchar(64) | Код СПИУИ |
| `federal_project` | varchar(256) | Федеральный проект |
| `program` | varchar(512) | Название программы |
| `is_forecast` | bool | true=Инвест (прогноз), false=Инвест Факт |
| `zone` | int2 | Зона (0/1/2/4) |
| `exp_approved_year` | float8 | Утв. план года (расходы) |
| `exp_period_plan` | float8 | План периода (расходы) |
| `exp_fact_or_forecast` | float8 | Факт или прогноз |
| `exp_pct_to_period` | float8 | % к плану периода |
| `exp_pct_to_year` | float8 | % к плану года |
| `funds_approved_year` | float8 | Утв. план года (ввод фондов) |
| `funds_period_plan` | float8 | План периода (ввод фондов) |
| `funds_fact_or_forecast` | float8 | Факт или прогноз |
| `funds_pct_to_period` | float8 | % к плану периода |
| `funds_pct_to_year` | float8 | % к плану года |

### `report_comments` — текстовые комментарии (15 395 строк)

| Колонка | Тип | Описание |
|---|---|---|
| `id` | uuid PK | Идентификатор |
| `report_id` | uuid FK→reports | Ссылка на доклад |
| `metric_id` | uuid FK→metrics | Ссылка на показатель |
| `indicator_number` | varchar(255) | Номер показателя |
| `commentary` | text | Текст комментария |
| `management_action` | text | Управленческое действие |
| `row_index` | int4 | Порядок в источнике |

Индексы: полнотекстовый GIN по `commentary || ' ' || management_action`.

### `dept_codes` — справочник кодов подразделений (143 строки)

| Колонка | Тип | Описание |
|---|---|---|
| `code` | text PK | Телеграфный код (ЦФТО, ЦД, ЦБС…) |
| `name` | text | Полное наименование |

JOIN: `metrics.responsible = dept_codes.code`.

### `kb_chunks` — база знаний (векторное хранилище)

| Колонка | Тип | Описание |
|---|---|---|
| `id` | bigserial PK | Идентификатор |
| `collection` | text | Коллекция: pte/textbooks/reference/glossary |
| `source_file` | text | Имя исходного файла |
| `breadcrumb` | text | Навигация («Книга > Глава > Раздел») |
| `citation` | text | Цитата-источник («ПТЭ, разд. II, п.6») |
| `content` | text | Тело чанка |
| `is_verbatim` | bool | Дословный (ПТЭ) или очищенный (учебники) |
| `embedding` | vector(1024) | Эмбеддинг (multilingual-e5-large-instruct) |
| `tsv` | tsvector | Русский полнотекстовый индекс (GENERATED) |
| `source_hash` | text | Хеш контента (идемпотентная перезагрузка) |

**Индексы:**
- `kb_chunks_embedding_idx` — HNSW для косинусного сходства
- `kb_chunks_tsv_idx` — GIN для полнотекстового поиска

**Коллекции и их ограничения по длине в ответах:**

| Коллекция | Чанков | Лимит символов в ответе |
|---|---|---|
| pte | 676 | 2600 |
| textbooks | 1006 | 600 |
| reference | 8 | 4000 |
| glossary | 202 | 2500 |

### `indicator_index` — семантический индекс показателей

| Колонка | Тип | Описание |
|---|---|---|
| `name` | varchar(512) PK | Имя показателя |
| `embedding` | vector(1024) | Эмбеддинг имени |
| `example_inum` | varchar(32) | Пример номера показателя |
| `example_section` | varchar(8) | Пример раздела |
| `example_unit` | varchar(64) | Единица измерения |
| `n_occurrences` | int | Сколько строк metrics используют это имя |
| `has_road` | boolean | Есть ли разбивка по дорогам |

Перестраивается через `build_indicator_index.py` после загрузки новых данных.

## Справки-источники (spravki_*)

Детализированные оперативные справки, связываются с докладом через `report_date`.

### `spravki_delays` — задержанные поезда

Коды причин: 0=без приказа, 1=неприём грузополучателем, 2=погранпереход, 4=др. вид транспорта, 5=временное размещение, 6=ожидание накопления судовой партии, 21=отказ техсредств Т, 22=нет лок-ва перевозчика, 24=нет лок-ва, 43=отказ техсредств ДИ, 44=несвоевременная очистка, 92=угроза теракта.

### `spravki_failures` — отказы техсредств 1-2 категории

По подразделениям: `failures_2025`, `failures_2026`, `change_pct`, `resolved`, `registered`, `investigated`.

### `spravki_locomotives` — эксплуатируемый парк локомотивов

По полигонам и типам тяги: `section` (AC/DC/diesel), `polygon`, `road`, `plan`, `fact`, `delta`.

### `spravki_port_stations` — припортовые станции

Дороги ДВОСТ/ОКТ/СКАВ: погрузка план/факт, наличие вагонов, отставленные поезда.

### `spravki_speed` — участковая и техническая скорость

`speed_type`: section (участковая) / technical (техническая). По дорогам.

### `spravki_speed_restrictions` — ограничения скорости

`row_type`: plan (заложено в график) / fact (фактически в наличии). Данные извлечены вручную из PNG-картинок в xlsx.

### `spravki_sort_stations` — сортировочные станции

Рабочий парк, роспуск, расформирование, формирование, средний вес и длина состава. `period`: сут./ср/сут.

## Покрытие по датам

- **reports:** 2022-03-01 … 2026-04-30 (62 даты)
- **spravki_*:** 2026-03-12 (загружена одна дата — нужна дозагрузка за апрель)
