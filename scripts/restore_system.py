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
        SystemExit: manifest 缺失、清单为空、产物缺失或 sha256 不匹配。
    """
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        sys.exit(f"❌ 未找到 {manifest_path}，该备份可能不完整")

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    files = manifest.get("files") or {}
    if not files:
        sys.exit(f"❌ {manifest_path} 未登记任何产物，无法确认备份完整性")

    for name, meta in files.items():
        expected = (meta or {}).get("sha256")
        if not expected:
            sys.exit(f"❌ {name} 在 manifest 中缺少 sha256，无法校验")
        path = backup_dir / name
        if not path.exists():
            sys.exit(f"❌ 备份缺失产物: {name}")
        actual = _sha256(path)
        if actual != expected:
            sys.exit(f"❌ 校验失败 {name}: 期望 {expected} 实际 {actual}")
        print(f"✔ 校验通过 {name} ({path.stat().st_size} bytes)")
    return manifest


def needs_confirm(*, skip_mysql: bool, skip_dataface: bool,
                  assume_yes: bool, dry_run: bool) -> bool:
    """本次运行是否需要交互确认。

    ⚠️ 判据是「本次会不会改动现场」，而不是「会不会还原数据库」：`--skip-mysql`
    只是跳过数据库，数据面（instance/：向量库、缓存 db）仍会被原地覆盖，
    因此不能拿它当免确认开关。
    """
    return not (dry_run or assume_yes or (skip_mysql and skip_dataface))


def confirm(database: str, backup_dir: Path, mysql: bool = True,
            dataface: bool = True) -> None:
    """按实际影响面打印破坏性操作提示，并要求交互确认。

    ⚠️ 确认必须与「本次是否真的会改动现场」对齐：此前用 `--skip-mysql` 顺带跳过
    了确认，但数据面还原依然会原地覆盖 instance/（Chroma 向量库、FTS5 sqlite、
    pickle）—— 等于留了一条「不加确认就能破坏数据」的命令行。

    Args:
        database: 将被覆盖的目标库名。
        backup_dir: 备份来源。
        mysql: 本次是否会还原数据库。
        dataface: 本次是否会还原数据面。

    Raises:
        SystemExit: 用户未输入 yes。
    """
    print("=" * 60)
    print("⚠️  即将执行恢复操作，这会覆盖现场数据")
    print(f"    来源备份: {backup_dir}")
    if mysql:
        print(f"    影响数据库: {database}（同名表将被 DROP 后重建）")
    if dataface:
        print(f"    影响数据面: {INSTANCE_DIR}（向量库/缓存 db 原地覆盖）")
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
    pwd = cfg["password"]
    if "\n" in pwd or "\r" in pwd:
        os.unlink(defaults)
        sys.exit("❌ 数据库密码含换行符，无法安全写入临时凭据文件，请检查 .env")
    esc_pwd = pwd.replace("\\", "\\\\").replace('"', '\\"')
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
        with tempfile.TemporaryFile() as err_file:
            proc = subprocess.Popen(
                [mysql_bin, f"--defaults-extra-file={defaults}", database],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err_file,
            )
            try:
                with gzip.open(sql_gz, "rb") as gz:
                    shutil.copyfileobj(gz, proc.stdin, length=1024 * 1024)
            except BrokenPipeError:
                pass
            finally:
                try:
                    proc.stdin.close()
                except BrokenPipeError:
                    pass
            proc.wait()
            err_file.seek(0)
            stderr_out = err_file.read()
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

    if needs_confirm(skip_mysql=args.skip_mysql, skip_dataface=args.skip_dataface,
                     assume_yes=args.yes, dry_run=args.dry_run):
        confirm(database, backup_dir, mysql=not args.skip_mysql,
                dataface=not args.skip_dataface)

    if not args.skip_mysql:
        restore_mysql(backup_dir, cfg, database, args.dry_run)
    if not args.skip_dataface:
        restore_dataface(backup_dir, args.dry_run)

    print(f"✅ 恢复完成（来源 commit={manifest.get('git_commit')} "
          f"备份时间={manifest.get('created_at')}）")
    print("   建议：启动应用后抽查 3 张业务表，并核对 instance/chroma 体积是否一致")


if __name__ == "__main__":
    main()
