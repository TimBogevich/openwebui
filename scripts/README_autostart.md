# Autostart on user login

What auto-starts when Iskandar logs in:

| Component       | Mechanism                                        | Where configured |
|-----------------|--------------------------------------------------|------------------|
| **LM Studio**   | `HKCU\…\Run` with `--run-as-service`              | already in registry — survives reboots |
| **Docker Desktop** | Windows Scheduled Task `Docker Desktop Autostart` | `scripts/docker_autostart.task.xml` |
| **Containers** (postgres/mcp/openwebui/upload/watch) | `restart: unless-stopped` in `docker-compose.yml` | Docker engine starts them automatically once it's up |
| **e5 embedder** | Windows Scheduled Task `GCU_Embedder_LMStudio`   | `scripts/ensure_gcu_embedder.ps1` (probes API, loads if missing) |
| **MoE model**   | LM Studio JIT (`jitModelTTL.enabled=true`)       | loads on first API request from OWI; stays resident 1h |

## Re-import the Docker autostart task after a reinstall

```powershell
$xml = Get-Content 'C:\llm\gcu-export\scripts\docker_autostart.task.xml' -Raw
Register-ScheduledTask -TaskName 'Docker Desktop Autostart' -Xml $xml -Force
```

## If anything didn't auto-start (post-reboot recovery)

```cmd
REM Manual: open Docker Desktop, then everything cascades
"C:\Program Files\Docker\Docker\Docker Desktop.exe"

REM Or trigger the task on demand
schtasks /Run /TN "Docker Desktop Autostart"

REM Embedder (rarely needed — pre-existing task handles it)
schtasks /Run /TN "GCU_Embedder_LMStudio"
```
