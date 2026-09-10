#!/usr/bin/env bash
# ============================================================
# install.sh - ipip 一键安装脚本
# ------------------------------------------------------------
# 功能：
#   1. 版本基线检查 + 系统依赖
#      基线取本机 dev 实测版本：Python 3.14.7 / Node v26.7.0 / pnpm 10.34.5 /
#      MySQL 8.4+ / Redis 8.0+
#      处理策略：Python、Node、pnpm 低于基线 → 硬失败（已被实测证实会中断
#      安装或运行）；MySQL、Redis 低于基线 → 告警不阻断（本机不可测得，
#      且低版本已实测可用）。做严格分级的目的是：把"悄无声息的环境偏差"
#      变成安装阶段可见的决策点，而不是留到运行时才炸。
#   2. 创建 Python venv 并安装 requirements.txt
#   3. 前端依赖安装 + 构建（pnpm install && pnpm build → frontend-new/dist/）
#   4. 初始化 .env（若不存在则从 .env.example 拷贝，并自动生成 SECRET_KEY/JWT_SECRET_KEY 随机密钥）
#   5. 创建数据库并导入 schema + 种子
#   6. 配置监控维护 cron（02:00 预建分区 / 03:00 归档清理）
#
# 用法:
#   bash scripts/install.sh                    # 完整安装
#   bash scripts/install.sh --skip-frontend    # 跳过前端构建（假设 frontend-new/dist 已存在）
#   bash scripts/install.sh --skip-db          # 跳过数据库初始化
#   bash scripts/install.sh --skip-seed        # 跳过种子导入
#   bash scripts/install.sh --help
#
# 幂等：可重复执行，已存在的步骤会跳过
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# 颜色输出
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[INSTALL]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()  { err "$*"; exit 1; }

# ── 安装进度反馈 & pip 源自动选择 ───────────────────────────────
# 背景：pip install 是全流程最慢的一步，过去用 -q 完全静默，运维无法判断
# "在装"还是"卡死"。此处提供三件事：
#   ① 步骤计时——每个长步骤打印起止与耗时；
#   ② pip 实时输出——去掉 -q 并强制 PYTHONUNBUFFERED，日志重定向时也能 tail -f 看到滚动；
#   ③ 源自动切换——官方慢到阈值以上即切清华镜像，安装失败再自动重试一次。

# 判据必须是**真实安装速度**，不能是 curl 首页响应时间：实测官方源首页
# 0.98s 可用，但安装单个依赖包 60s 仍未完成——首页延迟与包下载吞吐完全无关。
# 故此处"先装一个真实包并计时"，超阈值未完成即判定该源不可用。
PIP_INSTALL_TIMEOUT="${PIP_INSTALL_TIMEOUT:-120}"   # 探测包安装上限（秒）
PIP_INDEX_OFFICIAL="https://pypi.org/simple"
PIP_INDEX_TUNA="https://pypi.tuna.tsinghua.edu.cn/simple"
PIP_INDEX_ARG=""   # 空=官方源；非空=携带 -i <url>
# 探测包取项目自身依赖之一（装完计入 pip 缓存，后续安装不浪费下载）
# 探测包用中等体积的 numpy（约 15-20MB wheel）：uvicorn 这类小包在官方源也能
# 秒装，无法反映大文件（torch ≈554MB）场景下的真实吞吐。
PIP_PROBE_PACKAGE="${PIP_PROBE_PACKAGE:-numpy}"

# --no-deps：只取目标包本体，避免依赖树把耗时放大、污染速度判据
install_probe_pip() {
  timeout "$PIP_INSTALL_TIMEOUT" "$VENV_PY" -m pip install --no-deps \
    $PIP_INDEX_ARG "$PIP_PROBE_PACKAGE" -q
}

select_pip_index() {
  # 支持强制指定源（跳过探测）：PIP_INDEX_URL=<url> bash scripts/install.sh
  if [ -n "${PIP_INDEX_URL:-}" ]; then
    PIP_INDEX_ARG="-i $PIP_INDEX_URL"
    log "使用 PIP_INDEX_URL 强制指定的 pip 源: $PIP_INDEX_URL"
    return 0
  fi
  local rc
  log "实测 pip 下载速度：安装 ${PIP_PROBE_PACKAGE}（上限 ${PIP_INSTALL_TIMEOUT}s，超时即换源）..."
  install_probe_pip
  rc=$?
  if [ "$rc" -eq 0 ]; then
    log "官方源可用（${PIP_PROBE_PACKAGE} 安装完成）"
    return 0
  fi
  if [ "$rc" -eq 124 ]; then
    warn "官方源下载过慢：${PIP_INSTALL_TIMEOUT}s 未装完 ${PIP_PROBE_PACKAGE} —— 切换清华源"
  else
    warn "官方源安装失败（退出码 $rc）—— 尝试清华源"
  fi
  PIP_INDEX_ARG="-i $PIP_INDEX_TUNA"
  if install_probe_pip; then
    log "清华源可用，后续依赖均走 ${PIP_INDEX_TUNA}"
  else
    warn "清华源同样未能完成安装，继续尝试（后续安装可能很慢或失败）"
  fi
}

# ── Node 源自动选择（同样以真实下载为判据）─────────────────────
NPM_REGISTRY_OFFICIAL="https://registry.npmjs.org"
NPM_REGISTRY_MIRROR="https://registry.npmmirror.com"
NPM_REGISTRY=""
NODE_PROBE_TIMEOUT="${NODE_PROBE_TIMEOUT:-120}"
NODE_PROBE_PACKAGE="debug"   # 极小且无依赖，专门用作网络速度试金石

select_npm_registry() {
  # 幂等：同一轮安装中只实测一次（第 1 步装 pnpm 与第 3 步构建都会用到）
  if [ -n "$NPM_REGISTRY" ]; then return 0; fi
  local probe_dir
  probe_dir="$(mktemp -d)"
  log "实测 npm registry 下载速度：安装 ${NODE_PROBE_PACKAGE}（上限 ${NODE_PROBE_TIMEOUT}s）..."
  if timeout "$NODE_PROBE_TIMEOUT" npm install --prefix "$probe_dir" \
       --registry "$NPM_REGISTRY_OFFICIAL" --no-audit --no-fund \
       --loglevel=error "$NODE_PROBE_PACKAGE" >/dev/null 2>&1; then
    NPM_REGISTRY="$NPM_REGISTRY_OFFICIAL"
    log "npm 官方 registry 可用"
  else
    warn "npm 官方 registry 过慢/超时 —— 切换 ${NPM_REGISTRY_MIRROR}"
    NPM_REGISTRY="$NPM_REGISTRY_MIRROR"
  fi
  rm -rf "$probe_dir"
}

# pnpm 安装：不要依赖 corepack
# 理由：corepack 会从 registry 拉 pnpm 版本签名并用内置公钥校验，在部分
# node/corepack 组合下失败（Node 20.18.1 实测报 "Cannot find matching keyid"）。
# 更重要的是它会留下**可执行但一跑就崩**的 shim，导致 command -v pnpm 误判为已安装。
ensure_pnpm() {
  local want="${1:-${PNPM_VERSION:-10.34.5}}"
  local have=""
  # 判据必须是真跑一次 pnpm：corepack 会留下"可执行但一跑就崩"的 shim，
  # command -v pnpm 会误判为已安装。
  if command -v pnpm >/dev/null 2>&1; then have="$(pnpm --version 2>/dev/null || true)"; fi
  if [ -n "$have" ] && ver_ge "$have" "$want"; then
    log "pnpm: $have ✓ (>= $want)"
    return 0
  fi
  if [ -n "$have" ]; then
    warn "pnpm 版本过低（$have < $want），将升级到 $want"
  else
    warn "pnpm 不可用（缺失，或 corepack shim 签名校验失败），改用 npm 全局安装 pnpm@${want}"
  fi
  local PNPM_VERSION="$want"
  # 清掉 corepack 残留 shim，否则 npm install -g 会因同名文件冲突直接拒绝安装
  local pnpm_path
  pnpm_path="$(command -v pnpm 2>/dev/null || true)"
  if [ -n "$pnpm_path" ] && [ -f "$pnpm_path" ]; then
    warn "移除冲突/损坏的 corepack shim: $pnpm_path"
    rm -f "$pnpm_path" "$(dirname "$pnpm_path")/pnpx" 2>/dev/null || true
  fi
  select_npm_registry
  npm install -g "pnpm@${PNPM_VERSION}" --registry "$NPM_REGISTRY" --no-audit --no-fund \
    || die "pnpm 安装失败，请手动执行: npm i -g pnpm@${PNPM_VERSION}"
  log "pnpm: $(pnpm --version)"
}

run_timed() {
  # 执行一条命令并汇报耗时，避免长步骤看起来像卡死
  local name="$1"; shift
  local started=$SECONDS
  log "▶ $name ..."
  if "$@"; then
    log "✔ $name 完成（耗时 $((SECONDS - started))s）"
    return 0
  fi
  local rc=$?
  err "✘ $name 失败（退出码 $rc，耗时 $((SECONDS - started))s）"
  return $rc
}

# 参数解析
SKIP_FRONTEND=0
SKIP_DB=0
SKIP_SEED=0
for arg in "$@"; do
  case "$arg" in
    --skip-frontend) SKIP_FRONTEND=1 ;;
    --skip-db)       SKIP_DB=1 ;;
    --skip-seed)     SKIP_SEED=1 ;;
    --help|-h)
      sed -n '2,30p' "$0"
      exit 0
      ;;
    *) die "未知参数: $arg（用 --help 查看用法）" ;;
  esac
done

log "项目根目录: $PROJECT_ROOT"

# ── 1. 系统依赖与版本基线检查 ──────────────────────────────
log "=== [1/7] 检查系统依赖与版本基线 ==="

# ══ 版本基线＝本机 dev 环境实测版本 ═══════════════════════════
# 低于基线＝未经完整验证的环境。分级处理：
#   硬失败(DIE)：已被实测证实会导致安装或运行中断的项
#   告警(WARN) ：本机无法直接测得，或已实测可运行的项（仅提示偏差）
PYTHON_MIN="3.14"      # 本机 3.14.7
NODE_MIN="26.7"        # 本机 v26.7.0
PNPM_MIN="10.34.5"     # frontend-new/package.json 的 packageManager
MYSQL_MIN="8.4"        # 安装文档标称版本
REDIS_MIN="8.0"        # 本机 Redis server 8.10.1

# 版本比较：ver_ge <当前> <最低>，满足返回 0
ver_ge() {
  awk -v cur="$1" -v min="$2" '
    BEGIN{ n=split(cur,a,"."); m=split(min,b,".")
           for(i=1;i<=m;i++){ if(a[i]+0>b[i]+0) exit 0; if(a[i]+0<b[i]+0) exit 1 }
           exit 0 }'
}

# Python：必须 >= 3.14，**不允许降级**
# 理由：realtime_gateway 使用 asyncio.AsyncGenerator，该属性在 Python 3.14 才存在；
# 旧脚本"找不到 3.14 就降级继续"会把必然崩溃压缩成一行 WARN，部署完成后才发现
# gateway 起不来，排查成本极高。
PY_BIN=""
for c in python3.14 python3.13 python3.12 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    v="$("$c" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo 0.0)"
    if ver_ge "$v" "$PYTHON_MIN"; then PY_BIN="$c"; break; fi
  fi
done
if [ -z "$PY_BIN" ]; then
  die "未找到 Python >= ${PYTHON_MIN}（当前系统最高 $(python3 --version 2>/dev/null || echo 未知)）。
  这是硬性要求：realtime_gateway 的 asyncio.AsyncGenerator 在更低版本不存在，启动即崩。
  安装方式（任选其一）：
    · uv（推荐）: curl -LsSf https://astral.sh/uv/install.sh | sh && uv python install 3.14
    · PPA      : sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt-get install -y python3.14 python3.14-venv
    · 官方源    : https://www.python.org/downloads/"
fi
log "Python: $PY_BIN ($("$PY_BIN" --version 2>&1)) ✓ (>= $PYTHON_MIN)"

# Node（前端构建必需）
if [ "$SKIP_FRONTEND" -eq 0 ]; then
  if ! command -v node >/dev/null 2>&1; then
    die "未找到 node。前端构建需要 Node >= ${NODE_MIN}，请先安装：https://nodejs.org/"
  fi
  # 判据取本机 dev 基线，而非"主版本 >= 20"：vite 8 / rolldown 的 engines 为
  # ^20.19.0 || >=22.12.0，Node 20.18.x 能通过粗放的主版本检查，但 pnpm 会
  # **静默跳过**不满足 engines 的可选原生依赖(@rolldown/binding-linux-x64-gnu)，
  # 到构建阶段才报 Cannot find native binding —— 报错点离根因很远，极难排查。
  cur_node="$(node -v 2>/dev/null | sed 's/^v//')"
  if ! ver_ge "${cur_node:-0.0}" "$NODE_MIN"; then
    die "Node 版本过低：当前 v${cur_node}，基线要求 >= ${NODE_MIN}（本机 dev = v26.7.0）。
  升级方式（任选其一）：
    · nvm    : nvm install 26 && nvm use 26
    · 二进制 : https://nodejs.org/dist/latest-v26.x/ 下载 linux-x64 包解压到 /usr/local
    · NodeSource: https://github.com/nodesource/distributions"
  fi
  log "Node: $(node --version) ✓ (>= $NODE_MIN)"

  # pnpm：低于基线版本则自动安装/升级
  ensure_pnpm "$PNPM_MIN"
fi

# MySQL（WARN 级：8.0.x 已实测可完成部署，但不等于 dev 基线，仅记录偏差）
MYSQL_CLIENT=""
for c in mysql mysql8; do
  if command -v "$c" >/dev/null 2>&1; then MYSQL_CLIENT="$c"; break; fi
done
if [ -n "$MYSQL_CLIENT" ]; then
  mysql_ver="$("$MYSQL_CLIENT" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1)"
  if ver_ge "${mysql_ver:-0.0}" "$MYSQL_MIN"; then
    log "MySQL: ${mysql_ver} ✓ (>= $MYSQL_MIN)"
  else
    warn "MySQL ${mysql_ver:-未知} 低于基线 ${MYSQL_MIN}。8.0.x 已实测可跑通部署，但属于「未验证组合」，
      生产环境建议对齐，避免 payroll/json 相关 SQL 行为差异。"
  fi
else
  warn "未找到 mysql 客户端，将使用 PyMySQL 导入 SQL（功能等价）"
fi

# Redis（WARN 级：本机 dev 为 8.10.1）
if command -v redis-server >/dev/null 2>&1; then
  redis_ver="$(redis-server --version 2>/dev/null | grep -oE 'v=[0-9]+\.[0-9]+(\.[0-9]+)?' | cut -d= -f2)"
elif command -v redis-cli >/dev/null 2>&1; then
  redis_ver="$(redis-cli --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1)"
else
  warn "未找到 redis-server / redis-cli。Redis 为缓存与 Celery broker，必须另行安装并启动。"
  redis_ver=""
fi
if [ -n "${redis_ver:-}" ]; then
  if ver_ge "$redis_ver" "$REDIS_MIN"; then
    log "Redis: ${redis_ver} ✓ (>= $REDIS_MIN)"
  else
    warn "Redis ${redis_ver} 低于 dev 基线 ${REDIS_MIN}（本机 8.10.1）。基础功能可用，但属「未验证组合」。"
  fi
fi

# ── 2. Python 虚拟环境 ─────────────────────────────────────
log "=== [2/7] 创建 Python venv 并安装依赖 ==="
VENV_DIR="$PROJECT_ROOT/.venv"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  log "创建 venv: $VENV_DIR"
  "$PY_BIN" -m venv "$VENV_DIR"
else
  log "venv 已存在，跳过创建"
fi
VENV_PY="$VENV_DIR/bin/python"

# 选择 pip 源（官方慢则自动切清华）
select_pip_index
# 日志被重定向到文件时 pip 输出会被缓冲，导致 tail -f 看不到滚动进度；
# PYTHONUNBUFFERED=1 让其行缓冲实时落盘。
export PYTHONUNBUFFERED=1

# ⚠️ 为什么用 script 包一层（而不是直接调用 pip）：
# pip 检测到输出不是终端(TTY)时会**不渲染进度条**。依赖树里的 torch ≈554MB，
# 下载期间日志一行不动，运维极易误判为"卡死"而反复重启安装——而 pip
# **不支持断点续传**，每次重来都要从 0 下载这 554MB，于是陷入死循环。
# script -qec 提供伪终端，让进度实时可见（tail -f 也能看到滚动）。
pip_tty() {
  script -qec "$VENV_PY -m pip install $*" /dev/null
}

# 大包预警：提前给出时间预期，避免"进度条不动 = 卡死"的误判
if grep -qE "^sentence-transformers" "$PROJECT_ROOT/requirements.txt" 2>/dev/null; then
  log "ℹ️  依赖树含 sentence-transformers → torch(≈554MB)，镜像源预计 1-4 分钟；"
  log "    期间进度条不动属正常（大文件正在下载）。若长时间无进展，可用"
  log "    PIP_INDEX_URL=<更快镜像> bash scripts/install.sh 强制指定源。"
fi

run_timed "升级 pip" script -qec "$VENV_PY -m pip install --upgrade pip wheel setuptools $PIP_INDEX_ARG --timeout 30 --retries 3" /dev/null

# 大文件易受网络抖动影响，单次连接超时放宽到 60s；失败则自动换清华源重试一次。
# 若两次都失败，多半是 requirements.txt 内部版本冲突（非网络问题）。
if run_timed "安装 requirements.txt" pip_tty \
      "-r $PROJECT_ROOT/requirements.txt $PIP_INDEX_ARG --progress-bar on --timeout 60 --retries 5"; then
  :
else
  warn "依赖安装失败，尝试改用清华源重试一次..."
  run_timed "安装 requirements.txt（清华源重试）" pip_tty \
      "-r $PROJECT_ROOT/requirements.txt -i $PIP_INDEX_TUNA --progress-bar on --timeout 60 --retries 5" \
    || die "依赖安装失败。若上方报错为 ResolutionImpossible/版本冲突，属 requirements.txt 内部矛盾（非网络问题）；若卡在 torch 等大包下载，请用 PIP_INDEX_URL 指定更快镜像后重跑。"
fi
log "Python 依赖安装完成"

# ── 3. 前端构建 ────────────────────────────────────────────
log "=== [3/7] 前端构建 ==="
FRONTEND_DIR="$PROJECT_ROOT/frontend-new"
if [ "$SKIP_FRONTEND" -eq 1 ]; then
  if [ -d "$FRONTEND_DIR/dist" ] && [ -f "$FRONTEND_DIR/dist/index.html" ]; then
    log "跳过前端构建（--skip-frontend），使用已有 dist/"
  else
    die "frontend-new/dist 不存在，不能跳过前端构建。请去掉 --skip-frontend。"
  fi
else
  if [ ! -f "$FRONTEND_DIR/package.json" ]; then
    die "frontend-new/package.json 不存在"
  fi
  cd "$FRONTEND_DIR"
  select_npm_registry
  log "安装前端依赖 (pnpm install)..."
  # 实测教训：小包探测能过不代表大依赖树能撑住——官方 registry 在完整安装时
  # 掉到 24 KiB/s 并丢失 rolldown 原生 binding 包导致构建失败。故首次尝试
  # 失败后，一律用 npmmirror 重试一次再判定失败。
  install_frontend_deps() {
    pnpm install --frozen-lockfile --registry "$NPM_REGISTRY" 2>/dev/null \
      || pnpm install --registry "$NPM_REGISTRY"
  }
  if ! install_frontend_deps; then
    warn "前端依赖安装失败，改用 ${NPM_REGISTRY_MIRROR} 重试一次..."
    NPM_REGISTRY="$NPM_REGISTRY_MIRROR"
    install_frontend_deps \
      || die "前端依赖安装失败（官方与 npmmirror 均失败），请检查网络后手动执行 pnpm install"
  fi
  log "构建前端 (pnpm build)..."
  pnpm build
  cd "$PROJECT_ROOT"
  if [ ! -f "$FRONTEND_DIR/dist/index.html" ]; then
    die "前端构建失败，frontend-new/dist/index.html 未生成"
  fi
  log "前端构建完成: frontend-new/dist/ ($(du -sh "$FRONTEND_DIR/dist" | cut -f1))"
fi

# ── 4. .env 初始化 ─────────────────────────────────────────
log "=== [4/7] 初始化 .env ==="
if [ ! -f "$PROJECT_ROOT/.env" ]; then
  cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
  warn ".env 已从 .env.example 创建。请编辑 $PROJECT_ROOT/.env 填写实际数据库/Redis 密码后重新运行本脚本。"
  warn "（若已配置好 .env，可忽略此提示，脚本将继续执行）"
else
  log ".env 已存在，跳过创建"
fi

# 安全密钥自动注入：SECRET_KEY / JWT_SECRET_KEY 凡缺失（空值）或仍为 change-me
# 占位符，一律生成 64 位随机 hex 覆盖，杜绝弱默认密钥上线（生产配置对占位符
# 会拒绝启动，此处提前自动修复，避免部署者漏填）。
"$VENV_PY" - <<PYEOF
import re, secrets
from pathlib import Path

p = Path("$PROJECT_ROOT/.env")
lines = p.read_text().splitlines()
generated = []
targets = {"SECRET_KEY", "JWT_SECRET_KEY"}
for i, line in enumerate(lines):
    m = re.match(r"^([A-Z_]+)=(.*)$", line)
    if not m or m.group(1) not in targets:
        continue
    val = m.group(2).strip()
    if val == "" or val.lower().startswith("change-me"):
        lines[i] = f"{m.group(1)}={secrets.token_hex(32)}"
        generated.append(m.group(1))
if generated:
    p.write_text("\n".join(lines) + "\n")
    print("    已自动生成随机密钥: " + ", ".join(generated))
else:
    print("    SECRET_KEY / JWT_SECRET_KEY 已配置，跳过")
PYEOF
set -a; . "$PROJECT_ROOT/.env"; set +a

# ── 5. 数据库初始化 ────────────────────────────────────────
if [ "$SKIP_DB" -eq 1 ]; then
  log "=== [5/7] 跳过数据库初始化 (--skip-db) ==="
else
  log "=== [5/7] 数据库初始化 ==="
  DB_HOST="${MYSQL_HOST:-localhost}"
  DB_PORT="${MYSQL_PORT:-3306}"
  DB_USER="${MYSQL_USER:-root}"
  DB_NAME="${MYSQL_DATABASE:-ip_manager}"
  export MYSQL_PWD="${MYSQL_PASSWORD:-}"

  log "预检 MySQL 连通性 ($DB_HOST:$DB_PORT)..."
  "$VENV_PY" - << PYEOF || die "MySQL 连接失败，请检查 .env 中 MYSQL_* 配置"
import pymysql, os
c = pymysql.connect(host="$DB_HOST", port=int("$DB_PORT"), user="$DB_USER",
                       init_command="SET time_zone='+00:00'",
                    password=os.getenv("MYSQL_PASSWORD",""), charset="utf8mb4")
c.close()
print("    MySQL 连接 OK")
PYEOF

  log "创建数据库 $DB_NAME（若不存在）..."
  "$VENV_PY" - << PYEOF
import pymysql, os
c = pymysql.connect(host="$DB_HOST", port=int("$DB_PORT"), user="$DB_USER",
                       init_command="SET time_zone='+00:00'",
                    password=os.getenv("MYSQL_PASSWORD",""), charset="utf8mb4", autocommit=True)
cur = c.cursor()
cur.execute("CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
c.close()
print("    数据库 $DB_NAME 就绪")
PYEOF

  # 全新安装的权威 DDL 源是迁移基线（0000_baseline.sql，生产库真实导出，
  # 含分区表与 15 个触发器）。快照已包含 0000_baseline.covers 清单中
  # 各迁移的效果，导入后按清单 stamp 版本即可与升级过的库保持一致。
  SCHEMA_FILE="$PROJECT_ROOT/migrations/versions/0000_baseline.sql"
  COVERS_FILE="$PROJECT_ROOT/migrations/versions/0000_baseline.covers"
  if [ -f "$SCHEMA_FILE" ]; then
    log "导入 $(basename "$SCHEMA_FILE")..."
    if [ -n "$MYSQL_CLIENT" ]; then
      # mysql CLI 原生支持 DELIMITER 指令
      # --init-command：固定会话时区为 UTC，使导入期间的 NOW()/CURRENT_TIMESTAMP
      # 与应用运行时的 UTC 口径一致（见 extensions.py 连接事件）
      "$MYSQL_CLIENT" --init-command="SET time_zone='+00:00'" -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" "$DB_NAME" < "$SCHEMA_FILE"
    else
      # 无 mysql 客户端时走 PyMySQL；触发器体含分号，必须用 DELIMITER 感知的切分器
      "$VENV_PY" "$PROJECT_ROOT/scripts/import_sql.py" "$SCHEMA_FILE"
    fi
    log "schema 导入完成"

    # 版本登记：按 covers 清单把"已体现进基线快照"的迁移版本 stamp 进
    # schema_migrations。之后 `flask db-upgrade` 只 apply 清单之外的增量
    # 迁移，新库逐版本升级到与生产库一致。
    # 纪律：重导 baseline 时必须同步更新 covers 清单（覆盖到链头就列到链头）。
    if [ -f "$COVERS_FILE" ]; then
      COVERED="$(grep -Ev '^[[:space:]]*(#|$)' "$COVERS_FILE" | tr -d ' \r' | paste -sd, -)"
    else
      warn "未找到 covers 清单，回退只 stamp 0000"
      COVERED="0000"
    fi
    "$VENV_PY" - << PYEOF || die "schema_migrations 版本登记失败"
import pymysql, os
covered = "${COVERED}".split(",")
c = pymysql.connect(host="$DB_HOST", port=int("$DB_PORT"), user="$DB_USER",
                       init_command="SET time_zone='+00:00'",
                    database="$DB_NAME", password=os.getenv("MYSQL_PASSWORD",""),
                    charset="utf8mb4", autocommit=True)
cur = c.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(16) NOT NULL PRIMARY KEY,
    description VARCHAR(255) NOT NULL DEFAULT '',
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
for v in covered:
    cur.execute(
        "INSERT IGNORE INTO schema_migrations (version, description)"
        " VALUES (%s, 'baseline')", (v,))
c.close()
print("    版本登记完成: baseline covers =", ",".join(covered))
PYEOF
  else
    warn "未找到任何 schema 文件，跳过（假设数据库已建表）"
  fi
fi

# ── 6. 种子数据 ────────────────────────────────────────────
if [ "$SKIP_SEED" -eq 1 ]; then
  log "=== [6/7] 跳过种子导入 (--skip-seed) ==="
else
  log "=== [6/7] 导入种子数据 ==="
  bash "$PROJECT_ROOT/migrations/seed_all.sh"
fi

# ── 7. 监控维护 cron ────────────────────────────────────────
log "=== [7/7] 配置监控维护 cron ==="
# 为什么必须有（生产教训 2026-09-07）：device_monitor_probe_events 与
# device_metric_timeseries 两张表按日分区，且都带 p_future(MAXVALUE) 兜底分区。
# 无人每天预建分区时，新数据全部落进 p_future（实测 30 天积压 12.6 万行），
# 按天 DROP PARTITION 的清理与分区裁剪随之全部失效 —— 表会无限膨胀。
# 预建必须走 REORGANIZE（有 MAXVALUE 兜底时 ADD PARTITION 会报 1481），
# CLI 已实现，但**必须有人调度**才会执行，故此处落地为默认 cron。
CRON_TAG="ipip-monitor-maintenance"
mkdir -p "$PROJECT_ROOT/logs" || warn "无法创建 logs 目录（不影响安装主体，但 cron 日志会写失败）"
if command -v crontab >/dev/null 2>&1; then
  # 幂等：先剔除旧的同类条目（按行尾标记识别），再整体重建，重跑 install.sh 不会重复叠加
  EXISTING="$(crontab -l 2>/dev/null | grep -v "$CRON_TAG" || true)"
  {
    [ -n "$EXISTING" ] && printf '%s\n' "$EXISTING"
    printf '# %s（由 scripts/install.sh 写入，重跑本脚本会整体重建，勿手工编辑）\n' "$CRON_TAG"
    printf '0 2 * * * cd %s && ./.venv/bin/flask --app wsgi:app monitor-manage-partitions >> %s/logs/monitor-partitions.log 2>&1 # %s\n' \
      "$PROJECT_ROOT" "$PROJECT_ROOT" "$CRON_TAG"
    printf '0 3 * * * cd %s && ./.venv/bin/flask --app wsgi:app monitor-archive >> %s/logs/monitor-archive.log 2>&1 # %s\n' \
      "$PROJECT_ROOT" "$PROJECT_ROOT" "$CRON_TAG"
  } | crontab -
  log "cron 已写入：02:00 预建分区 / 03:00 归档清理（日志 logs/monitor-*.log）"
else
  warn "未找到 crontab，跳过监控维护 cron。请自行添加两条定时任务："
  warn "  0 2 * * * cd $PROJECT_ROOT && ./.venv/bin/flask --app wsgi:app monitor-manage-partitions"
  warn "  0 3 * * * cd $PROJECT_ROOT && ./.venv/bin/flask --app wsgi:app monitor-archive"
fi

log "============================================================"
log "安装完成 ✅"
log "下一步: 编辑 .env 确认配置后，执行 bash scripts/start.sh 启动系统"
log "============================================================"
