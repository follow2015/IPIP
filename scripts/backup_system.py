#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""IPIP 系统级备份（MySQL 全库 + instance/ 非 DB 数据面）。

用法:
    python scripts/backup_system.py [--output-dir DIR] [--prune] [--dry-run]

产物结构（每次备份一个自包含目录）：
    <output-dir>/ipip-backup-YYYYmmdd-HHMMSS/
        mysql.sql.gz      # mysqldump 全量
        dataface.tar.gz   # instance/ 数据面（chroma 向量库 / FTS5 sqlite / pickle）
        manifest.json     # 校验清单：commit、mysqldump 版本、各产物 sha256/size

设计约束（勿破坏，详见 WBS T1）：
- **不依赖 Flask app 上下文**：备份是"应用坏了时要用"的工具，不能因 ORM/插件
  初始化失败而失效，故只用 subprocess + os.environ；
- **不复用 app.config["SQLALCHEMY_DATABASE_URI"]**：该值是 @property，
  经 from_object 拷入的是描述符对象而非字符串（见 config.py:459-472）；
  此处直接读 MYSQL_* 裸环境变量；
- **密码经临时 defaults-extra-file 传入**（权限 0600），避免出现在进程命令行
  被 ps 看到；
- 产物**不含 .env**（内含生产库密码），且权限 0600。
"""
import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTANCE_DIR = ROOT / "instance"
DEFAULT_OUTPUT_DIR = ROOT / "backups" / "system"

KEEP_DAILY = 7
KEEP_WEEKLY = 4
KEEP_MONTHLY = 3


def load_db_env() -> dict:
    """读取数据库裸环境变量作为连接参数。

    Returns:
        dict: host/port/user/password/database；键名与 config.py:122-126 一致。
    """
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", 3306)),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "ip_management"),
    }


def _write_defaults_file(cfg: dict) -> str:
    """生成临时 MySQL defaults 文件，供 mysqldump/mysql 免交互式取凭据。

    MySQL ini 支持双引号包裹，故对密码中的特殊字符做最小化转义即可，
    比把密码拼进命令行安全（命令行对 ps 可见）。

    Args:
        cfg: load_db_env() 的返回。

    Returns:
        str: 临时文件路径（权限 0600），调用方负责删除。
    """
    fd, path = tempfile.mkstemp(prefix="ipip-backup-", suffix=".cnf")
    os.close(fd)
    os.chmod(path, 0o600)
    esc_pwd = cfg["password"].replace("\\", "\\\\").replace('"', '\\"')
    with open(path, "w", encoding="utf-8") as f:
        f.write("[client]\n")
        f.write(f"host={cfg['host']}\n")
        f.write(f"port={cfg['port']}\n")
        f.write(f"user={cfg['user']}\n")
        f.write(f'password="{esc_pwd}"\n')
    return path


def _locate_tool(name: str) -> str:
    """定位 mysqldump / mysql 二进制路径。

    Args:
        name: 工具名。

    Returns:
        str: 可执行文件路径。

    Raises:
        SystemExit: 未找到该命令。
    """
    found = shutil.which(name)
    if not found:
        sys.exit(f"❌ 未找到 {name} 命令，请先安装 MySQL 客户端工具")
    return found


def _git_commit() -> str:
    """获取当前 Git commit（失败降级为 unknown，不影响备份本身）。"""
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        ).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _mysqldump_version(dump_bin: str) -> str:
    """获取 mysqldump 版本号字符串，用于还原时的兼容性判断。"""
    try:
        out = subprocess.run(
            [dump_bin, "--version"], capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        return out.splitlines()[0] if out else "unknown"
    except Exception:
        return "unknown"


def dump_mysql(cfg: dict, target: Path, dry_run: bool = False) -> None:
    """导出 MySQL 全库并 gzip 压缩。

    Args:
        cfg: 数据库连接参数。
        target: 输出的 .sql.gz 路径。
        dry_run: True 时只打印将执行的命令，不落盘。
    """
    dump_bin = _locate_tool("mysqldump")
    defaults = _write_defaults_file(cfg)
    try:
        cmd = [
            dump_bin, f"--defaults-extra-file={defaults}",
            "--single-transaction", "--routines", "--triggers", "--events",
            "--default-character-set=utf8mb4", "--set-gtid-purged=OFF",
            cfg["database"],
        ]
        if dry_run:
            print(f"[dry-run] {' '.join(cmd)} > {target}")
            return
        print(f"导出 MySQL 库 {cfg['database']} ...")
        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode != 0:
            sys.exit(f"❌ mysqldump 失败: {proc.stderr.decode('utf-8', 'replace')}")
        with gzip.open(target, "wb") as gz:
            gz.write(proc.stdout)
    finally:
        os.unlink(defaults)


def archive_dataface(target: Path, dry_run: bool = False) -> None:
    """打包 instance/ 数据面（chroma 向量库、FTS5 sqlite、缓存 db 等）。

    Args:
        target: 输出的 .tar.gz 路径。
        dry_run: True 时只统计不打包。
    """
    if not INSTANCE_DIR.exists():
        print("⚠️  instance/ 不存在，跳过数据面打包")
        return

    def _filter(info: tarfile.TarInfo):
        """排除 __pycache__，减小体积并避免打包无关字节码。"""
        if "__pycache__" in info.name:
            return None
        return info

    if dry_run:
        n = sum(1 for p in INSTANCE_DIR.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
        print(f"[dry-run] 将打包 instance/ 下 {n} 个文件 -> {target}")
        return
    print("打包 instance/ 数据面 ...")
    with tarfile.open(target, "w:gz") as tar:
        tar.add(INSTANCE_DIR, arcname="instance", filter=_filter)


def _sha256(path: Path) -> str:
    """计算文件 sha256（分块读取，避免大文件占内存）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(stamp: str, files: dict) -> dict:
    """构造备份校验清单。

    Args:
        stamp: 备份时间戳（YYYYmmdd-HHMMSS）。
        files: {相对文件名: 绝对路径}。

    Returns:
        dict: 可直接 json.dump 的清单结构。
    """
    entries = {}
    for name, path in files.items():
        if path.exists():
            entries[name] = {
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
    if not entries:
        sys.exit("❌ 备份产物为空，未生成 manifest（视为失败）")
    return {
        "stamp": stamp,
        "created_at": datetime.now().astimezone().isoformat(),
        "git_commit": _git_commit(),
        "mysqldump_version": _mysqldump_version(_locate_tool("mysqldump")),
        "database": os.getenv("MYSQL_DATABASE", "ip_management"),
        "files": entries,
    }


def prune(output_dir: Path, dry_run: bool = False) -> None:
    """按日/周/月三级策略清理过期备份。

    规则：保留最近 7 个每日备份、再保留 4 个"该周最后一个"、再保留 3 个
    "该月最后一个"。落选者删除。

    Args:
        output_dir: 备份根目录。
        dry_run: True 时只打印将被删除的目录。
    """
    backups = sorted(
        (d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith("ipip-backup-")),
        key=lambda d: d.name,
    )
    if not backups:
        return

    keep = set()
    daily = backups[-KEEP_DAILY:]
    keep.update(d.name for d in daily)

    rest = backups[:-KEEP_DAILY] if len(backups) > KEEP_DAILY else []
    by_week, by_month = {}, {}
    for d in rest:
        try:
            dt = datetime.strptime(d.name, "ipip-backup-%Y%m%d-%H%M%S")
        except ValueError:
            continue
        by_week[dt.isocalendar()[:2]] = d.name
        by_month[(dt.year, dt.month)] = d.name
    keep.update(list(by_week.values())[-KEEP_WEEKLY:])
    keep.update(list(by_month.values())[-KEEP_MONTHLY:])

    for d in backups:
        if d.name not in keep:
            print(f"{'[dry-run] 将删除' if dry_run else '删除过期备份'}: {d.name}")
            if not dry_run:
                shutil.rmtree(d)


def main() -> None:
    """命令行入口：解析参数并执行备份（可选 prune）。"""
    parser = argparse.ArgumentParser(description="IPIP 系统级备份")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR),
                        help=f"备份根目录（默认 {DEFAULT_OUTPUT_DIR}）")
    parser.add_argument("--prune", action="store_true", help="备份后按策略清理过期备份")
    parser.add_argument("--dry-run", action="store_true", help="只打印将执行的操作")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = output_dir / f"ipip-backup-{stamp}"

    cfg = load_db_env()
    mysql_file = dest / "mysql.sql.gz"
    dataface_file = dest / "dataface.tar.gz"

    if not args.dry_run:
        dest.mkdir(parents=True, exist_ok=True)
        os.chmod(dest, 0o700)

    dump_mysql(cfg, mysql_file, args.dry_run)
    archive_dataface(dataface_file, args.dry_run)

    if args.dry_run:
        print(f"[dry-run] 将生成清单 -> {dest}/manifest.json")
    else:
        manifest = build_manifest(stamp, {
            "mysql.sql.gz": mysql_file,
            "dataface.tar.gz": dataface_file,
        })
        manifest_path = dest / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        os.chmod(manifest_path, 0o600)
        os.chmod(mysql_file, 0o600)
        if dataface_file.exists():
            os.chmod(dataface_file, 0o600)
        print(f"✅ 备份完成：{dest}")
        print(f"   产物：{', '.join(manifest['files'])}")

    if args.prune:
        prune(output_dir, args.dry_run)


if __name__ == "__main__":
    main()
