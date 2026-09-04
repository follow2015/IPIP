#!/usr/bin/env bash
# ============================================================
# install.sh - ipip 一键安装脚本
# ------------------------------------------------------------
# 功能：
#   1. 检查系统依赖（Python 3.14+, Node 20+, pnpm 10+, MySQL 8.4+, Redis）
#   2. 创建 Python venv 并安装 requirements.txt
#   3. 前端依赖安装 + 构建（pnpm install && pnpm build → frontend-new/dist/）
#   4. 初始化 .env（若不存在则从 .env.example 拷贝）
#   5. 创建数据库并导入 schema + 种子
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

# ── 1. 系统依赖检查 ────────────────────────────────────────
log "=== [1/6] 检查系统依赖 ==="

# Python
PY_BIN=""
for c in python3.14 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    ver=$("$c" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo "0")
    if [ "${ver%%.*}" -ge 3 ] && [ "$(echo "$ver" | cut -d. -f2)" -ge 14 ] 2>/dev/null; then
      PY_BIN="$c"; break
    fi
  fi
done
if [ -z "$PY_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PY_BIN="python3"
    warn "未找到 Python 3.14，使用 $(python3 --version)。可能存在兼容性风险。"
  else
    die "未找到 Python 3.14+。请先安装：https://www.python.org/downloads/"
  fi
fi
log "Python: $PY_BIN ($($PY_BIN --version))"

# Node（前端构建必需）
if [ "$SKIP_FRONTEND" -eq 0 ]; then
  if ! command -v node >/dev/null 2>&1; then
    die "未找到 node。前端构建需要 Node.js 20+，请先安装：https://nodejs.org/"
  fi
  NODE_MAJOR=$(node -e 'console.log(process.versions.node.split(".")[0])')
  if [ "$NODE_MAJOR" -lt 20 ]; then
    die "Node.js 版本过低 ($(node --version))，需要 20+。"
  fi
  log "Node: $(node --version)"

  # pnpm
  if ! command -v pnpm >/dev/null 2>&1; then
    warn "未找到 pnpm，尝试通过 corepack 启用..."
    if command -v corepack >/dev/null 2>&1; then
      corepack enable pnpm 2>/dev/null || corepack prepare pnpm@10.34.5 --activate 2>/dev/null || die "pnpm 启用失败，请手动安装: npm i -g pnpm"
    else
      die "未找到 corepack，请手动安装 pnpm: npm i -g pnpm"
    fi
  fi
  log "pnpm: $(pnpm --version)"
fi

# MySQL 客户端（可选，seed_all.sh 内部会回退到 PyMySQL）
MYSQL_CLIENT=""
for c in mysql mysql8; do
  if command -v "$c" >/dev/null 2>&1; then MYSQL_CLIENT="$c"; break; fi
done
if [ -n "$MYSQL_CLIENT" ]; then
  log "MySQL 客户端: $MYSQL_CLIENT"
else
  warn "未找到 mysql 客户端，将使用 PyMySQL 导入 SQL（功能等价）"
fi

# Redis 客户端（仅检查，非必须）
if command -v redis-cli >/dev/null 2>&1; then
  log "redis-cli: $(command -v redis-cli)"
else
  warn "未找到 redis-cli（Redis 服务需另行安装并启动）"
fi

# ── 2. Python 虚拟环境 ─────────────────────────────────────
log "=== [2/6] 创建 Python venv 并安装依赖 ==="
VENV_DIR="$PROJECT_ROOT/.venv"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  log "创建 venv: $VENV_DIR"
  "$PY_BIN" -m venv "$VENV_DIR"
else
  log "venv 已存在，跳过创建"
fi
VENV_PY="$VENV_DIR/bin/python"
log "升级 pip..."
"$VENV_PY" -m pip install --upgrade pip wheel setuptools -q
log "安装 requirements.txt..."
"$VENV_PY" -m pip install -r "$PROJECT_ROOT/requirements.txt" -q
log "Python 依赖安装完成"

# ── 3. 前端构建 ────────────────────────────────────────────
log "=== [3/6] 前端构建 ==="
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
  log "安装前端依赖 (pnpm install)..."
  pnpm install --frozen-lockfile 2>/dev/null || pnpm install
  log "构建前端 (pnpm build)..."
  pnpm build
  cd "$PROJECT_ROOT"
  if [ ! -f "$FRONTEND_DIR/dist/index.html" ]; then
    die "前端构建失败，frontend-new/dist/index.html 未生成"
  fi
  log "前端构建完成: frontend-new/dist/ ($(du -sh "$FRONTEND_DIR/dist" | cut -f1))"
fi

# ── 4. .env 初始化 ─────────────────────────────────────────
log "=== [4/6] 初始化 .env ==="
if [ ! -f "$PROJECT_ROOT/.env" ]; then
  cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
  warn ".env 已从 .env.example 创建。请编辑 $PROJECT_ROOT/.env 填写实际数据库/Redis 密码后重新运行本脚本。"
  warn "（若已配置好 .env，可忽略此提示，脚本将继续执行）"
else
  log ".env 已存在，跳过"
fi
set -a; . "$PROJECT_ROOT/.env"; set +a

# ── 5. 数据库初始化 ────────────────────────────────────────
if [ "$SKIP_DB" -eq 1 ]; then
  log "=== [5/6] 跳过数据库初始化 (--skip-db) ==="
else
  log "=== [5/6] 数据库初始化 ==="
  DB_HOST="${MYSQL_HOST:-localhost}"
  DB_PORT="${MYSQL_PORT:-3306}"
  DB_USER="${MYSQL_USER:-root}"
  DB_NAME="${MYSQL_DATABASE:-ip_manager}"
  export MYSQL_PWD="${MYSQL_PASSWORD:-}"

  log "预检 MySQL 连通性 ($DB_HOST:$DB_PORT)..."
  "$VENV_PY" - << PYEOF || die "MySQL 连接失败，请检查 .env 中 MYSQL_* 配置"
import pymysql, os
c = pymysql.connect(host="$DB_HOST", port=int("$DB_PORT"), user="$DB_USER",
                    password=os.getenv("MYSQL_PASSWORD",""), charset="utf8mb4")
c.close()
print("    MySQL 连接 OK")
PYEOF

  log "创建数据库 $DB_NAME（若不存在）..."
  "$VENV_PY" - << PYEOF
import pymysql, os
c = pymysql.connect(host="$DB_HOST", port=int("$DB_PORT"), user="$DB_USER",
                    password=os.getenv("MYSQL_PASSWORD",""), charset="utf8mb4", autocommit=True)
cur = c.cursor()
cur.execute("CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
c.close()
print("    数据库 $DB_NAME 就绪")
PYEOF

  # 全新安装的权威 DDL 源是迁移基线条目（0000_baseline.sql，生产库真实导出，
  # 含分区表与 15 个触发器）。database/schema.sql 由 SQLAlchemy 模型生成，
  # 表达不了触发器/分区，仅作模型漂移参考，不作为安装源。
  SCHEMA_FILE="$PROJECT_ROOT/migrations/versions/0000_baseline.sql"
  if [ ! -f "$SCHEMA_FILE" ]; then
    warn "未找到 $SCHEMA_FILE，回退到 database/schema.sql（缺触发器/分区表）"
    SCHEMA_FILE="$PROJECT_ROOT/database/schema.sql"
  fi
  if [ -f "$SCHEMA_FILE" ]; then
    log "导入 $(basename "$SCHEMA_FILE")..."
    if [ -n "$MYSQL_CLIENT" ]; then
      # mysql CLI 原生支持 DELIMITER 指令
      "$MYSQL_CLIENT" -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" "$DB_NAME" < "$SCHEMA_FILE"
    else
      # 无 mysql 客户端时走 PyMySQL；触发器体含分号，必须用 DELIMITER 感知的切分器
      "$VENV_PY" "$PROJECT_ROOT/scripts/import_sql.py" "$SCHEMA_FILE"
    fi
    log "schema 导入完成"

    # 版本登记：baseline 快照 = 迁移链 "0000 已应用、0001+ 未应用" 的状态。
    # 必须把 0000 stamp 进 schema_migrations 版本表，之后 `flask db-upgrade`
    # 才会只 apply 真正的增量迁移（0001、0002...），新库由此逐版本升级到
    # 与生产库一致。若不 stamp，db-status 会误报"未应用任何迁移"，且版本
    # 正确性只能依赖每个迁移都幂等。
    # 纪律：若将来重导 baseline 且快照已含某迁移的效果，须同步 stamp 该版本。
    "$VENV_PY" - << PYEOF || die "schema_migrations 版本登记失败"
import pymysql, os
c = pymysql.connect(host="$DB_HOST", port=int("$DB_PORT"), user="$DB_USER",
                    database="$DB_NAME", password=os.getenv("MYSQL_PASSWORD",""),
                    charset="utf8mb4", autocommit=True)
cur = c.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(16) NOT NULL PRIMARY KEY,
    description VARCHAR(255) NOT NULL DEFAULT '',
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
cur.execute("INSERT IGNORE INTO schema_migrations (version, description) VALUES ('0000', 'baseline')")
c.close()
print("    版本登记完成: 0000 baseline 已应用")
PYEOF
  else
    warn "未找到任何 schema 文件，跳过（假设数据库已建表）"
  fi
fi

# ── 6. 种子数据 ────────────────────────────────────────────
if [ "$SKIP_SEED" -eq 1 ]; then
  log "=== [6/6] 跳过种子导入 (--skip-seed) ==="
else
  log "=== [6/6] 导入种子数据 ==="
  bash "$PROJECT_ROOT/database/seed/seed_all.sh"
fi

log "============================================================"
log "安装完成 ✅"
log "下一步: 编辑 .env 确认配置后，执行 bash scripts/start.sh 启动系统"
log "============================================================"
