#!/usr/bin/env bash
# ============================================================
# start.sh - ipip 一键启动/停止/状态脚本
# ------------------------------------------------------------
# 管理四个进程:
#   1. Flask HTTP API  (gunicorn 优先，回退 Flask dev server)
#   2. realtime_gateway (uvicorn ASGI SSE 网关)
#   3. monitor service  (独立设备健康监控进程)
#   4. celery worker    (AI 异步任务 + 语音通知，队列 ai,voice)
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
#
# PID 文件存放于 logs/run/，日志输出到 logs/*.log
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

# 加载 .env
if [ -f "$PROJECT_ROOT/.env" ]; then
  set -a; . "$PROJECT_ROOT/.env"; set +a
fi

# 运行时目录
RUN_DIR="$PROJECT_ROOT/logs/run"
mkdir -p "$RUN_DIR" "$PROJECT_ROOT/logs"

# PID 文件
PID_FLASK="$RUN_DIR/flask.pid"
PID_GATEWAY="$RUN_DIR/gateway.pid"
PID_MONITOR="$RUN_DIR/monitor.pid"
PID_CELERY="$RUN_DIR/celery.pid"

# 日志文件
LOG_FLASK="$PROJECT_ROOT/logs/flask.log"
LOG_GATEWAY="$PROJECT_ROOT/logs/gateway.log"
LOG_MONITOR="$PROJECT_ROOT/logs/monitor.log"
LOG_CELERY="$PROJECT_ROOT/logs/celery.log"

# Python 解释器
VENV_PY="$PROJECT_ROOT/.venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  die "venv 不存在。请先运行 bash scripts/install.sh"
fi

# 端口
FLASK_PORT="${FLASK_PORT:-5000}"
GATEWAY_PORT="${GATEWAY_PORT:-8000}"

# ── 进程检查工具 ────────────────────────────────────────────
is_running() {
  local pidfile="$1"
  if [ ! -f "$pidfile" ]; then return 1; fi
  local pid; pid=$(cat "$pidfile" 2>/dev/null || echo "")
  if [ -z "$pid" ]; then return 1; fi
  if kill -0 "$pid" 2>/dev/null; then return 0; else return 1; fi
}

pid_of() { cat "$1" 2>/dev/null || echo "none"; }

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
  nohup "$CELERY_BIN" -A app.celery_app.celery worker \
    -Q ai,voice \
    --concurrency="${CELERY_CONCURRENCY:-4}" \
    --loglevel="${CELERY_LOGLEVEL:-info}" \
    --chdir "$PROJECT_ROOT" \
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
  kill -TERM "$pid" 2>/dev/null || true
  for i in $(seq 1 "$timeout"); do
    if ! kill -0 "$pid" 2>/dev/null; then break; fi
    sleep 1
  done
  if kill -0 "$pid" 2>/dev/null; then
    warn "$name 未在 ${timeout}s 内退出，发送 SIGKILL"
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$pidfile"
  log "$name 已停止"
}

stop_all() {
  # celery worker 等 30s：SIGTERM 后 celery 会等当前任务完成才退出，
  # 诊断 task time_limit=1800 但 soft_time_limit=1500 会先优雅退出，
  # 30s 覆盖绝大多数场景；超时 SIGKILL 对 acks_late=True 安全（重投）。
  stop_one "celery worker"    "$PID_CELERY" 30
  stop_one "monitor service" "$PID_MONITOR"
  stop_one "realtime_gateway" "$PID_GATEWAY"
  stop_one "Flask" "$PID_FLASK"
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
}

# ── 主入口 ──────────────────────────────────────────────────
CMD="${1:-start}"
case "$CMD" in
  start)
    start_flask
    start_gateway
    start_monitor
    start_celery
    log "全部服务已启动。状态: bash scripts/start.sh status"
    ;;
  stop)
    stop_all
    log "全部服务已停止"
    ;;
  restart)
    stop_all
    sleep 1
    start_flask
    start_gateway
    start_monitor
    start_celery
    log "全部服务已重启"
    ;;
  status)
    status_all
    ;;
  flask)
    start_flask
    ;;
  gateway)
    start_gateway
    ;;
  monitor)
    start_monitor
    ;;
  celery)
    start_celery
    ;;
  *)
    die "未知命令: $CMD（可用: start|stop|restart|status|flask|gateway|monitor|celery）"
    ;;
esac
