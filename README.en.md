# ipip — IP Address Management System

[简体中文](README.md) | English

Open-source IP/IPAM management platform: data centers, cabinets, devices, IP allocation, VLANs, switches, monitoring & alerting, and customer management in a single system, with a built-in AI assistant (alert interpretation / NL query / RAG knowledge base / Agentic inspection & diagnosis).

**Current version: v1.4.1** — the single source of truth for the version is `VERSION` in `config.py`; the runtime endpoint is `GET /api/health` (`data.version`, also shown at the bottom of the sidebar).

Backend: Flask + SQLAlchemy + MySQL + Redis. Frontend: React 19 + Ant Design 6 + Vite 8. ASGI SSE real-time push gateway (multi-replica ready), Celery async task base (AI long tasks + voice notifications).

Notification channels: in-app, Feishu (Lark), WeCom (Enterprise WeChat), **DingTalk (custom robot with signing)**, email, **custom Webhook**, and **voice calls (Alibaba Cloud / Tencent Cloud)** — with a unified delivery worker featuring **cooldown windows** (Redis, per event + channel), dead-letter tracking on queue-full, and strict delivery (failures are reported for alert-outbox retry).

Authentication: local accounts + **LDAP/AD external authentication** (group→role mapping, emergency bypass allowlist).

## Features

| Module | Capabilities |
|--------|--------------|
| IP/IPAM | Data center / cabinet / device / IP allocation / VLAN / switch management |
| Monitoring & Alerting | SNMP metric polling, threshold alerts, dependency suppression, alert tracking |
| **SNMP Trap** | Standalone `ipip-trapd` process receiving v1/v2c traps, built-in standard rules + site-specific OID rules, global rate limiting against trap storms, reusing the unified alert governance pipeline (silence/throttle → outbox → SSE) |
| **Topology Discovery** | LLDP/CDP live probing (Huawei/H3C/Cisco) → produces connection **suggestions**; nothing is written until manually confirmed (**manual entries are never overwritten**) |
| **Event Center** | Alert aggregation (L1 rule merge / L2 topology suppression / L3 change correlation), event impact analysis, lookback window |
| **Notification Delivery** | Multi-channel (in-app / Feishu / WeCom / DingTalk / email / custom Webhook / voice), delivery worker, cooldown window (Redis), dead-letter tracking, strict delivery, per-user preferences |
| **Voice Channel** | Alibaba Cloud / Tencent Cloud voice notifications, dedicated voice worker, callback authentication, P0 alert wake-up escalation |
| **SSE Real-time** | Gateway seq/ring state shared via Redis, horizontally scalable across replicas |
| Customer / Audit | Customer management, operation audit, RBAC permissions |
| **Unified Identity** | LDAP/AD integration, group→role mapping, local emergency bypass allowlist (see the "Unified Identity Integration" ops manual) |
| **AI Assistant** | Alert interpretation / NL query / RAG knowledge base / Agentic inspection & diagnosis; executed asynchronously on the Celery `ai` queue, isolated by `ai:use` / `ai:admin` RBAC permissions |

## Directory Layout

```
ipip/
├── README.md                   # This file (Chinese)
├── README.en.md                # English version of this document
├── LICENSE                     # Open-source license
├── RELEASE_NOTES_v1.0.md       # v1.0 release notes
├── .env.example                # Environment variable template (sanitized)
├── .gitignore
├── app/                        # Flask backend
│   ├── api/                    # Routes (incl. monitor/incident, voice_callback/voice_settings, topology)
│   ├── adapters/               # Device adapters (Huawei/H3C/Cisco: command wrapping + LLDP/CDP parsing)
│   ├── models/                 # SQLAlchemy models (incl. monitor_incident, voice_setting, etc.)
│   ├── services/               # Business services
│   │   ├── monitoring/         # Monitoring (incl. incident_aggregator, alert_dependency_service, escalation_service, trap_*)
│   │   ├── channels/           # Notification channels (incl. voice, voice_providers/aliyun/tencent)
│   │   ├── ldap_*.py           # LDAP/AD authentication, identity, group→role mapping, config self-check
│   │   ├── topology_discovery_service.py  # LLDP/CDP topology discovery (suggestion-only)
│   │   └── notification_delivery_worker.py  # Delivery worker (cooldown / dead-letter / strict delivery)
│   ├── tasks/                  # Celery async tasks (voice_tasks, etc.)
│   ├── celery_app.py           # Celery app definition
│   └── persistence/            # Repository layer (incl. monitor_incident_repository, etc.)
├── config.py                   # Backend config entry (incl. LDAP_* / TRAPD_* startup validation)
├── extensions.py               # SQLAlchemy extensions
├── wsgi.py                     # WSGI entry (for gunicorn)
├── run.py                      # Development entry point
├── run_monitor_service.py      # Standalone monitoring service entry
├── run_trapd_service.py        # Standalone SNMP Trap receiver entry (P1-1)
├── realtime_gateway/           # ASGI SSE gateway (uvicorn; seq/ring shared via Redis, multi-replica ready)
├── requirements.txt            # Pinned Python dependencies
├── frontend-new/               # Frontend source (React 19 + AntD 6 + Vite 8)
│   ├── src/
│   │   ├── pages/Monitor/Incidents/   # Event center page
│   │   ├── pages/Topology/            # Topology page (incl. LLDP/CDP discovery suggestion panel)
│   │   ├── pages/Settings/VoiceSettings.tsx  # Voice channel settings
│   │   └── services/voice-settings.ts
│   ├── package.json
│   ├── pnpm-lock.yaml
│   └── vite.config.js
├── migrations/
│   ├── versions/
│   │   ├── 0000_baseline.sql   # Full DDL baseline snapshot (incl. partitioned tables & triggers)
│   │   └── 0000_baseline.covers # Migrations already covered by the baseline
│   ├── seed_all.sh             # Unified seed entry point (called by install.sh)
│   ├── seed_data.sql           # Configuration seeds (fixed definitions for fresh installs)
│   ├── seed_rbac.py            # RBAC seeds (incl. ai:use/ai:admin permissions, idempotent)
│   ├── seed_component_templates.py
│   └── seed_users.py           # Default administrator account
├── scripts/
│   ├── install.sh              # One-command install (venv + frontend build + DB + seeds)
│   ├── start.sh                # One-command start/stop/status (4 processes: Flask + gateway + monitor + celery)
│   ├── credentials.py          # Credential view/reset tool (used by install.sh's credential summary)
│   ├── backup_system.py        # T1 backup (MySQL dump + Redis RDB + GPG-encrypted key export)
│   ├── restore_system.py       # T1 restore (automatic safety snapshot before restore, rollback-able)
│   ├── heartbeat_watchdog.py   # T2 self-monitoring watchdog (heartbeat timeout alerts)
│   ├── download_models.py      # Offline AI model pre-download (sentence-transformers, etc.)
│   ├── backfill_utc_timestamps.py  # Backfill legacy timestamps to UTC (default watermark = switch moment, prevents double offset)
│   └── import_sql.py           # SQL import tool (DELIMITER trigger splitting)
├── deploy/
│   └── systemd/                # systemd units (ADR-003; replaces start.sh hosting)
│       ├── ipip.target         # Unified target (stop ipip.target to stop everything)
│       ├── ipip-web.service    # Flask HTTP API
│       ├── ipip-gateway.service # SSE real-time gateway
│       ├── ipip-monitor.service # Monitoring service
│       ├── ipip-celery-ai.service # Celery AI async queue
│       ├── ipip-celery-voice.service # Celery voice queue
│       ├── ipip-trapd.service  # SNMP Trap receiver (opt-in, see below)
│       ├── ipip-backup.service / .timer # Scheduled backup
│       ├── ipip-watchdog.service / .timer # Heartbeat watchdog
│       ├── install-units.sh    # Unit installation script
│       ├── README.md           # systemd hosting guide (incl. per-unit troubleshooting)
│       └── ipip.env.example    # systemd environment template
├── docs/                       # Operations manuals (see "Documentation")
└── logs/                       # Runtime logs (gitignored)
```

## System Requirements

| Component | Version | Notes |
|-----------|---------|-------|
| Python | 3.14+ | Backend runtime (`realtime_gateway` requires `asyncio.AsyncGenerator` from 3.14; downgrading is not allowed) |
| Node.js | 20+ | Frontend build |
| pnpm | 10+ | Frontend package manager (`corepack enable pnpm`) |
| MySQL | 8.4+ | Database |
| Redis | 6+ | Cache / SSE event bus / Celery broker |

## Quick Deployment

### 1. Clone the repository

```bash
git clone https://github.com/<your-org>/ipip.git
cd ipip
```

### 2. One-command install

```bash
bash scripts/install.sh
```

The install script runs, in order:
1. System dependency checks (Python / Node / pnpm / MySQL client / redis-cli)
2. Python venv creation + `requirements.txt` install (CPU torch by default; `--gpu` for the CUDA build)
3. Frontend dependency install + build (`cd frontend-new && pnpm install && pnpm build`)
4. Create `.env` from `.env.example` (first run only; edit it, then re-run)
5. Create the MySQL database and import the migration baseline `0000_baseline.sql` (versions registered per the covers list)
6. Import seed data (`seed_all.sh`)
7. Download local RAG models into the HF cache (embedding ≈92MB + reranker ≈1100MB; `--skip-models` to skip)
8. [Optional] Install systemd units (`--with-units`, requires root)

**After the first run**: edit `.env` and fill in the real `MYSQL_PASSWORD`, `REDIS_PASSWORD`, `SECRET_KEY`, `JWT_SECRET_KEY`, then run `bash scripts/install.sh` again (completed steps are skipped).

### 3. Start

```bash
bash scripts/start.sh           # Start everything (Flask + gateway + monitor + celery)
bash scripts/start.sh status    # Check status
bash scripts/start.sh stop      # Stop everything
bash scripts/start.sh restart   # Restart everything
```

Then open `http://<server-ip>:5000`.

## install.sh Options

| Option | Description |
|--------|-------------|
| `--skip-frontend` | Skip the frontend build (requires `frontend-new/dist/` to exist) |
| `--skip-db` | Skip database schema initialization |
| `--skip-seed` | Skip seed data import |
| `--skip-models` | Skip local AI model download (when RAG is not needed) |
| `--cpu` | Explicitly install CPU torch (default, ~190MB) |
| `--gpu` | Install CUDA torch (requires an NVIDIA GPU, ~2.6–3.5GB, takes 30–60 minutes) |
| `--gpu-fast` | CUDA build + parallel prefetch of large packages from multiple mirrors (faster) |
| `--with-units` | Render and install systemd units after install (requires root) |
| `--units-user NAME` | Service run account (default `ipip`; use root if the project lives under /root) |
| `--units-group NAME` | Service run group (defaults to `--units-user`) |
| `--units-script PATH` | Path to `install-units.sh` |
| `--help` | Show usage |

## start.sh Commands

| Command | Description |
|---------|-------------|
| `start` (default) | Start Flask + gateway + monitor + celery |
| `stop` | Stop everything |
| `restart` | Restart everything |
| `status` | Show per-process status |
| `flask` | Start Flask only |
| `gateway` | Start the SSE gateway only |
| `monitor` | Start the monitoring service only |
| `celery` | Start the Celery worker only (`ai` async task queue) |

**Service ports** (configurable in `.env`):

| Service | Default port | Env var |
|---------|--------------|---------|
| Flask HTTP API | 5000 | `FLASK_PORT` |
| realtime_gateway (SSE) | 8000 | `GATEWAY_PORT` |
| SNMP Trap receiver (ipip-trapd) | 10162 (UDP) | `TRAPD_LISTEN_PORT` |

**PID files**: `logs/run/{flask,gateway,monitor,celery}.pid`
**Log files**: `logs/{flask,gateway,monitor,celery}.log`

> The Celery worker is controlled by `AI_ASYNC_ENABLED`: starts when set to `1`, otherwise skipped (AI tasks run on the synchronous path). It is also skipped automatically if `.venv/bin/celery` does not exist.
> `start.sh` does **not** manage `ipip-trapd` (trap reception is a separate optional service, hosted by systemd only).

### 3a. systemd hosting (recommended for production)

`start.sh` suits development / temporary runs; production should use systemd hosting (ADR-003) for boot autostart, namespace isolation (`ProtectSystem=strict`), and unified start/stop:

```bash
bash deploy/systemd/install-units.sh   # Install all units + ipip.target
systemctl start ipip.target            # Start everything
systemctl stop ipip.target             # Stop everything (PartOf cascades)
systemctl status ipip-web              # Check a single service
```

| Unit | Process | Description |
|------|---------|-------------|
| `ipip-web` | Flask HTTP API | gunicorn WSGI, port 5000 |
| `ipip-gateway` | SSE real-time gateway | uvicorn ASGI, port 8000 |
| `ipip-monitor` | Monitoring service | SNMP polling + alerts + event aggregation |
| `ipip-celery-ai` | Celery AI queue | Async AI tasks (`ai` queue) |
| `ipip-celery-voice` | Celery voice queue | Voice notification delivery (`voice` queue) |
| `ipip-trapd` | SNMP Trap receiver | UDP v1/v2c traps; **opt-in** — `install-units.sh` only renders/installs the unit, it is not auto-enabled |
| `ipip-backup` + `.timer` | Scheduled backup | MySQL dump + Redis RDB + GPG key export |
| `ipip-watchdog` + `.timer` | Heartbeat watchdog | T2 self-monitoring, heartbeat timeout alerts |

> `install-units.sh --enable` only `enable --now`s the always-on services and timers listed above **except `ipip-trapd` / `ipip-backup`**: backups are timer-scheduled and trap reception requires switch-side configuration first, so both stay opt-in.

## SNMP Trap Receiver (optional)

Besides polling, a standalone process `ipip-trapd` receives SNMP v1/v2c traps (P1-1). **Disabled by default** — when not enabled all `TRAPD_*` settings are inert, and it is **fully orthogonal** to polling (stopping it does not affect monitoring).

```bash
# 1) Enable in /etc/ipip/ipip.env
#    TRAPD_ENABLED=true
#    TRAPD_LISTEN_PORT=10162

# 2) Start (install-units.sh has installed the unit, but it must be enabled manually)
sudo systemctl enable --now ipip-trapd.service

# 3) Point switches' trap target at this host/port
#    snmp-server host <ipip-ip> <community> 10162

# Rollback
sudo systemctl disable --now ipip-trapd.service
```

| Item | Description |
|------|-------------|
| Listen / rate limit | `TRAPD_LISTEN_ADDRESS` (default `0.0.0.0`), `TRAPD_LISTEN_PORT` (default **10162**), `TRAPD_RATE_LIMIT_PER_MINUTE` (default 120/min, guards against trap storms) |
| Privileged port | The standard port **162** is privileged and requires root or `CAP_NET_ADMIN`; in unprivileged environments use 10162 and set the target port on the switch side |
| Community | `TRAPD_COMMUNITIES` (comma-separated, default `public`). **Change it from the default**; mismatched traps are dropped at the transport layer |
| Queue | `TRAPD_QUEUE_SIZE` (default 1000). When full, new traps are dropped with an aggregated counter logged periodically (not per-trap), so storms cannot overwhelm the service |
| Custom rules | `TRAP_CUSTOM_RULES` (JSON array, vendor-MIB OID extensions); **parse failures refuse startup** rather than degrading to "allow all / drop all" |

Rule hits do **not** raise alerts directly — they go through the same unified governance pipeline as the non-trap path (silence/throttle → alert outbox → SSE push), so silence rules, suppression, and tracking behave identically.

## Environment Variables

See `.env.example`. Key items:

| Variable | Description | Default |
|----------|-------------|---------|
| `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | Database connection | localhost / 3306 / root / / ip_manager |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` / `REDIS_DB` | Redis connection | localhost / 6379 / / 0 |
| `SECRET_KEY` | Flask session key | **must change** |
| `JWT_SECRET_KEY` | JWT signing key | **must change** |
| `FLASK_PORT` | Flask listen port | 5000 |
| `MONITOR_ENABLED` | Enable the monitoring service | true |
| `MONITOR_WORKER_IN_PROCESS` | In-process monitoring worker inside Flask (set false for standalone deployment) | false |
| `SSE_RING_BUFFER_SIZE` | SSE ring buffer size (Redis shared) | 200 |
| `SSE_RING_TTL_SECONDS` | SSE ring buffer TTL | 3600 |
| `AI_ASYNC_ENABLED` | Enable Celery AI async tasks | 1 |
| `CELERY_BROKER_URL` | Celery broker (a dedicated Redis db is recommended) | redis://localhost:6379/1 |
| `CELERY_RESULT_BACKEND` | Celery result backend | redis://localhost:6379/2 |
| `CELERY_CONCURRENCY` | Celery worker concurrency | 2 |
| `CELERY_LOGLEVEL` | Celery log level | info |
| `TRAPD_ENABLED` | Enable the SNMP Trap receiver | false |
| `TRAPD_LISTEN_PORT` | Trap listen port (UDP) | 10162 |
| `TRAPD_COMMUNITIES` | Allowed communities (comma-separated) | public |
| `LDAP_ENABLED` | Enable LDAP/AD external authentication | false |
| `LDAP_SERVER` | Directory server address (e.g. `ldaps://dc.corp.local:636`) | — |
| `LDAP_BASE_DN` | Search base DN | — |
| `LDAP_GROUP_ROLE_MAP` | Group→role mapping (`group=>role;group=>role`) | — |
| `LDAP_BYPASS_USERS` | Emergency allowlist (bypass the directory, use local passwords) | — |

> The full variable list for LDAP groups and `TRAPD_*` lives in `.env.example`. **If `LDAP_ENABLED=true` but `LDAP_SERVER`/`LDAP_BASE_DN` is missing, or `LDAP_GROUP_ROLE_MAP` cannot be parsed, the app fails fast at startup** instead of failing at login time.
> Voice channel (Alibaba/Tencent Cloud) API keys, template IDs and called numbers are configured in the database `voice_setting` table via the "Settings → Voice Notifications" page, not via env.

## Seed Data

`migrations/seed_data.sql` + `seed_all.sh` (chaining seed_data.sql / seed_rbac.py / seed_component_templates.py / seed_users.py) provide the configuration seeds required to run the system:

| Table | Content |
|-------|---------|
| permissions | Permission codes (incl. `ai:use` / `ai:admin`) |
| roles | 4 roles (admin / operator / viewer / …) |
| role_permissions | Role-permission mapping (admin gets ai:use+ai:admin, operator gets ai:use) |
| component_templates | Component templates (CPU / memory / disk / NIC / GPU) |
| monitor_metric_templates | Monitoring metric templates |
| monitor_oid_category_rules | OID classification rules |
| monitor_vendor_brands | Vendor brands |
| monitor_dynamic_config | Monitoring dynamic config |

> VLANs and Webhook configs are business data configured through the UI after deployment; they are not seeded.

**Idempotent**: `seed_all.sh` can be re-run; each table is `DELETE`d then `INSERT`ed.

**Default administrator**: created by `seed_users.py`; the password comes from the `SEED_ADMIN_PASSWORD` env var, or a random one is generated and printed.

## Documentation

| Document | Content |
|----------|---------|
| [Unified Identity Integration manual](docs/ops/运维手册-企业身份集成.md) | LDAP/AD integration, group→role mapping, emergency bypass allowlist, login troubleshooting (Chinese) |
| [Backup & Restore manual](docs/ops/运维手册-备份与恢复.md) | T1 backup/restore, key export & re-import, safety-snapshot rollback (Chinese) |
| [Keys & Environment Variables manual](docs/ops/运维手册-密钥与环境变量.md) | Key management, environment variable conventions (Chinese) |
| [systemd hosting guide](deploy/systemd/README.md) | Per-unit reference, `ProtectSystem` hardening & allowlists, start/stop & troubleshooting (Chinese) |
| [RELEASE_NOTES_v1.0.md](RELEASE_NOTES_v1.0.md) | v1.0 release notes (Chinese) |

## Frontend Development

```bash
cd frontend-new
pnpm install
pnpm dev          # Dev server (http://localhost:3000, proxies /api → localhost:5000)
pnpm build        # Production build → dist/
pnpm lint         # Lint
```

During development run the backend with `python run.py` (port 5000) and the frontend with `pnpm dev` (port 3000); Vite proxies `/api` to the backend.

## Troubleshooting

| Symptom | What to check |
|---------|---------------|
| install.sh: Python not found | Install Python 3.14+ |
| install.sh: Node not found | Install Node.js 20+ |
| install.sh: pnpm not found | `corepack enable pnpm` or `npm i -g pnpm` |
| install.sh: MySQL connection failed | Check `MYSQL_*` in `.env`; verify network reachability |
| start.sh: venv missing | Run `bash scripts/install.sh` first |
| 404 for static assets after Flask starts | Confirm `frontend-new/dist/index.html` exists (frontend build succeeded) |
| SSE not pushing | Check `logs/gateway.log`; confirm Redis connectivity; with multiple replicas confirm they share one Redis |
| Monitoring not running | `bash scripts/start.sh status`, check `logs/monitor.log` |
| Celery not started | Confirm `AI_ASYNC_ENABLED=1` and `.venv/bin/celery` exists; check `logs/celery.log` |
| Voice notifications not delivered | Check the voice worker in `logs/flask.log`; confirm keys/templates are configured in the `voice_setting` table |
| Event center empty | Confirm `incident_aggregator` is running; check the `monitor_incident` table |
| DingTalk notifications not delivered | Check `logs/flask.log`; confirm the DingTalk robot webhook + **signing secret** are configured (the signing algorithm is DingTalk's, not Feishu's) |
| SNMP traps not received | Confirm `TRAPD_ENABLED=true`, `systemctl status ipip-trapd`, the switch's `snmp-server host` target port matches `TRAPD_LISTEN_PORT`, and the community is in `TRAPD_COMMUNITIES` |
| Traps received but no alerts | Check `journalctl -u ipip-trapd`: the OID missed the rules, or it hit a silence rule (rules can be extended via `TRAP_CUSTOM_RULES`) |
| LDAP login failed | Check `logs/flask.log`; confirm `LDAP_ENABLED=true` and `LDAP_SERVER`/`LDAP_BASE_DN` are set (missing values **fail at startup**), and `LDAP_GROUP_ROLE_MAP` syntax is valid; see the Unified Identity Integration manual |
| Topology discovery returns nothing | Confirm LLDP/CDP is enabled on devices and credentials allow SSH; Cisco devices fall back to CDP automatically when LLDP has no neighbors. Discovery results are **suggestions only** and require manual confirmation |
| systemd unit fails to start | `journalctl -u ipip-web -e`; confirm the `ipip.env` environment path is correct |
| Backup failed | Check `ipip-backup.service` logs; confirm MySQL/Redis connectivity and GPG key availability |
| AI config missing after restore | Confirm the backup includes the Redis RDB (`--skip-redis` skips it); restore re-imports Redis |

## Tech Stack

**Backend**: Python 3.14 · Flask 3.1 · SQLAlchemy 2.0 · MySQL 8.4 · Redis 8 · JWT · bcrypt · Celery · pysnmp · netmiko · pyghmi · ldap3 (pure Python, no system libldap)

**Frontend**: TypeScript 6 · React 19 · Vite 8 · Ant Design 6 · Zustand 5 · TanStack Query 5 · React Router 7 · Axios

**Real-time gateway**: Starlette · uvicorn · Redis Pub/Sub · SSE (seq/ring shared via Redis, multi-replica ready)

**Async tasks**: Celery (broker/result backend on dedicated Redis DBs, queues `ai,voice`)

**Backup/Restore**: MySQL mysqldump + Redis RDB + GPG-encrypted key export (`--include-secrets`); automatic safety snapshot before restore, rollback-able

**AI Assistant**: OpenAI-compatible LLM · ChromaDB vector store · sentence-transformers (bge-small-zh-v1.5) · jieba Chinese tokenization · Pydantic skill schema · tenacity retries · prometheus-client metrics

## AI Assistant

The AI assistant module provides alert interpretation, natural-language query, RAG knowledge base retrieval, and Agentic tool inspection & diagnosis. The module is included in the deploy-repository sync scope (`app/api/ai/`, `app/services/ai/`, `app/models/ai_*.py`, `app/tasks/ai_tasks.py`, `frontend-new/src/pages/AI/`).

### Tables

| Table | Purpose |
|-------|---------|
| `ai_conversations` | Conversation history (user_id + scenario index; cascading cleanup on user deletion) |
| `ai_diagnosis_sessions` | Agentic diagnosis sessions (device/skill/status indexes; sessions are kept for retrospective when a device is deleted) |

DDL lives in `migrations/versions/0000_baseline.sql` (migration baseline snapshot); `install.sh` imports it automatically at initialization and registers versions per the `0000_baseline.covers` list; later increments upgrade via `flask db-upgrade`.

### Permissions

| Code | Description | Default roles |
|------|-------------|---------------|
| `ai:use` | AI assistant usage (alert interpretation / NL query / RAG / inspection) | admin, operator |
| `ai:admin` | AI knowledge base management (RAG document ingestion) | admin |

Seeded idempotently by `seed_rbac.py`.

### Configuration

The AI LLM connection (provider / key / model / timeouts) has **two mutually exclusive** configuration modes, decided by whether the `AI_*` keys in `.env` are non-empty (`.env.example` ships them empty/commented, i.e. UI self-service):

| Mode | How to configure | Priority | After restart | Intended for |
|------|------------------|----------|---------------|--------------|
| ① Deployment-pinned | Non-empty `AI_PROVIDER` / `AI_API_KEY` / `AI_BASE_URL` / `AI_MODEL` in `.env` | env wins; the corresponding UI fields show "locked by deployment env" | Always the env value, stable | Vendors pre-provisioning; customers cannot change it |
| ② UI self-service | Keep the 4 keys empty and comment out numeric keys | With no env override, the Redis snapshot wins | Restored automatically from Redis `ai:config`; **UI changes are not reverted** | Customers configuring in "System Settings → AI Config" |

> **The two modes cannot be mixed**: any non-empty key switches to mode ①, and edits to env-covered fields in the UI are rejected (`locked`). Do not deploy with the placeholder defaults (`openai` / `gpt-4o-mini`) — those fields get locked permanently, switching the customer to deepseek etc. will not take effect, and restarts revert to the env values.
> **Redis is the only persistence for UI configuration**: UI input is stored under the Redis key `ai:config` (api_key encrypted with `SWITCH_SECRET_KEY`). Losing/flushing that key invalidates the UI config and falls back to defaults — do not clean that DB after deployment.
> **Never leave numeric keys empty**: `AI_TIMEOUT` etc. must be commented out whole-line (e.g. `#AI_TIMEOUT=30`); an empty value crashes `int()`/`float()` parsing at startup.

Main variables (full list in `.env.example`):

| Variable | Description |
|----------|-------------|
| `AI_PROVIDER` | LLM provider identifier (`openai` / `anthropic` / `custom`) |
| `AI_API_KEY` | LLM API key (leave empty to configure in the UI; stored encrypted in Redis) |
| `AI_BASE_URL` / `AI_MODEL` | LLM endpoint and model name |
| `AI_TIMEOUT` / `AI_STREAM_TIMEOUT` / `AI_MAX_TOKENS` / `AI_TEMPERATURE` | Call timeout / streaming timeout / max tokens / sampling temperature (defaults 30s / 120s / 2048 / 0.3) |
| `AI_ASYNC_ENABLED` | Enable the Celery `ai` async queue (`1` enables; anything else uses the synchronous path) |
| `AI_RAG_*` | RAG vector store and embedding configuration |

### Degradation & Protection

- **LLM unavailable**: AI endpoints return structured degradation responses; the main business is unaffected.
- **Celery not running**: when `AI_ASYNC_ENABLED != 1`, AI tasks run on the synchronous path; the voice queue is still delivered synchronously by Flask.
- **RAG not ingested**: retrieval returns empty results without blocking the Agentic flow.
- **Diagnosis rollback**: `ai_diagnosis_sessions.rollback_failed` flags devices stuck in an intermediate state for operator intervention.
- **Circuit breaker**: LLM/tool call failures feed `circuit_breaker`; past the threshold it short-circuits and returns the degradation response.

## License

See [LICENSE](LICENSE).
