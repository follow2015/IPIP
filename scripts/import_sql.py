#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 DDL 文件导入 MySQL（DELIMITER 感知）。

存在理由
--------
全新安装的权威 DDL 源是 ``migrations/versions/0000_baseline.sql``（生产库真实
导出，含 1 张分区表与 15 个触发器）。触发器体内含分号，必须用 ``DELIMITER ;;``
包裹；而 ``DELIMITER`` 是 **mysql CLI 的客户端指令、不是 SQL 语句**，朴素写法
``sql.split(';')`` 会把触发器体切碎，直接报语法错误。

本模块实现与 mysql CLI 等价的切分逻辑，供无 mysql 客户端的环境（install.sh 的
PyMySQL 回退路径、CI 冒烟）使用。

用法::

    python3 scripts/import_sql.py <file.sql>            # 连接参数取环境变量
    python3 scripts/import_sql.py <file.sql> --dry-run  # 只切分不执行
"""
from __future__ import annotations

import argparse
import os
import sys


def split_statements(sql: str) -> list[str]:
    """按当前分隔符切分 SQL，逐行累积以正确处理触发器体。

    - ``DELIMITER x`` 行切换分隔符（大小写不敏感），自身不产出语句
    - 纯注释行（``--`` 开头）与空行跳过
    - 行尾命中当前分隔符时刷出一条语句（去掉尾部分隔符）
    - 文件末尾未闭合的残留一并刷出

    Returns:
        语句列表（不含分隔符与 DELIMITER 指令）
    """
    stmts: list[str] = []
    buf: list[str] = []
    delim = ";"

    for raw in sql.splitlines():
        line = raw.strip()
        if line.upper().startswith("DELIMITER"):
            parts = line.split(None, 1)
            if len(parts) == 2:
                delim = parts[1].strip()
            continue
        if not line or line.startswith("--"):
            continue

        buf.append(raw)
        if delim and line.endswith(delim):
            stmt = "\n".join(buf).strip()[: -len(delim)].strip()
            if stmt:
                stmts.append(stmt)
            buf = []

    tail = "\n".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


def import_sql_file(path: str, dry_run: bool = False) -> dict:
    """导入单个 SQL 文件，返回执行统计。

    Args:
        path: SQL 文件路径
        dry_run: True 时只切分不执行（CI 预检用）

    Returns:
        {"statements": int, "tables": int, "triggers": int, "executed": int}

    Raises:
        RuntimeError: 语句数为 0（多半是切分器没识别到内容，静默空导入更危险）
    """
    with open(path, "r", encoding="utf-8") as f:
        stmts = split_statements(f.read())

    stats = {
        "statements": len(stmts),
        "tables": sum(1 for s in stmts if s.upper().startswith("CREATE TABLE")),
        "triggers": sum(1 for s in stmts if s.upper().startswith("CREATE TRIGGER")),
        "executed": 0,
    }
    if not stmts:
        raise RuntimeError(f"{path} 未切分出任何语句，拒绝执行")

    if dry_run:
        return stats

    import pymysql

    conn = pymysql.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "ip_manager"),
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            for stmt in stmts:
                cur.execute(stmt)
                stats["executed"] += 1
    finally:
        conn.close()
    return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="DELIMITER 感知的 MySQL DDL 导入器")
    ap.add_argument("sql_file", help="待导入的 .sql 文件")
    ap.add_argument("--dry-run", action="store_true", help="只切分并打印统计，不执行")
    args = ap.parse_args(argv)

    stats = import_sql_file(args.sql_file, dry_run=args.dry_run)
    print(
        f"{os.path.basename(args.sql_file)}: "
        f"{stats['statements']} 条语句 / {stats['tables']} 表 / "
        f"{stats['triggers']} 触发器"
        + ("（dry-run，未执行）" if args.dry_run else f"，已执行 {stats['executed']} 条")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
