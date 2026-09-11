# systemd 托管部署说明（IPIP）

**决策依据**：`docs/adr-003-进程托管形态.md`
**适用场景**：裸 Linux 服务器（CentOS 7+ / Ubuntu 16.04+，含 systemd）

---

## 一、为什么不再用 `scripts/start.sh`

`start.sh` 是 nohup + PID 文件方案，**无法自动拉起崩溃进程**，且其判活存在缺陷
（`ipip-deploy/scripts/start.sh:69-75` 用 `kill -0` 只验证 PID 存在、不验证身份）：
一旦旧 PID 被系统复用给无关进程，看门狗会判定"存活"而**永不拉起**已死的服务。

systemd 提供 OS 级能力：崩溃自动拉起 + 退避抑制 + 进程组清理 + 依赖编排 + 开机自启 + journald
日志 + 资源上限，且**零新增 Python 依赖**。

---

## 二、安装步骤

> ⚠️ **前置：必须先完成 P0-1 备份演练**（`docs/2026-09-09-IPIP缺口整改-P0批次任务分解WBS.md` 的 T1.8）。
> 首次切换到 systemd 属于生产变更，改动前必须有可用备份。

### 1. 创建运行账号

```bash
sudo useradd --system --home /opt/ipip --shell /sbin/nologin ipip 2>/dev/null || true
```

### 2. 停止现有进程（避免端口冲突）

```bash
cd /opt/ipip
sudo bash scripts/start.sh stop
# 确认端口已释放（Flask 5000 / gateway 8000）
ss -lntp | grep -E ':(5000|8000)' || echo "端口已释放"
```

### 3. 目录属主（常被忽略的一步）

服务以 `ipip` 用户运行，需保证 `.env` 可读、`instance/` 与 `logs/` 可写：

```bash
sudo chown -R root:ipip /opt/ipip
sudo chown -R ipip:ipip /opt/ipip/instance /opt/ipip/logs
sudo chmod 640 /opt/ipip/.env
```

### 4. 环境变量文件 `/etc/ipip/ipip.env`

第 5 步的安装脚本在**该文件不存在时**会依据 `--project-root` / `--venv-bin` 等参数
自动生成它（权限 640）；**已存在则保留不覆盖**——其中可能含运维自定义值（如
`WATCHDOG_BASE_URL`）。

需要手工定制时：

```bash
sudo mkdir -p /etc/ipip
sudo cp deploy/systemd/ipip.env.example /etc/ipip/ipip.env
sudo vim /etc/ipip/ipip.env      # 必改：PROJECT_ROOT / VENV_BIN
sudo chmod 640 /etc/ipip/ipip.env
```

> 该文件只放「部署形态」变量。业务配置由 `config.py` 的 `load_dotenv()` 从
> `${PROJECT_ROOT}/.env` 读取，**不要**把业务 `.env` 拷过来——systemd 的
> EnvironmentFile 语法更严格（不支持 `export` 前缀等），直接套用会让 unit 启动失败。

### 5. 安装 unit（用脚本，不要手工 cp）

unit 模板里带 `${PROJECT_ROOT}` / `${VENV_BIN}` 等占位符，而 systemd 的 `User=` /
`Group=` **不支持**环境变量展开，必须在安装期替换成真实值。手工 `cp` 会把占位符原样
装进去，表现为 unit 启动即失败、且报错信息不指向根因。用安装脚本固化这一步：

```bash
# 通用（项目在 /opt/ipip，使用专用账号 ipip）
sudo bash deploy/systemd/install-units.sh --project-root /opt/ipip

# 项目装在 /root 下的场景
sudo bash deploy/systemd/install-units.sh \
  --project-root /root/ipip-deploy --user root --group root

# 只渲染打印、不落盘（上线前确认替换结果）
bash deploy/systemd/install-units.sh \
  --project-root /root/ipip-deploy --user root --group root --dry-run
```

脚本依次完成：渲染全部 unit（含 `User` / `Group`）→ **校验无残留占位符** →
备份既有 unit 到 `/root/ipip-units.bak.<时间戳>`（只保留最近 3 份）→ 安装到
`/etc/systemd/system/` →（首次）生成 `/etc/ipip/ipip.env` → `systemd-analyze verify`
+ `daemon-reload`。

**它刻意不做**：自动 `enable` / `start`。接管进程属于生产变更，应先按第 6 步逐个启用
并验证；确认无误后再用 `--enable` 一次性启用。

| 参数 | 默认 | 说明 |
|------|------|------|
| `--project-root` | 脚本上两级目录 | 项目根，须与 `WorkingDirectory` 一致 |
| `--venv-bin` | `$PROJECT_ROOT/.venv/bin` | 虚拟环境 bin 目录 |
| `--user` / `--group` | `ipip` / 同 `--user` | 服务运行身份。**项目在 `/root` 下必须用 `root`** |
| `--flask-port` / `--gateway-port` | 5000 / 8000 | 监听端口 |
| `--workers` | 4 | gunicorn worker 数 |
| `--celery-ai-concurrency` / `--celery-voice-concurrency` | 2 / 4 | celery 并发 |
| `--backup-dir` | `/var/backups/ipip` | 备份产物目录 |
| `--dry-run` | — | 只渲染并打印关键行 |
| `--enable` | — | 安装后 `enable --now` 全部 service 与 timer |
| `--skip-env-file` | — | 不生成 `/etc/ipip/ipip.env` |
| `--keep-backups N` | 3 | 旧 unit 备份保留份数（`0` = 不清理，全部保留） |

> ⚠️ 以 `root` 运行服务属于权限放宽。能用 `/opt/ipip` + 专用账号 `ipip` 时应优先该方案；
> 脚本检测到「项目位于 `/root` 下但账号不是 root」会主动告警。

**也可以让应用安装脚本一并完成本节**（把「装应用」与「装托管」合并成一条命令）：

```bash
sudo bash ipip-deploy/scripts/install.sh \
  --with-units --units-user root --units-group root
```

它会在安装收尾调用本节的 `install-units.sh`；托管失败只告警、不把整次安装判为失败。

### 6. 逐个启用并验证（不要一次全开）

```bash
sudo systemctl enable --now ipip-celery-ai.service
sudo systemctl enable --now ipip-celery-voice.service
sudo systemctl enable --now ipip-monitor.service
sudo systemctl enable --now ipip-gateway.service
sudo systemctl enable --now ipip-web.service

# 全部就绪后启用聚合 target（开机自启）
sudo systemctl enable ipip.target
```

### 7. 启用备份定时器（可选但推荐）

备份与恢复脚本的用法见 `docs/运维手册-备份与恢复.md`，此处只负责调度：

```bash
sudo systemctl enable --now ipip-backup.timer
systemctl list-timers ipip-*          # 查看下次触发时间
sudo journalctl -u ipip-backup.service -n 50
```

`Persistent=true`：错过触发时刻（机器关机）后开机立即跑一次，避免"长期没备份无人知晓"。
建议 `BACKUP_DIR` 与 `/opt/ipip` **不在同一块盘**——同盘故障会让两者一起丢失。

### 8. 启用自监控判活定时器（推荐）

```bash
sudo systemctl enable --now ipip-watchdog.timer
systemctl list-timers ipip-*                           # 每 60s 触发一次
sudo journalctl -u ipip-watchdog.service -n 100        # 看单轮判定结果
${VENV_BIN}/python ${PROJECT_ROOT}/scripts/heartbeat_watchdog.py --dry-run
```

`--dry-run` 只打印判定报告、不告警不写状态，用于上线前确认三层信号都能读到。

**前提**：`ipip-web.service` 已声明 `Environment=HEARTBEAT_SERVICE_NAME=web`。这是 T2 心跳的
身份声明，**不能**挪进 `ipip.env`（该文件被所有 unit 共用，会让 monitor/gateway 也自称 web，
心跳 key 互相覆盖后「一个进程活着就掩盖另一个已死」）。

**降级行为**：`systemctl show` 被 polkit 拒绝时第 1 层静默跳过；Redis 不可用时第 2 层跳过并
单独发一条「自监控降级」通知。三层全不可用**不产生故障判定**——自监控最忌讳基础设施一抖
就满屏假警，那会让它先于被监控对象失信。

### 9. 验证

```bash
systemctl status 'ipip-*' --no-pager
curl -fsS http://127.0.0.1:5000/api/health/check | head -c 400; echo
```

`/api/health/check` 返回 200 即健康，非健康返回 503（见 `app/api/health.py:49-54`）。
注意 health 蓝图的挂载前缀是 `/api/health`（`app/__init__.py:388`）。

---

## 三、日常运维

```bash
# 统一启停
sudo systemctl start  ipip.target
sudo systemctl stop   ipip.target
sudo systemctl status 'ipip-*'

# 单服务操作
sudo systemctl restart ipip-web.service

# 日志（journald，已内置轮转）
sudo journalctl -u ipip-web.service -f
sudo journalctl -u 'ipip-*' --since '10 min ago' -p warning

# 查看某个服务崩溃重启次数（失联告警信号源）
# ⚠️ NRestarts 是**累计值**（仅 reset-failed 清零），watchdog 按「增量」判定，详见第四节
systemctl show -p SubState -p NRestarts ipip-monitor.service
```

---

## 四、重启策略与告警的衔接

各 unit 配置 `Restart=on-failure` + `StartLimitBurst=5` / `StartLimitIntervalSec=300`：

- 偶发崩溃 → 10s 后自动拉起；
- 300s 内崩溃超 5 次 → **停止重试并进入 `failed` 状态**，避免重启风暴；
- 失联告警由独立 unit `ipip-watchdog.service`（`scripts/heartbeat_watchdog.py`）
  分三层检测，**跑在被监控进程之外**：

| 层级 | 检测手段 | 覆盖故障 |
|------|---------|---------|
| 1 | `systemctl show` 的 `ActiveState` / `NRestarts` | 进程崩溃且拉不起来 |
| 2 | Redis 心跳 key TTL（`ipip:heartbeat:<env>:<svc>`）| **进程活着但逻辑卡死**（EventLoop 阻塞、锁死）|
| 3 | HTTP `/api/health/check` | 服务在跑但依赖（DB/Redis/磁盘）异常 |

第 1 层只能抓到「进程不在」；`kill -9` 后 systemd 会拉起它，但**死循环 / GC 长暂停 /
锁等待**这类「进程还在、服务已死」的故障只有第 2 层能抓——这正是心跳存在的理由。

### 第 1 层的 `NRestarts` 按「增量」判定

`NRestarts` 是**累计值**，只有 `systemctl reset-failed` 才清零 —— 它描述的是「历史重启
总数」，而不是「当前是否故障」。因此 watchdog **不**用 `NRestarts > 0` 当异常判据，
而是与 Redis 中的基线比较，只报**超出基线的新增重启**：

- 基线存放：状态键 `ipip:watchdog:<env>:<service>` 的 `last_nrestarts` 字段（TTL 7 天）
- 无基线（首次判定、Redis 被清空）→ 保守告警一次，并把当前值记为基线
- 基线内的历史值 → 静默

> 反例：压测/演练在 `web`/`monitor` 留下 `NRestarts=1` 后，旧实现（`> 0`）会让这两个
> 服务每 15 分钟（冷却期）重复告警，而且 `problems` 恒非空使「恢复判定」永远走不到，
> 告警**永不收敛** —— 这类假警会训练运维忽略告警。

运维含义：

- 想确认「服务最近崩过没有」→ 看累计值 `NRestarts`；
- 想让累计值与基线归零（例如演练后清理）→ `sudo systemctl reset-failed <unit>`，
  下一轮 watchdog 会把基线跟随回落，两边重新对齐。

**注意**：三层全部依赖本机或 Redis，因此本闭环**覆盖"单进程失联"，不覆盖"整机宕机"**。
整机级监控需另行解决（外部拨测 / 独立监控机）。

---

## 五、排错

| 现象 | 排查 |
|------|------|
| unit 启动立即 failed | `journalctl -u <unit> -n 100`；多为 `EnvironmentFile` 语法错误或 `PROJECT_ROOT` 指向错误 |
| 服务起不来但日志无输出 | 检查 `WorkingDirectory` 是否为项目根——`python-dotenv` 依赖 cwd 找 `.env`，错了会静默回落到默认 DB/Redis 配置 |
| 端口被占用 | 旧的 `start.sh` 进程未停干净，`ss -lntp` 定位后 `kill`，并确认未同时启用两套方案 |
| celery 停止后仍在执行任务 | `TimeoutStopSec=1800` 是等 agentic 收尾的正常表现，勿强行 `kill -9`（会遗留 prefork 孤儿进程）|
| 启动报 "Failed to set up mount namespacing" 或 cgroup 相关错误 | 目标机不支持 `MemoryMax`（无 memory controller）时，注释掉对应 unit 的 `MemoryMax=` 行即可；也可能是 `PrivateTmp` 受限，同样注释即可 |
| 反复告警「进程被重启过 N 次」 | `NRestarts` 是累计值，watchdog 按增量判定：先看 `systemctl show -p NRestarts <unit>` 是否**在增长**（增长=真的在崩）；基线在 Redis `ipip:watchdog:<env>:<svc>`。演练后可用 `systemctl reset-failed <unit>` 归零并让基线回落 |
| `heartbeat_watchdog.py --quiet` 仍有输出 | `--quiet` 只抑制「报告 JSON」；应用初始化日志仍会打到 stdout。**判断有无告警请看退出码**（0=正常，1=有告警），不要用「输出是否为空」 |
| MySQL 未就绪导致启动失败 | `After=mysql.service` 已声明依赖；若 MySQL 服务名不同（`mysqld.service`）需改各 unit 的 `After=` |

---

## 六、回滚

```bash
sudo systemctl disable --now ipip.target
sudo systemctl disable --now ipip-web.service ipip-gateway.service \
     ipip-monitor.service ipip-celery-ai.service ipip-celery-voice.service
sudo systemctl disable --now ipip-backup.timer ipip-watchdog.timer
sudo rm -f /etc/systemd/system/ipip-*.service /etc/systemd/system/ipip-*.timer \
     /etc/systemd/system/ipip.target
sudo systemctl daemon-reload

# 回到手工方式
cd /opt/ipip && sudo bash scripts/start.sh start
```

⚠️ **两套方案禁止并存**：同时运行会导致 Flask/gateway 端口冲突而启动失败；
monitor 因有 Redis 锁互斥不会双跑，celery 是队列消费者不会重复消费——但资源白白翻倍。

---

## 七、文件清单

| 文件 | 说明 |
|------|------|
| `ipip.target` | 聚合单元（统一启停与开机自启）|
| `ipip-web.service` | gunicorn → `wsgi:application`（声明 `HEARTBEAT_SERVICE_NAME=web`）|
| `ipip-gateway.service` | uvicorn → `realtime_gateway.main:app`（SSE）|
| `ipip-monitor.service` | `run_monitor_service.py` 采集进程 |
| `ipip-celery-ai.service` | celery `-Q ai` |
| `ipip-celery-voice.service` | celery `-Q voice` |
| `ipip-backup.service` / `.timer` | 每日系统备份（T1，oneshot + 日历定时器）|
| `ipip-watchdog.service` / `.timer` | 进程自监控判活（T2，oneshot + 60s 轮询）|
| `ipip.env.example` | EnvironmentFile 模板 |

**心跳身份一览**（watchdog 据此判活，`ipip:heartbeat:<env>:<service>`）：

| 进程 | 心跳 service 名 | 声明位置 |
|------|----------------|---------|
| web（gunicorn）| `web` | unit 的 `Environment=HEARTBEAT_SERVICE_NAME=web` |
| monitor | `monitor` | `standalone_service.py` 内置默认 |
| gateway | `gateway` | `realtime_gateway/main.py` 内置默认 |
| celery | `celery-ai` / `celery-voice` | 由 `-Q` 队列推导 |

> **设计约束**：进程身份必须「由最清楚自己是谁的入口显式声明」。`create_app()` 刻意不提供
> `"web"` 回落——CLI、运维脚本与 watchdog 自身都会建 app，回落会让它们冒充 web 写心跳；
> watchdog 每 60s 跑一次而 TTL 仅 90s，等于持续给已死的 gunicorn 续命，第二层检测永久失效。

**部署副本同步**：`deploy/` 下的内容需同步到 `ipip-deploy/deploy/`，路径按部署机实际调整。
