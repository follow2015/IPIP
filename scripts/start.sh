#!/usr/bin/env bash
# ============================================================
# start.sh - ipip 一键启动/停止/状态脚本
# ------------------------------------------------------------
# 管理五个进程:
#   1. Flask HTTP API  (gunicorn 优先，回退 Flask dev server)
#   2. realtime_gateway (uvicorn ASGI SSE 网关)
#   3. monitor service  (独立设备健康监控进程)
#   4. celery worker    (AI 异步任务 + 语音通知，队列 ai,voice)
#   5. trapd receiver   (SNMP Trap 接收，UDP 10162)
#
# 用法:
#   bash scripts/start.sh           # 启动全部
#   bash scripts/start.sh start     # 启动全部
#   bash scripts/start.sh stop      # 停止全部
#   bash scripts/start.sh restart   # 重启全部
#   bash scripts/start.sh status    # 查看状态
#   bash scripts/start.sh flask     # 仅启动 Flask
#   bash scripts/start.sh gateway   # 仅启动 realtime_gateway
#   bash scripts/start.sh monitor   # 仅启动 monitor
#   bash scripts/start.sh celery    # 仅启动 celery worker
#   bash scripts/start.sh trapd     # 仅启动 trapd receiver
#
# PID 文件存放于 logs/run/，日志输出到 logs/*.log
#
# ── 本脚本与 systemd 的关系（互斥，不可同时持有）──────────────
# systemd 托管（ipip.target / ipip-*.service）是**默认形态**；
# 本脚本是 ADR-003 定义的**回退路径**：
#     systemctl disable --now ipip.target   →   bash scripts/start.sh start
# 二者同时运行会产生双实例（尤其 UDP 端口抢占与 gunicorn 孤儿 worker），
# 故 start/restart 前脚本会主动检测并拒绝启动。详见 ensure_systemd_not_managing()。
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# 颜色
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[START]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()  { err "$*"; exit 1; }

# Python 解释器
VENV_PY="$PROJECT_ROOT/.venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  die "venv 不存在。请先运行 bash scripts/install.sh"
fi

# 加载 .env（[WARN] 不能 `set -a; . .env`：.env 不是 shell 脚本，值里含 $ / 反引号 /
# 空格会被 shell 展开、执行或截断 —— install.sh 同一位置注释里有实测案例：
# 随机 MySQL 密码含 '$' 时 source 直接报 unbound variable 中断安装）。
# 改用 python-dotenv 解析 + shlex.quote 转义后 eval，与 install.sh 的 load_env_file 同一做法。
if [ -f "$PROJECT_ROOT/.env" ]; then
  eval "$("$VENV_PY" -c '
import shlex, sys
from dotenv import dotenv_values
for k, v in dotenv_values(sys.argv[1]).items():
    if v is not None and k:
        print("export %s=%s" % (k, shlex.quote(v)))
' "$PROJECT_ROOT/.env" 2>/dev/null)" || true
fi
# 环境可见性：start/restart 的第一条日志就说明本轮进程将以哪个 FLASK_ENV 运行。
# 实测教训：.env 改成 production 后 restart，日志里应用却加载了 DevelopmentConfig，
# 没有这行日志时"改了配置却没生效"完全不可见。
log "运行环境: FLASK_ENV=${FLASK_ENV:-<未设置>}（改 .env 后需 stop 再 start 才保证生效）"

# 运行时目录
RUN_DIR="$PROJECT_ROOT/logs/run"
mkdir -p "$RUN_DIR" "$PROJECT_ROOT/logs"

# PID 文件
PID_FLASK="$RUN_DIR/flask.pid"
PID_GATEWAY="$RUN_DIR/gateway.pid"
PID_MONITOR="$RUN_DIR/monitor.pid"
PID_CELERY="$RUN_DIR/celery.pid"
PID_TRAPD="$RUN_DIR/trapd.pid"

# 日志文件
LOG_FLASK="$PROJECT_ROOT/logs/flask.log"
LOG_GATEWAY="$PROJECT_ROOT/logs/gateway.log"
LOG_MONITOR="$PROJECT_ROOT/logs/monitor.log"
LOG_CELERY="$PROJECT_ROOT/logs/celery.log"
LOG_TRAPD="$PROJECT_ROOT/logs/trapd.log"

# 端口
FLASK_PORT="${FLASK_PORT:-5000}"
GATEWAY_PORT="${GATEWAY_PORT:-8000}"
# trapd 与其余组件不同：它是 **UDP** 而非 TCP，port_busy() 的 /dev/tcp 探测够不着它，
# 端口冲突只能靠绑socket失败时从日志里看出来。UDP/162 是特权端口，非 root 环境默认 10162。
TRAPD_PORT="${TRAPD_LISTEN_PORT:-10162}"

# ── 端口占用检测（restart 兜底用）：bash /dev/tcp 探测，不依赖 ss/lsof ──
port_busy() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null || return 1
  return 0
}

# ── systemd 互斥检查 ─────────────────────────────────────────
# 为什么必须检查：ipip.target 一旦 active，systemd 与本脚本会**同时**持有同一批端口。
# 后果不是单纯的"多一个进程"：
#   - UDP (trapd) 两个进程先后 bind 同一端口，后绑的可能失败也可能**静默接管**，
#     表现为 trap 时有时无地进不同实例的日志，极难归因；
#   - TCP 侧 gunicorn 抢不到端口会退出，被 systemd Restart=on-failure 反复拉起；
#   - 更糟的是 stop：systemd 与本脚本互不知情，一边 restart 一边 stop 会互相误杀。
# 因此这里**拒绝启动**而不是仅告警 —— 双实例的排查成本远高于一次显式 disable。
ensure_systemd_not_managing() {
  command -v systemctl >/dev/null 2>&1 || return 0
  # 单位文件根本不存在 ⇒ 这台机器从未走 systemd 托管，直接放行（容器/旧部署场景）
  systemctl list-unit-files ipip.target >/dev/null 2>&1 || return 0

  local active
  active=$(systemctl is-active ipip.target 2>/dev/null || echo "unknown")
  if [ "$active" = "active" ]; then
    die "检测到 systemd 正在托管 ipip.target，拒绝启动以避免双实例。
  本脚本与 systemd 互斥（详见文件头注释）。请二选一：
    · 继续用 systemd（默认）：systemctl restart ipip.target
    · 回退到本脚本（ADR-003）：systemctl disable --now ipip.target \\
        然后 bash scripts/start.sh start
  注：单组件命令（flask/gateway/monitor/celery/trapd）同样受此检查约束 ——
      端口冲突风险对单个组件一样存在，不提供绕过。"
  fi
}

# ── 进程检查工具 ────────────────────────────────────────────
is_running() {
  local pidfile="$1"
  if [ ! -f "$pidfile" ]; then return 1; fi
  local pid; pid=$(cat "$pidfile" 2>/dev/null || echo "")
  if [ -z "$pid" ]; then return 1; fi
  if kill -0 "$pid" 2>/dev/null; then return 0; else return 1; fi
}

pid_of() { cat "$1" 2>/dev/null || echo "none"; }

# ── 递归进程树操作（参照主仓 scripts/dev-start.sh 的成熟做法）────────
# 为什么必须递归：celery worker 会按 --concurrency fork 出子进程，monitor 这类常驻服务
# 也常有派生进程。只杀 pid 文件里的主进程，子进程会变成**孤儿继续运行**并继续持有
# 数据库连接 —— 真实案例：stop 之后残留的采集子进程仍在往 device_metric_latest 写数据，
# 导致后续 flask db-upgrade 因元数据锁一直等不到而报 1205 Lock wait timeout。
kill_tree() {
  local pid="$1" sig="$2" child
  # [WARN] pgrep 无匹配时返回 1；本文件是 `set -euo pipefail`，
  # 命令替换失败会让整个赋值语句返回非 0 从而**中断脚本**，故必须 `|| true`。
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    kill_tree "$child" "$sig"
  done
  kill "-$sig" "$pid" 2>/dev/null || true
}

# 进程树是否还活着（用于 TERM 后的等待，以及 KILL 前的判断）
tree_alive() {
  local pid="$1" child
  if kill -0 "$pid" 2>/dev/null; then
    return 0
  fi
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    if tree_alive "$child"; then
      return 0
    fi
  done
  return 1
}

# ── 启动函数 ────────────────────────────────────────────────
start_flask() {
  if is_running "$PID_FLASK"; then
    warn "Flask 已在运行 (PID $(pid_of "$PID_FLASK"))"
    return 0
  fi
  log "启动 Flask HTTP API (port $FLASK_PORT)..."
  # gunicorn 优先
  GUNICORN_BIN="$PROJECT_ROOT/.venv/bin/gunicorn"
  if [ -x "$GUNICORN_BIN" ]; then
    nohup "$GUNICORN_BIN" \
      --bind "0.0.0.0:$FLASK_PORT" \
      --workers 4 \
      --timeout 120 \
      --access-logfile "$LOG_FLASK" \
      --error-logfile "$LOG_FLASK" \
      --chdir "$PROJECT_ROOT" \
      wsgi:application > "$LOG_FLASK" 2>&1 &
  else
    warn "gunicorn 未安装，回退 Flask dev server（仅适用于低并发场景）"
    nohup "$VENV_PY" "$PROJECT_ROOT/run.py" > "$LOG_FLASK" 2>&1 &
  fi
  echo $! > "$PID_FLASK"
  sleep 2
  if is_running "$PID_FLASK"; then
    log "Flask 已启动 (PID $(pid_of "$PID_FLASK"))"
  else
    err "Flask 启动失败，查看日志: $LOG_FLASK"
    tail -20 "$LOG_FLASK" 2>/dev/null || true
    return 1
  fi
}

start_gateway() {
  if is_running "$PID_GATEWAY"; then
    warn "realtime_gateway 已在运行 (PID $(pid_of "$PID_GATEWAY"))"
    return 0
  fi
  log "启动 realtime_gateway (port $GATEWAY_PORT)..."
  UVICORN_BIN="$PROJECT_ROOT/.venv/bin/uvicorn"
  if [ ! -x "$UVICORN_BIN" ]; then
    warn "uvicorn 未安装，跳过 realtime_gateway（SSE 推送不可用）"
    return 0
  fi
  nohup "$UVICORN_BIN" realtime_gateway.main:app \
    --host 0.0.0.0 --port "$GATEWAY_PORT" \
    --app-dir "$PROJECT_ROOT" \
    > "$LOG_GATEWAY" 2>&1 &
  echo $! > "$PID_GATEWAY"
  sleep 2
  if is_running "$PID_GATEWAY"; then
    log "realtime_gateway 已启动 (PID $(pid_of "$PID_GATEWAY"))"
  else
    err "realtime_gateway 启动失败，查看日志: $LOG_GATEWAY"
    tail -20 "$LOG_GATEWAY" 2>/dev/null || true
    return 1
  fi
}

start_monitor() {
  if is_running "$PID_MONITOR"; then
    warn "monitor service 已在运行 (PID $(pid_of "$PID_MONITOR"))"
    return 0
  fi
  if [ "${MONITOR_ENABLED:-true}" != "true" ]; then
    warn "MONITOR_ENABLED != true，跳过 monitor service"
    return 0
  fi
  log "启动 monitor service..."
  nohup "$VENV_PY" "$PROJECT_ROOT/run_monitor_service.py" \
    > "$LOG_MONITOR" 2>&1 &
  echo $! > "$PID_MONITOR"
  sleep 2
  if is_running "$PID_MONITOR"; then
    log "monitor service 已启动 (PID $(pid_of "$PID_MONITOR"))"
  else
    err "monitor service 启动失败，查看日志: $LOG_MONITOR"
    tail -20 "$LOG_MONITOR" 2>/dev/null || true
    return 1
  fi
}

start_celery() {
  # Celery worker（AI 异步任务 + 语音通知）
  # 队列 ai,voice：ai 队列由 app/tasks/ai_tasks.py 消费，voice 队列由 voice_tasks.py 消费。
  # AI_ASYNC_ENABLED != 1 时跳过（AI 任务走同步路径，voice 仍由 Flask 同步投递）。
  if is_running "$PID_CELERY"; then
    warn "celery worker 已在运行 (PID $(pid_of "$PID_CELERY"))"
    return 0
  fi
  if [ "${AI_ASYNC_ENABLED:-1}" != "1" ]; then
    warn "AI_ASYNC_ENABLED != 1，跳过 celery worker（异步任务走同步路径）"
    return 0
  fi
  CELERY_BIN="$PROJECT_ROOT/.venv/bin/celery"
  if [ ! -x "$CELERY_BIN" ]; then
    warn "celery 未安装，跳过 celery worker（语音异步任务不可用）"
    return 0
  fi
  log "启动 celery worker (queue ai,voice, concurrency ${CELERY_CONCURRENCY:-4})..."
  # --chdir 是 celery 的**全局**选项，必须写在 `worker` 之前，否则报
  # "No such option '--chdir'" 导致 worker 起不来。本脚本开头已 cd 到
  # PROJECT_ROOT，故省略该选项。
  nohup "$CELERY_BIN" -A app.celery_app.celery worker \
    -Q ai,voice \
    --concurrency="${CELERY_CONCURRENCY:-4}" \
    --loglevel="${CELERY_LOGLEVEL:-info}" \
    > "$LOG_CELERY" 2>&1 &
  echo $! > "$PID_CELERY"
  sleep 2
  if is_running "$PID_CELERY"; then
    log "celery worker 已启动 (PID $(pid_of "$PID_CELERY"))"
  else
    err "celery worker 启动失败，查看日志: $LOG_CELERY"
    tail -20 "$LOG_CELERY" 2>/dev/null || true
    return 1
  fi
}

start_trapd() {
  # SNMP Trap 接收器。与其余四个组件有一个**根本区别**，必须先讲清楚：
  # 它是「常驻监督」模型 —— 进程起来后只是在每 POLL_INTERVAL_SECONDS 秒重读
  # 动态配置，**是否真的监听 UDP 端口由动态配置决定**，而不是由本脚本决定。
  # 因此这里进程 RUNNING 却查不到端口监听是**正常现象**，不是启动失败。
  # 排查顺序：先看 trapd.log，再看动态配置 TRAPD_ENABLED（Redis hash
  # monitor:dynamic_config 优先；直接改 DB 对运行中的服务不可见）。
  if is_running "$PID_TRAPD"; then
    warn "trapd receiver 已在运行 (PID $(pid_of "$PID_TRAPD"))"
    return 0
  fi
  if [ ! -f "$PROJECT_ROOT/run_trapd_service.py" ]; then
    warn "未找到 run_trapd_service.py，跳过 trapd receiver（该组件尚未部署）"
    return 0
  fi
  log "启动 trapd receiver (UDP $TRAPD_PORT)..."
  # 该脚本接受可选的 config_name 位置参数，缺省走 FLASK_ENV=production；
  # 这里不传，沿用 .env，避免与其余组件产生两套配置口径。
  nohup "$VENV_PY" "$PROJECT_ROOT/run_trapd_service.py" \
    > "$LOG_TRAPD" 2>&1 &
  echo $! > "$PID_TRAPD"
  sleep 2
  if is_running "$PID_TRAPD"; then
    log "trapd receiver 已启动 (PID $(pid_of "$PID_TRAPD"))"
    log "  注意：进程 RUNNING 不等于端口在监听 —— 是否 bind UDP ${TRAPD_PORT}"
    log "        取决于动态配置 TRAPD_ENABLED（见 $LOG_TRAPD 的『监听已启动』行）"
  else
    err "trapd receiver 启动失败，查看日志: $LOG_TRAPD"
    tail -20 "$LOG_TRAPD" 2>/dev/null || true
    return 1
  fi
}

# ── 停止函数 ────────────────────────────────────────────────
stop_one() {
  local name="$1" pidfile="$2"
  # 可选第三参数：等待超时秒数（默认 10，celery worker 需更长以等当前任务完成）
  local timeout="${3:-10}"
  if ! is_running "$pidfile"; then
    warn "$name 未在运行"
    rm -f "$pidfile"
    return 0
  fi
  local pid; pid=$(cat "$pidfile")
  log "停止 $name (PID $pid)..."
  # 先记下子孙：主进程被回收后 pgrep -P 就查不到，孤儿会漏网
  local descendants
  descendants=$(pgrep -P "$pid" 2>/dev/null || true)

  kill_tree "$pid" TERM
  for _ in $(seq 1 "$timeout"); do
    if tree_alive "$pid"; then sleep 1; else break; fi
  done
  if tree_alive "$pid"; then
    warn "$name 未在 ${timeout}s 内退出，对整棵进程树发送 SIGKILL"
    kill_tree "$pid" KILL
    # 兜底：子进程可能已被 init 收养，pgrep -P 查不到，按之前记下的 PID 再补一刀
    for child in $descendants; do
      kill -9 "$child" 2>/dev/null || true
    done
  fi
  rm -f "$pidfile"
  log "$name 已停止（含子进程）"
}

stop_all() {
  # celery worker 等 30s：SIGTERM 后 celery 会等当前任务完成才退出，
  # 诊断 task time_limit=1800 但 soft_time_limit=1500 会先优雅退出，
  # 30s 覆盖绝大多数场景；超时 SIGKILL 对 acks_late=True 安全（重投）。
  stop_one "celery worker"    "$PID_CELERY" 30
  stop_one "trapd receiver"   "$PID_TRAPD"
  stop_one "monitor service" "$PID_MONITOR"
  stop_one "realtime_gateway" "$PID_GATEWAY"
  stop_one "Flask" "$PID_FLASK"

  # 兜底清扫：pid 文件丢失 / 上次是 systemd 启动、这次用本脚本停止时，
  # 按 pid 停止会全部跳过，残留进程继续连库。这里按命令行特征再扫一遍。
  # 模式必须锁定本项目的特征路径/模块名，避免误伤同机其它 Python 服务。
  local leftovers
  leftovers=$(pgrep -f "run_trapd_service\.py|run_monitor_service\.py|gunicorn.*wsgi:application|uvicorn.*realtime_gateway\.main:app|celery.*-A app\.celery_app\.celery worker" 2>/dev/null || true)
  if [ -n "$leftovers" ]; then
    warn "发现未被 pid 文件覆盖的残留进程，一并清理：$(echo "$leftovers" | tr '\n' ' ')"
    for p in $leftovers; do
      kill_tree "$p" TERM
    done
    sleep 2
    for p in $leftovers; do
      if tree_alive "$p"; then kill_tree "$p" KILL; fi
    done
  fi
}

# ── 状态函数 ────────────────────────────────────────────────
status_one() {
  local name="$1" pidfile="$2" port="${3:-}"
  if is_running "$pidfile"; then
    log "$name: RUNNING (PID $(pid_of "$pidfile")${port:+, port $port})"
  else
    warn "$name: STOPPED"
  fi
}

status_all() {
  status_one "Flask"            "$PID_FLASK"   "$FLASK_PORT"
  status_one "realtime_gateway" "$PID_GATEWAY" "$GATEWAY_PORT"
  status_one "monitor service"  "$PID_MONITOR"
  status_one "celery worker"    "$PID_CELERY"
  status_one "trapd receiver"   "$PID_TRAPD"   "$TRAPD_PORT/udp"

  # trapd 的额外一行解释：RUNNING 与"端口在监听"是两件事，
  # 不给这句的话，运维看到端口没起来会误判成本脚本没拉起进程。
  if is_running "$PID_TRAPD"; then
    if grep -q "监听已启动" "$LOG_TRAPD" 2>/dev/null; then
      log "  └ trapd 端口状态: 监听中（来自 ${LOG_TRAPD}）"
    else
      warn "  └ trapd 进程在，但日志尚无「监听已启动」—— 通常意味着动态配置 TRAPD_ENABLED=false"
    fi
  fi
  # systemd 正在托管时，上面的 STOPPED **不等于服务挂了**：pid 文件是 systemd
  # 之外的另一套记账，两套互不知情。不提示的话，运维会用 status 的输出误判故障
  # （实测：systemd 下 6 个 unit 全 active，本脚本 status 却清一色 STOPPED）。
  if command -v systemctl >/dev/null 2>&1 \
     && systemctl list-unit-files ipip.target >/dev/null 2>&1 \
     && [ "$(systemctl is-active ipip.target 2>/dev/null || echo unknown)" = "active" ]; then
    warn "提示：ipip.target 正由 systemd 托管。上面显示 STOPPED 仅表示**本脚本未持有 pid 文件**，"
    warn "      实际进程状态请查看：systemctl list-units 'ipip*' --no-legend"
  fi
}

# ── 主入口 ──────────────────────────────────────────────────
CMD="${1:-start}"
case "$CMD" in
  start)
    ensure_systemd_not_managing
    start_flask
    start_gateway
    start_monitor
    start_celery
    start_trapd
    log "全部服务已启动。状态: bash scripts/start.sh status"
    ;;
  stop)
    stop_all
    log "全部服务已停止"
    ;;
  restart)
    ensure_systemd_not_managing
    stop_all
    # [WARN] 环境切换场景（.env 改 FLASK_ENV 等）必须等旧进程**彻底退净**再拉起：
    # gunicorn master 被 SIGKILL 时 worker 会变孤儿继续占着端口，新 master 绑不上
    # 端口而静默失败，健康检查打到旧 worker ⇒ 「改了配置却像没生效」（实测踩到：
    # development → production 切换后日志仍是 DevelopmentConfig）。
    for _ in $(seq 1 15); do
      if port_busy "$FLASK_PORT" || port_busy "$GATEWAY_PORT"; then
        sleep 1
      else
        break
      fi
    done
    # 兜底清理孤儿（模式锁定本项目的特征路径/模块名，不误伤其它进程）
    pkill -f "gunicorn.*--chdir $PROJECT_ROOT"      2>/dev/null || true
    pkill -f "uvicorn.*realtime_gateway.main:app"   2>/dev/null || true
    pkill -f "$VENV_PY $PROJECT_ROOT/run_monitor_service.py" 2>/dev/null || true
    pkill -f "celery.*-A app.celery_app.celery worker"        2>/dev/null || true
    pkill -f "$VENV_PY $PROJECT_ROOT/run_trapd_service.py"    2>/dev/null || true
    sleep 1
    start_flask
    start_gateway
    start_monitor
    start_celery
    start_trapd
    log "全部服务已重启（FLASK_ENV=${FLASK_ENV:-<未设置>}）"
    ;;
  status)
    status_all
    ;;
  flask)
    ensure_systemd_not_managing
    start_flask
    ;;
  gateway)
    ensure_systemd_not_managing
    start_gateway
    ;;
  monitor)
    ensure_systemd_not_managing
    start_monitor
    ;;
  celery)
    ensure_systemd_not_managing
    start_celery
    ;;
  trapd)
    ensure_systemd_not_managing
    start_trapd
    ;;
  *)
    die "未知命令: ${CMD}（可用: start|stop|restart|status|flask|gateway|monitor|celery|trapd）"
    ;;
esac
