"""数据库初始化与迁移。

这里是全流程最危险的一段，历史最大事故就发生在这里。


> 2026-10-01 测试机实测：脚本只在「库已初始化」分支调用 ``flask db-upgrade``，
> 全新安装路径漏掉 → 每次全新安装的库都停在 0001：
> 缺 ``circuit_segments`` 表、缺 ``ip_switch_info.source`` /
> ``monitor_incident.root_device_name`` 等列与索引，monitor 起服即刷
> 「缺列/缺表」告警，且 0008 的明文口令加密回填被整段跳过。

**两条路径都必须调用 ``apply_pending_migrations()``** —— 这个约束由一个函数
统一保证，而不是靠两条分支各自记得写。这也是把逻辑写成 Python 的直接收益：
当年在 bash 里，这件事靠的是"两个分支的代码看起来都差不多"。


迁baseline 含 **15 个触发器/函数**，MySQL 8 默认开 binlog，该状态下导入会
ERROR 1419。这里做 ``SET GLOBAL`` 兜底，但**必须明确告知它重启后会失效**。


无 mysql 客户端时必须走 PyMySQL 路径，而 naive ``sql.split(';')`` 会切碎触发器。
``scripts/import_sql.py`` 是 DELIMITER 感知的专用切分器，不可用别的替代。


Ubuntu/Debian 用 apt 装的 MySQL 会把 ``root@localhost`` 建成 **auth_socket** 插件：
``mysql`` CLI 走 unix socket 能进（且无需密码），但应用走 TCP **必然**被拒
``ERROR 1698 (28000) Access denied for user 'root'@'localhost'``。

两条放大危害的细节：

1. **报错形态是"密码错了"，真因却是认证插件**。
   ``preflight`` 拿到的是 PyMySQL 的 OperationalError，肉眼完全指不到 auth_socket。
2. **host 写成 localhost 也没用**。PyMySQL 只有在显式传 ``unix_socket`` 时才走
   socket，“localhost” 一样是 TCP；SQLAlchemy 的 URL 同理。所以这不是配置问题，
   改 host 绕不开。

故必须单独判、并直接修，而不是让运维去猜。


``mysql -u root dbname`` 后面不跟输入重定向时，客户端会从 stdin 读脚本；
读到 EOF（尤其 stdin 是 DEVNULL）便**正常退出并返回 0**。
于是「漏了 ``< baseline.sql``」这行 bug 会 100% 表现成成功：日志写着
「基线导入完成」，库里一张表都没有，真正的报错要延后到 ``flask db-upgrade``
才以 ``Table '...' doesn't exist`` 的形态出现，**完全指不到导入这一步**。

对应守卫生在 :func:`verify_baseline_tables` —— 退出码不看，直接数表。
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from .shell import run, which

__all__ = [
    "DbConfig",
    "from_env",
    "ensure_db_account",
    "preflight_connection",
    "ensure_trust_function_creators",
    "create_database",
    "is_initialized",
    "import_baseline",
    "stamp_covers",
    "apply_pending_migrations",
    "init_database",
]

_PURE_PY_IMPORTER = "scripts/import_sql.py"


class DbConfig:
    """连接参数。

    ⚠️ 兜底库名**必须**与 ``.env.example`` 一致（``ip_management``）。
    旧值 ``ip_manager`` 与模板不符时，会造成"授权/导入按一个库名建了库，
    脚本却连另一个"的静默错台（真机踩过）。
    """

    def __init__(self, host: str, port: int, user: str, password: str,
                 database: str = "ip_management") -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database

    def __repr__(self) -> str:
        return f"DbConfig({self.user}@{self.host}:{self.port}/{self.database})"


def from_env(env: dict[str, str]) -> DbConfig:
    return DbConfig(
        host=env.get("MYSQL_HOST", "localhost"),
        port=int(env.get("MYSQL_PORT", "3306") or 3306),
        user=env.get("MYSQL_USER", "root"),
        password=env.get("MYSQL_PASSWORD", ""),
        database=env.get("MYSQL_DATABASE", "ip_management"),
    )


def ensure_db_account(cfg: DbConfig, venv_py: str,
                      env_path: Path | None = None) -> DbConfig:
    """确保配置里的账号能**通过 TCP** 连上 MySQL（见模块文档事故四）。

    apt 装的 MySQL 默认给 ``root@localhost`` 上 auth_socket —— CLI 走 socket 能进，
    应用走 TCP 必被 ERROR 1698 拒。这里识别该形态并把认证方式换成
    ``caching_sha2_password``（MySQL 8.0/8.4 的默认且 PyMySQL 支持；
    ``mysql_native_password`` 在 8.4 已默认禁用，不能用）。

    :param env_path: 给了就把新密码写回 .env，保证下次跑安装器不再重复此步骤。
    :returns: 可能带新密码的 DbConfig —— **调用方必须用返回值**继续后续步骤。
    """
    first_err: RuntimeError | None = None
    try:
        preflight_connection(cfg, venv_py)
        return cfg
    except RuntimeError as exc:
        first_err = exc

    plugin = _root_auth_plugin()
    if plugin != "auth_socket":
        if first_err is not None:
            raise first_err
        raise RuntimeError("MySQL 连接失败且原因不明（未走到 preflight 异常分支）")

    from ..act.envfile import set_env_value

    print(f"[db] 检测到 MySQL 的 {cfg.user}@{cfg.host} 使用 auth_socket 认证 —— "
          "应用走 TCP 会被 ERROR 1698 拒绝")
    password = cfg.password or secrets.token_urlsafe(24)
    if cfg.password:
        print("[db] 沿用 .env 中已有的 MYSQL_PASSWORD，仅更换认证方式")
    else:
        print("[db] 已为该账号生成随机强密码，并写回 .env")

    escaped = password.replace("\\", "\\\\").replace("'", "''")
    stmt = (f"ALTER USER '{cfg.user}'@'localhost' "
            f"IDENTIFIED WITH caching_sha2_password BY '{escaped}';\n"
            "FLUSH PRIVILEGES;")
    client = which("mysql") or which("mysql8")
    if not client:
        raise RuntimeError(
            "MySQL 的 root 走 auth_socket 且无 mysql 客户端可用，无法就地修复认证方式。\n"
            "  请以能连上的方式手工执行：\n"
            f"    ALTER USER '{cfg.user}'@'localhost' IDENTIFIED WITH "
            "caching_sha2_password BY '<password>';"
        ) from first_err

    res = run([client, "-u", "root"],
              stdin_text=stmt,
              check=False, label="切换 root 认证为 caching_sha2_password", timeout=60)
    if not res.ok:
        raise RuntimeError(
            "切换 root 认证方式失败：\n    " + "\n    ".join(res.lines[-6:])
        )

    new_cfg = DbConfig(cfg.host, cfg.port, cfg.user, password, cfg.database)
    preflight_connection(new_cfg, venv_py)     # 换完必须复验，不能假定成功
    print("[db] root 认证已切换，TCP 连接验证通过")

    if env_path is not None:
        set_env_value(env_path, "MYSQL_PASSWORD", password)
        print(f"[db] 新密码已写回 {env_path}")
    return new_cfg


def _root_auth_plugin() -> str:
    """查 root@localhost 的认证插件。查不到返回空串（表示「不是这个原因」）。"""
    client = which("mysql") or which("mysql8")
    if not client:
        return ""
    res = run([client, "-u", "root", "-N", "-B", "-e",
               "SELECT plugin FROM mysql.user WHERE user='root' AND host='localhost'"],
              check=False, echo=False, timeout=30)
    return res.stdout.strip() if res.ok else ""


def _explain_connect_error(errno: str, msg: str, cfg: "DbConfig") -> str:
    """把连接错误翻译成**可执行的下一步**，而不是"请检查配置"。

    笼统报错的下场在实测里很清楚：ERROR 1045（密码不对）、auth_socket、
    服务没起来全混成一句"请检查 .env 中的 MYSQL_* 配置"，运维只能逐个试。
    """
    head = f"MySQL 连接失败（{cfg.user}@{cfg.host}:{cfg.port}）"
    if errno == "1045":
        return (
            f"{head}：账号已设密码而 .env 不匹配（errno 1045）。\n"
            "  把这行补对一个即可：\n"
            f"    MYSQL_PASSWORD=<{cfg.user} 的真实密码>\n"
            "  忘记密码时由管理员重置：\n"
            f"    ALTER USER '{cfg.user}'@'localhost' IDENTIFIED BY '<password>';\n"
            f"  原始报错: {msg}"
        )
    if errno == "1698":
        return f"{head}：该账号用 auth_socket 认证（errno 1698），应用走 TCP 连不上（事故四）。"
    if errno == "2003":
        return (
            f"{head}：连不上服务（errno 2003）。\n"
            f"    mysqld 是否运行、是否监听 {cfg.host}:{cfg.port}？ systemctl status mysql\n"
            f"  原始报错: {msg}"
        )
    return f"{head}（errno {errno or '未知'}）。\n    {msg}"


def preflight_connection(cfg: DbConfig, venv_py: str) -> None:
    """预检连通性，失败时按 errno 给出针对性诊断。

    刻意把 errno **结构化**地从子进程带回来：traceback 里虽然也含 errno，
    但那样只能靠正则去猜行号位置。
    """
    child_env = dict(os.environ, MYSQL_PASSWORD=cfg.password)
    res = run(
        [venv_py, "-c", (
            "import pymysql, os, sys\n"
            "try:\n"
            f"    c = pymysql.connect(host={cfg.host!r}, port={cfg.port}, user={cfg.user!r},\n"
            "                       init_command=\"SET time_zone='+00:00'\",\n"
            "                       password=os.getenv('MYSQL_PASSWORD',''), charset='utf8mb4')\n"
            "    c.close()\n"
            "    print('    MySQL 连接 OK')\n"
            "except Exception as e:\n"
            "    _a = getattr(e, 'args', ()) or ()\n"
            "    sys.stdout.write('MYSQLCONNERR errno=%s msg=%s\\n' % "
            "(_a[0] if _a else '?', str(e).replace('\\n', ' ')))\n"
            "    sys.exit(1)\n"
        )],
        check=False, env=child_env, label="预检 MySQL 连通性", timeout=60,
    )
    if not res.ok:
        import re

        errno = ""
        msg = "\n    ".join(res.lines[-4:])
        for ln in res.lines:
            m = re.search(r"MYSQLCONNERR errno=(\S+) msg=(.*)", ln)
            if m:
                errno, msg = m.group(1), m.group(2)
                break
        raise RuntimeError(_explain_connect_error(errno, msg, cfg))


def ensure_trust_function_creators(cfg: DbConfig, venv_py: str) -> None:
    """确保 log_bin_trust_function_creators 生效。

    ``SET GLOBAL`` **仅运行时生效** —— MySQL 重启后会回到默认值，届时升级导入
    会再次碰 ERROR 1419。这一点必须在收尾时明确告诉运维。
    持久化的正解是写 ``/etc/mysql/conf.d/*.cnf``（见 deploy/ops/install-ci-mysql.sh）。
    """
    code = (
        "import pymysql, os, sys\n"
        f"c = pymysql.connect(host={cfg.host!r}, port={cfg.port}, user={cfg.user!r},\n"
        "                     init_command=\"SET time_zone='+00:00'\",\n"
        "                     password=os.getenv('MYSQL_PASSWORD',''), charset='utf8mb4',\n"
        "                     autocommit=True)\n"
        "cur = c.cursor()\n"
        "cur.execute('SELECT @@global.log_bin, @@global.log_bin_trust_function_creators')\n"
        "log_bin, tfc = cur.fetchone()\n"
        "if not log_bin or tfc:\n"
        "    print('    log_bin_trust_function_creators 预检通过')\n"
        "    c.close(); sys.exit(0)\n"
        "try:\n"
        "    cur.execute('SET GLOBAL log_bin_trust_function_creators = 1')\n"
        "except Exception as e:\n"
        "    print('无权限 SET GLOBAL: %s' % e); c.close(); sys.exit(1)\n"
        "cur.execute('SELECT @@global.log_bin_trust_function_creators')\n"
        "if not cur.fetchone()[0]:\n"
        "    print('SET GLOBAL 已执行但未生效'); c.close(); sys.exit(1)\n"
        "print('    已自动开启 log_bin_trust_function_creators（运行时生效，重启后失效）')\n"
        "c.close()"
    )
    child_env = dict(os.environ, MYSQL_PASSWORD=cfg.password)
    res = run([venv_py, "-c", code], check=False, env=child_env,
              label="预检 log_bin_trust_function_creators", timeout=60)
    if not res.ok:
        raise RuntimeError(
            "log_bin_trust_function_creators 未开启且当前账号无权修改。\n"
            "  迁移基线含 15 个触发器/函数，MySQL 8 默认开 binlog 时导入会报 ERROR 1419。\n"
            "  请用管理员执行并持久化到 my.cnf [mysqld]（SET GLOBAL 重启后失效）：\n"
            "    SET GLOBAL log_bin_trust_function_creators = 1;\n"
            "    # /etc/mysql/conf.d/ipip.cnf\n"
            "    [mysqld]\n"
            "    log_bin_trust_function_creators = 1"
        )


def create_database(cfg: DbConfig, venv_py: str) -> None:
    code = (
        "import pymysql, os\n"
        f"c = pymysql.connect(host={cfg.host!r}, port={cfg.port}, user={cfg.user!r},\n"
        "                     init_command=\"SET time_zone='+00:00'\",\n"
        "                     password=os.getenv('MYSQL_PASSWORD',''), charset='utf8mb4',\n"
        "                     autocommit=True)\n"
        "cur = c.cursor()\n"
        f"cur.execute('CREATE DATABASE IF NOT EXISTS `%s` DEFAULT CHARACTER SET utf8mb4 "
        "COLLATE utf8mb4_0900_ai_ci' % os.getenv('MYSQL_DATABASE','ip_management'))\n"
        "c.close()\n"
        "print('    数据库就绪')"
    )
    child_env = dict(os.environ, MYSQL_PASSWORD=cfg.password, MYSQL_DATABASE=cfg.database)
    run([venv_py, "-c", code], check=True, env=child_env, label=f"创建数据库 {cfg.database}",
        timeout=120)


def is_initialized(cfg: DbConfig, venv_py: str) -> bool:
    """查 information_schema 判断 schema_migrations 是否存在。

    探测失败按**未初始化**处理（走 baseline 全量），避免升级路径误判 ——
    宁可多导一次，也不要漏跑迁移。
    """
    code = (
        "import pymysql, os, sys\n"
        "try:\n"
        f"    c = pymysql.connect(host={cfg.host!r}, port={cfg.port}, user={cfg.user!r},\n"
        "                        init_command=\"SET time_zone='+00:00'\",\n"
        "                        password=os.getenv('MYSQL_PASSWORD',''), charset='utf8mb4',\n"
        "                        autocommit=True)\n"
        "except Exception as e:\n"
        "    print('连接失败：%s' % e); sys.exit(0)\n"
        "cur = c.cursor()\n"
        "cur.execute('SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema=%s AND table_name=\"schema_migrations\"', (os.getenv('MYSQL_DATABASE'),))\n"
        "sys.exit(0 if cur.fetchone()[0] > 0 else 1)\n"
    )
    child_env = dict(os.environ, MYSQL_PASSWORD=cfg.password, MYSQL_DATABASE=cfg.database)
    res = run([venv_py, "-c", code], check=False, echo=False, env=child_env, timeout=60)
    return res.ok


def import_baseline(cfg: DbConfig, venv_py: str, project_root: Path) -> None:
    schema = project_root / "migrations" / "versions" / "0000_baseline.sql"
    if not schema.is_file():
        raise FileNotFoundError(f"找不到迁移基线: {schema}")

    client = which("mysql") or which("mysql8")
    if client:
        child_env = dict(os.environ, MYSQL_PWD=cfg.password)
        res = run([client, "--init-command=SET time_zone='+00:00'",
                   f"-h{cfg.host}", f"-P{cfg.port}", f"-u{cfg.user}", cfg.database],
                  stdin=schema,
                  env=child_env, check=False, label="导入 0000_baseline.sql", timeout=1800)
        if not res.ok:
            raise RuntimeError(
                "基线导入失败。基线语句无 IF NOT EXISTS —— 若是上次中断留下的"
                "残表（ERROR 1050 already exists），须先清库再重跑：\n"
                f"    mysql -h{cfg.host} -P{cfg.port} -u{cfg.user} -p -e "
                f"'DROP DATABASE `{cfg.database}`; CREATE DATABASE `{cfg.database}` "
                "CHARACTER SET utf8mb4'\n"
                "    末行日志:\n    " + "\n    ".join(res.lines[-10:])
            )
    else:
        importer = project_root / _PURE_PY_IMPORTER
        if not importer.is_file():
            raise FileNotFoundError(
                f"未找到 mysql 客户端，也没有 {importer} —— 无法安全导入触发器。"
            )
        child_env = dict(os.environ, MYSQL_PASSWORD=cfg.password,
                         MYSQL_HOST=cfg.host, MYSQL_PORT=str(cfg.port),
                         MYSQL_USER=cfg.user, MYSQL_DATABASE=cfg.database)
        res = run([venv_py, str(importer), str(schema)], check=False, env=child_env,
                  label="导入 0000_baseline.sql (PyMySQL)", timeout=1800)
        if not res.ok:
            raise RuntimeError(
                "基线导入失败。基线语句无 IF NOT EXISTS —— 若是上次中断留下的"
                "残表（ERROR 1050 already exists），须先清库再重跑：\n"
                f"    mysql -h{cfg.host} -P{cfg.port} -u{cfg.user} -p -e "
                f"'DROP DATABASE `{cfg.database}`; CREATE DATABASE `{cfg.database}` "
                "CHARACTER SET utf8mb4'\n"
                "    末行日志:\n    " + "\n    ".join(res.lines[-10:])
            )
    print("[db] 基线导入完成")
    verify_baseline_tables(schema, cfg, venv_py)


def expected_table_count(schema: Path) -> int:
    """基线 SQL 里声明要建多少张表。

    不从「上次导入后有多少表」这类经验值取，而是**回到 SQL 本身**去数 ——
    基线文件演进时判据自动跟随，不会变成一个写死、迟早过期的魔法数。
    """
    import re

    text = schema.read_text(encoding="utf-8", errors="replace")
    return len(re.findall(r"^\s*CREATE\s+TABLE\s", text, re.MULTILINE | re.IGNORECASE))


def verify_baseline_tables(schema: Path, cfg: DbConfig, venv_py: str) -> None:
    """**退出码 0 不等于导进去了**（事故五）。

    mysql 客户端在没有输入时会从 stdin 读到 EOF 就正常退出并返回 0。
    一次不带文件重定向的调用因此会 100% 静默成功 —— 日志上写着"基线导入完成"，
    库却是空的。后果要延到 ``flask db-upgrade`` 才炸，届时报错是
    ``Table 'ip_management.xxx' doesn't exist``，**完全指不到导入这一步**。

    所以对「导入完到底有多少表」单独做一次实测校核，把事故当场拦住。
    """
    expected = expected_table_count(schema)
    if expected <= 0:
        return
    code = (
        "import pymysql, os\n"
        f"c = pymysql.connect(host={cfg.host!r}, port={cfg.port}, user={cfg.user!r},\n"
        "                     init_command=\"SET time_zone='+00:00'\",\n"
        "                     password=os.getenv('MYSQL_PASSWORD',''), charset='utf8mb4')\n"
        "cur = c.cursor()\n"
        "cur.execute('SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema=%s AND table_type=\"BASE TABLE\"', (os.getenv('MYSQL_DATABASE'),))\n"
        "print(cur.fetchone()[0])\n"
        "c.close()"
    )
    child_env = dict(os.environ, MYSQL_PASSWORD=cfg.password, MYSQL_DATABASE=cfg.database)
    res = run([venv_py, "-c", code], check=False, echo=False, env=child_env, timeout=120)
    if not res.ok:
        raise RuntimeError("基线导入后无法核对表数量：\n    " + "\n    ".join(res.lines[-6:]))

    try:
        actual = int(res.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise RuntimeError(f"核对表数量失败，未能解析出计数：{res.stdout!r}") from None

    if actual < expected:
        raise RuntimeError(
            f"基线导入不完整：SQL 声明 {expected} 张表，实际只有 {actual} 张。\n"
            "  最常见的原因是 mysql 客户端没有真正读到基线文件（缺输入重定向）\n"
            f"  —— 那样它会以退出码 0 静默成功。请检查 {schema} 是否被完整执行。\n"
            f"  手工复核：mysql -u {cfg.user} -p {cfg.database} < {schema}"
        )
    print(f"[db] 基线校核通过：实际 {actual} 张表 / SQL 声明 {expected} 张")


def stamp_covers(cfg: DbConfig, venv_py: str, project_root: Path) -> None:
    """按 covers 清单把「已体现在基线快照里」的版本登记进 schema_migrations。"""
    covers_file = project_root / "migrations" / "versions" / "0000_baseline.covers"
    if not covers_file.is_file():
        print("[db] ⚠ 无 covers 清单，跳过版本登记（后续 db-upgrade 会从链头 applying）")
        return
    covered = [ln.strip() for ln in covers_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not covered:
        return

    code = (
        "import pymysql, os\n"
        f"c = pymysql.connect(host={cfg.host!r}, port={cfg.port}, user={cfg.user!r},\n"
        f"                     password=os.getenv('MYSQL_PASSWORD',''), charset='utf8mb4',\n"
        f"                     database={cfg.database!r}, autocommit=True,\n"
        "                     init_command=\"SET time_zone='+00:00'\")\n"
        "cur = c.cursor()\n"
        "cur.execute('''CREATE TABLE IF NOT EXISTS schema_migrations (\n"
        "  version VARCHAR(64) PRIMARY KEY,\n"
        "  description VARCHAR(255),\n"
        "  applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP\n"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')\n"
        "for v in " + repr(covered) + ":\n"
        "    cur.execute('INSERT IGNORE INTO schema_migrations (version, description) "
        "VALUES (%s, %s)', (v, 'baseline snapshot'))\n"
        "c.close()\n"
        "print('    版本登记完成: ' + ','.join(" + repr(covered) + "))"
    )
    child_env = dict(os.environ, MYSQL_PASSWORD=cfg.password)
    run([venv_py, "-c", code], check=True, env=child_env, label="登记基线覆盖版本", timeout=180)


def apply_pending_migrations(venv_py: str, project_root: Path) -> None:
    """应用尚未记账的迁移。**两条路径都必须调用**，详见模块文档首节事故一。"""
    res = run([venv_py, "-m", "flask", "--app", "wsgi:app", "db-upgrade"],
              cwd=str(project_root), check=False, label="应用数据库迁移 (flask db-upgrade)",
              timeout=1800, quiet_tail=150)
    if not res.ok:
        raise RuntimeError(
            "数据库迁移失败。请手工预检后重试：\n"
            f"    cd {project_root} && {venv_py} -m flask --app wsgi:app db-upgrade --dry-run\n"
            "    并排查 migrations/versions 与当前 schema 的漂移。\n"
            "  " + "\n  ".join(res.lines[-8:])
        )


def init_database(cfg: DbConfig, venv_py: str, project_root: Path,
                  *, env_path: Path | None = None) -> None:
    """完整的第 5 步。"""
    cfg = ensure_db_account(cfg, venv_py, env_path)
    preflight_connection(cfg, venv_py)
    ensure_trust_function_creators(cfg, venv_py)
    create_database(cfg, venv_py)

    if is_initialized(cfg, venv_py):
        print("[db] 库已初始化（schema_migrations 存在），走升级路径")
    else:
        print("[db] 全新库：导入基线快照并登记 covers 版本")
        import_baseline(cfg, venv_py, project_root)
        stamp_covers(cfg, venv_py, project_root)

    apply_pending_migrations(venv_py, project_root)
