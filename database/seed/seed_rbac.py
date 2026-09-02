#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RBAC 角色与权限种子数据导入脚本

将 PermissionManager 中定义的权限和角色映射写入数据库：
  - permissions      （权限清单）
  - roles            （角色清单）
  - role_permissions （角色-权限关联）

幂等执行：利用唯一约束 (code) / (name) 的 ON DUPLICATE KEY UPDATE 特性，
重复运行不会重复插入，只会更新已有记录。
角色权限关联则采用"先清空再重建"策略，确保与代码定义完全一致。

用法:
    python3 migrations/seed_rbac.py

环境变量（默认读取 .env 或 config.py 中的值）:
    MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
"""
import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv

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


PERMISSIONS = {
    "room:view": ("查看机房", "room", "查看机房信息"),
    "room:create": ("创建机房", "room", "创建新机房"),
    "room:update": ("更新机房", "room", "修改机房信息"),
    "room:delete": ("删除机房", "room", "删除机房"),
    "cabinet:view": ("查看机柜", "cabinet", "查看机柜信息"),
    "cabinet:create": ("创建机柜", "cabinet", "创建新机柜"),
    "cabinet:update": ("更新机柜", "cabinet", "修改机柜信息"),
    "cabinet:delete": ("删除机柜", "cabinet", "删除机柜"),
    "device:view": ("查看设备", "device", "查看设备信息"),
    "device:create": ("创建设备", "device", "创建新设备"),
    "device:update": ("更新设备", "device", "修改设备信息"),
    "device:delete": ("删除设备", "device", "删除设备"),
    "customer:view": ("查看客户", "customer", "查看客户信息"),
    "customer:create": ("创建客户", "customer", "创建新客户"),
    "customer:update": ("更新客户", "customer", "修改客户信息"),
    "customer:delete": ("删除客户", "customer", "删除客户"),
    "customer:terminate": ("终止客户", "customer", "终止客户并释放全部资源（含重建存档 PDF）"),
    "user:view": ("查看用户", "user", "查看用户信息"),
    "user:create": ("创建用户", "user", "创建新用户"),
    "user:update": ("更新用户", "user", "修改用户信息"),
    "user:delete": ("删除用户", "user", "删除用户"),
    "user:permission": ("管理用户权限", "user", "管理用户权限分配"),
    "user:role": ("管理用户角色", "user", "管理用户角色分配"),
    "user:log": ("管理用户登录日志", "user", "查看和管理用户登录日志"),
    "network:view": ("查看网络", "network", "查看网络信息"),
    "network:create": ("创建网络", "network", "创建新网络"),
    "network:update": ("更新网络", "network", "修改网络信息"),
    "network:delete": ("删除网络", "network", "删除网络"),
    "network:scan": ("网络扫描", "network", "执行网络扫描"),
    "switch:view": ("查看交换机", "switch", "查看交换机信息"),
    "switch:create": ("创建交换机", "switch", "创建新交换机"),
    "switch:update": ("更新交换机", "switch", "修改交换机信息"),
    "switch:delete": ("删除交换机", "switch", "删除交换机"),
    "switch:config": ("配置交换机", "switch", "配置交换机参数"),
    "ip:view": ("查看IP", "ip", "查看IP地址信息"),
    "ip:update": ("更新IP", "ip", "修改IP地址信息"),
    "ip:scan": ("IP扫描", "ip", "执行IP扫描"),
    "system:config": ("系统配置", "system", "管理系统配置"),
    "system:logs": ("查看日志", "system", "查看系统日志"),
    "system:backup": ("备份恢复", "system", "执行系统备份和恢复"),
    "system:scan": ("系统扫描", "system", "执行系统扫描"),
    "system:stats": ("查看统计", "system", "查看系统统计数据"),
    "asset:view": ("查看资产", "asset", "查看资产信息"),
    "asset:create": ("创建资产", "asset", "创建新资产"),
    "asset:update": ("更新资产", "asset", "修改资产信息"),
    "asset:delete": ("删除资产", "asset", "删除资产"),
    "monitor:view": ("查看监控", "monitor", "查看监控信息"),
    "monitor:config": ("配置监控", "monitor", "配置监控凭据和探测参数"),
    "monitor:alert": ("管理告警", "monitor", "管理监控告警"),
    "monitor:report": ("查看报表", "monitor", "查看监控报表"),
    "maintenance:view": ("查看维护", "maintenance", "查看维护信息"),
    "maintenance:create": ("创建维护", "maintenance", "创建维护记录"),
    "maintenance:update": ("更新维护", "maintenance", "修改维护记录"),
    "maintenance:delete": ("删除维护", "maintenance", "删除维护记录"),
    "security:read": ("查看安全设置", "security", "查看安全相关配置"),
    "security:config": ("配置安全设置", "security", "修改安全相关配置"),
    "security:session": ("管理会话", "security", "管理用户会话"),
    "rbac:view": ("查看角色权限", "rbac", "查看角色和权限配置"),
    "rbac:create": ("创建角色", "rbac", "创建新角色"),
    "rbac:update": ("更新角色", "rbac", "修改角色信息"),
    "rbac:delete": ("删除角色", "rbac", "删除角色"),
    "audit:view": ("查看审计日志", "audit", "查看审计日志记录"),
    "import:view": ("查看导入导出", "import", "查看导入导出记录"),
    # AI 能力
    "ai:use": ("AI 助手使用", "ai", "使用告警解读/NL 查询/RAG/巡查"),
    "ai:admin": ("AI 知识库管理", "ai", "RAG 文档入库"),
}

ROLES = {
    "admin": ("管理员", "拥有所有权限的系统管理员"),
    "operator": ("操作员", "可以查看和修改数据，但不能删除"),
    "viewer": ("查看者", "只能查看数据"),
    "user": ("普通用户", "只能查看基本信息"),
}

ROLE_PERMISSIONS = {
    "admin": [
        "room:view", "room:create", "room:update", "room:delete",
        "cabinet:view", "cabinet:create", "cabinet:update", "cabinet:delete",
        "device:view", "device:create", "device:update", "device:delete",
        "customer:view", "customer:create", "customer:update", "customer:delete", "customer:terminate",
        "user:view", "user:create", "user:update", "user:delete",
        "user:permission", "user:role", "user:log",
        "network:view", "network:create", "network:update", "network:delete", "network:scan",
        "switch:view", "switch:create", "switch:update", "switch:delete", "switch:config",
        "ip:view", "ip:update", "ip:scan",
        "system:config", "system:logs", "system:backup", "system:scan", "system:stats",
        "asset:view", "asset:create", "asset:update", "asset:delete",
        "monitor:view", "monitor:config", "monitor:alert", "monitor:report",
        "maintenance:view", "maintenance:create", "maintenance:update", "maintenance:delete",
        "security:read", "security:config", "security:session",
        "rbac:view", "rbac:create", "rbac:update", "rbac:delete",
        "audit:view",
        "import:view",
        "ai:use", "ai:admin",
    ],
    "operator": [
        "room:view", "room:create", "room:update",
        "cabinet:view", "cabinet:create", "cabinet:update",
        "device:view", "device:create", "device:update",
        "customer:view", "customer:create", "customer:update",
        "user:view",
        "network:view", "network:create", "network:update", "network:scan",
        "switch:view", "switch:create", "switch:update", "switch:config",
        "ip:view", "ip:update", "ip:scan",
        "system:scan", "system:stats",
        "monitor:view", "monitor:config",
        "ai:use",
    ],
    "viewer": [
        "room:view", "cabinet:view", "device:view", "customer:view", "user:view",
        "network:view", "switch:view", "ip:view", "system:stats",
    ],
    "user": [
        "room:view", "cabinet:view", "device:view",
        "network:view", "switch:view", "ip:view", "system:stats",
    ],
}


def _ensure_tables(cur):
    required = ("permissions", "roles", "role_permissions")
    for table in required:
        cur.execute(
            "SELECT COUNT(*) as cnt FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = %s",
            (table,),
        )
        if cur.fetchone()["cnt"] == 0:
            print(f"ERROR: {table} 表不存在，请先执行数据库迁移")
            sys.exit(1)


def seed_permissions(cur):
    perm_ids = {}
    inserted = updated = 0

    for code, (name, category, description) in PERMISSIONS.items():
        sql = """
            INSERT INTO permissions (code, name, category, description)
            VALUES (%s, %s, %s, %s)
            AS new_data
            ON DUPLICATE KEY UPDATE
              name        = new_data.name,
              category    = new_data.category,
              description = new_data.description
        """
        cur.execute(sql, (code, name, category, description))
        if cur.rowcount == 1:
            inserted += 1
        elif cur.rowcount == 2:
            updated += 1
        perm_ids[code] = cur.lastrowid if cur.lastrowid else None

    if any(v is None for v in perm_ids.values()):
        cur.execute("SELECT id, code FROM permissions WHERE code IN %s", (tuple(PERMISSIONS.keys()),))
        for row in cur.fetchall():
            perm_ids[row["code"]] = row["id"]

    print(f"  permissions: 新增 {inserted} 条, 更新 {updated} 条")
    return perm_ids


def seed_roles(cur):
    role_ids = {}
    inserted = updated = 0

    for name, (display_name, description) in ROLES.items():
        sql = """
            INSERT INTO roles (name, display_name, description, status)
            VALUES (%s, %s, %s, 0)
            AS new_data
            ON DUPLICATE KEY UPDATE
              display_name = new_data.display_name,
              description  = new_data.description,
              status       = new_data.status
        """
        cur.execute(sql, (name, display_name, description))
        if cur.rowcount == 1:
            inserted += 1
        elif cur.rowcount == 2:
            updated += 1
        role_ids[name] = cur.lastrowid if cur.lastrowid else None

    if any(v is None for v in role_ids.values()):
        cur.execute("SELECT id, name FROM roles WHERE name IN %s", (tuple(ROLES.keys()),))
        for row in cur.fetchall():
            role_ids[row["name"]] = row["id"]

    print(f"  roles:       新增 {inserted} 条, 更新 {updated} 条")
    return role_ids


def seed_role_permissions(cur, role_ids, perm_ids):
    system_role_ids = tuple(role_ids.values())
    cur.execute(
        "DELETE FROM role_permissions WHERE role_id IN %s",
        (system_role_ids,),
    )
    deleted = cur.rowcount

    inserted = 0
    for role_name, perm_codes in ROLE_PERMISSIONS.items():
        rid = role_ids.get(role_name)
        if not rid:
            continue
        for code in perm_codes:
            pid = perm_ids.get(code)
            if not pid:
                print(f"  WARNING: 权限 {code} 不存在，跳过")
                continue
            cur.execute(
                "INSERT IGNORE INTO role_permissions (role_id, permission_id) VALUES (%s, %s)",
                (rid, pid),
            )
            if cur.rowcount == 1:
                inserted += 1

    print(f"  role_permissions: 清空 {deleted} 条旧关联, 新建 {inserted} 条关联")


def seed():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            _ensure_tables(cur)

            print("=== 开始导入 RBAC 种子数据 ===")
            perm_ids = seed_permissions(cur)
            role_ids = seed_roles(cur)
            seed_role_permissions(cur, role_ids, perm_ids)
            conn.commit()

            print("\n=== 当前数据汇总 ===")
            cur.execute("SELECT COUNT(*) as cnt FROM permissions")
            print(f"  permissions:      {cur.fetchone()['cnt']} 条")
            cur.execute("SELECT COUNT(*) as cnt FROM roles")
            print(f"  roles:            {cur.fetchone()['cnt']} 条")
            cur.execute("SELECT COUNT(*) as cnt FROM role_permissions")
            print(f"  role_permissions: {cur.fetchone()['cnt']} 条")

            print("\n=== 各角色权限数量 ===")
            cur.execute(
                """
                SELECT r.name, COUNT(rp.permission_id) as cnt
                FROM roles r
                LEFT JOIN role_permissions rp ON r.id = rp.role_id
                WHERE r.name IN %s
                GROUP BY r.id, r.name
                ORDER BY r.id
                """,
                (tuple(ROLES.keys()),),
            )
            for row in cur.fetchall():
                print(f"  {row['name']:10s}: {row['cnt']} 条权限")

            print("\nRBAC 种子数据导入完成!")
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
