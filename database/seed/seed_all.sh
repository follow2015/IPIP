#!/usr/bin/env bash
# ============================================================
# seed_all.sh - 一键执行全部数据库种子
# ------------------------------------------------------------
# 顺序（有依赖关系，不可乱序）：
#   1. seed_data.sql              配置类种子（权限/角色/指标模板/OID规则/VLAN等，幂等）
#   2. seed_rbac.py               RBAC 角色/权限（与 seed_data.sql 中 roles/permissions 互补，幂等）
#   3. seed_component_templates.py 配件模板（CPU/内存/硬盘/网卡/GPU，幂等）
#   4. seed_users.py              默认管理员账户 + 角色绑定
#
# 用法:
#   bash database/seed/seed_all.sh
#   SEED_ADMIN_PASSWORD='YourStrongPass!23' bash database/seed/seed_all.sh
#
# 环境变量:
#   SEED_ADMIN_PASSWORD  默认管理员密码（缺省随机生成并打印）
#   SEED_ADMIN_USERNAME  默认管理员用户名（缺省 root）
#   SEED_ADMIN_ROLE      默认管理员角色（缺省 admin）
#   SKIP_SQL_SEED=1      跳过 seed_data.sql（仅运行 Python 种子）
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# 加载 .env（若存在）
if [ -f "$PROJECT_ROOT/.env" ]; then
  set -a
  . "$PROJECT_ROOT/.env"
  set +a
fi

# 选择 Python 解释器
if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
  PY="$PROJECT_ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
else
  echo "ERROR: 未找到可用的 Python 解释器（期望 .venv 或 python3）" >&2
  exit 1
fi
echo ">>> Python: $PY"

# 选择 MySQL 客户端（用于执行 seed_data.sql）
MYSQL_CLIENT=""
for c in mysql mysql8; do
  if command -v "$c" >/dev/null 2>&1; then
    MYSQL_CLIENT="$c"
    break
  fi
done

# ── 1. 配置类种子 SQL ──────────────────────────────────────
if [ "${SKIP_SQL_SEED:-0}" != "1" ]; then
  echo "=== [1/4] 导入配置类种子 (seed_data.sql) ==="
  if [ -n "$MYSQL_CLIENT" ]; then
    MYSQL_HOST="${MYSQL_HOST:-localhost}"
    MYSQL_PORT="${MYSQL_PORT:-3306}"
    MYSQL_USER="${MYSQL_USER:-root}"
    MYSQL_DATABASE="${MYSQL_DATABASE:-ip_manager}"
    # 密码通过 MYSQL_PWD 环境变量传递，避免命令行暴露
    export MYSQL_PWD="${MYSQL_PASSWORD:-}"
    "$MYSQL_CLIENT" -h"$MYSQL_HOST" -P"$MYSQL_PORT" -u"$MYSQL_USER" "$MYSQL_DATABASE" \
      < "$SCRIPT_DIR/seed_data.sql"
    echo "    seed_data.sql imported via $MYSQL_CLIENT"
  else
    echo "    mysql 客户端未找到，改用 Python + PyMySQL 导入" >&2
    "$PY" - "$SCRIPT_DIR/seed_data.sql" << 'PYEOF'
import sys, os, pymysql
sql_file = sys.argv[1]
host = os.getenv('MYSQL_HOST', 'localhost')
port = int(os.getenv('MYSQL_PORT', '3306'))
user = os.getenv('MYSQL_USER', 'root')
pwd = os.getenv('MYSQL_PASSWORD', '')
db = os.getenv('MYSQL_DATABASE', 'ip_manager')
c = pymysql.connect(host=host, port=port, user=user, password=pwd, database=db, charset='utf8mb4', autocommit=True)
with open(sql_file, 'r', encoding='utf-8') as f:
    sql = f.read()
# 按分号拆分语句，跳过注释行和空行
stmts = []
buf = []
for line in sql.splitlines():
    stripped = line.strip()
    if stripped.startswith('--') or stripped == '':
        continue
    buf.append(line)
    if stripped.endswith(';'):
        stmts.append('\n'.join(buf))
        buf = []
if buf:
    stmts.append('\n'.join(buf))
cur = c.cursor()
for s in stmts:
    if s.strip():
        cur.execute(s)
c.close()
print(f"    seed_data.sql imported via PyMySQL ({len(stmts)} statements)")
PYEOF
  fi
  echo
else
  echo "=== [1/4] 跳过 seed_data.sql (SKIP_SQL_SEED=1) ==="
  echo
fi

# ── 2. RBAC 角色与权限（Python，幂等）──────────────────────
echo "=== [2/4] 种子 RBAC 角色与权限 ==="
"$PY" "$SCRIPT_DIR/seed_rbac.py"
echo

# ── 3. 配件模板（Python，幂等）────────────────────────────
echo "=== [3/4] 种子配件模板（CPU / 内存 / 硬盘 / 网卡 / GPU）==="
"$PY" "$SCRIPT_DIR/seed_component_templates.py"
echo

# ── 4. 默认管理员账户 + 角色绑定 ──────────────────────────
echo "=== [4/4] 种子默认管理员账户 ==="
"$PY" "$SCRIPT_DIR/seed_users.py"
echo

echo ">>> 全部种子脚本执行完成 ✅"
