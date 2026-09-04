# -*- coding: utf-8 -*-
"""数据库 Schema 版本化迁移 runner（基线 + 迁移链 + schema_migrations 版本表）。

背景（2026-09-04）：migrations/ 顶层 30+ 散迁移已冻结（生产库均已应用）。
自本日起 schema 变更一律走 migrations/versions/ 迁移链：

- 0000_baseline.sql  —— 基线快照（真实生产库 SHOW CREATE TABLE 导出，由
  scripts/export_schema_dump.py 生成），仅全新安装时手动导入；runner 不执行
  任何 .sql 文件。
- NNNN_name.py       —— 增量迁移，必须实现 ``apply(conn)``；内容须幂等
  （失败重跑安全）。DBAPI 连接由 runner 注入，与既有散迁移的 pymysql 惯例
  一致。

用户升级：新版发布后执行 ``flask db-upgrade``——按序应用未记录的迁移并写入
schema_migrations；``flask db-status`` 查看状态；``flask db-upgrade --dry-run``
只打印计划不落库（对齐「先只读预检再执行」纪律）。

纪律：
- 模型改动与迁移文件同一 commit（防模型↔库漂移）；
- 数据回填也走迁移链（.py 内批处理），不放 DDL 文件；
- 已知 MySQL 8.4 硬约束见项目 memory：分区表无 FK(1506)、表 COMMENT 先于
  PARTITION BY(1064)、FK 引用列类型须完全一致(3780)。
"""
import importlib.util
import re
from dataclasses import dataclass
from pathlib import Path

VERSION_FILE_RE = re.compile(r"^(\d{4})_[a-z0-9_]+\.py$")

VERSION_TABLE = "schema_migrations"

VERSION_TABLE_DDL = (
    f"CREATE TABLE IF NOT EXISTS {VERSION_TABLE} ("
    " version VARCHAR(16) NOT NULL PRIMARY KEY,"
    " description VARCHAR(255) NOT NULL DEFAULT '',"
    " applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
    ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
)


@dataclass(frozen=True)
class MigrationFile:
    version: str
    path: Path
    description: str


def _module_description(path: Path) -> str:
    """从迁移模块 docstring 首行取描述（无 docstring 回退文件名）。"""
    try:
        import ast

        tree = ast.parse(path.read_text(encoding="utf-8"))
        doc = ast.get_docstring(tree) or ""
        first = doc.strip().splitlines()[0].strip() if doc.strip() else ""
        return first[:255] or path.stem
    except Exception:  # noqa: BLE001 - 描述解析失败不阻塞迁移本身
        return path.stem


def discover_migrations(versions_dir) -> list[MigrationFile]:
    """扫描目录返回按序号排序的迁移清单（不符合命名的文件忽略）。"""
    d = Path(versions_dir)
    if not d.is_dir():
        return []
    found: list[MigrationFile] = []
    for p in sorted(d.iterdir()):
        m = VERSION_FILE_RE.match(p.name)
        if not m:
            continue
        found.append(MigrationFile(version=m.group(1), path=p,
                                   description=_module_description(p)))
    found.sort(key=lambda x: x.version)
    return found


def _load_apply_fn(mf: MigrationFile):
    """按路径加载迁移模块，返回其 apply 函数（缺失时报可定位错误）。"""
    spec = importlib.util.spec_from_file_location(
        f"ipip_migration_{mf.version}", mf.path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, "apply", None)
    if not callable(fn):
        raise RuntimeError(
            f"迁移 {mf.path.name} 缺少可调用的 apply(conn) 函数（契约见"
            f" app/services/schema_migration_service.py 模块 docstring）"
        )
    return fn


class SchemaMigrationRunner:
    """按 versions/ 迁移链推进 schema 版本（连接由调用方注入）。"""

    def __init__(self, conn, versions_dir):
        self._conn = conn
        self._migrations = discover_migrations(versions_dir)


    def _version_table_exists(self) -> bool:
        cur = self._conn.cursor()
        try:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = %s",
                (VERSION_TABLE,),
            )
            return bool(cur.fetchall())
        finally:
            cur.close()

    def applied_versions(self) -> set:
        if not self._version_table_exists():
            return set()
        cur = self._conn.cursor()
        try:
            cur.execute(f"SELECT version FROM {VERSION_TABLE}")
            return {row[0] for row in cur.fetchall()}
        finally:
            cur.close()

    def pending(self) -> list[MigrationFile]:
        applied = self.applied_versions()
        return [m for m in self._migrations if m.version not in applied]


    def run(self, dry_run: bool = False) -> list:
        """应用全部 pending；dry_run=True 只返回计划不执行任何写操作。

        返回实际应用（或计划应用）的 version 列表。单迁移成功后立即
        commit 并记录版本——迁移内容自身幂等，失败重跑安全。
        """
        todo = self.pending()
        if dry_run:
            return [m.version for m in todo]

        self._ensure_version_table()
        applied_now: list[str] = []
        for mf in todo:
            apply_fn = _load_apply_fn(mf)
            apply_fn(self._conn)
            cur = self._conn.cursor()
            try:
                cur.execute(
                    f"INSERT INTO {VERSION_TABLE} (version, description)"
                    " VALUES (%s, %s)",
                    (mf.version, mf.description),
                )
            finally:
                cur.close()
            self._conn.commit()
            applied_now.append(mf.version)
        return applied_now

    def _ensure_version_table(self) -> None:
        cur = self._conn.cursor()
        try:
            cur.execute(VERSION_TABLE_DDL)
        finally:
            cur.close()
        self._conn.commit()
