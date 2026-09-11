#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""IPIP 系统级恢复（还原 scripts/backup_system.py 产出的备份）。

用法:
    python scripts/restore_system.py --from backups/system/ipip-backup-20260909-120000
    python scripts/restore_system.py --from <DIR> --database test_ip_management  # 恢复到指定库
    python scripts/restore_system.py --from <DIR> --skip-mysql                   # 只还原数据面
    python scripts/restore_system.py --from <DIR> --skip-redis                    # 不回灌 Redis

⚠️ 破坏性操作：
- MySQL 侧会 **覆盖同名库**（mysqldump 产物带 DROP TABLE IF EXISTS）；
- 必须先完成 manifest 校验才动手，校验不通过一律拒绝执行；
- 恢复前自动做一次安全快照（`--snapshot-dir`，默认 /var/backups/ipip-pre-restore）；
  **快照失败即中止恢复**，不留"无回退手段却已覆盖"的现场；
- 失败时保留现场（不自动清理已还原的部分），便于人工判断；
- Redis 侧**不自动回灌**（无安全的热载路径，停服替换会清空实例当前数据），
  本工具只做「识别产物 + 打印命令级手工步骤」，由运维在维护窗口执行，见 restore_redis()。
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

DEFAULT_SNAPSHOT_DIR = Path("/var/backups/ipip-pre-restore")


def _backup_module():
    """加载同级 `backup_system` 模块（复用其连接参数解析，不重复实现一份）。

    ⚠️ 必须同时兼容两种入口，只写其一会让另一种在运行时抛 ModuleNotFoundError：
    - pytest / `python -m scripts.restore_system`：`scripts` 可作为命名空间包导入；
    - 文档推荐的 `python scripts/restore_system.py`：此时 sys.path[0] 是 `scripts/`
      目录，`scripts` 包**不可**导入（实测 `python scripts/restore_system.py`
      会在快照步骤直接 ModuleNotFoundError），只能按顶层模块名导入 backup_system。

    Returns:
        module: 已加载的 backup_system 模块。
    """
    try:
        from scripts import backup_system as bs
    except ModuleNotFoundError as exc:
        if exc.name not in ("scripts", "scripts.backup_system"):
            raise
        import backup_system as bs   # type: ignore[import-not-found]
    return bs


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


def snapshot_before_restore(dest_root: Path) -> Path:
    """恢复前对**当前**库做一次全量安全快照，返回最新快照目录。

    restore 用的 dump 自带 `DROP TABLE IF EXISTS`，一旦恢复错目标库（例如把
    测试备份灌进生产库）就**不可逆**。先备一份，成本几分钟，换来"能回退到恢复前"。

    复用 `scripts/backup_system.py` 的 CLI（subprocess），不重写备份逻辑。

    Args:
        dest_root: 快照落盘目录（与备份产物目录分离）。

    Returns:
        Path: 本次生成的快照目录（最新一份）。

    Raises:
        RuntimeError: 备份命令失败、或未产出任何备份目录。**调用方必须据此中止
            恢复** —— 没有快照就没有回滚保障，不能继续破坏性覆盖。
    """
    bs = _backup_module()   # 延迟导入：避免与备份脚本相互 import，并兼容两种入口

    try:
        dest_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"恢复前快照失败，已中止恢复：无法创建快照目录 {dest_root}（{exc}）") from exc
    argv = [sys.executable, str(Path(bs.__file__)), "--output-dir", str(dest_root)]
    print(f"📦 恢复前安全快照 -> {dest_root}")
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise RuntimeError(f"恢复前快照失败，已中止恢复：{detail}")

    produced = sorted(dest_root.glob("ipip-backup-*"))
    if not produced:
        raise RuntimeError(f"恢复前快照未在 {dest_root} 产出任何备份，已中止恢复")
    latest = produced[-1]
    print(f"   ✅ 快照完成：{latest}")
    return latest


def _reject_snapshot_dir_overlap(backup_dir: Path, snapshot_dir: Path) -> None:
    """快照目录不得落在备份来源目录内（含相等）。

    否则预恢复快照会混进备份产物目录，后续 `restore --from <最新>` 可能把这份
    "安全快照"当成待恢复的定时备份 —— 正是要避免的两类目录混淆。

    Args:
        backup_dir: 本次恢复的来源备份目录。
        snapshot_dir: 预恢复快照落盘目录。

    Raises:
        RuntimeError: 两目录相等，或快照目录是备份来源的父目录。
    """
    src = backup_dir.resolve()
    dest = snapshot_dir.resolve()
    if src == dest or src.is_relative_to(dest):
        raise RuntimeError(
            f"快照目录 {snapshot_dir} 与备份来源 {backup_dir} 重叠，"
            f"会让预恢复快照与备份产物混淆，已中止恢复")


def ensure_pre_restore_snapshot(backup_dir: Path, snapshot_dir: Path,
                                dry_run: bool) -> Path | None:
    """所有破坏性还原步骤（MySQL + 数据面）**共用的前置安全快照**。

    ⚠️ 这是"快照失败 ⇒ 整条破坏性路径都不执行"的**显式结构**，而不是靠
    `main()` 的调用顺序"搭便车"：`restore_dataface()` 同样会原地覆盖
    `instance/`，却完全不经过 MySQL 入口，一旦有人只调它（或调整 main 顺序、
    加 try/except），数据面就会在没有回退快照的情况下被覆盖。

    Args:
        backup_dir: 本次恢复的来源备份目录（用于拒绝与快照目录重叠）。
        snapshot_dir: 快照落盘目录。
        dry_run: True 时只提示、不做真实快照。

    Returns:
        Path | None: 非 dry-run 时返回本次快照目录；dry-run 时返回 None。

    Raises:
        RuntimeError: 快照失败、未产出备份，或快照目录与备份来源重叠。
            调用方必须据此中止全部还原动作。
    """
    if dry_run:
        print(f"[dry-run] 将先对当前库做安全快照 -> {snapshot_dir}，再执行恢复")
        return None
    _reject_snapshot_dir_overlap(backup_dir, snapshot_dir)
    return snapshot_before_restore(snapshot_dir)


def restore_mysql_safely(backup_dir: Path, cfg: dict, database: str, dry_run: bool,
                         snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR) -> None:
    """先安全快照、再恢复 MySQL（MySQL-only 入口，供库/直接调用）。

    ⚠️ `main()` 不走本函数：main 需要让**同一份**前置快照同时覆盖数据面，故用
    `ensure_pre_restore_snapshot()` 作共享前置，再依次调 `restore_mysql()` /
    `restore_dataface()`。本函数保留为"只恢复 MySQL"的独立入口。

    Args:
        backup_dir: 备份来源目录。
        cfg: 数据库连接参数（含 host/user/password）。
        database: 目标库名。
        dry_run: True 时只提示、不做真实快照，也不动现场。
        snapshot_dir: 快照落盘目录。

    Raises:
        RuntimeError: 快照失败或快照目录与备份来源重叠。
    """
    ensure_pre_restore_snapshot(backup_dir, snapshot_dir, dry_run)
    restore_mysql(backup_dir, cfg, database, dry_run)


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


REDIS_AI_CONFIG_PREFIX = "ai:config"


def _redis_rdb_in_backup(manifest: dict) -> bool:
    """备份清单是否登记了 redis.rdb。

    以 manifest 登记为准（load_and_verify_manifest 已校验其存在与 sha256）。
    与**旧备份兼容**：Task 4 之前的产物没有该条目，据此判定为"不含 Redis"。
    """
    return "redis.rdb" in (manifest.get("files") or {})


def recommended_redis_restore_steps(backup_dir: Path, host: str, port: str) -> list[str]:
    """【推荐 · 首选】只回灌 ai:config* 的命令级步骤：临时实例 + DUMP|RESTORE。

    为什么把它排在**前面**：它不动现网其它键（缓存 / Celery / SSE），是"只想
    找回界面 AI 配置"场景下唯一不产生附带破坏的路径。旧实现只打印全量替换方案，
    运维极易照做而误清实例——那正是 Review 的 Important 1。

    认证一律走 REDISCLI_AUTH（`-a` 会把口令暴露在 ps 命令行里）。

    Args:
        backup_dir: 本次恢复的来源备份目录（步骤里用其真实 redis.rdb 路径）。
        host: Redis 主机（复用 backup_system._redis_target() 的解析结果）。
        port: Redis 端口。

    Returns:
        list[str]: 逐行命令级步骤。
    """
    rdb = backup_dir / "redis.rdb"
    return [
        "【推荐 · 首选】只回灌 ai:config，不影响现网其它键（临时实例 + DUMP|RESTORE）:",
        "① 起一个临时 Redis 只加载备份 RDB（不触碰生产实例）:",
        "   WORK=$(mktemp -d /tmp/ipip-redis-restore.XXXX)",
        f"   cp {rdb} \"$WORK/dump.rdb\"",
        "   redis-server --port 6399 --bind 127.0.0.1 --dir \"$WORK\" "
        "--dbfilename dump.rdb --daemonize yes",
        "② 逐个把 ai:config 键迁到生产实例（保留 TTL；认证走 REDISCLI_AUTH）:",
        "   export REDISCLI_AUTH='<密码>'",
        f"   redis-cli -p 6399 --scan --pattern '{REDIS_AI_CONFIG_PREFIX}*' "
        "| while read -r k; do",
        "     ttl=$(redis-cli -p 6399 PTTL \"$k\"); [ \"$ttl\" -lt 0 ] && ttl=0",
        f"     redis-cli -p 6399 --no-raw DUMP \"$k\" "
        f"| redis-cli -h {host} -p {port} -x RESTORE \"$k\" \"$ttl\" REPLACE",
        "   done",
        "③ 校验并清理临时实例:",
        f"   redis-cli -h {host} -p {port} --scan --pattern '{REDIS_AI_CONFIG_PREFIX}*'",
        "   redis-cli -p 6399 SHUTDOWN NOSAVE; unset REDISCLI_AUTH; rm -rf \"$WORK\"",
    ]


def full_replace_redis_restore_steps(
        backup_dir: Path, host: str, port: str) -> list[str]:
    """【备选 · 仅整机损毁，或确认可全量覆盖时使用】停服替换整个 RDB。

    ⚠️ 会丢弃实例当前**全部**数据（缓存/Celery/SSE）—— 只应在整机恢复、或运维
    确认可全量覆盖的场景使用。措辞必须显式标注适用范围，避免被当成默认路径。

    Args:
        backup_dir: 本次恢复的来源备份目录。
        host: Redis 主机。
        port: Redis 端口。

    Returns:
        list[str]: 逐行命令级步骤。
    """
    rdb = backup_dir / "redis.rdb"
    return [
        "【备选 · 仅整机损毁，或确认可全量覆盖时使用】停服替换整个 RDB"
        "（会丢弃实例当前全部数据：缓存/Celery/SSE）:",
        "① 查 Redis 数据目录与文件名:",
        f"   REDISCLI_AUTH='<密码>' redis-cli -h {host} -p {port} CONFIG GET dir dbfilename",
        "② 停 Redis（需 root；服务名以实际部署为准，如 redis / redis-server）:",
        "   sudo systemctl stop redis-server",
        "③ 先留存当前 RDB 以便回退，再用备份 RDB 覆盖（文件名取 ① 的返回值）:",
        "   sudo cp <dir>/<dbfilename> <dir>/<dbfilename>.bak-$(date +%s)",
        f"   sudo install -m 0600 -o redis -g redis {rdb} <dir>/<dbfilename>",
        "④ 启动并核对 AI 配置键已回来（认证同样走 REDISCLI_AUTH）:",
        "   sudo systemctl start redis-server",
        f"   REDISCLI_AUTH='<密码>' redis-cli -h {host} -p {port} "
        f"--scan --pattern '{REDIS_AI_CONFIG_PREFIX}*'",
    ]


def manual_redis_restore_steps(backup_dir: Path, host: str, port: str) -> list[str]:
    """两种回灌方案的合集（**推荐在前、破坏性备选在后**），供打印与手册引用。

    顺序本身就是安全语义：先给不动现网其它键的方案，破坏性全量替换明确降为备选。
    """
    return recommended_redis_restore_steps(backup_dir, host, port) + [
        "",
    ] + full_replace_redis_restore_steps(backup_dir, host, port)


def restore_redis(backup_dir: Path, manifest: dict, dry_run: bool) -> None:
    """Redis 回灌步骤：识别产物 + 打印命令级手工步骤（**不自动改写实例**）。

    为何不自动回灌（本任务明确授权的退出路径）：
    - redis-cli 没有"从任意文件热载"的安全命令：`DEBUG RELOAD` 会先用**当前**
      数据覆写服务器 dump 路径，只能配合停服使用；`DEBUG` 还常被 rename-command
      关闭。因此"在线重载"在本项目并无可用路径。
    - 停服替换 dump.rdb 需要 root 且要重启 Redis：本工具以应用账号运行，无权也
      不该替运维停一个**外部** Redis 服务（deploy/ 下并无 Redis unit）。
    - `--pipe` / `RESTORE` 需先从 RDB **解出键**：等于自研 RDB 解析（引入新依赖）
      或另起临时 Redis —— 两者都超出"不引入任何新依赖"的约束。
    而盲目的全量替换会清空实例当前**全部**数据（本项目 Redis 还承载缓存、Celery
    broker/backend、SSE ring），破坏面远大于收益。故此处只做**失败可发现**的提示，
    把破坏性决策留给运维在维护窗口执行（步骤见 manual_redis_restore_steps）。

    ⚠️ 与 main() 破坏性前置快照的关系：本步骤**不写任何数据**，故无需置于快照之后；
    调用顺序仍放在最后，以免未来若改为写操作时破坏"快照先于破坏性步骤"的结构。

    Args:
        backup_dir: 备份目录。
        manifest: 已校验的备份清单（判定是否含 redis.rdb 的依据）。
        dry_run: True 时只提示、不做任何写操作（本实现本就不写，语义一致）。
    """
    if not _redis_rdb_in_backup(manifest):
        print("⚠️  本次备份不含 Redis（redis.rdb），AI 界面配置（ai:config）不会恢复")
        print("    曾在「系统设置 → AI 配置」改过 api_key 的，恢复后需人工重新填写")
        return

    rdb = backup_dir / "redis.rdb"
    if not rdb.is_file():
        sys.exit(f"❌ 备份清单登记了 redis.rdb，但文件已不存在: {rdb}（备份可能已被改动）")
    size = rdb.stat().st_size

    bs = _backup_module()
    host, port, _pwd = bs._redis_target(os.environ.copy())

    print(f"🔴 备份内含 Redis 快照 redis.rdb（{size} bytes）")
    print("   本工具不会自动回灌 Redis"
          "（无安全的热载路径；停服替换会清空实例当前全部数据）")
    print("   请由运维在维护窗口手工执行，认证一律走 REDISCLI_AUTH（勿用 -a：ps 可见）:")
    for line in manual_redis_restore_steps(backup_dir, host, port):
        print(f"   {line}")
    if dry_run:
        print("[dry-run] 仅提示，未执行任何写操作")


def main() -> None:
    """命令行入口：校验 → 确认 → 还原 MySQL 与数据面。"""
    parser = argparse.ArgumentParser(description="IPIP 系统级恢复")
    parser.add_argument("--from", dest="backup_dir", required=True, help="备份目录路径")
    parser.add_argument("--database", default=None,
                        help="目标库名；缺省取 .env 的 MYSQL_DATABASE")
    parser.add_argument("--yes", action="store_true", help="跳过交互确认（脚本化场景）")
    parser.add_argument("--skip-mysql", action="store_true", help="只还原数据面")
    parser.add_argument("--skip-dataface", action="store_true", help="只还原数据库")
    parser.add_argument("--skip-redis", action="store_true",
                        help="跳过 Redis 回灌步骤（该步骤只提示、不写盘）")
    parser.add_argument("--dry-run", action="store_true", help="只打印将执行的操作")
    parser.add_argument("--snapshot-dir", default=str(DEFAULT_SNAPSHOT_DIR),
                        help=f"恢复前安全快照的落盘目录（默认 {DEFAULT_SNAPSHOT_DIR}）")
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

    if not args.skip_mysql or not args.skip_dataface:
        try:
            ensure_pre_restore_snapshot(backup_dir, Path(args.snapshot_dir), args.dry_run)
        except RuntimeError as exc:
            sys.exit(f"❌ {exc}")

    if not args.skip_mysql:
        restore_mysql(backup_dir, cfg, database, args.dry_run)
    if not args.skip_dataface:
        restore_dataface(backup_dir, args.dry_run)
    if not args.skip_redis:
        restore_redis(backup_dir, manifest, args.dry_run)

    print(f"✅ 恢复完成（来源 commit={manifest.get('git_commit')} "
          f"备份时间={manifest.get('created_at')}）")
    print("   建议：启动应用后抽查 3 张业务表，并核对 instance/chroma 体积是否一致")


if __name__ == "__main__":
    main()
