#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
默认管理员用户种子脚本

系统首次部署 / 重置数据库后，RBAC 角色权限已由 seed_rbac.py 写入，
但 users 表为空、admin 账户不存在、user_roles 关联缺失，会导致无法登录。
本脚本用于创建默认管理员账户并绑定 admin 角色，补齐 bootstrap 的最后一块。

幂等执行：按 username 查重，已存在则跳过创建（可选项：显式提供密码时重置）。
重复运行不会产生重复账户或重复的角色关联。

依赖：须先运行 seed_rbac.py 写入 admin 角色。

用法:
    python3 migrations/seed_users.py

环境变量（可选）:
    SEED_ADMIN_USERNAME  默认管理员用户名        (默认 admin)
    SEED_ADMIN_PASSWORD  明文密码；不设置则随机生成并打印到控制台
    SEED_ADMIN_NAME      真实姓名                (默认 系统管理员)
    SEED_ADMIN_EMAIL     邮箱                    (默认 空)
    SEED_ADMIN_ROLE      绑定角色名              (默认 admin)
    SEED_ADMIN_BCRYPT_ROUNDS  bcrypt 加密轮数    (默认 12，与 app/utils/security/password.py 一致)

    MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
"""
import os
import secrets
import string
import sys
import logging
from pathlib import Path

import bcrypt
import pymysql
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root / ".env")

DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "ip_management"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

BCRYPT_ROUNDS = int(os.getenv("SEED_ADMIN_BCRYPT_ROUNDS", "12"))


def _hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def _generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _ensure_tables(cur):
    required = ("users", "roles", "user_roles")
    for table in required:
        cur.execute(
            "SELECT COUNT(*) as cnt FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = %s",
            (table,),
        )
        if cur.fetchone()["cnt"] == 0:
            print(f"ERROR: {table} 表不存在，请先执行数据库迁移")
            sys.exit(1)


def seed():
    admin_username = os.getenv("SEED_ADMIN_USERNAME", "admin")
    admin_password = os.getenv("SEED_ADMIN_PASSWORD")
    admin_name = os.getenv("SEED_ADMIN_NAME", "系统管理员")
    admin_email = os.getenv("SEED_ADMIN_EMAIL", "")
    admin_role = os.getenv("SEED_ADMIN_ROLE", "admin")

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            _ensure_tables(cur)

            cur.execute("SELECT id FROM roles WHERE name = %s", (admin_role,))
            role_row = cur.fetchone()
            if not role_row:
                print(f"ERROR: 角色 '{admin_role}' 不存在，请先运行 migrations/seed_rbac.py")
                sys.exit(1)
            role_id = role_row["id"]

            cur.execute("SELECT id FROM users WHERE username = %s", (admin_username,))
            user_row = cur.fetchone()

            if user_row:
                user_id = user_row["id"]
                if admin_password:
                    cur.execute(
                        "UPDATE users SET password = %s, name = %s, email = %s, status = 0 WHERE id = %s",
                        (_hash_password(admin_password), admin_name, admin_email, user_id),
                    )
                    print(f"  用户 '{admin_username}' 已存在，已按 SEED_ADMIN_PASSWORD 重置密码")
                else:
                    print(f"  用户 '{admin_username}' 已存在，跳过创建（未提供 SEED_ADMIN_PASSWORD，保留原密码）")
            else:
                if not admin_password:
                    admin_password = _generate_password()
                    print("=" * 64)
                    print(f"  未设置 SEED_ADMIN_PASSWORD，已为 '{admin_username}' 随机生成密码。")
                    print("  密码已写入日志文件，不会在此显示；建议首次登录后立即修改。")
                    print("=" * 64)
                    logger.warning(f"管理员 '{admin_username}' 初始密码: {admin_password}")
                cur.execute(
                    "INSERT INTO users (username, password, name, email, status) "
                    "VALUES (%s, %s, %s, %s, 0)",
                    (admin_username, _hash_password(admin_password), admin_name, admin_email),
                )
                user_id = cur.lastrowid
                print(f"  已创建用户 '{admin_username}' (id={user_id})")

            cur.execute(
                "INSERT IGNORE INTO user_roles (user_id, role_id) VALUES (%s, %s)",
                (user_id, role_id),
            )
            if cur.rowcount == 1:
                print(f"  已为用户 '{admin_username}' 绑定角色 '{admin_role}'")
            else:
                print(f"  用户 '{admin_username}' 已绑定角色 '{admin_role}'，无需重复绑定")

            conn.commit()
            print("\n默认管理员种子完成!")
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
