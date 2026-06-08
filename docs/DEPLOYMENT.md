# Развёртывание

## Варианты развёртывания

1. **Docker Compose** (основной) — все 5 контейнеров
2. **Нативный Windows** — через Scheduled Tasks и .cmd лаунчеры

---

## Docker-развёртывание

### Требования

- Docker + Docker Compose
- WSL2 (на Windows)
- LM Studio на хосте (порт 1234)
- API-ключ agentplatform.ru (опционально, для удалённой модели)

### Шаги

```bash
# 1. Конфигурация
cp .env.example .env
# Заполнить:
#   POSTGRES_PASSWORD=...    # пароль БД
#   REMOTE_API_BASE_URL=...  # опционально
#   REMOTE_API_KEY=...       # опционально
#   WEBUI_SECRET_KEY=...     # 32-символьная hex-строка

# 2. Запуск
docker compose up -d --build

# 3. Применить схему БД
docker exec -i gcu-postgres psql -U postgres -d postgres < db/schema_v2.sql
docker exec -i gcu-postgres psql -U postgres -d postgres < db/kb_schema.sql
docker exec -i gcu-postgres psql -U postgres -d postgres < db/spravki_schema.sql
docker exec -i gcu-postgres psql -U postgres -d postgres < db/dept_codes.sql

# 4. Открыть
# http://localhost:3000   — чат-интерфейс
# http://localhost:8810   — страница загрузки докладов
```

### Сервисы

| Сервис | Порт | Контейнер |
|---|---|---|
| PostgreSQL | 5433→5432 | `gcu-postgres` |
| MCP-сервер | 8808 | `gcu-mcp` |
| Open WebUI | 3000→8080 | `gcu-openwebui` |
| Загрузчик | 8810 | `gcu-upload` |
| Наблюдатель | — | `gcu-watch` |

### Управление

```bash
# Пересборка после изменений кода
docker compose up -d --build gcu-mcp

# Остановка
docker compose stop

# Полная очистка (данные сохраняются в volumes)
docker compose down

# Просмотр логов
docker logs -f gcu-mcp
docker logs -f gcu-openwebui
```

### Тома (volumes)

| Том | Назначение |
|---|---|
| `postgres-data` | Данные PostgreSQL |
| `openwebui-data` | Данные Open WebUI (чаты, конфигурация, загрузки) |

---

## Нативная Windows-установка

### Требования

- PostgreSQL 18, база данных в `C:\DB_DATA`
- Open WebUI venv: `C:\llm\openwebui\.venv`
- Python-зависимости: `mcp`, `psycopg[binary]`, `uvicorn`, `flask`, `openpyxl`, `pypdf`
- Код проекта в `C:\llm\gcu-fork`

### Переменные окружения

```powershell
$env:POSTGRES_PASSWORD = "Gcu2026!"
$env:PGHOST = "127.0.0.1"
$env:PGPORT = "5432"
```

### Лаунчеры (`launchers/`)

| Скрипт | Назначение |
|---|---|
| `launch_openwebui.cmd` | Запуск Open WebUI на порту 3000 |
| `run_mcp.cmd` | Запуск MCP-сервера на порту 8808 |
| `run_watch.cmd` | Запуск файлового наблюдателя |

### Windows Scheduled Tasks (автозапуск)

```powershell
# Создание задач (logon trigger):
# OpenWebUI   — launch_openwebui.cmd
# GCU_MCP     — run_mcp.cmd
# GCU_Watch   — run_watch.cmd
```

Настроен автологин для пользователя (`HKLM\...\Winlogon`), задачи запускаются при входе в систему.

### Ручной запуск

```powershell
# Open WebUI
C:\llm\openwebui\.venv\Scripts\open-webui.exe serve --host 0.0.0.0 --port 3000

# MCP-сервер
C:\llm\openwebui\.venv\Scripts\python.exe gcu\mcp_postgres_server.py

# Наблюдатель
C:\llm\openwebui\.venv\Scripts\python.exe gcu\watch_uploads.py C:\llm\openwebui\data\uploads
```

### Переключение между Docker и нативным режимом

```bash
# Остановить Docker → запустить нативные задачи
docker compose stop
powershell Start-ScheduledTask -TaskName OpenWebUI
powershell Start-ScheduledTask -TaskName GCU_MCP

# Остановить нативные задачи → запустить Docker
powershell Stop-ScheduledTask -TaskName OpenWebUI
docker compose up -d --build
```

---

## Конфигурация Open WebUI

После первого запуска необходимо применить конфигурацию (модели, MCP-сервер, фильтры) через API:

```python
import httpx

BASE = "http://localhost:3000"

# 1. Вход
r = httpx.post(f"{BASE}/api/v1/auths/signin",
    json={"email":"admin@zero16.ru","password":"..."})
TOKEN = r.json()["token"]
H = {"Authorization": f"Bearer {TOKEN}"}

# 2. OpenAI-подключения
httpx.post(f"{BASE}/openai/config/update", headers=H, json={
    "ENABLE_OPENAI_API": True,
    "OPENAI_API_BASE_URLS": [
        "http://host.docker.internal:1234/v1",  # LM Studio
        "https://api.agentplatform.ru/v1",      # Remote API
    ],
    "OPENAI_API_KEYS": ["lm-studio", "<API_KEY>"],
    "OPENAI_API_CONFIGS": {
        "0": {"enable": True, "prefix_id": ""},
        "1": {"enable": True, "prefix_id": "ap", "model_ids": ["qwen/qwen3.6-27b"]},
    }
})

# 3. MCP-сервер
httpx.post(f"{BASE}/api/v1/configs/tool_servers", headers=H, json={
    "TOOL_SERVER_CONNECTIONS": [{
        "url": "http://gcu-mcp:8808/mcp",
        "path": "mcp", "type": "mcp",
        "auth_type": "none",
        "config": {"enable": True},
        "info": {"id": "gcu-postgres", "name": "GCU Postgres"}
    }]
})

# 4. Пресеты моделей — см. openwebui_config.json и db/add_*.py
```

### Критические настройки LM Studio

- **Контекст:** минимум 32k токенов (для MoE рекомендуется 64k)
- **Max Concurrent Predictions:** 1 (не 4 — дробит контекст)
- **GPU Offload:** максимальный (модель должна полностью помещаться в VRAM)
- **Модель:** Qwen3.6-35B-A3B (Q4_K_M, ~17 GB VRAM)

### Docker vs Native — различия в URL

| Параметр | Docker | Native |
|---|---|---|
| LM Studio | `http://host.docker.internal:1234/v1` | `http://localhost:1234/v1` |
| MCP-сервер | `http://gcu-mcp:8808/mcp` | `http://localhost:8808/mcp` |
| PostgreSQL | `postgres:5432` (внутри сети) | `127.0.0.1:5432` |

---

## Известные проблемы при развёртывании

1. **OOM (Out of Memory):** LM Studio + загруженная модель + загрузка другой модели может убить все Docker-контейнеры (exit 137). Выгружайте неиспользуемые модели.
2. **LM Studio не контейнеризуется** — GUI Electron-приложение, держит GPU напрямую. Всегда работает нативно на хосте.
3. **Контекст модели:** при загрузке с контекстом 4096 (JIT-дефолт LM Studio) первый же запрос с системным промптом + инструментами превысит лимит. Сохраните 65536 как дефолт модели в LM Studio.
4. **Ошибка 421 Misdirected Request:** патч в `docker/Dockerfile.mcp` исправляет проверку хоста в MCP SDK.
5. **WEBUI_SECRET_KEY:** должен совпадать между экземплярами Open WebUI, иначе ошибка «error parsing body».
