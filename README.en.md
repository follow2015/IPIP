# ipip — IP Address & Network Asset Management Platform

[简体中文](README.md) | [English](README.en.md)

An all-in-one asset management & monitoring platform for network operations: data centers, cabinets, devices, IP subnets / VLANs, **carrier circuits**, topology, monitoring & alerting, customers and deployment planning — with a built-in AI assistant (alert interpretation / NL query / local RAG knowledge base / Agentic inspection & diagnosis).

**Current version: v1.5.0** — the single source of truth for the version is `VERSION` in `config.py`; the runtime endpoint is `GET /api/health` (`data.version`, also shown at the bottom of the sidebar).

- **Backend**: Flask + SQLAlchemy + Celery + MySQL 8.4 + Redis (cache / Celery broker / rate limiting)
- **Frontend**: React 19 + TypeScript + Vite + Ant Design 6
- **Realtime**: ASGI SSE gateway (seq/ring state shared via Redis, horizontally scalable)
- **AI**: chromadb (local vector store) + sentence-transformers (bge models) — **local inference, data never leaves the machine**
- **Hosting**: systemd units (recommended for production); Docker Compose for evaluation (see below)

## Features

| Module | Capabilities |
|--------|--------------|
| IP / IPAM | Data center / cabinet / device / IP allocation / VLAN / switch management |
| **Carrier Circuits (v1.5.0)** | Carrier profiles (contacts / NOC hotline), circuit management (circuit no. / bandwidth / five billing modes / lease expiry & renewal reminders), end-to-end segmented paths (device & port dropdowns with automatic route-anchor lookup), impact analysis (by connection / device / customer), customer linkage (customers with active circuits cannot be terminated) |
| Monitoring & Alerting | SNMP metric polling, threshold alerts, dependency suppression, alert tracking |
| **SNMP Trap** | Standalone `ipip-trapd` process receiving v1/v2c traps (see dedicated section below), reusing the unified alert governance pipeline |
| **Topology Discovery** | LLDP/CDP live probing (Huawei/H3C/Cisco) produces connection **suggestions**; nothing is written until manually confirmed (manual entries are never overwritten) |
| **Event Center** | Alert aggregation (L1 rule merge / L2 topology suppression / L3 change correlation), event impact analysis, lookback window |
| **Notification Delivery** | Multi-channel (in-app / Feishu / WeCom / DingTalk signed robot / email / custom Webhook / **voice calls**), delivery worker, cooldown windows (Redis, per event + channel), dead-letter tracking, strict delivery, per-user preferences |
| **Voice Channel** | Alibaba Cloud / Tencent Cloud voice notifications, dedicated voice worker, callback authentication, P0 alert escalation |
| **SSE Realtime** | Gateway seq/ring state shared via Redis, multi-replica ready |
| Customer / Audit | Customer management, operation audit, RBAC permissions |
| **Unified Identity** | LDAP/AD integration, group→role mapping, local emergency bypass allowlist (see the identity integration ops manual) |
| **AI Assistant** | Alert interpretation / NL query / RAG knowledge base / Agentic inspection & diagnosis; async on the Celery `ai` queue, isolated by `ai:use` / `ai:admin` permissions |
| Import Pipelines | Bulk import for devices / cabinets / customers |

## Option 1: One-command Script Install (Recommended for Production)

### Supported Systems & Field-test Status

The installer validates your OS **before touching anything** against `scripts/installer/supported-systems.conf` (the single data source shared by shell and Python): `supported` (field-tested recipe) / `manual` (allowed but not individually verified) / `rejected` (refused, with an upgrade pointer).

> **Ubuntu 24.04 LTS (or newer) is the recommended path** — fully field-tested, works out of the box: Python comes from the deadsnakes PPA without compilation, the fastest route. Unless you have a good reason, don't leave this path.

| OS | Level | Field-test status |
|---|---|---|
| **Ubuntu 24.04 LTS** | ✅ supported | **Fully tested 2026-10-04**: install completed, all six units active, HTTP 200 (recommended path) |
| Debian 12 | ✅ supported | Fully tested 2026-10-04: Python via uv (python-build-standalone) |
| Rocky Linux 10.2 | ✅ supported | Fully tested 2026-10-03: AI/RAG fully functional |
| CentOS Stream 9 | ✅ supported | Tested on real hardware 2026-10-03 |
| Ubuntu 26.04 / Debian 13 | ✅ supported | Supported by design, not individually tested |
| Rocky 9 / AlmaLinux 9 / RHEL 9 | ✅ supported | Criteria-level tested; **installer automatically uses uv for Python** (el9 system sqlite doesn't satisfy chromadb; source build would downgrade AI/RAG) |
| AlmaLinux 10 / RHEL 10 | ⚙️ manual | Same recipe as el10 (MySQL auto-installs `mysql8.4-server`, Redis auto-installs `valkey`), not individually tested |
| CentOS 7 / 8, RHEL 7 / 8, Rocky / Alma 8 | ❌ rejected | EOL; glibc/openssl insufficient for building Python 3.14 |
| Ubuntu 18.04 / 20.04, Debian 10 / 11 | ❌ rejected | Past maintenance end |
| Alpine | ❌ rejected | musl libc; wheel ecosystem and systemd hosting both unsuitable |

### Install

```bash
git clone https://github.com/follow2015/IPIP.git
cd IPIP
bash scripts/installer/bootstrap.sh            # Full install (auto-provisions Python/Node/MySQL/Redis)
bash scripts/installer/bootstrap.sh --help     # All options
```

The installer has two layers:

1. **`bootstrap.sh` (pre-flight guard)**: zero-dependency OS verdict, /tmp noexec detection, openssl upgrade pre-check, sqlite version check, and automatic provisioning of Python 3.14 (Ubuntu=deadsnakes, others=uv, source build as fallback);
2. **`python -m installer` (orchestrator)**: completes dependency installation, frontend build, DB initialization, model download and final verification, in **seven steps**:

| Step | Contents |
|---|---|
| [1/7] | Host facts + host package baseline provisioning (skip with `--skip-syspkg`) |
| [2/7] ‖ [3/7] | venv + Python deps (torch flavor handling) ‖ frontend build (**parallel**) |
| [4/7] | Initialize `.env` (first run creates it from `.env.example`) |
| [5/7] ‖ [6/7] | Database initialization (create DB + migration baseline) ‖ RAG model download (fallback retry if the parallel branch fails) |
| [6/7] | Seed data import (incl. default admin; in upgrade mode becomes idempotent RBAC role/permission sync) |
| [7/7] | Process hosting install (`--with-units`) + final verification & credential summary |

**After the first run**: edit `.env` and fill in the real `MYSQL_PASSWORD`, `REDIS_PASSWORD`, `SECRET_KEY`, `JWT_SECRET_KEY`, then run the install command again — completed steps are skipped automatically.

### Installer Options (compatible with the legacy install.sh)

| Option | Effect |
|---|---|
| `--skip-syspkg` | Don't touch host packages (when Python/Node/MySQL/Redis already provided) |
| `--skip-frontend` | Skip the frontend build (requires `frontend-new/dist/` to exist) |
| `--skip-db` | Skip database schema initialization |
| `--skip-seed` | Skip seed data import |
| `--skip-models` | Skip RAG model download (~1.2GB, RAG unavailable) |
| `--cpu` | Explicitly install CPU torch (default, ~190MB) |
| `--gpu` | CUDA build of torch (~2.6-3.5GB, NVIDIA GPU required; **always use the default CPU build without a GPU**) |
| `--gpu-fast` | CUDA build + parallel prefetch of large packages from multiple mirrors (faster) |
| `--with-units` | Install systemd hosting units (requires root; required for production) |
| `--units-user NAME` | Service run account (default `ipip`; use root if the project lives under /root) |
| `--units-group NAME` | Service run group (defaults to `--units-user`) |
| `--upgrade` | Upgrade mode: reuses installed torch flavor, runs DB migrations automatically, seeds become idempotent RBAC sync |
| `--selftest` | Run criteria self-checks only (mirror speed + baseline health), no system changes |

**Upgrading to a new release**: pull the code, then run `bash scripts/installer/bootstrap.sh --upgrade` (runs `flask db-upgrade` automatically; since 1.5.0 RBAC permission changes require running `seed_rbac` per the release notes).

### Start

#### Option A: systemd Hosting (recommended for production, after `--with-units`)

```bash
bash deploy/systemd/install-units.sh   # Render & install all units + ipip.target
systemctl start ipip.target            # Start everything
systemctl stop  ipip.target            # Stop everything (PartOf cascades)
systemctl status ipip-web              # Check a single service
```

| Unit | Process | Description |
|---|---|---|
| `ipip-web` | Flask HTTP API | gunicorn WSGI, port 5000 |
| `ipip-gateway` | SSE realtime gateway | uvicorn ASGI, port 8000 |
| `ipip-monitor` | Monitoring service | SNMP polling + alerts + event aggregation |
| `ipip-celery-ai` | Celery AI queue | Async AI tasks (`ai` queue) |
| `ipip-celery-voice` | Celery voice queue | Voice notification delivery (`voice` queue) |
| `ipip-trapd` | SNMP Trap receiver | UDP v1/v2c; **opt-in** — the unit is rendered/installed but not auto-enabled |
| `ipip-backup` + `.timer` | Scheduled backup | MySQL dump + Redis RDB + GPG key export |
| `ipip-watchdog` + `.timer` | Heartbeat watchdog | T2 self-monitoring, heartbeat-timeout alerts |

> `install-units.sh --enable` only `enable --now`s the always-on services and timers, **excluding `ipip-trapd` / `ipip-backup`**: backups are timer-scheduled and trap reception needs switch-side configuration first, so both stay opt-in. Per-unit troubleshooting: `deploy/systemd/README.md`.

#### Option B: Script Start/Stop (development / temporary runs)

```bash
bash scripts/start.sh           # Start everything (Flask + gateway + monitor + celery)
bash scripts/start.sh status    # Per-process status
bash scripts/start.sh stop      # Stop
bash scripts/start.sh restart   # Restart
bash scripts/start.sh flask     # Flask only; gateway / monitor / celery likewise
```

**Service ports** (configurable in `.env`): Flask API `5000` (`FLASK_PORT`), SSE gateway `8000` (`GATEWAY_PORT`), Trap receiver `10162/udp` (`TRAPD_LISTEN_PORT`).
**PID files**: `logs/run/{flask,gateway,monitor,celery}.pid`; **logs**: `logs/{flask,gateway,monitor,celery}.log`.

> The Celery worker is controlled by `AI_ASYNC_ENABLED=1`; when off, AI tasks run on the synchronous path. It is skipped automatically if `.venv/bin/celery` doesn't exist. `start.sh` does **not** manage `ipip-trapd` (trap reception is a separate optional service, hosted by systemd only).

Then open `http://<server-ip>:5000`.

### Version Baseline (below baseline = unverified environment)

| Component | Baseline | Level |
|---|---|---|
| Python | **3.14** | Hard (`realtime_gateway` needs `asyncio.AsyncGenerator` from 3.14; lower versions crash at startup) |
| Node | 26.7 | Hard (older pnpm silently skips the rolldown native binding, breaking at build time) |
| MySQL | 8.4 | Warning (8.0 tested working, but an unverified combination) |
| Redis | 8.0 | Warning (7.x tested working; el10 uses valkey) |

## SNMP Trap Receiver (Optional)

Besides polling, a standalone process `ipip-trapd` receives SNMP v1/v2c traps. **Disabled by default** — when off, all `TRAPD_*` settings are inert, and it is **fully orthogonal** to polling (stopping it doesn't affect monitoring).

```bash
# 1) Enable in /etc/ipip/ipip.env
#    TRAPD_ENABLED=true
#    TRAPD_LISTEN_PORT=10162

# 2) Start (the unit is installed by install-units.sh, but must be enabled manually)
sudo systemctl enable --now ipip-trapd.service

# 3) Point switches' trap target at this host/port
#    snmp-server host <ipip-ip> <community> 10162

# Rollback
sudo systemctl disable --now ipip-trapd.service
```

| Item | Description |
|---|---|
| Listen / rate limit | `TRAPD_LISTEN_ADDRESS` (default `0.0.0.0`), `TRAPD_LISTEN_PORT` (default **10162**), `TRAPD_RATE_LIMIT_PER_MINUTE` (default 120/min, guards against trap storms) |
| Privileged port | Standard port **162** requires root or `CAP_NET_ADMIN`; in unprivileged environments use 10162 and set the target port on the switch side |
| Community | `TRAPD_COMMUNITIES` (comma-separated, default `public`). **Change it from the default**; mismatched traps are dropped at the transport layer |
| Queue | `TRAPD_QUEUE_SIZE` (default 1000). When full, new traps are dropped with an aggregated counter logged periodically (not per-trap), so storms cannot overwhelm the service |
| Custom rules | `TRAP_CUSTOM_RULES` (JSON array, vendor-MIB OID extensions); **parse failures refuse startup** rather than degrading to "allow all / drop all" |

Rule hits do **not** raise alerts directly — they go through the same unified governance pipeline as the non-trap path (silence/throttle → alert outbox → SSE push), so silence rules, suppression, and tracking behave identically.

## Option 2: Docker Compose (For Evaluation)

Images are built and published to GHCR (`ghcr.io/follow2015/ipip`) automatically by GitHub Actions (`.github/workflows/docker-publish.yml`) — evaluators don't need a local build:

| Trigger | Image tag produced |
|---|---|
| Pushing a `v*` version tag (release) | `:1.5.0` (semver) |
| Every push to `main` | `:main` (default tag, works out of the box) |
| Manual `workflow_dispatch` | `:main` of the chosen branch |

- **Multi-arch**: `linux/amd64` + `linux/arm64` (native on Apple Silicon, no Rosetta emulation)
- Images **include the RAG models** (the build carries a ~1.15GB model layer)

```bash
cp .env.example .env                  # Set passwords & secrets as needed
docker compose pull && docker compose up -d   # Services up in 1-3 min
```

- Topology: `mysql + redis → migrate → seed → web / celery-ai / celery-voice / monitor`, with the nginx `proxy` as the single entry point; `trapd` runs on an opt-in profile (off by default to avoid a 162/udp conflict)
- Pin a version: set `IPIP_IMAGE_TAG=1.5.0` in `.env` (the image produced by the repo's `v1.5.0` tag; defaults to `main` when unset)
- ⚠️ This compose file targets **dev/evaluation environments**, not production; use the systemd path (Option 1) for production
- Local code changes: `docker compose build && docker compose up -d` (overwrites the same tag, first build ~20 min)

## Configuration

Copy `.env.example` to `.env`. Key items (full list with comments in `.env.example`):

| Variable | Description | Default |
|---|---|---|
| `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | Database connection | localhost / 3306 / root / — / ip_manager |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` / `REDIS_DB` | Redis connection | localhost / 6379 / — / 0 |
| `SECRET_KEY` / `JWT_SECRET_KEY` | Session & JWT signing keys | **must change** |
| `FLASK_PORT` | Flask listen port | 5000 |
| `MONITOR_ENABLED` / `MONITOR_WORKER_IN_PROCESS` | Monitoring toggle / in-process worker (set false for standalone deployment) | true / false |
| `SSE_RING_BUFFER_SIZE` / `SSE_RING_TTL_SECONDS` | SSE ring buffer (Redis shared) | 200 / 3600 |
| `AI_ASYNC_ENABLED` | Enable Celery AI async tasks | 1 |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` / `CELERY_CONCURRENCY` | Celery broker / result backend / concurrency (dedicated Redis DBs recommended) | redis://…:6379/1, /2, 2 |
| `TRAPD_ENABLED` / `TRAPD_LISTEN_PORT` / `TRAPD_COMMUNITIES` | Trap receiver toggle / port / communities | false / 10162 / public |
| `LDAP_ENABLED` / `LDAP_SERVER` / `LDAP_BASE_DN` / `LDAP_GROUP_ROLE_MAP` / `LDAP_BYPASS_USERS` | LDAP/AD external authentication (see the identity integration manual) | false |
| Notification channels | Feishu / WeCom / DingTalk / email / Webhook variables | as needed |

Three caveats:

- **LDAP fail-fast**: if `LDAP_ENABLED=true` but `LDAP_SERVER`/`LDAP_BASE_DN` is missing, or `LDAP_GROUP_ROLE_MAP` cannot be parsed, the app **fails at startup**, not at login time.
- **Voice channel is not env-configured**: Alibaba / Tencent Cloud keys, template IDs and called numbers are configured on the "Settings → Voice Notifications" page (database `voice_setting` table).
- **AI LLM connection has two mutually exclusive modes**: non-empty `AI_PROVIDER` / `AI_API_KEY` etc. in `.env` = deployment-pinned (UI fields locked); all empty = UI self-service ("System Settings → AI Config", snapshot in Redis `ai:config` — **don't flush that DB after deployment**). The modes cannot be mixed; never deploy with placeholder defaults (`openai`/`gpt-4o-mini`).

## Seed Data

`migrations/seed_data.sql` + `migrations/seed_all.sh` (chaining seed_data.sql / seed_rbac.py / seed_component_templates.py / seed_users.py) provide the configuration seeds required to run the system:

| Table | Content |
|---|---|
| permissions | Permission codes (incl. `ai:use` / `ai:admin`) |
| roles / role_permissions | Roles (admin / operator / viewer, etc.) and their mapping |
| component_templates | Component templates (CPU / memory / disk / NIC / GPU) |
| monitor_metric_templates | Monitoring metric templates |
| monitor_oid_category_rules | OID classification rules |
| monitor_vendor_brands | Vendor brands |
| monitor_dynamic_config | Monitoring dynamic config |

- **Idempotent**: `seed_all.sh` can be re-run (each table is DELETEd then INSERTed)
- **Default administrator**: created by `seed_users.py`; the password comes from the `SEED_ADMIN_PASSWORD` env var, or a random one is generated and printed
- VLANs and Webhook configs are business data configured through the UI after deployment; they are not seeded

## Directory Layout

```
IPIP/
├── README.md                   # Chinese version
├── README.en.md                # This file (English)
├── LICENSE
├── .env.example                # Environment variable template (sanitized)
├── app/                        # Flask backend
│   ├── api/                    # Routes (monitor/incident, topology, circuit, voice, etc.)
│   ├── adapters/               # Device adapters (Huawei/H3C/Cisco command wrapping + LLDP/CDP parsing + TextFSM templates)
│   ├── models/                 # SQLAlchemy models
│   ├── services/               # Business services
│   │   ├── monitoring/         # Monitoring (event aggregation, dependency suppression, escalation, trap_*)
│   │   ├── channels/           # Notification channels (incl. voice, Ali/Tencent providers)
│   │   ├── ldap_*.py           # LDAP/AD authentication, group→role mapping, config self-check
│   │   ├── topology/           # Topology queries & impact analysis
│   │   └── notification_delivery_worker.py  # Delivery worker (cooldown / dead-letter / strict delivery)
│   ├── tasks/                  # Celery async tasks
│   ├── celery_app.py           # Celery app definition
│   └── persistence/            # Repository layer
├── frontend-new/               # Frontend source (React 19 + AntD 6 + Vite)
├── realtime_gateway/           # ASGI SSE gateway (uvicorn, multi-replica ready)
├── migrations/
│   ├── versions/               # Alembic migrations (0000_baseline.sql = baseline snapshot)
│   └── seed_all.sh / seed_*.py # Seed data (idempotent)
├── scripts/
│   ├── installer/              # bootstrap.sh + Python installer (OS verdict / deps / DB init)
│   ├── start.sh                # One-command start/stop (4 processes)
│   ├── credentials.py          # Credential view/reset tool
│   ├── backup_system.py        # T1 backup (MySQL dump + Redis RDB + GPG key export)
│   ├── restore_system.py       # T1 restore (automatic safety snapshot, rollback-able)
│   ├── heartbeat_watchdog.py   # T2 self-monitoring watchdog (heartbeat-timeout alerts)
│   └── download_models.py      # Offline AI model pre-download
├── deploy/
│   ├── systemd/                # systemd units + install-units.sh + README (per-unit troubleshooting)
│   └── docker/                 # Image entrypoint & nginx config
├── docs/ops/                   # Operations manuals (see below)
├── config.py                   # Backend config entry (incl. LDAP_* / TRAPD_* startup validation)
├── run.py / wsgi.py            # Development / production (gunicorn) entry points
└── run_trapd_service.py        # Standalone SNMP Trap receiver entry
```

## Documentation

| Document | Contents |
|---|---|
| [运维手册-密钥与环境变量](docs/ops/运维手册-密钥与环境变量.md) | Key management, environment variable conventions (Chinese) |
| [运维手册-备份与恢复](docs/ops/运维手册-备份与恢复.md) | T1 backup/restore, key export & re-import, safety-snapshot rollback (Chinese) |
| [运维手册-企业身份集成](docs/ops/运维手册-企业身份集成.md) | LDAP/AD integration, group→role mapping, emergency bypass, login troubleshooting (Chinese) |
| [systemd hosting guide](deploy/systemd/README.md) | Per-unit reference, `ProtectSystem` hardening & allowlists, start/stop & troubleshooting (Chinese) |

For the full API, see the OpenAPI snapshot (`openapi.json`); at runtime, `GET /api/health` serves as the liveness probe.

## Frontend Development

```bash
cd frontend-new
pnpm install
pnpm dev          # Dev server (http://localhost:3000, proxies /api → localhost:5000)
pnpm build        # Production build → dist/
pnpm lint         # Lint
```

## License

See [LICENSE](LICENSE).
