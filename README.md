# ipip — IP 地址与网络资产管理平台

[简体中文](README.md) | [English](README.en.md)

面向网络运维的一体化资产管理与监控平台：数据中心、机柜、设备、IP 网段 / VLAN、**运营商线路**、拓扑、监控告警、客户与部署规划，一个系统管完；内置 AI 助手（告警解读 / 自然语言查询 / RAG 本地知识库 / Agentic 巡检诊断）。

**当前版本：v1.5.0** —— 版本唯一真源是 `config.py` 的 `VERSION`；运行时出口为 `GET /api/health`（`data.version`，前端侧边栏底部同步展示）。

- **后端**：Flask + SQLAlchemy + Celery + MySQL 8.4 + Redis（缓存 / Celery broker / 限流）
- **前端**：React 19 + TypeScript + Vite + Ant Design 6
- **实时**：ASGI SSE 网关（seq/ring 状态经 Redis 共享，多副本可横向扩展）
- **AI**：chromadb（本地向量库）+ sentence-transformers（bge 系列），**本地推理、数据不出机**
- **托管**：systemd 单元（生产推荐）；Docker Compose 评估编排（见下）

## 功能特性

| 模块 | 能力 |
|------|------|
| IP / IPAM | 数据中心 / 机柜 / 设备 / IP 分配 / VLAN / 交换机管理 |
| **运营商线路（v1.5.0）** | 运营商档案（联系人 / 报障热线）、线路管理（电路号 / 带宽 / 五种计费模式 / 起租到期与临期提醒）、分段端到端路径（设备 / 端口下拉 + 路由锚点自动反查）、影响面反查（按连接 / 设备 / 客户）、客户联动（名下有在用线路的客户不可终止） |
| 监控告警 | SNMP 指标轮询、阈值告警、依赖抑制、告警追踪 |
| **SNMP Trap** | 独立 `ipip-trapd` 进程接收 v1/v2c Trap（详见下文专节），复用统一告警治理管线 |
| **拓扑发现** | LLDP/CDP 实探（华为 / H3C / 思科）产出连接**建议**，人工确认才落库（人工录入永不被覆盖） |
| **事件中心** | 告警聚合（L1 规则合并 / L2 拓扑抑制 / L3 变更关联）、事件影响分析、回看窗口 |
| **通知投递** | 多渠道（站内 / 飞书 / 企业微信 / 钉钉签名机器人 / 邮件 / 自定义 Webhook / **语音电话**），投递 worker、冷却窗口（Redis 按事件 + 渠道）、队列满死信追踪、严格投递、用户级偏好 |
| **语音渠道** | 阿里云 / 腾讯云语音通知，独立语音 worker、回调鉴权、P0 告警唤醒升级 |
| **SSE 实时** | 网关 seq/ring 状态经 Redis 共享，多副本水平扩展 |
| 客户 / 审计 | 客户管理、操作审计、RBAC 权限 |
| **统一身份** | LDAP/AD 集成、组 → 角色映射、本地紧急旁路白名单（见《运维手册-企业身份集成》） |
| **AI 助手** | 告警解读 / 自然语言查询 / RAG 知识库 / Agentic 巡检诊断；Celery `ai` 队列异步执行，`ai:use` / `ai:admin` 权限隔离 |
| 导入管线 | 设备 / 机柜 / 客户批量导入 |

## 方式一：脚本一键安装（生产推荐）

### 系统支持与实测情况

安装入口在**动任何东西之前**会按 `scripts/installer/supported-systems.conf`（shell 与 Python 共用的唯一数据源）判定系统：`supported`（有实测配方）/ `manual`（放行但未单独验证）/ `rejected`（明确拒绝并给升级指路）。

> **首选 Ubuntu 24.04 LTS（或更新）**——安装器全流程实测、开箱即用的路径：Python 走 deadsnakes PPA 免编译，全流程最快。没有特殊理由，不要离开这条推荐路径。

| 系统 | 级别 | 实测情况 |
|---|---|---|
| **Ubuntu 24.04 LTS** | ✅ supported | **2026-10-04 全流程实测**：安装完成、六 unit 全 active、HTTP 200（推荐路径） |
| Debian 12 | ✅ supported | 2026-10-04 全流程实测：Python 走 uv（python-build-standalone） |
| Rocky Linux 10.2 | ✅ supported | 2026-10-03 全流程实测：AI/RAG 完整可用 |
| CentOS Stream 9 | ✅ supported | 2026-10-03 真机实测 |
| Ubuntu 26.04 / Debian 13 | ✅ supported | 推演支持，未单独实测 |
| Rocky 9 / AlmaLinux 9 / RHEL 9 | ✅ supported | 判据层实测；**Python 由安装器自动走 uv**（el9 系统 sqlite 不满足 chromadb，源码编译会让 AI/RAG 降级） |
| AlmaLinux 10 / RHEL 10 | ⚙️ manual | 同 el10 配方（MySQL 自动装 `mysql8.4-server`、Redis 自动装 `valkey`），未单独实测 |
| CentOS 7 / 8，RHEL 7 / 8，Rocky / Alma 8 | ❌ rejected | 已 EOL；glibc/openssl 不足以构建 Python 3.14 |
| Ubuntu 18.04 / 20.04，Debian 10 / 11 | ❌ rejected | 过维护期 |
| Alpine | ❌ rejected | musl libc，wheel 生态与 systemd 托管均不适用 |

### 安装

```bash
git clone https://github.com/follow2015/IPIP.git
cd IPIP
bash scripts/installer/bootstrap.sh            # 完整安装（自动补齐 Python/Node/MySQL/Redis）
bash scripts/installer/bootstrap.sh --help     # 全部参数
```

安装器分两层：

1. **`bootstrap.sh`（前置守卫）**：零依赖系统判定、/tmp noexec 拦截、openssl 升级预检、sqlite 版本检查，并自动备好 Python 3.14（Ubuntu=deadsnakes，其余=uv，源码编译兜底）；
2. **`python -m installer`（编排器）**：完成依赖安装、前端构建、DB 初始化、模型下载与收尾校验，按**七步**执行：

| 步骤 | 内容 |
|---|---|
| [1/7] | 系统事实采集 + 宿主机依赖基线补齐（`--skip-syspkg` 跳过） |
| [2/7] ‖ [3/7] | venv + Python 依赖（torch flavor 处理）‖ 前端构建（**并行**） |
| [4/7] | 初始化 `.env`（首次运行从 `.env.example` 生成） |
| [5/7] ‖ [6/7] | 数据库初始化（建库 + 迁移基线）‖ RAG 模型下载（并行路失败有兜底重试） |
| [6/7] | 种子数据导入（含默认管理员；升级模式改为幂等同步 RBAC 角色/权限） |
| [7/7] | 进程托管安装（`--with-units`）+ 收尾校验与凭据摘要 |

**首次运行后**：编辑 `.env` 填入真实的 `MYSQL_PASSWORD`、`REDIS_PASSWORD`、`SECRET_KEY`、`JWT_SECRET_KEY`，再次执行安装命令即可——已完成的步骤会自动跳过。

### 安装器参数（与旧 install.sh 兼容）

| 参数 | 作用 |
|---|---|
| `--skip-syspkg` | 不碰宿主机依赖（已自备 Python/Node/MySQL/Redis 时） |
| `--skip-frontend` | 跳过前端构建（需 `frontend-new/dist/` 已存在） |
| `--skip-db` | 跳过数据库初始化 |
| `--skip-seed` | 跳过种子数据导入 |
| `--skip-models` | 跳过 RAG 模型下载（约 1.2GB，RAG 不可用） |
| `--cpu` | 显式指定 CPU 版 torch（默认，约 190MB） |
| `--gpu` | CUDA 版 torch（约 2.6-3.5GB，需 NVIDIA GPU；**无 GPU 一律用默认 CPU**） |
| `--gpu-fast` | GPU 版 + 多镜像分散预取大包（更快） |
| `--with-units` | 安装 systemd 进程托管单元（需 root；生产部署必选） |
| `--units-user NAME` | 服务运行账号（默认 `ipip`；项目在 /root 下应为 root） |
| `--units-group NAME` | 服务运行组（默认同 `--units-user`） |
| `--upgrade` | 升级模式：沿用已装 torch flavor、自动执行数据库迁移、种子改为幂等 RBAC 同步 |
| `--selftest` | 只跑判据层自检（源测速 + 基线体检），不改系统 |

**升级到新版本**：拉取代码后执行 `bash scripts/installer/bootstrap.sh --upgrade`（自动 `flask db-upgrade`；1.5.0 起含权限码变更，按发布说明执行 `seed_rbac`）。

### 启动

#### 方式 A：systemd 托管（生产推荐，`--with-units` 安装后）

```bash
bash deploy/systemd/install-units.sh   # 渲染并安装全部单元 + ipip.target
systemctl start ipip.target            # 启动全部
systemctl stop  ipip.target            # 停止全部（PartOf 级联）
systemctl status ipip-web              # 查看单个服务
```

| Unit | 进程 | 说明 |
|---|---|---|
| `ipip-web` | Flask HTTP API | gunicorn WSGI，端口 5000 |
| `ipip-gateway` | SSE 实时网关 | uvicorn ASGI，端口 8000 |
| `ipip-monitor` | 监控服务 | SNMP 轮询 + 告警 + 事件聚合 |
| `ipip-celery-ai` | Celery AI 队列 | 异步 AI 任务（`ai` 队列） |
| `ipip-celery-voice` | Celery 语音队列 | 语音通知投递（`voice` 队列） |
| `ipip-trapd` | SNMP Trap 接收 | UDP v1/v2c；**opt-in**——单元只渲染安装，不自动启用 |
| `ipip-backup` + `.timer` | 定时备份 | MySQL dump + Redis RDB + GPG 密钥导出 |
| `ipip-watchdog` + `.timer` | 心跳看门狗 | T2 自监控，心跳超时告警 |

> `install-units.sh --enable` 只会 `enable --now` 常驻服务与定时器，**不含 `ipip-trapd` / `ipip-backup`**：备份走 timer 调度、Trap 接收需先配交换机侧，两者保持 opt-in。逐单元排障见 `deploy/systemd/README.md`。

#### 方式 B：脚本启停（开发 / 临时运行）

```bash
bash scripts/start.sh           # 启动全部（Flask + 网关 + 监控 + celery）
bash scripts/start.sh status    # 逐进程状态
bash scripts/start.sh stop      # 停止
bash scripts/start.sh restart   # 重启
bash scripts/start.sh flask     # 只启 Flask；gateway / monitor / celery 同理
```

**服务端口**（`.env` 可改）：Flask API `5000`（`FLASK_PORT`）、SSE 网关 `8000`（`GATEWAY_PORT`）、Trap 接收 `10162/udp`（`TRAPD_LISTEN_PORT`）。
**PID**：`logs/run/{flask,gateway,monitor,celery}.pid`；**日志**：`logs/{flask,gateway,monitor,celery}.log`。

> Celery 由 `AI_ASYNC_ENABLED=1` 控制，未开启时 AI 任务走同步路径；`.venv/bin/celery` 不存在时自动跳过。`start.sh` 不管理 `ipip-trapd`（Trap 接收是独立可选服务，仅 systemd 托管）。

启动后访问 `http://<server-ip>:5000`。

### 版本基线（低于基线 = 未经完整验证的环境）

| 组件 | 基线 | 级别 |
|---|---|---|
| Python | **3.14** | 硬性（`realtime_gateway` 依赖 3.14 才有的 `asyncio.AsyncGenerator`，低了启动即崩） |
| Node | 26.7 | 硬性（低版本会让 pnpm 静默跳过 rolldown 原生 binding，构建期才炸） |
| MySQL | 8.4 | 警告（8.0 实测可跑，属未验证组合） |
| Redis | 8.0 | 警告（7.x 实测可跑；el10 用 valkey） |

## SNMP Trap 接收器（可选）

除轮询外，独立进程 `ipip-trapd` 接收 SNMP v1/v2c Trap。**默认关闭**——未启用时所有 `TRAPD_*` 配置不生效，且与轮询**完全正交**（停掉不影响监控）。

```bash
# 1) 在 /etc/ipip/ipip.env 启用
#    TRAPD_ENABLED=true
#    TRAPD_LISTEN_PORT=10162

# 2) 启动（单元已由 install-units.sh 安装，但需手动启用）
sudo systemctl enable --now ipip-trapd.service

# 3) 把交换机的 trap 目标指向本机/端口
#    snmp-server host <ipip-ip> <community> 10162

# 回滚
sudo systemctl disable --now ipip-trapd.service
```

| 项 | 说明 |
|---|---|
| 监听 / 限流 | `TRAPD_LISTEN_ADDRESS`（默认 `0.0.0.0`）、`TRAPD_LISTEN_PORT`（默认 **10162**）、`TRAPD_RATE_LIMIT_PER_MINUTE`（默认 120/min，防 Trap 风暴） |
| 特权端口 | 标准端口 **162** 需 root 或 `CAP_NET_ADMIN`；无特权环境用 10162，并在交换机侧指明目标端口 |
| Community | `TRAPD_COMMUNITIES`（逗号分隔，默认 `public`）。**务必改掉默认值**；不匹配的 Trap 在传输层直接丢弃 |
| 队列 | `TRAPD_QUEUE_SIZE`（默认 1000）。满时丢弃新 Trap 并周期性聚合计数（不逐条刷日志），风暴压不垮服务 |
| 自定义规则 | `TRAP_CUSTOM_RULES`（JSON 数组，厂商 MIB OID 扩展）；**解析失败拒绝启动**，绝不静默降级为"全放行/全丢弃" |

规则命中**不直接**产生告警——与非 Trap 路径走同一治理管线（静默 / 节流 → 告警 outbox → SSE 推送），静默规则、抑制、追踪行为完全一致。

## 方式二：Docker Compose（评估用）

镜像由 GitHub Actions（`.github/workflows/docker-publish.yml`）自动构建并发布到 GHCR（`ghcr.io/follow2015/ipip`），评估者无需本地构建：

| 触发 | 产出镜像 tag |
|---|---|
| 推送 `v*` 版本 tag（发版） | `:1.5.0`（semver 版本号） |
| 每次推送 `main` | `:main`（默认 tag，评估者开箱即用） |
| 手动 `workflow_dispatch` | 对应分支的 `:main` |

- **多架构**：`linux/amd64` + `linux/arm64`（Apple Silicon 原生运行，不走 Rosetta 模拟）
- 镜像**已内置 RAG 模型**（构建含约 1.15GB 的模型层）

```bash
cp .env.example .env                  # 按需改密码与密钥
docker compose pull && docker compose up -d   # 1-3 分钟起服务
```

- 拓扑：`mysql + redis → migrate → seed → web / celery-ai / celery-voice / monitor`，nginx `proxy` 为唯一对外入口；`trapd` 走 opt-in profile（默认不起，避免 162/udp 冲突）
- 锁定版本：`.env` 里设 `IPIP_IMAGE_TAG=1.5.0`（对应仓库 `v1.5.0` tag 产出的镜像；不设则默认 `main`）
- ⚠️ 该编排定位**开发 / 评估环境**，不是生产部署方案；生产请用方式一的 systemd 路径
- 本地改代码：`docker compose build && docker compose up -d`（覆盖同名 tag，首次构建约 20 分钟）

## 配置

复制 `.env.example` 为 `.env`。关键项（完整清单与注释见 `.env.example`）：

| 变量 | 说明 | 默认 |
|---|---|---|
| `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | 数据库连接 | localhost / 3306 / root / — / ip_manager |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` / `REDIS_DB` | Redis 连接 | localhost / 6379 / — / 0 |
| `SECRET_KEY` / `JWT_SECRET_KEY` | 会话与 JWT 签名密钥 | **必须修改** |
| `FLASK_PORT` | Flask 监听端口 | 5000 |
| `MONITOR_ENABLED` / `MONITOR_WORKER_IN_PROCESS` | 监控服务开关 / 进程内 worker（独立部署设 false） | true / false |
| `SSE_RING_BUFFER_SIZE` / `SSE_RING_TTL_SECONDS` | SSE 环形缓冲（Redis 共享） | 200 / 3600 |
| `AI_ASYNC_ENABLED` | Celery AI 异步任务开关 | 1 |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` / `CELERY_CONCURRENCY` | Celery broker / 结果后端 / 并发（建议独立 Redis db） | redis://…:6379/1 、/2 、2 |
| `TRAPD_ENABLED` / `TRAPD_LISTEN_PORT` / `TRAPD_COMMUNITIES` | Trap 接收开关 / 端口 / community | false / 10162 / public |
| `LDAP_ENABLED` / `LDAP_SERVER` / `LDAP_BASE_DN` / `LDAP_GROUP_ROLE_MAP` / `LDAP_BYPASS_USERS` | LDAP/AD 外部认证（详见《运维手册-企业身份集成》） | false |
| 通知渠道 | 飞书 / 企微 / 钉钉 / 邮件 / Webhook 相关变量 | 按需填 |

三点注意：

- **LDAP fail-fast**：`LDAP_ENABLED=true` 但 `LDAP_SERVER`/`LDAP_BASE_DN` 缺失、或 `LDAP_GROUP_ROLE_MAP` 解析失败时，**启动即报错**（不是等到登录才失败）。
- **语音渠道不走环境变量**：阿里云 / 腾讯云的密钥、模板 ID、被叫号码在「设置 → 语音通知」页面（数据库 `voice_setting` 表）配置。
- **AI LLM 连接有互斥的两种模式**：`.env` 中 `AI_PROVIDER` / `AI_API_KEY` 等非空 = 部署方钉死（UI 字段锁定）；全留空 = UI 自助（「系统设置 → AI 配置」，快照存 Redis `ai:config`，**勿在部署后清理该 db**）。两模式不可混用，切勿带着占位默认值（`openai`/`gpt-4o-mini`）上线。

## 种子数据

`migrations/seed_data.sql` + `migrations/seed_all.sh`（串联 seed_data.sql / seed_rbac.py / seed_component_templates.py / seed_users.py）提供系统运行所需配置种子：

| 表 | 内容 |
|---|---|
| permissions | 权限码（含 `ai:use` / `ai:admin`） |
| roles / role_permissions | 角色（admin / operator / viewer 等）及映射 |
| component_templates | 组件模板（CPU / 内存 / 磁盘 / 网卡 / GPU） |
| monitor_metric_templates | 监控指标模板 |
| monitor_oid_category_rules | OID 分类规则 |
| monitor_vendor_brands | 厂商品牌 |
| monitor_dynamic_config | 监控动态配置 |

- **幂等**：`seed_all.sh` 可重复执行（每表先 DELETE 再 INSERT）
- **默认管理员**由 `seed_users.py` 创建：密码取 `SEED_ADMIN_PASSWORD` 环境变量，未设置则随机生成并打印
- VLAN、Webhook 等属业务数据，部署后通过 UI 配置，不在种子内

## 目录结构

```
IPIP/
├── README.md                   # 本文件（中文）
├── README.en.md                # 英文版
├── LICENSE
├── .env.example                # 环境变量模板（脱敏）
├── app/                        # Flask 后端
│   ├── api/                    # 路由（monitor/incident、topology、circuit、voice 等）
│   ├── adapters/               # 设备适配器（华为/H3C/思科命令封装 + LLDP/CDP 解析 + TextFSM 模板）
│   ├── models/                 # SQLAlchemy 模型
│   ├── services/               # 业务服务
│   │   ├── monitoring/         # 监控（事件聚合、依赖抑制、升级策略、trap_*）
│   │   ├── channels/           # 通知渠道（含语音、阿里/腾讯 provider）
│   │   ├── ldap_*.py           # LDAP/AD 认证、组→角色映射、配置自检
│   │   ├── topology/           # 拓扑查询与影响面分析
│   │   └── notification_delivery_worker.py  # 投递 worker（冷却/死信/严格投递）
│   ├── tasks/                  # Celery 异步任务
│   ├── celery_app.py           # Celery 应用定义
│   └── persistence/            # 仓储层
├── frontend-new/               # 前端源码（React 19 + AntD 6 + Vite）
├── realtime_gateway/           # ASGI SSE 网关（uvicorn，多副本可扩展）
├── migrations/
│   ├── versions/               # Alembic 迁移（0000_baseline.sql 为基线快照）
│   └── seed_all.sh / seed_*.py # 种子数据（幂等）
├── scripts/
│   ├── installer/              # bootstrap.sh + Python 安装器（系统判定/依赖补齐/DB 初始化）
│   ├── start.sh                # 一键启停（4 进程）
│   ├── credentials.py          # 凭据查看/重置工具
│   ├── backup_system.py        # T1 备份（MySQL dump + Redis RDB + GPG 密钥导出）
│   ├── restore_system.py       # T1 恢复（恢复前自动安全快照，可回滚）
│   ├── heartbeat_watchdog.py   # T2 自监控看门狗（心跳超时告警）
│   └── download_models.py      # AI 模型离线预下载
├── deploy/
│   ├── systemd/                # systemd 单元 + install-units.sh + README（逐单元排障）
│   └── docker/                 # 镜像 entrypoint 与 nginx 配置
├── docs/ops/                   # 运维手册（见下）
├── config.py                   # 后端配置入口（含 LDAP_* / TRAPD_* 启动校验）
├── run.py / wsgi.py            # 开发 / 生产（gunicorn）入口
└── run_trapd_service.py        # 独立 SNMP Trap 接收进程入口
```

## 文档

| 文档 | 内容 |
|---|---|
| [运维手册-密钥与环境变量](docs/ops/运维手册-密钥与环境变量.md) | 密钥管理、环境变量约定 |
| [运维手册-备份与恢复](docs/ops/运维手册-备份与恢复.md) | T1 备份/恢复、密钥导出与重导入、安全快照回滚 |
| [运维手册-企业身份集成](docs/ops/运维手册-企业身份集成.md) | LDAP/AD 集成、组→角色映射、紧急旁路白名单、登录排障 |
| [systemd 托管指南](deploy/systemd/README.md) | 逐单元参考、`ProtectSystem` 加固与白名单、启停与排障 |

完整 API 见 OpenAPI 快照（`openapi.json`）；运行时亦可通过 `GET /api/health` 探活。

## 前端开发

```bash
cd frontend-new
pnpm install
pnpm dev          # 开发服务器（http://localhost:3000，/api 代理到 localhost:5000）
pnpm build        # 生产构建 → dist/
pnpm lint         # 代码检查
```

## 许可证

见 [LICENSE](LICENSE)。
