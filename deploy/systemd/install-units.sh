#!/usr/bin/env bash
# -*- coding: utf-8 -*-
# =============================================================================
# install-units.sh —— 渲染并安装 deploy/systemd/ 下的 unit 模板
#
# 为什么需要它：
#   unit 模板里带 ${PROJECT_ROOT} / ${VENV_BIN} 等占位符，而 systemd 的
#   `User=` / `Group=` **不支持**环境变量展开 —— 安装期必须替换成真实值。
#   以往靠手工 sed：不可复现，且漏掉任意一个占位符就会让 unit 启动失败，
#   而报错信息（"Invalid environment assignment" / 空路径）并不会指向根因。
#   本脚本把替换固化，并在安装前**校验无残留占位符**。
#
# 用法：
#   sudo bash deploy/systemd/install-units.sh --project-root /opt/ipip
#   sudo bash deploy/systemd/install-units.sh --project-root /root/ipip-deploy \
#        --user root --group root                  # 项目装在 /root 下的场景
#   bash deploy/systemd/install-units.sh --dry-run        # 只打印，不落盘
#
# 设计取舍：
#   - 默认**不** enable/start：接管进程属于生产变更，应先逐个启用并验证
#     （`--enable` 可显式授权）；
#   - 覆盖前自动备份既有 unit，便于回滚；
#   - /etc/ipip/ipip.env 已存在时**不覆盖**（可能含运维自定义值，如
#     WATCHDOG_BASE_URL），只提示。
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
ENV_FILE="${ENV_FILE:-/etc/ipip/ipip.env}"

PROJECT_ROOT=""
VENV_BIN=""
RUN_USER="ipip"
RUN_GROUP=""
FLASK_PORT=5000
GATEWAY_PORT=8000
GUNICORN_WORKERS=4
CELERY_AI_CONCURRENCY=2
CELERY_VOICE_CONCURRENCY=4
BACKUP_DIR="/var/backups/ipip"

# watchdog 与 backup 是 oneshot + timer，watchdog 必须独立于被监控进程
SERVICES="ipip-web.service ipip-gateway.service ipip-monitor.service ipip-celery-ai.service ipip-celery-voice.service ipip-watchdog.service"
TIMERS="ipip-backup.timer ipip-watchdog.timer"
TARGET="ipip.target"

DRY_RUN=0
DO_ENABLE=0
SKIP_ENV_FILE=0
# 既有 unit 的备份根目录（可用环境变量覆盖，便于在非 root 环境做演练）
UNITS_BACKUP_ROOT="${UNITS_BACKUP_ROOT:-/root}"
# 备份保留份数：备份是回滚手段而非归档，无限堆积既让备份目录变乱，也会掩盖
# 「最近一次可用备份是哪份」。0 表示不清理。
UNITS_BACKUP_KEEP="${UNITS_BACKUP_KEEP:-3}"

log()  { printf '\033[0;32m[UNITS]\033[0m %s\n' "$*"; }
warn() { printf '\033[0;33m[UNITS]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[0;31m[UNITS]\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'USAGE'
用法: sudo bash install-units.sh [选项]

路径与身份（最关键的三项）:
  --project-root PATH   项目根目录（默认按脚本位置推导为 ../../）
  --venv-bin PATH       虚拟环境 bin 目录（默认 $PROJECT_ROOT/.venv/bin）
  --user NAME           服务运行账号（默认 ipip；项目在 /root 下需用 root）
  --group NAME          服务运行组（默认与 --user 相同）

数值（写入 unit 的 ${VAR} 占位符）:
  --flask-port N                 默认 5000
  --gateway-port N               默认 8000
  --workers N                    gunicorn worker 数，默认 4
  --celery-ai-concurrency N      默认 2
  --celery-voice-concurrency N   默认 4
  --backup-dir PATH              默认 /var/backups/ipip

行为:
  --dry-run         只渲染并打印关键行，不写入 /etc
  --enable          安装后 enable --now 全部 service 与 timer（默认不启用）
  --skip-env-file   不生成 /etc/ipip/ipip.env
  --keep-backups N  旧 unit 备份保留份数，默认 3；0 表示不清理
  -h, --help        显示本帮助

环境变量覆盖（便于测试）:
  SYSTEMD_DIR        安装目标目录，默认 /etc/systemd/system
  ENV_FILE           部署环境文件路径，默认 /etc/ipip/ipip.env
  UNITS_BACKUP_ROOT  既有 unit 的备份根目录，默认 /root
USAGE
}

# ── 参数解析 ────────────────────────────────────────────────
while [ $# -gt 0 ]; do
  case "$1" in
    --project-root)              PROJECT_ROOT="${2:?--project-root 需要参数}"; shift 2 ;;
    --venv-bin)                  VENV_BIN="${2:?--venv-bin 需要参数}"; shift 2 ;;
    --user)                      RUN_USER="${2:?--user 需要参数}"; shift 2 ;;
    --group)                     RUN_GROUP="${2:?--group 需要参数}"; shift 2 ;;
    --flask-port)                FLASK_PORT="${2:?}"; shift 2 ;;
    --gateway-port)              GATEWAY_PORT="${2:?}"; shift 2 ;;
    --workers)                   GUNICORN_WORKERS="${2:?}"; shift 2 ;;
    --celery-ai-concurrency)     CELERY_AI_CONCURRENCY="${2:?}"; shift 2 ;;
    --celery-voice-concurrency)  CELERY_VOICE_CONCURRENCY="${2:?}"; shift 2 ;;
    --backup-dir)                BACKUP_DIR="${2:?}"; shift 2 ;;
    --dry-run)                   DRY_RUN=1; shift ;;
    --enable)                    DO_ENABLE=1; shift ;;
    --skip-env-file)             SKIP_ENV_FILE=1; shift ;;
    --keep-backups)
      [ $# -ge 2 ] || die "--keep-backups 需要一个数字（如 --keep-backups 3）"
      UNITS_BACKUP_KEEP="$2"; shift 2 ;;
    --keep-backups=*)            UNITS_BACKUP_KEEP="${1#*=}"; shift ;;
    -h|--help)                   usage; exit 0 ;;
    *)                           die "未知参数: $1（用 --help 查看用法）" ;;
  esac
done

[ -n "$RUN_GROUP" ] || RUN_GROUP="$RUN_USER"

# ── 路径推导与前置校验 ──────────────────────────────────────
if [ -z "$PROJECT_ROOT" ]; then
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
  log "未指定 --project-root，按脚本位置推导: $PROJECT_ROOT"
fi
PROJECT_ROOT="$(cd "$PROJECT_ROOT" && pwd)" || die "项目根目录不存在: $PROJECT_ROOT"
[ -n "$VENV_BIN" ] || VENV_BIN="$PROJECT_ROOT/.venv/bin"

[ -x "$VENV_BIN/python" ] || die "venv 解释器不可用: $VENV_BIN/python
  → 先执行 ipip-deploy/scripts/install.sh 创建虚拟环境，或用 --venv-bin 指定正确路径"
[ -f "$PROJECT_ROOT/.env" ] || warn "未找到 $PROJECT_ROOT/.env：服务将按默认配置连库，请确认部署完整"

# 项目在 /root 下却用非 root 账号 —— 这是实测踩过的坑，提前拦住
case "$PROJECT_ROOT" in
  /root/*)
    if [ "$RUN_USER" != "root" ]; then
      warn "项目位于 ${PROJECT_ROOT}（/root 下仅 root 可访问），但运行账号是 ${RUN_USER}。"
      warn "  → 服务会因权限不足启动失败；请加 --user root --group root，"
      warn "    或把项目迁到 /opt/ipip 并使用专用账号 ipip（更推荐）。"
    fi
    ;;
esac

# ── 渲染 ────────────────────────────────────────────────────
# sed 替换串里 & 与 | 有特殊含义，必须转义，否则路径含 & 时会被替换成整段匹配
escape_sed() { printf '%s' "$1" | sed -e 's/[&|\\]/\\&/g'; }

render_unit() {
  local src="$1" dst="$2"
  sed \
    -e "s|\${PROJECT_ROOT}|$(escape_sed "$PROJECT_ROOT")|g" \
    -e "s|\${VENV_BIN}|$(escape_sed "$VENV_BIN")|g" \
    -e "s|\${FLASK_PORT}|$(escape_sed "$FLASK_PORT")|g" \
    -e "s|\${GATEWAY_PORT}|$(escape_sed "$GATEWAY_PORT")|g" \
    -e "s|\${GUNICORN_WORKERS}|$(escape_sed "$GUNICORN_WORKERS")|g" \
    -e "s|\${CELERY_AI_CONCURRENCY}|$(escape_sed "$CELERY_AI_CONCURRENCY")|g" \
    -e "s|\${CELERY_VOICE_CONCURRENCY}|$(escape_sed "$CELERY_VOICE_CONCURRENCY")|g" \
    -e "s|\${BACKUP_DIR}|$(escape_sed "$BACKUP_DIR")|g" \
    -e "s|^User=.*|User=$RUN_USER|" \
    -e "s|^Group=.*|Group=$RUN_GROUP|" \
    "$src" > "$dst"
}

# 残留占位符检测：漏替换会让 unit 启动失败且报错不指向根因，必须装机前拦住
check_no_placeholder() {
  local f="$1" left
  left="$(grep -oE '[$][{][A-Za-z_][A-Za-z0-9_]*[}]' "$f" | sort -u | tr '\n' ' ')" || true
  [ -z "$left" ] || die "渲染后仍存在未替换占位符: ${left}（模板 $f 有新增变量？请在 render_unit 中补充）"
}

# 只保留最近 N 份 unit 备份。
# 目录名固定为 ipip-units.bak.YYYYmmdd-HHMMSS，字典序即时序，故 sort 后取最早的
# 若干份删除即可（不用 ls -t：其排序在同秒写入或跨平台时不稳定）。glob 只匹配本
# 脚本自己的命名，不会触碰备份根目录下的其它内容。
prune_unit_backups() {
  local root="$1" keep="$2" total
  # 非数字（含空）直接跳过并提示：静默容错会让「设了份数却没生效」极难排查
  case "${keep:-}" in
    ''|*[!0-9]*) warn "--keep-backups 值非数字（${keep:-空}），跳过清理"; return 0 ;;
  esac
  [ "$keep" -gt 0 ] || return 0                      # 0 = 不清理
  total=$(ls -1d "${root}"/ipip-units.bak.* 2>/dev/null | wc -l | tr -d ' ')
  [ "${total:-0}" -gt "$keep" ] || return 0
  ls -1d "${root}"/ipip-units.bak.* 2>/dev/null | sort \
    | head -n "$((total - keep))" \
    | while read -r old; do
        rm -rf "$old" && log "已清理超出保留数的旧备份: $old"
      done
}

# ipip-backup.service 此前未纳入渲染/安装循环（SERVICES 只列了常驻服务），
# 导致它的 ${PROJECT_ROOT}/${BACKUP_DIR} 占位符从不替换、单元实际缺失而 timer
# 指向的 Unit 不存在。此处并入渲染与安装（含 check_no_placeholder 校验），但
# 不加入 SERVICES，故 --enable 不会直接 enable --now 它——备份只应由 timer 调度，
# 保持既有语义（避免开机自启抢在 timer 之前重复跑）。
ALL_UNITS="$SERVICES $TIMERS $TARGET ipip-backup.service"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

log "渲染 unit 模板：project_root=$PROJECT_ROOT"
log "                 venv_bin=$VENV_BIN"
log "                 user=$RUN_USER group=$RUN_GROUP"
for u in $ALL_UNITS; do
  src="$SCRIPT_DIR/$u"
  [ -f "$src" ] || die "模板缺失: $src"
  render_unit "$src" "$TMP_DIR/$u"
  check_no_placeholder "$TMP_DIR/$u"
  printf '  %-26s ok\n' "$u"
done

if [ "$DRY_RUN" = 1 ]; then
  log "--dry-run：以下为渲染结果中的关键行（未写入任何文件）"
  for u in $ALL_UNITS; do
    printf '\n----- %s\n' "$u"
    grep -E '^(User|Group|WorkingDirectory|Environment|EnvironmentFile|ExecStart|OnCalendar)=' "$TMP_DIR/$u" \
      | sed 's/^/    /' || true
  done
  exit 0
fi

# ── 安装 ────────────────────────────────────────────────────
# 只在写系统目录时强制 root；SYSTEMD_DIR 指向可写目录（本地演练）时放行
if [ "$(id -u)" != "0" ] && [ "$SYSTEMD_DIR" = "/etc/systemd/system" ]; then
  die "写入 $SYSTEMD_DIR 需要 root 权限，请用 sudo 运行（或用 SYSTEMD_DIR 指定可写目录做演练）"
fi
[ -d "$SYSTEMD_DIR" ] || die "目录不存在: $SYSTEMD_DIR"

# 覆盖前备份既有 unit（回滚用）
need_backup=0
for u in $ALL_UNITS; do [ -e "$SYSTEMD_DIR/$u" ] && need_backup=1; done
if [ "$need_backup" = 1 ]; then
  BACKUP_PATH="${UNITS_BACKUP_ROOT}/ipip-units.bak.$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$BACKUP_PATH"
  for u in $ALL_UNITS; do
    [ -e "$SYSTEMD_DIR/$u" ] && cp -p "$SYSTEMD_DIR/$u" "$BACKUP_PATH/"
  done
  log "既有 unit 已备份到 ${BACKUP_PATH}（回滚：cp $BACKUP_PATH/* $SYSTEMD_DIR/ && systemctl daemon-reload）"
  prune_unit_backups "$UNITS_BACKUP_ROOT" "$UNITS_BACKUP_KEEP"
fi

for u in $ALL_UNITS; do
  install -m 0644 "$TMP_DIR/$u" "$SYSTEMD_DIR/$u"
done
log "已安装 $(echo $ALL_UNITS | wc -w | tr -d ' ') 个 unit 到 $SYSTEMD_DIR"

# ── /etc/ipip/ipip.env ──────────────────────────────────────
if [ "$SKIP_ENV_FILE" = 0 ]; then
  if [ -e "$ENV_FILE" ]; then
    log "$ENV_FILE 已存在，保留不覆盖（内含运维自定义值时请勿盲目重生成）"
  else
    mkdir -p "$(dirname "$ENV_FILE")"
    sed \
      -e "s|^PROJECT_ROOT=.*|PROJECT_ROOT=$PROJECT_ROOT|" \
      -e "s|^VENV_BIN=.*|VENV_BIN=$VENV_BIN|" \
      -e "s|^FLASK_PORT=.*|FLASK_PORT=$FLASK_PORT|" \
      -e "s|^GATEWAY_PORT=.*|GATEWAY_PORT=$GATEWAY_PORT|" \
      -e "s|^GUNICORN_WORKERS=.*|GUNICORN_WORKERS=$GUNICORN_WORKERS|" \
      -e "s|^CELERY_AI_CONCURRENCY=.*|CELERY_AI_CONCURRENCY=$CELERY_AI_CONCURRENCY|" \
      -e "s|^CELERY_VOICE_CONCURRENCY=.*|CELERY_VOICE_CONCURRENCY=$CELERY_VOICE_CONCURRENCY|" \
      -e "s|^BACKUP_DIR=.*|BACKUP_DIR=$BACKUP_DIR|" \
      "$SCRIPT_DIR/ipip.env.example" > "$ENV_FILE"
    chmod 640 "$ENV_FILE"
    log "已生成 ${ENV_FILE}（权限 640）"
  fi
fi

# ── 校验与加载 ──────────────────────────────────────────────
if command -v systemctl >/dev/null 2>&1; then
  if command -v systemd-analyze >/dev/null 2>&1; then
    for u in $ALL_UNITS; do
      # 个别告警（如 Documentation= 使用 %E 占位符）不影响运行，故只提示不阻断
      systemd-analyze verify "$SYSTEMD_DIR/$u" 2>&1 | grep -q . && \
        warn "systemd-analyze verify 对 $u 有提示（多为 Documentation 占位符，可忽略）"
    done
  fi
  systemctl daemon-reload
  log "已执行 systemctl daemon-reload"
else
  warn "未找到 systemctl，跳过 daemon-reload（非 systemd 环境？）"
fi

# ── 可选启用 ────────────────────────────────────────────────
if [ "$DO_ENABLE" = 1 ]; then
  for u in $SERVICES; do
    systemctl enable --now "$u"
    log "enabled+started: $u"
  done
  for t in $TIMERS; do
    systemctl enable --now "$t"
    log "enabled+started: $t"
  done
  systemctl enable "$TARGET"
  log "enabled: ${TARGET}（开机自启聚合）"
  exit 0
fi

log "下一步（本脚本刻意不代做，接管进程前请逐个验证）："
cat <<'NEXT'
    sudo systemctl enable --now ipip-celery-ai.service
    sudo systemctl enable --now ipip-celery-voice.service
    sudo systemctl enable --now ipip-monitor.service
    sudo systemctl enable --now ipip-gateway.service
    sudo systemctl enable --now ipip-web.service
    sudo systemctl enable ipip.target
    sudo systemctl enable --now ipip-backup.timer ipip-watchdog.timer
  或直接：sudo bash install-units.sh --project-root <路径> --enable
NEXT
