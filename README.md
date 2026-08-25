# ipip — IP 管理系统

开源 IP/IPAM 管理系统：机房、机柜、设备、IP 分配、VLAN、交换机、监控告警、客户管理一体化平台。

后端 Flask + SQLAlchemy + MySQL + Redis，前端 React 19 + Ant Design 6 + Vite 8，ASGI SSE 实时推送网关。

支持站内,飞书,企业微信，邮件通知告警

## 目录结构

```
ipip/
├── README.md                   # 本文件
├── LICENSE                     # 开源协议
├── .env.example                # 环境变量模板（脱敏）
├── .gitignore
├── app/                        # 后端 Flask 应用
├── config.py                   # 后端配置入口
├── extensions.py               # SQLAlchemy 扩展
├── wsgi.py                     # WSGI 入口（gunicorn 用）
├── run.py                      # 开发启动入口
├── run_monitor_service.py      # 监控独立服务入口
├── realtime_gateway/           # ASGI SSE 网关（uvicorn）
├── requirements.txt            # Python 依赖（钉版）
├── frontend-new/               # 前端源码（React 19 + AntD 6 + Vite 8）
│   ├── src/                    # 源码
│   ├── package.json
│   ├── pnpm-lock.yaml
│   └── vite.config.ts
├── database/
│   ├── schema.sql              # 完整建表 DDL
│   └── seed/
│       ├── seed_all.sh         # 统一种子入口
│       ├── seed_data.sql       # 配置类种子（权限/角色/指标模板/OID规则等）
│       ├── seed_rbac.py        # RBAC 种子（幂等）
│       ├── seed_component_templates.py  # 配件模板种子
│       └── seed_users.py       # 默认管理员账户
├── scripts/
│   ├── install.sh              # 一键安装（venv + 前端构建 + DB + 种子）
│   └── start.sh                # 一键启动/停止/状态
└── logs/                       # 运行时日志（gitignore）
```

## 系统要求

| 组件 | 版本 | 说明 |
|------|------|------|
| Python | 3.14+ | 后端运行时 |
| Node.js | 20+ | 前端构建 |
| pnpm | 10+ | 前端包管理（`corepack enable pnpm` 可启用） |
| MySQL | 8.4+ | 数据库 |
| Redis | 6+ | 缓存与 SSE 事件总线 |

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
2. 创建 Python venv 并安装 `requirements.txt`
3. 前端依赖安装 + 构建（`cd frontend-new && pnpm install && pnpm build`）
4. 从 `.env.example` 创建 `.env`（首次运行，需编辑后重跑）
5. 创建 MySQL 数据库并导入 `schema.sql`
6. 导入种子数据（`seed_all.sh`）

**首次运行后**：编辑 `.env` 填写实际的 `MYSQL_PASSWORD`、`REDIS_PASSWORD`、`SECRET_KEY`、`JWT_SECRET_KEY`，然后再次执行 `bash scripts/install.sh`（已完成的步骤会跳过）。

### 3. 启动

```bash
bash scripts/start.sh           # 启动全部（Flask + realtime_gateway + monitor）
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
| `--help` | 查看用法 |

## 启动脚本命令

| 命令 | 说明 |
|------|------|
| `start` (默认) | 启动 Flask + realtime_gateway + monitor |
| `stop` | 停止全部 |
| `restart` | 重启全部 |
| `status` | 查看各进程运行状态 |
| `flask` | 仅启动 Flask |
| `gateway` | 仅启动 SSE 网关 |
| `monitor` | 仅启动监控服务 |

**服务端口**（可在 `.env` 中配置）：

| 服务 | 默认端口 | 环境变量 |
|------|----------|----------|
| Flask HTTP API | 5000 | `FLASK_PORT` |
| realtime_gateway (SSE) | 8000 | `GATEWAY_PORT` |

**PID 文件**：`logs/run/{flask,gateway,monitor}.pid`
**日志文件**：`logs/{flask,gateway,monitor}.log`

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

## 种子数据

`database/seed/seed_data.sql` 包含系统运行所需的配置类种子：

| 表 | 行数 | 内容 |
|----|------|------|
| permissions | 63 | 权限码 |
| roles | 4 | 角色 |
| role_permissions | 107 | 角色-权限映射 |
| component_templates | 162 | 配件模板（CPU/内存/硬盘/网卡/GPU） |
| monitor_metric_templates | 239 | 监控指标模板 |
| monitor_metric_template_groups | 26 | 指标模板分组 |
| monitor_metric_template_group_items | 193 | 分组明细 |
| monitor_oid_category_rules | 159 | OID 分类规则 |
| monitor_vendor_brands | 27 | 厂商品牌 |
| monitor_device_type_recommends | 3 | 设备类型推荐 |
| monitor_dynamic_config | 1 | 监控动态配置 |

> VLAN 与 Webhook 配置属于业务数据，由部署后通过界面配置，不纳入种子。

**幂等**：`seed_all.sh` 可重复执行，每张表先 `DELETE` 再 `INSERT`。

**默认管理员**：由 `seed_users.py` 创建，密码通过环境变量 `SEED_ADMIN_PASSWORD` 指定，缺省随机生成并打印。

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
| SSE 不推送 | 检查 `logs/gateway.log`，确认 Redis 连通 |
| 监控不运行 | `bash scripts/start.sh status`，查 `logs/monitor.log` |

## 技术栈

**后端**：Python 3.14 · Flask 3.1 · SQLAlchemy 2.0 · MySQL 8.4 · Redis 8 · JWT · bcrypt · pysnmp · netmiko · pyghmi

**前端**：TypeScript 6 · React 19 · Vite 8 · Ant Design 6 · Zustand 5 · TanStack Query 5 · React Router 7 · Axios

**实时网关**：Starlette · uvicorn · Redis Pub/Sub · SSE

## License

见 [LICENSE](LICENSE)。
