# ipip — IP 管理系统

开源 IP/IPAM 管理系统：机房、机柜、设备、IP 分配、VLAN、交换机、监控告警、客户管理一体化平台，内置 AI 助手（告警解读 / NL 查询 / RAG 知识库 / Agentic 巡查诊断）。

后端 Flask + SQLAlchemy + MySQL + Redis，前端 React 19 + Ant Design 6 + Vite 8，ASGI SSE 实时推送网关（多副本就绪），Celery 异步任务底座（AI 长任务 + 语音通知）。

通知渠道：站内、飞书、企业微信、**钉钉（自定义机器人加签）**、邮件、**自定义 Webhook**、**语音（阿里云/腾讯云）**，统一投递 worker 带**冷却窗口**（Redis，按事件+渠道）、队列满死信留痕、严格投递（失败上报，供告警发件箱重试）。

认证方式：本地账号 + **LDAP/AD 外部认证**（组→角色映射、白名单应急绕过）。

## 功能概览

| 模块 | 能力 |
|------|------|
| IP/IPAM | 机房/机柜/设备/IP 分配/VLAN/交换机管理 |
| 监控告警 | SNMP 指标采集、阈值告警、依赖抑制、告警留痕 |
| **SNMP Trap** | 独立 `ipip-trapd` 进程接收 v1/v2c trap，内置标准规则 + 站点自定义 OID 规则，全局限流防风暴，复用统一告警治理链路（静默/节流 → 发件箱 → SSE） |
| **拓扑发现** | LLDP/CDP 活体探测（华为/H3C/Cisco）→ 生成连接**建议**，人工确认后落库（**绝不覆盖手工录入**） |
| **事件中心** | 告警聚合（L1 规则归并 / L2 拓扑抑制 / L3 变更关联）、事件影响面、回溯窗口 |
| **通知投递** | 多渠道（站内/飞书/企微/钉钉/邮件/自定义 Webhook/语音）、投递 worker、冷却窗口（Redis）、死信留痕、严格投递、用户偏好 |
| **语音渠道** | 阿里云/腾讯云语音通知、独立 voice worker、回调鉴权、升级链路 P0 告警叫醒 |
| **SSE 实时** | 网关 seq/ring 迁 Redis 共享状态，多副本水平扩展 |
| 客户/审计 | 客户管理、操作审计、RBAC 权限 |
| **统一身份** | LDAP/AD 接入、组→角色映射、本地白名单应急绕过（详见《运维手册-企业身份集成》） |
| **AI 助手** | 告警解读 / NL 查询 / RAG 知识库 / Agentic 巡查诊断；Celery `ai` 队列异步执行，RBAC `ai:use`/`ai:admin` 权限隔离 |

## 目录结构

```
ipip/
├── README.md                   # 本文件
├── LICENSE                     # 开源协议
├── RELEASE_NOTES_v1.0.md       # v1.0 发布说明
├── .env.example                # 环境变量模板（脱敏）
├── .gitignore
├── app/                        # 后端 Flask 应用
│   ├── api/                    # 路由（含 monitor/incident、voice_callback/voice_settings、topology）
│   ├── adapters/               # 设备适配器（华为/H3C/Cisco：命令封装 + LLDP/CDP 解析）
│   ├── models/                 # SQLAlchemy 模型（含 monitor_incident、voice_setting 等）
│   ├── services/               # 业务服务
│   │   ├── monitoring/         # 监控（含 incident_aggregator、alert_dependency_service、escalation_service、trap_*）
│   │   ├── channels/           # 通知渠道（含 voice、voice_providers/aliyun/tencent）
│   │   ├── ldap_*.py           # LDAP/AD 认证、身份、组→角色映射、配置自检
│   │   ├── topology_discovery_service.py  # LLDP/CDP 拓扑发现（建议式）
│   │   └── notification_delivery_worker.py  # 投递 worker（冷却窗口/死信留痕/严格投递）
│   ├── tasks/                  # Celery 异步任务（voice_tasks 等）
│   ├── celery_app.py           # Celery 应用定义
│   └── persistence/            # 仓储层（含 monitor_incident_repository 等）
├── config.py                   # 后端配置入口（含 LDAP_* / TRAPD_* 启动期校验）
├── extensions.py               # SQLAlchemy 扩展
├── wsgi.py                     # WSGI 入口（gunicorn 用）
├── run.py                      # 开发启动入口
├── run_monitor_service.py      # 监控独立服务入口
├── run_trapd_service.py        # SNMP Trap 接收独立服务入口（P1-1）
├── realtime_gateway/           # ASGI SSE 网关（uvicorn，seq/ring 走 Redis 共享，多副本就绪）
├── requirements.txt            # Python 依赖（钉版）
├── frontend-new/               # 前端源码（React 19 + AntD 6 + Vite 8）
│   ├── src/
│   │   ├── pages/Monitor/Incidents/   # 事件中心页
│   │   ├── pages/Topology/            # 拓扑页（含 LLDP/CDP 发现建议面板）
│   │   ├── pages/Settings/VoiceSettings.tsx  # 语音渠道配置
│   │   └── services/voice-settings.ts
│   ├── package.json
│   ├── pnpm-lock.yaml
│   └── vite.config.js
├── migrations/
│   ├── versions/
│   │   ├── 0000_baseline.sql   # 完整建表 DDL（迁移基线快照，含分区表与触发器）
│   │   └── 0000_baseline.covers # 基线已覆盖的迁移版本清单
│   ├── seed_all.sh             # 统一种子入口（install.sh 调用）
│   ├── seed_data.sql           # 配置类种子（初次安装固定定义数据）
│   ├── seed_rbac.py            # RBAC 种子（含 ai:use/ai:admin 权限，幂等）
│   ├── seed_component_templates.py
│   └── seed_users.py           # 默认管理员账户
├── scripts/
│   ├── install.sh              # 一键安装（venv + 前端构建 + DB + 种子）
│   ├── start.sh                # 一键启动/停止/状态（4 进程：Flask + gateway + monitor + celery）
│   ├── credentials.py          # 凭据查看/重置工具（install.sh 收尾的凭据汇总会调用）
│   ├── backup_system.py        # T1 备份（MySQL dump + Redis RDB + GPG 加密密钥导出）
│   ├── restore_system.py       # T1 恢复（恢复前自动安全快照，可回退）
│   ├── heartbeat_watchdog.py   # T2 自监控 watchdog（心跳超时告警）
│   ├── download_models.py      # 离线 AI 模型预置（sentence-transformers 等）
│   ├── backfill_utc_timestamps.py  # 存量时间戳 UTC 回填（默认水位=切换时刻，防二次偏移）
│   └── import_sql.py           # SQL 导入工具（DELIMITER 触发器切分）
├── deploy/
│   └── systemd/                # systemd unit（ADR-003 拍板，替代 start.sh 托管）
│       ├── ipip.target         # 统一目标（stop ipip.target 一键停全部）
│       ├── ipip-web.service    # Flask HTTP API
│       ├── ipip-gateway.service # SSE 实时网关
│       ├── ipip-monitor.service # 监控服务
│       ├── ipip-celery-ai.service # Celery AI 异步队列
│       ├── ipip-celery-voice.service # Celery 语音队列
│       ├── ipip-trapd.service  # SNMP Trap 接收（opt-in，见下文）
│       ├── ipip-backup.service / .timer # 定时备份
│       ├── ipip-watchdog.service / .timer # 心跳 watchdog
│       ├── install-units.sh    # unit 安装脚本
│       ├── README.md           # systemd 托管部署说明（含逐 unit 排障）
│       └── ipip.env.example    # systemd 环境段模板
├── docs/                       # 运维手册（见「文档」节）
└── logs/                       # 运行时日志（gitignore）
```

## 系统要求

| 组件 | 版本 | 说明 |
|------|------|------|
| Python | 3.14+ | 后端运行时（`realtime_gateway` 依赖 3.14 的 `asyncio.AsyncGenerator`，不允许降级） |
| Node.js | 20+ | 前端构建 |
| pnpm | 10+ | 前端包管理（`corepack enable pnpm` 可启用） |
| MySQL | 8.4+ | 数据库 |
| Redis | 6+ | 缓存 / SSE 事件总线 / Celery broker |

## 快速部署

### 1. 克隆仓库

```bash
git clone https://github.com/<your-org>/ipip.git
cd ipip
```

### 2. 一键安装

```bash
bash scripts/install.sh
```

安装脚本会依次执行：
1. 检查系统依赖（Python / Node / pnpm / MySQL 客户端 / redis-cli）
2. 创建 Python venv 并安装 `requirements.txt`（默认 CPU 版 torch，`--gpu` 装 CUDA 版）
3. 前端依赖安装 + 构建（`cd frontend-new && pnpm install && pnpm build`）
4. 从 `.env.example` 创建 `.env`（首次运行，需编辑后重跑）
5. 创建 MySQL 数据库并导入迁移基线 `0000_baseline.sql`（按 covers 清单登记版本）
6. 导入种子数据（`seed_all.sh`）
7. 下载 RAG 本地模型到 HF 缓存（embedding ≈92MB + reranker ≈1100MB，`--skip-models` 跳过）
8. 【可选】安装 systemd unit（`--with-units`，需 root）

**首次运行后**：编辑 `.env` 填写实际的 `MYSQL_PASSWORD`、`REDIS_PASSWORD`、`SECRET_KEY`、`JWT_SECRET_KEY`，然后再次执行 `bash scripts/install.sh`（已完成的步骤会跳过）。

### 3. 启动

```bash
bash scripts/start.sh           # 启动全部（Flask + gateway + monitor + celery）
bash scripts/start.sh status    # 查看运行状态
bash scripts/start.sh stop      # 停止全部
bash scripts/start.sh restart   # 重启全部
```

访问 `http://<server-ip>:5000` 即可使用。

## 安装脚本选项

| 选项 | 说明 |
|------|------|
| `--skip-frontend` | 跳过前端构建（要求 `frontend-new/dist/` 已存在） |
| `--skip-db` | 跳过数据库 schema 初始化 |
| `--skip-seed` | 跳过种子数据导入 |
| `--skip-models` | 跳过本地 AI 模型下载（不需要 RAG 时用） |
| `--cpu` | 显式指定 CPU 版 torch（默认，约 190MB） |
| `--gpu` | 安装 CUDA 版 torch（需 NVIDIA GPU，约 2.6-3.5GB，耗时 30-60 分钟） |
| `--gpu-fast` | CUDA 版 + 多镜像分散并行预取大包（更快） |
| `--with-units` | 安装完成后渲染并安装 systemd unit（需 root） |
| `--units-user NAME` | 服务运行账号（默认 ipip；项目在 /root 下应为 root） |
| `--units-group NAME` | 服务运行组（默认同 `--units-user`） |
| `--units-script PATH` | 指定 `install-units.sh` 路径 |
| `--help` | 查看用法 |

## 启动脚本命令

| 命令 | 说明 |
|------|------|
| `start` (默认) | 启动 Flask + gateway + monitor + celery |
| `stop` | 停止全部 |
| `restart` | 重启全部 |
| `status` | 查看各进程运行状态 |
| `flask` | 仅启动 Flask |
| `gateway` | 仅启动 SSE 网关 |
| `monitor` | 仅启动监控服务 |
| `celery` | 仅启动 Celery worker（AI 异步任务队列 `ai`） |

**服务端口**（可在 `.env` 中配置）：

| 服务 | 默认端口 | 环境变量 |
|------|----------|----------|
| Flask HTTP API | 5000 | `FLASK_PORT` |
| realtime_gateway (SSE) | 8000 | `GATEWAY_PORT` |
| SNMP Trap 接收 (ipip-trapd) | 10162 (UDP) | `TRAPD_LISTEN_PORT` |

**PID 文件**：`logs/run/{flask,gateway,monitor,celery}.pid`
**日志文件**：`logs/{flask,gateway,monitor,celery}.log`

> Celery worker 受 `AI_ASYNC_ENABLED` 控制：设为 `1` 启动，非 `1` 跳过（AI 任务走同步路径）。若 `.venv/bin/celery` 不存在也会自动跳过。
> `start.sh` **不管理** `ipip-trapd`（trap 接收是独立的可选服务，仅由 systemd 托管）。

### 3a. systemd 托管（生产推荐）

`start.sh` 适合开发/临时运行；生产环境推荐用 systemd 托管（ADR-003），支持开机自启、命名空间隔离（`ProtectSystem=strict`）、统一启停：

```bash
bash deploy/systemd/install-units.sh   # 安装全部 unit + ipip.target
systemctl start ipip.target            # 启动全部
systemctl stop ipip.target             # 停止全部（PartOf 级联）
systemctl status ipip-web              # 查看单个服务
```

| unit | 进程 | 说明 |
|------|------|------|
| `ipip-web` | Flask HTTP API | gunicorn WSGI，端口 5000 |
| `ipip-gateway` | SSE 实时网关 | uvicorn ASGI，端口 8000 |
| `ipip-monitor` | 监控服务 | SNMP 采集 + 告警 + 事件聚合 |
| `ipip-celery-ai` | Celery AI 队列 | 异步 AI 任务（`ai` 队列） |
| `ipip-celery-voice` | Celery 语音队列 | 语音通知投递（`voice` 队列） |
| `ipip-trapd` | SNMP Trap 接收 | UDP 收 v1/v2c trap；**opt-in**——`install-units.sh` 只渲染安装、不自动 enable |
| `ipip-backup` + `.timer` | 定时备份 | MySQL dump + Redis RDB + GPG 密钥导出 |
| `ipip-watchdog` + `.timer` | 心跳 watchdog | T2 自监控，心跳超时告警 |

> `install-units.sh --enable` 只 `enable --now` 上表中**除 `ipip-trapd`/`ipip-backup` 外**的常驻服务与 timer：备份按 timer 调度、trap 接收需先配好交换机侧，均保持 opt-in。

## SNMP Trap 接收（可选）

除轮询采集外，另提供独立进程 `ipip-trapd` 接收 SNMP v1/v2c Trap（P1-1）。**默认关闭**——不启用时全部 `TRAPD_*` 配置无效，且与轮询采集**完全正交**（停掉它不影响监控）。

```bash
# 1) 在 /etc/ipip/ipip.env 中启用
#    TRAPD_ENABLED=true
#    TRAPD_LISTEN_PORT=10162

# 2) 启动（install-units.sh 已安装该 unit，但需手工 enable）
sudo systemctl enable --now ipip-trapd.service

# 3) 交换机侧把 trap 目标指向本机端口
#    snmp-server host <ipip-ip> <community> 10162

# 回滚
sudo systemctl disable --now ipip-trapd.service
```

| 项 | 说明 |
|----|------|
| 监听/限流 | `TRAPD_LISTEN_ADDRESS`（默认 `0.0.0.0`）、`TRAPD_LISTEN_PORT`（默认 **10162**）、`TRAPD_RATE_LIMIT_PER_MINUTE`（默认 120 条/分钟，防 trap 风暴） |
| 特权端口 | 标准端口 **162** 属特权端口，需 root 或 `CAP_NET_ADMIN`；无特权环境用 10162 并在交换机侧指定目标端口 |
| community | `TRAPD_COMMUNITIES`（逗号分隔，默认 `public`）。**务必改为非默认值**；不匹配的 trap 在传输层即被丢弃 |
| 队列 | `TRAPD_QUEUE_SIZE`（默认 1000）。队列满时丢弃新 trap，并**累计计数、周期性记录**（不逐条刷日志），避免风暴期间压垮服务 |
| 自定义规则 | `TRAP_CUSTOM_RULES`（JSON 数组、按厂商 MIB 补 OID）；**解析失败会拒绝启动**，不会降级为"全部放行/全部丢弃" |

命中规则后**不直接发告警**，而是走与非 trap 路径同一套统一治理链路（静默/节流 → 告警发件箱 → SSE 推送），因此静默规则、抑制与留痕行为一致。

## 环境变量

参见 `.env.example`。关键项：

| 变量 | 说明 | 默认 |
|------|------|------|
| `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | 数据库连接 | localhost / 3306 / root / / ip_manager |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` / `REDIS_DB` | Redis 连接 | localhost / 6379 / / 0 |
| `SECRET_KEY` | Flask 会话密钥 | **必须修改** |
| `JWT_SECRET_KEY` | JWT 签名密钥 | **必须修改** |
| `FLASK_PORT` | Flask 监听端口 | 5000 |
| `MONITOR_ENABLED` | 是否启用监控服务 | true |
| `MONITOR_WORKER_IN_PROCESS` | Flask 进程内监控 worker（独立部署设 false） | false |
| `SSE_RING_BUFFER_SIZE` | SSE 环形缓冲大小（Redis 共享） | 200 |
| `SSE_RING_TTL_SECONDS` | SSE 环形缓冲 TTL | 3600 |
| `AI_ASYNC_ENABLED` | 是否启用 Celery AI 异步任务 | 1 |
| `CELERY_BROKER_URL` | Celery broker（建议独立 Redis db） | redis://localhost:6379/1 |
| `CELERY_RESULT_BACKEND` | Celery result backend | redis://localhost:6379/2 |
| `CELERY_CONCURRENCY` | Celery worker 并发数 | 2 |
| `CELERY_LOGLEVEL` | Celery 日志级别 | info |
| `TRAPD_ENABLED` | 是否启用 SNMP Trap 接收服务 | false |
| `TRAPD_LISTEN_PORT` | Trap 接收端口（UDP） | 10162 |
| `TRAPD_COMMUNITIES` | 允许的 community（逗号分隔） | public |
| `LDAP_ENABLED` | 是否启用 LDAP/AD 外部认证 | false |
| `LDAP_SERVER` | 目录服务地址（如 `ldaps://dc.corp.local:636`） | — |
| `LDAP_BASE_DN` | 检索基点 DN | — |
| `LDAP_GROUP_ROLE_MAP` | 组→角色映射（`组=>角色;组=>角色`） | — |
| `LDAP_BYPASS_USERS` | 应急白名单（绕过目录，走本地口令） | — |

> LDAP 组与 `TRAPD_*` 的完整变量清单见 `.env.example`。**`LDAP_ENABLED=true` 却缺 `LDAP_SERVER`/`LDAP_BASE_DN`、或 `LDAP_GROUP_ROLE_MAP` 写法无法解析时，应用会启动即报错**（fail-fast，而非拖到登录时才暴露）。
> 语音渠道（阿里云/腾讯云）的 API 密钥、模板 ID、被叫号码等通过数据库 `voice_setting` 表配置，在「设置 → 语音通知」页面维护，不通过 env。

## 种子数据

`migrations/seed_data.sql` + `seed_all.sh`（串联 seed_data.sql / seed_rbac.py / seed_component_templates.py / seed_users.py）包含系统运行所需的配置类种子：

| 表 | 内容 |
|----|------|
| permissions | 权限码（含 `ai:use` / `ai:admin`） |
| roles | 4 角色（admin / operator / viewer / ...） |
| role_permissions | 角色-权限映射（admin 含 ai:use+ai:admin，operator 含 ai:use） |
| component_templates | 配件模板（CPU/内存/硬盘/网卡/GPU） |
| monitor_metric_templates | 监控指标模板 |
| monitor_oid_category_rules | OID 分类规则 |
| monitor_vendor_brands | 厂商品牌 |
| monitor_dynamic_config | 监控动态配置 |

> VLAN 与 Webhook 配置属于业务数据，由部署后通过界面配置，不纳入种子。

**幂等**：`seed_all.sh` 可重复执行，每张表先 `DELETE` 再 `INSERT`。

**默认管理员**：由 `seed_users.py` 创建，密码通过环境变量 `SEED_ADMIN_PASSWORD` 指定，缺省随机生成并打印。

## 文档

| 文档 | 内容 |
|------|------|
| [运维手册-企业身份集成](docs/运维手册-企业身份集成.md) | LDAP/AD 接入、组→角色映射、白名单应急绕过、登录排障 |
| [运维手册-备份与恢复](docs/运维手册-备份与恢复.md) | T1 备份/恢复、密钥导出与回灌、安全快照回退 |
| [运维手册-密钥与环境变量](docs/运维手册-密钥与环境变量.md) | 密钥管理、环境变量口径 |
| [systemd 托管部署说明](deploy/systemd/README.md) | 逐 unit 说明、`ProtectSystem` 加固与放行、启停/排障 |
| [RELEASE_NOTES_v1.0.md](RELEASE_NOTES_v1.0.md) | v1.0 发布说明 |

## 前端开发

```bash
cd frontend-new
pnpm install
pnpm dev          # 开发服务器（http://localhost:3000，代理 /api → localhost:5000）
pnpm build        # 生产构建 → dist/
pnpm lint         # 代码检查
```

开发时后端跑 `python run.py`（端口 5000），前端 `pnpm dev`（端口 3000），Vite 已配置 `/api` 代理到后端。

## 故障排查

| 现象 | 排查 |
|------|------|
| install.sh 报 Python 未找到 | 安装 Python 3.14+ |
| install.sh 报 Node 未找到 | 安装 Node.js 20+ |
| install.sh 报 pnpm 未找到 | `corepack enable pnpm` 或 `npm i -g pnpm` |
| install.sh 报 MySQL 连接失败 | 检查 `.env` 中 `MYSQL_*` 配置，确认网络可达 |
| start.sh 报 venv 不存在 | 先运行 `bash scripts/install.sh` |
| Flask 启动后 404 静态资源 | 确认 `frontend-new/dist/index.html` 存在（前端构建成功） |
| SSE 不推送 | 检查 `logs/gateway.log`，确认 Redis 连通；多副本时确认各副本连同一 Redis |
| 监控不运行 | `bash scripts/start.sh status`，查 `logs/monitor.log` |
| Celery 未启动 | 确认 `AI_ASYNC_ENABLED=1` 且 `.venv/bin/celery` 存在，查 `logs/celery.log` |
| 语音通知不送达 | 查 `logs/flask.log` 中 voice worker，确认 `voice_setting` 表已配置密钥/模板 |
| 事件中心无数据 | 确认 `incident_aggregator` 在跑，查 `monitor_incident` 表 |
| 钉钉通知不送达 | 查 `logs/flask.log`，确认钉钉机器人 webhook + **加签密钥**已配置（加签算法用的是钉钉口径，不是飞书口径） |
| SNMP Trap 收不到 | 确认 `TRAPD_ENABLED=true`、`systemctl status ipip-trapd`、交换机 `snmp-server host` 的目标端口与 `TRAPD_LISTEN_PORT` 一致、community 在 `TRAPD_COMMUNITIES` 内 |
| SNMP Trap 有包但无告警 | 查 `journalctl -u ipip-trapd`：OID 未命中规则、或命中静默规则被抑制（规则表可用 `TRAP_CUSTOM_RULES` 扩展） |
| LDAP 登录失败 | 查 `logs/flask.log`；确认 `LDAP_ENABLED=true` 且 `LDAP_SERVER`/`LDAP_BASE_DN` 已配（缺项**启动即报错**）、`LDAP_GROUP_ROLE_MAP` 语法正确；详见《运维手册-企业身份集成》 |
| 拓扑发现无结果 | 确认设备已开 LLDP/CDP、凭据可 SSH 登录；Cisco 设备在 LLDP 无邻居时会自动回退 CDP。发现结果仅是**建议**，需人工确认后落库 |
| systemd unit 启动失败 | `journalctl -u ipip-web -e`，确认 `ipip.env` 环境段路径正确 |
| 备份失败 | 查 `ipip-backup.service` 日志，确认 MySQL/Redis 连通、GPG 密钥可用 |
| 恢复后 AI 配置丢失 | 确认备份含 Redis RDB（`--skip-redis` 会跳过），恢复时回灌 Redis |

## 技术栈

**后端**：Python 3.14 · Flask 3.1 · SQLAlchemy 2.0 · MySQL 8.4 · Redis 8 · JWT · bcrypt · Celery · pysnmp · netmiko · pyghmi · ldap3（纯 Python，免系统 libldap）

**前端**：TypeScript 6 · React 19 · Vite 8 · Ant Design 6 · Zustand 5 · TanStack Query 5 · React Router 7 · Axios

**实时网关**：Starlette · uvicorn · Redis Pub/Sub · SSE（seq/ring Redis 共享，多副本就绪）

**异步任务**：Celery（broker/result backend 独立 Redis db，队列 `ai,voice`）

**备份/恢复**：MySQL mysqldump + Redis RDB + GPG 加密密钥导出（`--include-secrets`），恢复前自动安全快照可回退

**AI 助手**：OpenAI 兼容 LLM · ChromaDB 向量库 · sentence-transformers（bge-small-zh-v1.5）· jieba 中文分词 · Pydantic 技能 schema · tenacity 重试 · prometheus-client 指标

## AI 助手

AI 助手模块提供告警解读、自然语言查询、RAG 知识库检索、Agentic 工具巡查与诊断能力。该模块已纳入部署仓库同步范围（`app/api/ai/`、`app/services/ai/`、`app/models/ai_*.py`、`app/tasks/ai_tasks.py`、`frontend-new/src/pages/AI/`）。

### 数据表

| 表 | 用途 |
|----|------|
| `ai_conversations` | 对话历史（user_id + scenario 索引，用户删除级联清理） |
| `ai_diagnosis_sessions` | Agentic 诊断会话（设备/技能/状态索引，设备删除保留会话供回溯） |

DDL 已迁至 `migrations/versions/0000_baseline.sql`（迁移基线快照），`install.sh` 初始化时自动导入并按 `0000_baseline.covers` 清单登记版本；后续增量通过 `flask db-upgrade` 逐版本升级。

### 权限

| 权限码 | 说明 | 默认角色 |
|--------|------|----------|
| `ai:use` | AI 助手使用（告警解读/NL 查询/RAG/巡查） | admin、operator |
| `ai:admin` | AI 知识库管理（RAG 文档入库） | admin |

由 `seed_rbac.py` 幂等种入。

### 配置

AI 的 LLM 接入（服务商 / 密钥 / 模型 / 超时）配置来源**二选一**，由 `.env` 中 `AI_*` 键是否非空决定（`.env.example` 默认全部为空 / 注释，即走界面自助）：

| 模式 | 配置方式 | 优先级 | 重启后 | 适用 |
|------|----------|--------|--------|------|
| ① 部署级固化 | `.env` 中 `AI_PROVIDER` / `AI_API_KEY` / `AI_BASE_URL` / `AI_MODEL` 填非空值 | env 最高，界面对应字段显示「由部署环境变量锁定，不可改」 | 始终为 env 值，稳定 | 厂商统一下发、客户不可改 |
| ② 界面自助 | 上述 4 键保持为空、数值键整行注释 | 无 env 覆盖时以 Redis 快照为准 | 从 Redis `ai:config` 自动恢复，**UI 修改不会被还原** | 客户在「系统设置 → AI 配置」页自行配置 |

> **两种模式不可混用**：任一键非空即进入模式①，界面其余被 env 覆盖字段的修改会被拒绝（`locked`）。切勿照抄占位默认值（`openai` / `gpt-4o-mini`）部署——这些字段会被永久锁死，客户改为 deepseek 等不生效，且重启还原为 env 值。
> **Redis 是界面配置的唯一持久层**：界面填写内容存于 Redis `key=ai:config`（api_key 以 `SWITCH_SECRET_KEY` 加密）。该 key 丢失 / 被 flush 会使界面配置失效并回落默认，部署后请勿清理该库。
> **数值键不要留空**：`AI_TIMEOUT` 等只能整行注释（如 `#AI_TIMEOUT=30`），留空会让启动时 `int()`/`float()` 解析崩溃。

主要变量（完整见 `.env.example`）：

| 变量 | 说明 |
|------|------|
| `AI_PROVIDER` | LLM 服务商标识（`openai` / `anthropic` / `custom`） |
| `AI_API_KEY` | LLM 接入密钥（留空则改在界面填写，加密存 Redis） |
| `AI_BASE_URL` / `AI_MODEL` | LLM 端点与模型名 |
| `AI_TIMEOUT` / `AI_STREAM_TIMEOUT` / `AI_MAX_TOKENS` / `AI_TEMPERATURE` | 调用超时 / 流式超时 / 最大 token / 采样温度（默认 30s / 120s / 2048 / 0.3） |
| `AI_ASYNC_ENABLED` | 是否启用 Celery `ai` 异步队列（`1` 启用，非 `1` 走同步路径） |
| `AI_RAG_*` | RAG 向量库与 embedding 相关配置 |

### 降级与保护

- **LLM 不可用**：AI 接口返回结构化降级响应，不影响主业务。
- **Celery 未启动**：`AI_ASYNC_ENABLED != 1` 时 AI 任务走同步路径，voice 队列仍由 Flask 同步投递。
- **RAG 未入库**：检索返回空结果，不阻断 Agentic 流程。
- **诊断回滚**：`ai_diagnosis_sessions.rollback_failed` 标记设备滞留中间态，供运维介入。
- **熔断**：LLM/工具调用失败走 `circuit_breaker`，达到阈值后短路返回降级响应。

## License

见 [LICENSE](LICENSE)。
