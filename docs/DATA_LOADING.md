# Загрузка данных

## Источники данных

1. **Доклады ГЦУ** (.xlsx) — основной источник оперативных показателей
2. **Справки-источники** (.xlsx, .xlsb) — детализированные оперативные данные
3. **База знаний** (.pdf, .docx) — нормативная литература (отдельный пайплайн, см. [KNOWLEDGE_BASE.md](KNOWLEDGE_BASE.md))

---

## Загрузка докладов ГЦУ

### Автоматическая загрузка (рекомендуется)

**Вариант А: Веб-загрузчик** (http://localhost:8810)

Перетащите .xlsx файл в окно браузера. Сервер проверит формат, вызовет парсер и покажет результат (красный/жёлтый/зелёный счётчики).

**Вариант Б: Файловый наблюдатель**

Положите .xlsx в отслеживаемую папку. Наблюдатель (`gcu-watch`) автоматически обнаружит файл и запустит парсер. В режиме `NO_MOVE=1` файлы остаются на месте, состояние отслеживается через JSON-сайдкар.

### Ручная загрузка через CLI

```bash
# Один файл
docker exec gcu-watch python /app/parse_gtsu_v2.py /data/ГЦУ-03-31.xlsx

# Папка с файлами (batch)
docker exec gcu-watch python /app/parse_gtsu_v2.py /data/march_reports/

# Принудительная перезагрузка (если файл изменился)
docker exec gcu-watch python /app/parse_gtsu_v2.py /data/ГЦУ-03-31.xlsx --force

# С указанием даты (если не удалось определить из имени)
docker exec gcu-watch python /app/parse_gtsu_v2.py /data/report.xlsx --date 2026-04-15

# Быстрая загрузка с рабочего стола
docker cp "C:/Users/Iskandar/Desktop/март 22 — копия" gcu-watch:/tmp/march
docker cp "C:/Users/Iskandar/Desktop/апрель 2026" gcu-watch:/tmp/april
docker exec gcu-watch python /app/parse_gtsu_v2.py /tmp/march
docker exec gcu-watch python /app/parse_gtsu_v2.py /tmp/april
```

### Как работает парсер (`parse_gtsu_v2.py`)

1. **Определение типа листа:**
   - `Доклад Ц ЦЗ` + `Срок доставки` → таблица `metrics`
   - `Инвест` + `Инвест Факт` → таблица `investment_metrics`

2. **Извлечение данных:**
   - Римские заголовки разделов (I, II, III…)
   - Нумерованная иерархия показателей (1.1 → 1.1.1 → 1.1.1.1)
   - Определение дороги (Октябрьская, Дальневосточная…) для строк с разбивкой
   - Маппинг зон (красная/жёлтая/зелёная/особая)
   - Наследование категорий

3. **Дедупликация:**
   - SHA256-хеш файла → если хеш уже есть в `reports`, импорт пропускается
   - Флаг `--force` удаляет существующие строки для этой даты и переимпортирует

4. **Определение baseline_year:**
   - Автоматически из строки заголовка («… к уровню 2021 года»)
   - Март 2022 → baseline_year = 2021
   - Апрель 2026 → baseline_year = 2025

---

## Загрузка справок-источников

```bash
# Внутри контейнера gcu-watch или gcu-mcp
python gcu/parse_spravki.py --date 2026-03-12 --dir /data/spravki/2026-03-12/
```

### Ожидаемые файлы в директории

| Файл | Таблица |
|---|---|
| `Справка о наличии задержанных поездов.xlsx` | `spravki_delays` |
| `Суточная оперативная справка о случаях отказов...xlsx` | `spravki_failures` |
| `Справка Локомотивы.xlsx` | `spravki_locomotives` |
| `Справка о работе припортовых станций на ДВОСТ ж.д. *.xlsx` | `spravki_port_stations` |
| `Справка о работе припортовых станций на ОКТ ж.д. *.xlsx` | `spravki_port_stations` |
| `Справка о работе припортовых станций на СКАВ ж.д. *.xlsx` | `spravki_port_stations` |
| `Справка Анализ выполнения участковой скорости*.xlsb` | `spravki_speed` |
| `Справка о Выполнении технической скорости*.xlsb` | `spravki_speed` |
| `Справка Анализ работы...сортировочных станций...xlsb` | `spravki_sort_stations` |

**Текущее покрытие:** данные загружены только за 2026-03-12. Необходима дозагрузка за апрель 2026.

---

## Загрузка ограничений скорости (особый случай)

Данные об ограничениях скорости хранятся в xlsx как PNG-картинки. Числа извлечены вручную в JSON.

```bash
python gcu/load_speed_restrictions.py
```

---

## Построение вспомогательных индексов

### Индекс показателей (после загрузки новых данных)

```bash
docker exec gcu-mcp python3 /app/build_indicator_index.py
```

Перестраивает `indicator_index` — эмбеддит все уникальные `metrics.name`. Нужен для работы `find_indicator()`.

---

## Применение схемы БД (после первой установки)

```bash
docker exec -i gcu-postgres psql -U postgres -d postgres < db/schema_v2.sql
docker exec -i gcu-postgres psql -U postgres -d postgres < db/kb_schema.sql
docker exec -i gcu-postgres psql -U postgres -d postgres < db/spravki_schema.sql
docker exec -i gcu-postgres psql -U postgres -d postgres < db/indicator_index_schema.sql
docker exec -i gcu-postgres psql -U postgres -d postgres < db/dept_codes.sql
```

Все SQL-файлы идемпотентны (`CREATE IF NOT EXISTS`, `OR REPLACE`).

---

## Проверка загруженных данных

```sql
-- Количество докладов
SELECT count(*), min(report_date), max(report_date) FROM reports;

-- Количество показателей
SELECT count(*) FROM metrics;

-- Проверка конкретной даты
SELECT report_date, red_count, yellow_count, green_count
FROM reports WHERE report_date = '2026-03-12';

-- Поиск показателя
SELECT indicator_number, name, road, day_fact, day_to_plan, zone
FROM metrics
JOIN reports ON metrics.report_id = reports.id
WHERE reports.report_date = '2026-04-01' AND zone = 2
ORDER BY day_to_plan ASC
LIMIT 10;
```
