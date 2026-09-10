#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""IPIP 系统级恢复（还原 scripts/backup_system.py 产出的备份）。

用法:
    python scripts/restore_system.py --from backups/system/ipip-backup-20260909-120000
    python scripts/restore_system.py --from <DIR> --database test_ip_management  # 恢复到指定库
    python scripts/restore_system.py --from <DIR> --skip-mysql                   # 只还原数据面

⚠️ 破坏性操作：
- MySQL 侧会 **覆盖同名库**（mysqldump 产物带 DROP TABLE IF EXISTS）；
- 必须先完成 manifest 校验才动手，校验不通过一律拒绝执行；
- 失败时保留现场（不自动清理已还原的部分），便于人工判断。
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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTANCE_DIR = ROOT / "instance"


def _sha256(path: Path) -> str:
    """计算文件 sha256（分块读取，避免大文件占内存）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_and_verify_manifest(backup_dir: Path) -> dict:
    """读取并校验备份清单中的所有产物。

    Args:
        backup_dir: 备份目录。

    Returns:
        dict: manifest 内容。

    Raises:
        SystemExit: manifest 缺失、产物缺失或 sha256 不匹配。
    """
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        sys.exit(f"❌ 未找到 {manifest_path}，该备份可能不完整")

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    for name, meta in manifest.get("files", {}).items():
        path = backup_dir / name
        if not path.exists():
            sys.exit(f"❌ 备份缺失产物: {name}")
        actual = _sha256(path)
        if actual != meta["sha256"]:
            sys.exit(f"❌ 校验失败 {name}: 期望 {meta['sha256']} 实际 {actual}")
        print(f"✔ 校验通过 {name} ({path.stat().st_size} bytes)")
    return manifest


def confirm(database: str, backup_dir: Path) -> None:
    """打印破坏性操作提示并要求交互确认。

    Args:
        database: 将被覆盖的目标库名。
        backup_dir: 备份来源。

    Raises:
        SystemExit: 用户未输入 yes。
    """
    print("=" * 60)
    print("⚠️  即将执行恢复操作，这会覆盖目标库的现有数据")
    print(f"    来源备份: {backup_dir}")
    print(f"    目标库  : {database}")
    print("=" * 60)
    if input("请输入 yes 继续（其它任意输入取消）: ").strip().lower() != "yes":
        sys.exit("已取消")


def restore_mysql(backup_dir: Path, cfg: dict, database: str, dry_run: bool) -> None:
    """还原 MySQL 全库。

    Args:
        backup_dir: 备份目录。
        cfg: 数据库连接参数（含 host/user/password）。
        database: 目标库名。
        dry_run: True 时只打印命令。
    """
    mysql_bin = shutil.which("mysql")
    if not mysql_bin:
        sys.exit("❌ 未找到 mysql 命令，请先安装 MySQL 客户端工具")

    sql_gz = backup_dir / "mysql.sql.gz"
    if not sql_gz.exists():
        print("⚠️  无可用的 mysql.sql.gz，跳过数据库还原")
        return

    fd, defaults = tempfile.mkstemp(prefix="ipip-restore-", suffix=".cnf")
    os.close(fd)
    os.chmod(defaults, 0o600)
    esc_pwd = cfg["password"].replace("\\", "\\\\").replace('"', '\\"')
    with open(defaults, "w", encoding="utf-8") as f:
        f.write("[client]\n")
        f.write(f"host={cfg['host']}\n")
        f.write(f"port={cfg['port']}\n")
        f.write(f"user={cfg['user']}\n")
        f.write(f'password="{esc_pwd}"\n')

    if dry_run:
        print(f"[dry-run] gunzip -c {sql_gz} | mysql ... {database}")
        os.unlink(defaults)
        return

    try:
        print(f"还原 MySQL 到库 {database} ...")
        proc = subprocess.Popen(
            [mysql_bin, f"--defaults-extra-file={defaults}", database],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        with gzip.open(sql_gz, "rb") as gz:
            shutil.copyfileobj(gz, proc.stdin)
        proc.stdin.close()
        stderr_out = proc.stderr.read()
        proc.wait()
        if proc.returncode != 0:
            sys.exit(f"❌ 数据库还原失败: {stderr_out.decode('utf-8', 'replace')}\n"
                     f"   现场已保留，请勿重复执行以免半途状态")
    finally:
        os.unlink(defaults)


def _safe_extract(tar_path: Path, dest: Path, dry_run: bool) -> None:
    """安全解包 tar.gz，防御路径穿越攻击。

    逐成员校验后再提取：拒绝绝对路径、".." 上级引用与符号链接逃逸。
    优先使用 Python 3.12+ 的 filter="data"，老 version 退回手工校验。

    Args:
        tar_path: 归档文件。
        dest: 解包目标根目录。
        dry_run: True 时只打印成员数量。

    Raises:
        SystemExit: 发现非法成员。
    """
    with tarfile.open(tar_path, "r:gz") as tar:
        members = []
        for member in tar.getmembers():
            target = (dest / member.name).resolve()
            if not member.name.startswith("instance/") and member.name != "instance":
                sys.exit(f"❌ 拒绝解包：归档含非 instance/ 路径成员 {member.name}")
            if target != dest.resolve() and dest.resolve() not in target.parents:
                sys.exit(f"❌ 拒绝解包：检测到路径穿越成员 {member.name}")
            if member.issym() or member.islnk():
                sys.exit(f"❌ 拒绝解包：包含链接成员 {member.name}")
            members.append(member)
        if dry_run:
            print(f"[dry-run] 将解包 {len(members)} 个成员 -> {dest}")
            return
        try:
            tar.extractall(dest, members=members, filter="data")
        except TypeError:
            tar.extractall(dest, members=members)


def restore_dataface(backup_dir: Path, dry_run: bool) -> None:
    """还原 instance/ 数据面（覆盖同名文件）。

    Args:
        backup_dir: 备份目录。
        dry_run: True 时只打印计划。
    """
    tar_path = backup_dir / "dataface.tar.gz"
    if not tar_path.exists():
        print("⚠️  无可用的 dataface.tar.gz，跳过数据面还原")
        return
    print("还原 instance/ 数据面 ...")
    _safe_extract(tar_path, ROOT, dry_run)


def main() -> None:
    """命令行入口：校验 → 确认 → 还原 MySQL 与数据面。"""
    parser = argparse.ArgumentParser(description="IPIP 系统级恢复")
    parser.add_argument("--from", dest="backup_dir", required=True, help="备份目录路径")
    parser.add_argument("--database", default=None,
                        help="目标库名；缺省取 .env 的 MYSQL_DATABASE")
    parser.add_argument("--yes", action="store_true", help="跳过交互确认（脚本化场景）")
    parser.add_argument("--skip-mysql", action="store_true", help="只还原数据面")
    parser.add_argument("--skip-dataface", action="store_true", help="只还原数据库")
    parser.add_argument("--dry-run", action="store_true", help="只打印将执行的操作")
    args = parser.parse_args()

    backup_dir = Path(args.backup_dir)
    if not backup_dir.is_dir():
        sys.exit(f"❌ 备份目录不存在: {backup_dir}")

    manifest = load_and_verify_manifest(backup_dir)

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    cfg = {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", 3306)),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
    }
    database = args.database or os.getenv("MYSQL_DATABASE", "ip_management")

    if not args.dry_run and not args.yes and not args.skip_mysql:
        confirm(database, backup_dir)

    if not args.skip_mysql:
        restore_mysql(backup_dir, cfg, database, args.dry_run)
    if not args.skip_dataface:
        restore_dataface(backup_dir, args.dry_run)

    print(f"✅ 恢复完成（来源 commit={manifest.get('git_commit')} "
          f"备份时间={manifest.get('created_at')}）")
    print("   建议：启动应用后抽查 3 张业务表，并核对 instance/chroma 体积是否一致")


if __name__ == "__main__":
    main()
