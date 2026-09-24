#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# 容器角色分发入口
#
# 纪律：每个分支的命令**逐字对齐** deploy/systemd/*.service 的 ExecStart。
#   改本文件时，先去核对对应的 .service 是否也要同步改，两边不能出现
#   "文档一套、实现一套"的漂移。
#
# 与 systemd 的两处**有意差异**（已核对，非疏漏）：
#   ① web：unit 用 `--chdir ${PROJECT_ROOT}`，这里写 `--chdir /app`（同义，显式化）
#   ② gateway：unit 用 `--app-dir ${PROJECT_ROOT}`，这里写 `--app-dir /app`（同上）
#      —— 不依赖 "WORKDIR 恰好等于项目根" 这个巧合。
#
# migrate 角色不复用裸 `flask db-upgrade`：见下方实现，它在空库上建不出 schema。
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

ROLE="${1:-web}"
shift || true

case "$ROLE" in
  web)
    exec gunicorn \
      --bind 0.0.0.0:"${FLASK_PORT:-5000}" \
      --workers "${GUNICORN_WORKERS:-4}" \
      --timeout 120 \
      --access-logfile - \
      --error-logfile - \
      --chdir /app \
      wsgi:application
    ;;

  gateway)
    exec uvicorn realtime_gateway.main:app \
      --host 0.0.0.0 \
      --port "${GATEWAY_PORT:-8000}" \
      --app-dir /app
    ;;

  celery-ai)
    exec celery -A app.celery_app.celery worker \
      -Q ai \
      --concurrency="${CELERY_AI_CONCURRENCY:-2}" \
      --loglevel=info
    ;;

  celery-voice)
    exec celery -A app.celery_app.celery worker \
      -Q voice \
      --concurrency="${CELERY_VOICE_CONCURRENCY:-4}" \
      --loglevel=info
    ;;

  monitor)
    exec python /app/run_monitor_service.py
    ;;

  trapd)
    exec python /app/run_trapd_service.py
    ;;

  migrate)
    # ─────────────────────────────────────────────────────────────────────
    # 全新库的正确初始化序列（复刻 scripts/install.sh:1028-1070）：
    #   ① 探测 schema_migrations 是否存在
    #   ② 不存在 → scripts/import_sql.py 导入 0000_baseline.sql（DELIMITER 感知）
    #   ③          按 0000_baseline.covers 清单 stamp 版本
    #   ④ flask --app wsgi:app db-upgrade 应用清单之外的增量
    #
    # 为什么不能只跑 db-upgrade：
    #   schema_migration_service.py 的 VERSION_FILE_RE 只匹配 `NNNN_*.py`，
    #   且其 docstring 明确写 "0000_baseline.sql … 仅全新安装时手动导入；
    #   runner 不执行任何 .sql 文件"。空库上直接跑增量迁移会打到不存在的表。
    # ─────────────────────────────────────────────────────────────────────
    DB_INITIALIZED="$(python - <<'PYEOF' || echo 0
import os, sys
import pymysql
try:
    conn = pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "mysql"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ.get("MYSQL_USER", "root"),
        password=os.environ.get("MYSQL_PASSWORD", ""),
        charset="utf8mb4",
        autocommit=True,
        init_command="SET time_zone='+00:00'",
    )
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema=%s AND table_name='schema_migrations'",
        (os.environ.get("MYSQL_DATABASE", "ip_management"),),
    )
    sys.stdout.write("1" if cur.fetchone()[0] > 0 else "0")
    conn.close()
except Exception as exc:                      # noqa: BLE001
    sys.stderr.write("schema_migrations 探测失败（%s），按未初始化处理\n" % exc)
    sys.stdout.write("0")
PYEOF
)"

    if [ "${DB_INITIALIZED}" != "1" ]; then
      echo "==> [migrate] 全新库：导入基线 0000_baseline.sql"
      python /app/scripts/import_sql.py /app/migrations/versions/0000_baseline.sql

      echo "==> [migrate] 按 0000_baseline.covers 登记已覆盖版本"
      python - <<'PYEOF'
import os
import pymysql

covers_path = "/app/migrations/versions/0000_baseline.covers"
covered = []
with open(covers_path, encoding="utf-8") as fh:
    for line in fh:
        s = line.strip()
        if s and not s.startswith("#"):
            covered.append(s)

conn = pymysql.connect(
    host=os.environ.get("MYSQL_HOST", "mysql"),
    port=int(os.environ.get("MYSQL_PORT", "3306")),
    user=os.environ.get("MYSQL_USER", "root"),
    password=os.environ.get("MYSQL_PASSWORD", ""),
    database=os.environ.get("MYSQL_DATABASE", "ip_management"),
    charset="utf8mb4",
    autocommit=True,
    init_command="SET time_zone='+00:00'",
)
cur = conn.cursor()
cur.execute(
    "CREATE TABLE IF NOT EXISTS schema_migrations ("
    " version VARCHAR(16) NOT NULL PRIMARY KEY,"
    " description VARCHAR(255) NOT NULL DEFAULT '',"
    " applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
    ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
)
for v in covered:
    cur.execute(
        "INSERT IGNORE INTO schema_migrations (version, description)"
        " VALUES (%s, 'baseline')",
        (v,),
    )
conn.close()
print("    版本登记完成: baseline covers =", ",".join(covered))
PYEOF
    else
      echo "==> [migrate] 库已初始化：跳过 baseline，仅应用增量迁移"
    fi

    echo "==> [migrate] flask --app wsgi:app db-upgrade"
    exec flask --app wsgi:app db-upgrade
    ;;

  seed)
    # 幂等：seed_all.sh 内部四步（配置类 SQL / RBAC / 配件模板 / 管理员账号）全部幂等，
    # 重跑安全。SEED_ADMIN_PASSWORD 由 .env 提供，避免"密码只打印一次"导致找回困难。
    exec bash /app/migrations/seed_all.sh
    ;;

  shell)
    exec bash
    ;;

  *)
    echo "未知角色：$ROLE" >&2
    echo "可选：web / gateway / celery-ai / celery-voice / monitor / trapd / migrate / seed / shell" >&2
    exit 1
    ;;
esac
