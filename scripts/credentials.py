#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""凭据查看与重置（运维期）

职责边界（与 migrations/seed_users.py 的分工）：
  - `migrations/seed_users.py` —— **bootstrap**：首次部署时创建 admin 账户；
  - 本脚本 —— **运维期**：查看现有凭据、重置 admin / MySQL / 应用密钥。

为什么需要它：
  1. 首次部署时 admin 密码是随机生成的、只输出一次，极易丢失（实测踩到过：
     两次安装日志里各有一个密码，靠 bcrypt 反查才知道哪个有效）；
  2. **MySQL 密码同时存在于两处** —— `.env` 的 `MYSQL_PASSWORD` 与 MySQL 服务器
     里的账号本身。手工只改一处，结果是「改完就连不上库」或「改了库却忘了改
     .env」。本脚本把两者一起改并**当场验证新密码可连**，杜绝配置漂移。

安全约定：
  - 生成的密码会打印到 stdout，并追加写入 `$PROJECT_ROOT/.credentials`（权限 600）；
  - **不提供 `SWITCH_SECRET_KEY` 重置**：它是 AES-256-GCM 设备凭据加密密钥，
    直接更换会让既有密文永久不可解，必须走「先解密再加密」的迁移。

用法：
    python scripts/credentials.py show
    python scripts/credentials.py reset-admin [--username admin] [--password P]
    python scripts/credentials.py reset-mysql [--db-user ipip] [--password P]
    python scripts/credentials.py reset-secret-keys --yes
"""
import argparse
import os
import re
import secrets
import string
import sys
from datetime import datetime
from pathlib import Path

import bcrypt
import pymysql
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
CRED_PATH = PROJECT_ROOT / ".credentials"

BCRYPT_ROUNDS = int(os.getenv("SEED_ADMIN_BCRYPT_ROUNDS", "12"))

CREDENTIAL_KEYS = [
    ("数据库", ["MYSQL_USER", "MYSQL_HOST", "MYSQL_DATABASE", "MYSQL_PASSWORD"]),
    ("缓存", ["REDIS_HOST", "REDIS_PORT", "REDIS_PASSWORD"]),
    ("应用密钥", ["SECRET_KEY", "JWT_SECRET_KEY", "SWITCH_SECRET_KEY"]),
    ("第三方", ["AI_API_KEY", "WX_SECRET", "WX_TOKEN", "XCC_SECRET"]),
]

NEVER_RESET = {"SWITCH_SECRET_KEY"}


def info(msg): print(msg)
def ok(msg):   print(f"  \033[0;32m✓\033[0m {msg}")
def warn(msg): print(f"  \033[0;33m!\033[0m {msg}")
def die(msg):
    print(f"  \033[0;31m✗\033[0m {msg}", file=sys.stderr)
    sys.exit(1)


PASSWORD_ALPHABET = string.ascii_letters + string.digits + "-_.~!*()"


def gen_password(length: int = 16) -> str:
    """强随机密码（大小写 + 数字 + 有限符号，避开 URI/shell 元字符）。"""
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))


def read_env() -> dict:
    """解析 .env（不依赖 os.environ，避免进程环境已存在同名变量时读到旧值）。"""
    data = {}
    if not ENV_PATH.exists():
        return data
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
        if m:
            data[m.group(1)] = m.group(2).strip()
    return data


def update_env(updates: dict) -> None:
    """就地替换 KEY=value（保留注释与行序），缺失的键追加到末尾；原子写。

    只改值、不重排文件：.env 里有大量解释性注释，重写会破坏它们的上下文。
    """
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    seen = set()
    for i, line in enumerate(lines):
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
        if m and m.group(1) in updates:
            lines[i] = f"{m.group(1)}={updates[m.group(1)]}"
            seen.add(m.group(1))
    for key, val in updates.items():
        if key not in seen:
            lines.append(f"{key}={val}")
    tmp = ENV_PATH.with_suffix(".env.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(ENV_PATH)          # 原子替换，避免写到一半留下半截 .env


def record_credential(title: str, items: list) -> None:
    """把本次生成的凭据追加到 .credentials（600）。失败不致命，仅告警。"""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        block = [f"\n[{ts}] {title}"] + [f"  {k} = {v}" for k, v in items]
        with open(CRED_PATH, "a", encoding="utf-8") as fh:
            fh.write("\n".join(block) + "\n")
        os.chmod(CRED_PATH, 0o600)
        print(f"  已追加记录到 {CRED_PATH}")
    except OSError as exc:
        warn(f"写入 {CRED_PATH} 失败（{exc}）—— 请手工抄录上面的密码")


def db_config(env: dict) -> dict:
    return {
        "host": env.get("MYSQL_HOST", "localhost"),
        "port": int(env.get("MYSQL_PORT", "3306")),
        "user": env.get("MYSQL_USER", "root"),
        "password": env.get("MYSQL_PASSWORD", ""),
        "database": env.get("MYSQL_DATABASE", "ip_management"),
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
    }


def connect_socket_root() -> pymysql.connections.Connection:
    """以 root 身份走 unix socket 连接（Debian/Ubuntu 默认 auth_socket 认证）。

    这是重置 MySQL 密码的首选路径：**不需要知道 root 密码**，只要以 root 运行。
    """
    last = None
    for sock in ("/var/run/mysqld/mysqld.sock", "/tmp/mysql.sock",
                 "/var/lib/mysql/mysql.sock"):
        if not os.path.exists(sock):
            continue
        try:
            return pymysql.connect(unix_socket=sock, user="root",
                                   charset="utf8mb4",
                                   cursorclass=pymysql.cursors.DictCursor)
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise RuntimeError(
        f"无法以 root 通过 socket 连接 MySQL（{last}）。\n"
        "    → 请用 sudo 运行本脚本（root 账号通常是 auth_socket 认证）"
    )


def cmd_show(_args) -> int:
    env = read_env()
    if not env:
        die(f"未找到 {ENV_PATH}，无法读取凭据")
    print("=" * 68)
    print(f"凭据清单（读取自 {ENV_PATH}）")
    print("=" * 68)
    for group, keys in CREDENTIAL_KEYS:
        print(f"\n[{group}]")
        for key in keys:
            val = env.get(key)
            if val is None:
                print(f"  {key:20s} （未设置）")
            elif val == "":
                print(f"  {key:20s} （空）")
            else:
                print(f"  {key:20s} {val}")
    print("\n[管理员账户]")
    try:
        conn = pymysql.connect(**db_config(env))
        with conn.cursor() as cur:
            cur.execute("SELECT id, username, status FROM users "
                        "WHERE username = %s", (env.get("SEED_ADMIN_USERNAME", "admin"),))
            row = cur.fetchone()
        conn.close()
        if row:
            ok(f"用户 '{row['username']}' 存在（id={row['id']}, status={row['status']}）；"
               "密码为哈希存储、**不可回显**")
            print(f"  {'':20s} 如需重置：python scripts/credentials.py reset-admin")
        else:
            warn("未找到默认管理员，请先执行 migrations/seed_all.sh")
    except Exception as exc:  # noqa: BLE001
        warn(f"无法连接数据库核对管理员账户（{exc}）")
    if CRED_PATH.exists():
        print(f"\n历史生成记录: {CRED_PATH}（权限 600，含历次重置的明文）")
    print("=" * 68)
    return 0


def cmd_reset_admin(args) -> int:
    env = read_env()
    username = args.username or env.get("SEED_ADMIN_USERNAME", "admin")
    new_pwd = args.password or gen_password()

    conn = pymysql.connect(**db_config(env))
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username = %s", (username,))
            row = cur.fetchone()
            if not row:
                die(f"用户 '{username}' 不存在 —— 请先执行 migrations/seed_all.sh 创建"
                    "（本脚本只重置已存在的账户，不负责创建与角色绑定）")
            cur.execute("UPDATE users SET password = %s WHERE id = %s",
                        (bcrypt.hashpw(new_pwd.encode(), bcrypt.gensalt(rounds=BCRYPT_ROUNDS))
                         .decode(), row["id"]))
        conn.commit()
    finally:
        conn.close()

    print("=" * 68)
    ok(f"管理员 '{username}' 密码已重置")
    print(f"      新密码: {new_pwd}")
    print("  ⚠️ 请立即保存；已登录的会话不受影响，其它人下次登录需用新密码。")
    print("=" * 68)
    record_credential(f"reset-admin ({username})", [("username", username), ("password", new_pwd)])
    return 0


def cmd_reset_mysql(args) -> int:
    env = read_env()
    db_user = args.db_user or env.get("MYSQL_USER", "root")
    new_pwd = args.password or gen_password()

    if db_user == "root" and not args.force:
        warn("目标账号是 root —— 重置它可能影响其它管理入口；确实需要请加 --force")

    try:
        conn = connect_socket_root()
    except RuntimeError as exc:
        warn(str(exc))
        info("  → 回退：尝试用 .env 中的账号执行 ALTER USER")
        conn = pymysql.connect(**db_config(env))

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT host FROM mysql.user WHERE user = %s", (db_user,))
            hosts = [r["host"] for r in cur.fetchall()]
            if not hosts:
                die(f"MySQL 中不存在账号 '{db_user}'")
            for host in hosts:
                cur.execute(
                    f"ALTER USER %s@%s IDENTIFIED BY %s", (db_user, host, new_pwd))
                ok(f"已修改 MySQL 账号 '{db_user}'@'{host}' 的密码")
        conn.commit()
    finally:
        conn.close()

    update_env({"MYSQL_PASSWORD": new_pwd})
    ok(f"已同步 {ENV_PATH} 的 MYSQL_PASSWORD")

    try:
        probe = db_config(env)
        probe["password"] = new_pwd
        c = pymysql.connect(**probe)
        with c.cursor() as cur:
            cur.execute("SELECT 1")
        c.close()
        ok("新密码连接验证通过")
    except Exception as exc:  # noqa: BLE001
        warn(f"新密码连接验证失败（{exc}）—— 请检查账号 host 与授权设置")

    print("=" * 68)
    print(f"  MySQL 账号: {db_user}")
    print(f"  新密码:     {new_pwd}")
    print("  ⚠️ 常驻服务仍持有旧连接，需重启后生效：")
    print("       systemctl restart ipip-web ipip-monitor ipip-gateway "
          "ipip-celery-ai ipip-celery-voice")
    print("=" * 68)
    record_credential(f"reset-mysql ({db_user})",
                      [("db_user", db_user), ("password", new_pwd)])
    return 0


def cmd_reset_secret_keys(args) -> int:
    if not args.yes:
        die("该操作会让所有用户登出、全部 JWT 立即失效。确认请输入 --yes")
    env = read_env()
    updates = {"SECRET_KEY": secrets.token_hex(32),
               "JWT_SECRET_KEY": secrets.token_hex(32)}
    blocked = sorted(NEVER_RESET & set(updates))
    if blocked:
        die(f"内部错误：{blocked} 不应出现在可重置列表")
    update_env(updates)
    print("=" * 68)
    ok("已重置应用密钥：SECRET_KEY、JWT_SECRET_KEY")
    print("  影响: 所有用户需重新登录；签发中的 JWT 立即失效。")
    print("  ⚠️ 未改动 SWITCH_SECRET_KEY —— 它加密设备凭据，更换需先做密文迁移")
    print("      （见 docs/运维手册-密钥与环境变量.md 第四节）")
    print("  需重启服务后生效：systemctl restart 'ipip-*'")
    print("=" * 68)
    record_credential("reset-secret-keys",
                      [(k, v) for k, v in updates.items()])
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="IPIP 凭据查看与重置（运维期）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  python scripts/credentials.py show\n"
               "  python scripts/credentials.py reset-admin\n"
               "  sudo python scripts/credentials.py reset-mysql\n"
               "  python scripts/credentials.py reset-secret-keys --yes\n")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show", help="列出 .env 中的凭据与管理员账户状态")

    p_admin = sub.add_parser("reset-admin", help="重置管理员密码（默认随机 16 位）")
    p_admin.add_argument("--username", help="管理员用户名（默认取 .env 的 SEED_ADMIN_USERNAME 或 admin）")
    p_admin.add_argument("--password", help="指定新密码（默认随机生成）")

    p_mysql = sub.add_parser("reset-mysql", help="重置 MySQL 账号密码并同步 .env")
    p_mysql.add_argument("--db-user", help="MySQL 账号（默认取 .env 的 MYSQL_USER）")
    p_mysql.add_argument("--password", help="指定新密码（默认随机生成）")
    p_mysql.add_argument("--force", action="store_true", help="允许重置 root 账号")

    p_keys = sub.add_parser("reset-secret-keys", help="重置 SECRET_KEY / JWT_SECRET_KEY")
    p_keys.add_argument("--yes", action="store_true", help="确认执行（会让所有用户登出）")

    args = parser.parse_args(argv)
    load_dotenv(ENV_PATH)          # 兼容依赖 os.environ 的路径
    return {"show": cmd_show, "reset-admin": cmd_reset_admin,
            "reset-mysql": cmd_reset_mysql,
            "reset-secret-keys": cmd_reset_secret_keys}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
