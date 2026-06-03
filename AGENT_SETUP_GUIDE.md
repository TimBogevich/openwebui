# GCU Assistant — Agent Setup Guide
## Models, Tool Calling, Docker & Native Config

---

## 1. What we have

Three models in Open WebUI:

| Preset ID | Display name | Backend | Tool strategy |
|---|---|---|---|
| `qwen/qwen3.6-27b` | ГЦУ Ассистент | LM Studio :1234 (local) | Native MCP tool calls |
| `remote-qwen/qwen3.6-27b` | GCU Remote | agentplatform.ru (cloud) | Native MCP tool calls |
| `qwen/qwen3.5-9b` | ГЦУ 9B | LM Studio :1234 (local) | Filter injection (no tool chip) |

---

## 2. Applying model config via API

### Get token first

```python
import httpx

BASE = "http://localhost:3000"  # or Docker OWI
r = httpx.post(f"{BASE}/api/v1/auths/signin",
    json={"email":"admin@zero16.ru","password":"Gcu2026!"})
TOKEN = r.json()["token"]
H = {"Authorization": f"Bearer {TOKEN}"}
```

---

## 3. OpenAI connections (LM Studio + agentplatform)

```python
httpx.post(f"{BASE}/openai/config/update", headers=H, json={
    "ENABLE_OPENAI_API": True,
    "OPENAI_API_BASE_URLS": [
        "http://localhost:1234/v1",              # [0] LM Studio (native)
        # Docker: "http://host.docker.internal:1234/v1"
        "https://api.agentplatform.ru/v1",       # [1] Remote Qwen
    ],
    "OPENAI_API_KEYS": [
        "lm-studio",
        "sk-ap-JpHr_qOj4a3I0VmfLUUtow",
    ],
    "OPENAI_API_CONFIGS": {
        "0": {"enable": True,  "prefix_id": "",   "model_ids": []},
        "1": {"enable": True,  "prefix_id": "ap", "model_ids": ["qwen/qwen3.6-27b"]},
        # prefix "ap" means model shows as "ap.qwen/qwen3.6-27b" — required for routing
    }
})
```

---

## 4. MCP tool server

```python
httpx.post(f"{BASE}/api/v1/configs/tool_servers", headers=H, json={
    "TOOL_SERVER_CONNECTIONS": [{
        "url":  "http://localhost:8808/mcp",  # native
        # Docker: "http://gcu-mcp:8808/mcp"
        "path": "mcp", "type": "mcp",
        "auth_type": "none", "key": "", "headers": None,
        "config": {"enable": True},
        "info": {"id": "gcu-postgres", "name": "GCU Postgres"}
    }]
})
```

Verify it works:

```python
r = httpx.post(f"{BASE}/api/v1/configs/tool_servers/verify", headers=H, json={
    "url": "http://localhost:8808/mcp",  # or http://gcu-mcp:8808/mcp in Docker
    "path": "mcp", "type": "mcp", "auth_type": "none",
    "key": "", "headers": None, "config": {"enable": True},
    "info": {"id": "gcu-postgres"}
}, timeout=15)
print(r.json())  # {"status": True, "specs": [{"name": "query", ...}]}
```

---

## 5. Model presets

### Remote 27B (cloud, native tool calling)

```python
meta = {
    "toolIds": ["server:mcp:gcu-postgres"],  # MCP tool
    "filterIds": [],                          # NO filter on remote model
    "capabilities": {
        "vision": False, "citations": True,
        "tool_calling": True, "native_tool_calling": True,
        "builtin_tools": False,               # suppress 25 OWI built-ins (context overflow)
    }
}
params = {
    "function_calling": "native",             # REQUIRED — default mode breaks tool execution
    "max_tokens": 8192,
    "temperature": 0.2,
    "system": "Ты — аналитический ассистент по ежедневным докладам ГЦУ...",
}
httpx.post(f"{BASE}/api/v1/models/create", headers=H, json={
    "id": "remote-qwen/qwen3.6-27b",
    "name": "GCU Remote (Qwen 27B API)",
    "base_model_id": "ap.qwen/qwen3.6-27b",   # ap. prefix from connection config
    "meta": meta, "params": params
})
```

### Local 27B (LM Studio, native tool calling at 100k ctx)

```python
meta = {
    "toolIds": ["server:mcp:gcu-postgres"],
    "filterIds": [],
    "capabilities": {
        "tool_calling": True, "native_tool_calling": True,
        "builtin_tools": False,  # REQUIRED — 25 builtins overflow 4096 ctx
    }
}
params = {
    "function_calling": "native",
    "num_ctx": 100000,             # LM Studio must be loaded at 100k context in GUI
    "temperature": 0.2,
    "system": "Рассуждай на русском языке. Думай по-русски.\n\nТы — аналитический ассистент...",
}
httpx.post(f"{BASE}/api/v1/models/create", headers=H, json={
    "id": "qwen/qwen3.6-27b",
    "name": "ГЦУ Ассистент (Qwen 27B)",
    "base_model_id": None,
    "meta": meta, "params": params
})
```

### Local 9B (LM Studio, filter injection — no native tool calls)

```python
meta = {
    "toolIds": [],
    "filterIds": ["gcu_report_filter"],  # filter does DB queries instead
    "capabilities": {
        "tool_calling": False, "native_tool_calling": False,
    }
}
params = {
    "num_ctx": 262144,       # 9B supports full 262k at 24GB VRAM
    "temperature": 0.3,
    "system": "Рассуждай на русском языке. Думай по-русски.\n\nОтвечай строго на основе данных из БД.",
}
httpx.post(f"{BASE}/api/v1/models/create", headers=H, json={
    "id": "qwen/qwen3.5-9b",
    "name": "ГЦУ 9B (локальный)",
    "base_model_id": None,
    "meta": meta, "params": params
})
```

---

## 6. Filter function

```python
with open(r"C:\llm\gcu-fork\gcu\gcu_filter.py", "r", encoding="utf-8") as f:
    code = f.read()

httpx.post(f"{BASE}/api/v1/functions/create", headers=H, json={
    "id": "gcu_report_filter",
    "name": "GCU Report Data Filter",
    "content": code,
    "meta": {"description": "Auto-injects DB data for local models"}
})
# activate
httpx.post(f"{BASE}/api/v1/functions/id/gcu_report_filter/toggle", headers=H)
# make global (fires for ALL models unless filter checks model ID)
httpx.post(f"{BASE}/api/v1/functions/id/gcu_report_filter/toggle/global", headers=H)
```

**Critical:** `gcu_filter.py` inlet() must skip remote models:

```python
def inlet(self, body: dict, __user__=None) -> dict:
    if body.get("model", "").startswith("remote-"):
        return body   # remote model uses MCP tool — don't inject stale data
    ...
```

---

## 7. Docker-specific differences

| Setting | Native | Docker |
|---|---|---|
| LM Studio URL | `http://localhost:1234/v1` | `http://host.docker.internal:1234/v1` |
| MCP URL | `http://localhost:8808/mcp` | `http://gcu-mcp:8808/mcp` |
| OWI version | 0.9.5 | 0.9.6 |
| Model create already exists | Use update endpoint | 401 = use update |

**Docker model update** (when 401 on create):

```python
httpx.post(f"{BASE}/api/v1/models/id/{model_id}/update", headers=H, json={...})
# Note: /update returns 405 in 0.9.5, works in 0.9.6
```

**Docker start/stop:**

```bash
cd C:\llm\gcu-export

# Start (first stop native OWI to free ports 3000/8808)
powershell Stop-ScheduledTask -TaskName OpenWebUI
docker compose up -d --build

# Stop (to switch back to native)
docker compose stop
powershell Start-ScheduledTask -TaskName OpenWebUI
```

---

## 8. Critical bugs & fixes

### "error parsing body" 400 at x-process-time: 0
WEBUI_SECRET_KEY mismatch between OWI instances.  
Fix: `set "WEBUI_SECRET_KEY=rhLURysraja4ojZr"` in `launch_gcu.cmd`.

### MCP verify returns `status: None` 
Docker gcu-mcp container is intercepting port 8808.  
Fix: `docker compose stop gcu-mcp`

### Tool emitted but never executes
Filter fired on remote model and pre-injected data.  
Fix: add `if body.get("model","").startswith("remote-"): return body` to filter.

### "n_keep >= n_ctx" error from LM Studio
Model context too small for tool schemas + system prompt.  
Fix: load model at 100k context in LM Studio GUI.

### 9B tool chip not showing
By design — 9B uses filter injection (OWI 0.9.5 doesn't execute tool loop for local connections).  
Data is real, just no visible chip.

### Docker MCP 421 Misdirected Request
MCP SDK blocks Host: gcu-mcp:8808.  
Fix is in `docker/Dockerfile.mcp` (patches transport_security.py at build time).
