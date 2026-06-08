# Руководство разработчика

## Структура репозитория

```
C:\RZD\gcu\
├── gcu/                    # Ядро приложения (Python)
├── db/                     # SQL-схемы, скрипты, бенчмарки
├── docker/                 # Dockerfile'ы
├── kb_out/                 # Курированный корпус базы знаний
├── launchers/              # Windows .cmd лаунчеры
├── static/                 # Брендинг (CSS, JS, изображения)
├── docs/                   # Документация
├── docker-compose.yml      # Оркестрация
├── openwebui_config.json   # Конфигурация моделей и MCP
├── .env.example            # Шаблон переменных окружения
└── start.cmd               # Лаунчер Docker
```

## Рабочий процесс разработки

### Редактирование MCP-сервера

```bash
# После правок в gcu/mcp_postgres_server.py:
docker compose up -d --build gcu-mcp

# Проверка инструментов:
curl -s http://localhost:8808/mcp
```

### Редактирование парсера

```bash
# После правок в gcu/parse_gtsu_v2.py — пересобрать оба контейнера:
docker compose up -d --build gcu-watch gcu-upload
```

### Применение схемы БД

```bash
docker exec -i gcu-postgres psql -U postgres -d postgres < db/schema_v2.sql
```

Схема идемпотентна — безопасно переприменять.

### Конфигурация моделей

Конфигурация применяется через Open WebUI API (см. [DEPLOYMENT.md](DEPLOYMENT.md)). Идемпотентные скрипты в `db/add_*.py`:

| Скрипт | Действие |
|---|---|
| `db/add_coder32b.py` | Добавить пресет Coder 32B (⚠️ не работает как агент) |
| `db/add_gemma.py` | Добавить пресет Gemma 26B |
| `db/add_moe_35b.py` | Добавить пресет MoE 35B |
| `db/add_remote_9b.py` | Добавить пресет 9B удалённый |
| `db/show_only_moe.py` | Скрыть все пресеты кроме MoE (идемпотентный, обратимый) |
| `db/strip_analyst.py` | Удалить «аналитик» блок из промптов (делал ответы шаблонными) |
| `db/kb_directive.py` | Добавить «БАЗА ЗНАНИЙ» директиву в промпты |
| `db/kb_grounding.py` | Добавить «ОПОРА НА ИСТОЧНИКИ» правило |
| `db/ru_reasoning.py` | Добавить русскоязычное мышление |
| `db/formal_style.py` | Добавить формальный стиль (без emoji) |
| `db/tools_directive.py` | Добавить директиву вызова инструментов |
| `db/patch_system_prompts.py` | Добавить S4 блоки (период, иерархия, самоконтроль) |
| `db/ru_suggestions.py` | Русские prompt suggestions |
| `db/set_brand.py` | Брендирование имени пользователя |

## Системный промпт

Собирается композитно из нескольких скриптов, каждый добавляет свой блок с sentinel-маркером для идемпотентности:

1. **RU reasoning + formal style** — думать и отвечать по-русски, без emoji
2. **Tools directive** — порядок вызова инструментов (current_datetime → weather → describe → find_indicator → query)
3. **S4 блоки:**
   - **ПЕРИОД И НАКОПЛЕНИЕ (A8):** правила работы с периодами (day/month/year) и нарастающим итогом
   - **ИЕРАРХИЯ И РАЗРЕЗЫ (A1):** как использовать parent_indicator, road, zone
   - **САМОКОНТРОЛЬ:** проверка на синтетические данные
4. **БАЗА ЗНАНИЙ (KB directive):** когда вызывать `search_knowledge`
5. **ОПОРА НА ИСТОЧНИКИ (grounding):** отвечать строго из retrieved fragments

## Зависимости

### Python (в Docker-контейнерах)

```
mcp                    # FastMCP framework
psycopg[binary]        # PostgreSQL driver
uvicorn                # ASGI server
flask                  # Web upload server
openpyxl               # .xlsx parsing
pyxlsb                 # .xlsb parsing
pypdf                  # PDF extraction
```

Установка через `pip` в Dockerfile'ах.

### PostgreSQL расширения

```sql
CREATE EXTENSION pgcrypto;
CREATE EXTENSION pg_trgm;
CREATE EXTENSION vector;
```

Все три нужны для работы системы.

## Отладка

### Просмотр логов

```bash
docker logs -f gcu-mcp        # MCP-сервер
docker logs -f gcu-openwebui  # Чат-интерфейс
docker logs -f gcu-watch      # Наблюдатель
docker logs -f gcu-postgres   # База данных
```

### Проверка MCP-инструментов вручную

```bash
# describe
curl -s -X POST http://localhost:8808/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"describe","arguments":{"table":"metrics"}}}'

# query
curl -s -X POST http://localhost:8808/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"query","arguments":{"sql":"SELECT count(*) FROM reports"}}}'
```

### Проверка эмбеддингов

```bash
curl -s http://localhost:1234/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"text-embedding-multilingual-e5-large-instruct","input":["тестовый запрос"]}'
```

### Прямой доступ к БД

```bash
# Через DBeaver: host=127.0.0.1, port=5433, user=postgres, password=...

# Через psql в контейнере:
docker exec -it gcu-postgres psql -U postgres -d postgres
```

### Инспекция чатов

```bash
docker exec gcu-openwebui sqlite3 /app/backend/data/webui.db \
  "SELECT title, updated_at FROM chat ORDER BY updated_at DESC LIMIT 10"
```

## Известные архитектурные решения

1. **Typed schema v2** — отказ от JSONB в пользу `float8`. Позволяет модели писать чистый SQL без cast'ов.
2. **Anti-loop guards** — кольцевой буфер хешей в MCP-сервере, потому что MoE-модели зацикливаются на повторных запросах.
3. **RRF гибридный поиск** — вектор + FTS для KB, потому что один векторный поиск неточен (score'ы кластеризуются в 0.84-0.87).
4. **Семантический индекс показателей** — эмбеддинги имён вместо `ILIKE`, потому что имена в источнике сокращены («груз.» vs «грузовых»).
5. **SHA256 идемпотентность** — безопасная перезагрузка данных, повторный импорт того же файла = no-op.
6. **per-collection KB caps** — разные лимиты на длину ответа для разных коллекций, вместо одного жёсткого ограничения.

## Пуш в репозиторий

```bash
git push https://iskandaryv:<TOKEN>@github.com/iskandaryv/6EE3PKHeeUSCKx.git master:master
```

## Не включать в коммиты

- `.env` (секреты)
- `Лит-ра для ИИ/` (103 MB PDF/DOCX исходников)
- Файлы данных ГЦУ (.xlsx)
