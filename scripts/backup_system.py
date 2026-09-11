#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""IPIP 系统级备份（MySQL 全库 + instance/ 非 DB 数据面）。

用法:
    python scripts/backup_system.py [--output-dir DIR] [--prune] [--dry-run]
                                    [--include-secrets]

产物结构（每次备份一个自包含目录）：
    <output-dir>/ipip-backup-YYYYmmdd-HHMMSS/
        mysql.sql.gz      # mysqldump 全量
        dataface.tar.gz   # instance/ 数据面（chroma 向量库 / FTS5 sqlite / pickle）
        redis.rdb         # Redis 快照：ai:config（界面 AI 配置）的唯一持久层
        secrets.env.gpg   # 可选：--include-secrets 导出的 GPG 对称加密密钥
        manifest.json     # 校验清单：commit、mysqldump 版本、各产物 sha256/size

设计约束（勿破坏，详见 WBS T1）：
- **不依赖 Flask app 上下文**：备份是"应用坏了时要用"的工具，不能因 ORM/插件
  初始化失败而失效，故只用 subprocess + os.environ；
- **不复用 app.config["SQLALCHEMY_DATABASE_URI"]**：该值是 @property，
  经 from_object 拷入的是描述符对象而非字符串（见 config.py:459-472）；
  此处直接读 MYSQL_* 裸环境变量；
- **密码经临时 defaults-extra-file 传入**（权限 0600），避免出现在进程命令行
  被 ps 看到；
- 产物**不含 .env**（内含生产库密码），且权限 0600；
- **密钥导出必须是显式选项**（`--include-secrets`）：产物有意不含 .env 以避免
  密钥随备份扩散，故只有运维明确点名时才额外导出 GPG 加密的密钥，且不留明文。
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
from urllib.parse import unquote, urlparse

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
    pwd = cfg["password"]
    if "\n" in pwd or "\r" in pwd:
        os.unlink(path)
        sys.exit("❌ 数据库密码含换行符，无法安全写入临时凭据文件，请检查 .env")
    esc_pwd = pwd.replace("\\", "\\\\").replace('"', '\\"')
    with open(path, "w", encoding="utf-8") as f:
        f.write("[client]\n")
        f.write(f"host={cfg['host']}\n")
        f.write(f"port={cfg['port']}\n")
        f.write(f"user={cfg['user']}\n")
        f.write(f'password="{esc_pwd}"\n')
    return path


_TOOL_PACKAGE_HINTS = {
    "mysql": "MySQL 客户端工具",
    "mysqldump": "MySQL 客户端工具",
    "redis-cli": "Redis 客户端工具（如 redis-tools）",
    "gpg": "GnuPG 加密工具（如 gnupg / gpg）",
}


def _locate_tool(name: str) -> str:
    """定位 mysqldump / mysql / redis-cli / gpg 二进制路径。

    Args:
        name: 工具名。

    Returns:
        str: 可执行文件路径。

    Raises:
        SystemExit: 未找到该命令。
    """
    found = shutil.which(name)
    if not found:
        hint = _TOOL_PACKAGE_HINTS.get(name, "对应的客户端工具")
        sys.exit(f"❌ 未找到 {name} 命令，请先安装{hint}")
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
            print(f"[dry-run] {' '.join(cmd)} | gzip > {target}")
            return
        print(f"导出 MySQL 库 {cfg['database']} ...")
        with gzip.open(target, "wb") as gz:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                shutil.copyfileobj(proc.stdout, gz, length=1024 * 1024)
            finally:
                proc.stdout.close()
            stderr_out = proc.stderr.read()
            proc.stderr.close()
            proc.wait()
        if proc.returncode != 0:
            target.unlink(missing_ok=True)
            sys.exit(f"❌ mysqldump 失败: {stderr_out.decode('utf-8', 'replace')}")
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


SECRET_KEYS = ("SECRET_KEY", "JWT_SECRET_KEY", "SWITCH_SECRET_KEY",
               "MYSQL_PASSWORD", "REDIS_PASSWORD")

GPG_TIMEOUT_S = 300


def export_secrets(target: Path, passphrase: str | None,
                   dry_run: bool = False) -> None:
    """把恢复所必需的密钥/口令导出为 GPG 对称加密文件。

    为什么单独导出：`SWITCH_SECRET_KEY` 只存在于环境变量，整机损毁后即使库能恢复，
    `switch_credentials` 密文也永久不可解。备份产物本身不含 .env（避免密钥随备份
    扩散），所以这里提供一个**显式、加密、可离线保管**的口子。

    明文写完立刻覆盖删除：无论成功失败都不留中间态。

    Args:
        target: 输出路径（如 <dest>/secrets.env.gpg）。
        passphrase: GPG 对称加密口令；为空时拒绝导出（空口令等于没加密）。
        dry_run: True 时只打印将执行的操作。

    Raises:
        RuntimeError: 口令缺失、.env 中无可导出密钥、gpg 执行失败或超时。
    """
    if dry_run:
        print(f"[dry-run] 将导出加密密钥 -> {target}")
        return
    if not passphrase:
        raise RuntimeError("密钥导出需要 GPG_PASSPHRASE 环境变量（不支持空口令）")
    gpg = _locate_tool("gpg")
    plain = target.with_suffix("")          # secrets.env（临时明文）
    try:
        lines = []
        exported_keys = []
        env_file = ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue                        # 注释行绝不算"已设置"
                key_part, sep, value = stripped.partition("=")
                if not sep:
                    continue
                tokens = key_part.split()          # `export   KEY` → ["export","KEY"]
                if not tokens:
                    continue
                key = tokens[-1]
                if key in SECRET_KEYS:
                    lines.append(f"{key}={value.strip()}")
                    exported_keys.append(key)
        if not lines:
            raise RuntimeError(
                f"未在 {env_file} 中找到任何待导出密钥：{'、'.join(SECRET_KEYS)}")
        with open(plain, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        os.chmod(plain, 0o600)
        argv = [gpg, "--batch", "--yes", "--symmetric", "--cipher-algo", "AES256",
                "--pinentry-mode", "loopback",
                "--passphrase-fd", "0", "-o", str(target), str(plain)]
        try:
            proc = subprocess.run(argv, input=passphrase, capture_output=True,
                                  text=True, timeout=GPG_TIMEOUT_S)
        except subprocess.TimeoutExpired as exc:
            target.unlink(missing_ok=True)
            raise RuntimeError(f"密钥导出超时（{GPG_TIMEOUT_S}s）") from exc
        if proc.returncode != 0:
            target.unlink(missing_ok=True)
            raise RuntimeError(f"密钥导出失败：{proc.stderr.strip()}")
        os.chmod(target, 0o600)
        print(f"已导出密钥项: {', '.join(k for k in SECRET_KEYS if k in exported_keys)}")
    finally:
        plain.unlink(missing_ok=True)       # 无论成败都不留明文


REDIS_RDB_TIMEOUT_S = 300


def _redis_target(env: dict) -> tuple[str, str, str]:
    """解析 Redis 连接目标，返回 (host, port, password)。

    优先级与 `Config.REDIS_URL`（config.py）及网关 `_build_redis_url()` 一致：
    **显式 REDIS_URL 优先**，未设时才由 REDIS_HOST / REDIS_PORT / REDIS_PASSWORD
    组装（该优先级由 tests/test_config_redis_url.py 钉住）。

    ⚠️ 必须支持 REDIS_URL：只设它的部署若回退到 REDIS_HOST，备份会去连默认
    localhost —— 连不上尚能告警，但本机若恰有另一个 Redis 实例，就会**静默
    备错对象**。

    ⚠️ URL 里的 db 号被**有意忽略**：`--rdb` 导出的是整个实例（含全部 db），
    不要"顺手"把 REDIS_DB / URL 的 path 加进 argv。

    Args:
        env: 环境变量映射（通常是 os.environ 的副本）。

    Returns:
        tuple: (host, port, password)；password 可能为空串。
    """
    url = env.get("REDIS_URL") or ""
    parsed = urlparse(url) if url else None
    if parsed is not None and parsed.hostname:
        return (parsed.hostname, str(parsed.port or 6379),
                unquote(parsed.password or ""))
    return (env.get("REDIS_HOST") or "localhost",
            str(env.get("REDIS_PORT") or "6379"),
            env.get("REDIS_PASSWORD") or "")


def dump_redis(target: Path, dry_run: bool = False) -> None:
    """导出 Redis RDB 快照。

    为什么必须备：`ai:config`（config_admin_service.py）保存界面上的 AI 配置，
    含 AES 加密的 api_key_enc，是这些配置的**唯一持久层**（不落 MySQL、不落 .env）。
    不备 Redis，恢复后用户改过的 AI 配置全部丢失。

    用 `--rdb <file>` 直接取快照：由服务器端 fork 落盘，不依赖客户端内存，
    比先 BGSAVE 再 scp dump 文件更简单，也不会与 server 的 dump 路径耦合。

    连接目标见 `_redis_target()`：REDIS_URL 优先，其次拆分字段。

    Args:
        target: 输出的 .rdb 路径。
        dry_run: True 时只打印将执行的命令。

    Raises:
        RuntimeError: redis-cli 缺失、导出失败或超时。是否为致命错误由调用方决定
            （Redis 只是本工具的一个可选数据面，见 main()）。
    """
    if dry_run:
        print(f"[dry-run] 将导出 Redis RDB -> {target}")
        return
    try:
        redis_cli = _locate_tool("redis-cli")
    except SystemExit as exc:
        raise RuntimeError(
            "未找到 redis-cli 命令，无法导出 Redis RDB（本次产物不含 redis.rdb）"
        ) from exc

    env = os.environ.copy()
    host, port, pwd = _redis_target(env)
    if pwd:
        env["REDISCLI_AUTH"] = pwd          # 走环境变量，避免出现在 ps 命令行
    else:
        env.pop("REDISCLI_AUTH", None)
    argv = [redis_cli, "-h", host, "-p", port, "--rdb", str(target)]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, env=env,
                              timeout=REDIS_RDB_TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"Redis RDB 导出超时（{REDIS_RDB_TIMEOUT_S}s）") from exc
    if proc.returncode != 0 or not target.exists():
        target.unlink(missing_ok=True)
        raise RuntimeError(f"Redis RDB 导出失败：{proc.stderr.strip()}")
    os.chmod(target, 0o600)


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
    candidates = [
        d for d in output_dir.iterdir()
        if d.is_dir() and d.name.startswith("ipip-backup-")
    ]
    backups = sorted((d for d in candidates if (d / "manifest.json").is_file()),
                     key=lambda d: d.name)
    skipped = sorted(d.name for d in candidates if not (d / "manifest.json").is_file())
    if skipped:
        print(f"⚠️  跳过 {len(skipped)} 个目录（无 manifest.json，非本工具产物，不删）: "
              f"{'、'.join(skipped)}")
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
    parser.add_argument("--include-secrets", action="store_true",
                        help="额外导出 GPG 加密的密钥文件（需 GPG_PASSPHRASE 环境变量）")
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

    redis_file = dest / "redis.rdb"
    try:
        dump_redis(redis_file, args.dry_run)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  Redis 备份失败（AI 配置将不在本次产物中）：{exc}")

    secrets_file = dest / "secrets.env.gpg"
    if args.include_secrets:
        try:
            export_secrets(secrets_file, os.environ.get("GPG_PASSPHRASE"),
                           args.dry_run)
        except RuntimeError as exc:
            sys.exit(f"❌ {exc}")

    if args.dry_run:
        print(f"[dry-run] 将生成清单 -> {dest}/manifest.json")
    else:
        files = {
            "mysql.sql.gz": mysql_file,
            "dataface.tar.gz": dataface_file,
        }
        if redis_file.exists():
            files["redis.rdb"] = redis_file
        if secrets_file.exists():
            files["secrets.env.gpg"] = secrets_file
        manifest = build_manifest(stamp, files)
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
