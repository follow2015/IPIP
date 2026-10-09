"""编排主干 —— 把判据层和动作层串成一次安装。

编排的价值不在"顺序调用"，在于三件 bash 时代很难做对的事：

1. **并行边界明确**
   pip install ‖ 前端构建（分别写 ``.venv/`` 与 ``frontend-new/dist/``，无共享状态）；
   **RAG 模型下载 ‖ 依赖安装 ‖ 前端构建（三者零共享状态，模型下载是纯网络 IO，
   与 venv 是否就绪无关，因此从第一步就起跑 —— 这一笔把安装总时长从 609s
   压到 ~410s）**；DB 初始化只在模型那一路失败时才并行做兜底重试。

2. **并行任务的失败不会被静默吞掉**
   旧脚本这里踩过：``wait "$pid"`` 在 ``set -e`` 下，子进程失败会静默杀掉整个脚本，
   日志停在一行毫无线索处。Python 里子线程的异常会被收集，最后统一判定。

3. **每一步计时**
   为了回答"安装到底慢在哪"，而不是笼统地说"安装很慢"。
"""

from __future__ import annotations

import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .act import (
    db, envfile, frontend, production_check, shell, syspkg, units,
    venv as venv_mod,
)
from .judge.facts import HostFacts, check_baselines, collect

__all__ = ["Options", "RunReport", "install", "sync_source"]

PROJECT_ROOT = Path("/opt/ipip")

SYNC_EXCLUDES: tuple[str, ...] = (
    ".venv/", ".git/", ".env", "instance/", "logs/", "__pycache__/",
    "node_modules/", ".credentials",
    "frontend-new/dist/",
)


@dataclass
class Options:
    """CLI 选项。默认值与旧 install.sh 保持一致，保证运维肌肉记忆有效。"""

    source_root: Path
    skip_syspkg: bool = False
    skip_frontend: bool = False
    skip_db: bool = False
    skip_seed: bool = False
    skip_models: bool = False
    mysql_upgrade: str = "ask"
    force_unsupported: bool = False
    torch_flavor: str = "cpu"        # cpu | gpu（显式指定才生效）
    cuda_multi_mirror: str = "0"
    torch_explicit: bool = False
    force_torch_upstream: bool = False
    with_units: bool = False
    units_user: str = ""
    units_group: str = ""
    units_script: str = ""
    dev_env: bool = False
    upgrade: bool = False
    metrics_allowed_ips: str = "127.0.0.1/32"
    cors_origins: str = ""


@dataclass
class RunReport:
    """一次安装的产出，用于最后的凭据汇总。"""

    timings: dict[str, float] = field(default_factory=dict)
    admin_password: str = ""
    notes: list[str] = field(default_factory=list)
    failed: str = ""

    def total(self) -> float:
        """真实总耗时 = 各分项之和。

        ⚠️ 不能写成 ``sum(self.timings.values())``：``timings`` 里也放着
        ``总计`` 这一项，那样会把「总计」自己再加一遍。
        分项几乎铺满全程时结果会**接近真实耗时的两倍**（实测 677s 被报成 1354s），
        而安装报告里这个数字是唯一会被人记住的指标，错了比没有更糟。
        """
        return sum(v for k, v in self.timings.items() if k != "总计")


def sync_source(opts: Options) -> None:
    """把代码副本同步到固定的安装目录。"""
    src = opts.source_root
    if src.resolve() == PROJECT_ROOT.resolve():
        print(f"[sync] 副本已位于 {PROJECT_ROOT}，跳过同步")
        return
    PROJECT_ROOT.mkdir(parents=True, exist_ok=True)

    if shell.which("rsync"):
        args = ["rsync", "-a", "--delete"]
        for ex in SYNC_EXCLUDES:
            args += ["--exclude", ex]
        args += [f"{src}/", f"{PROJECT_ROOT}/"]
        shell.run(args, check=True, label="同步代码副本")
    else:
        from shlex import quote as _q

        tar_ex = ["--exclude=./" + e.rstrip("/") for e in SYNC_EXCLUDES]
        shell.run(["bash", "-c",
                   f"tar -C {_q(str(src))} {' '.join(tar_ex)} -cf - . "
                   f"| tar -C {_q(str(PROJECT_ROOT))} -xf -"],
                  check=True, label="同步代码副本 (tar 回退)")
    print(f"[sync] 项目根目录: {PROJECT_ROOT}")


def _step1_host_baseline(opts: Options) -> HostFacts:
    print("\n=== [1/7] 系统事实与版本基线 ===")
    facts = collect()
    print(f"  发行版 {facts.distro} {facts.distro_version} ({facts.arch})  包管理器={facts.pkg_manager}")
    print(f"  Python {facts.python_display}  node {facts.node_version or '-'}  "
          f"pnpm {facts.pnpm_version or '-'}")
    print(f"  mysql {facts.mysql_version or '-'}  redis {facts.redis_version or '-'}  "
          f"g++={facts.has_gpp}  root={facts.is_root}")

    _check_support(facts, opts)

    for issue in check_baselines(facts):
        level = "FATAL" if issue.fatal else "WARN"
        print(f"  [{level}] {issue}")

    if opts.skip_syspkg:
        print("  （--skip-syspkg：跳过宿主机依赖补齐）")
        return facts

    from .judge.version import BASELINES

    syspkg.ensure_python(facts, BASELINES["python"])
    syspkg.ensure_node(facts, BASELINES["node"])
    syspkg.ensure_build_toolchain(facts)
    syspkg.ensure_redis(facts)
    syspkg.ensure_mysql_server(facts, on_upgrade=opts.mysql_upgrade)
    return collect()   # 补齐后重新采集，后续步骤拿到的是新鲜事实


def _check_support(facts: HostFacts, opts: Options) -> None:
    """按支持矩阵放行或拒绝，并打印明确指路。

    拒绝时**不**继续：老系统上装到一半失败留下的半安装状态，
    比"什么都没做 + 一句清楚的指路"难收拾得多。
    """
    from .judge.support import SupportLevel, judge_support

    v = judge_support(facts)
    if v.level == SupportLevel.SUPPORTED:
        _announce_extra_time(v)
        return

    if v.level == SupportLevel.REJECTED and not opts.force_unsupported:
        print(f"\n  ❌ 不支持的系统：{facts.distro} {facts.distro_version}")
        print(f"     {v.reason}")
        print("     建议：")
        for line in v.advice:
            print(f"       · {line}")
        print("\n  若你已自行准备好 Python 3.14 与 MySQL 8.4，"
              "可跳过本步继续：")
        print("       --skip-syspkg        只跳过依赖补齐")
        print("       --force-unsupported  连同系统检查一起跳过")
        raise SystemExit(2)

    tag = ("[已强制放行·拒绝级]" if v.level == SupportLevel.REJECTED
           else "[MANUAL]")
    print(f"  {tag} {v.reason}")
    for line in v.advice:
        print(f"           · {line}")
    _announce_extra_time(v)


def _announce_extra_time(v) -> None:
    """把"这一步要多花多久"提前说清楚。

    为什么必须在**开始装之前**说：运维据此决定现在装还是等下班前跑。
    装到一半才发现要等 20 分钟，多半会有人按 Ctrl-C ——
    而中断源码编译会留下半安装状态，比等着难收拾得多。

    el9 走 uv（python-build-standalone，下载即用）与源码编译是两种完全
    不同的等待形态，文案必须分开 —— el9 混用"编译"字样会让运维白白做好
    等 20 分钟的心理准备。
    """
    if not v.extra_minutes:
        return
    if getattr(v, "python_via_uv", False):
        print(f"  ⏱ 本机将通过 uv 安装 Python 3.14（python-build-standalone，"
              f"自带 sqlite），预计额外耗时约 {v.extra_minutes} 分钟")
        print("     （el9 系统 sqlite 3.34.1 达不到 chromadb 要求，")
        print("      uv 装的 Python 自带 3.53.1，AI/RAG 功能不降级）")
        print("     下载期间会持续输出心跳；长时间无进展属正常，请勿中断")
        return
    print(f"  ⏱ 本机需要源码编译 Python 3.14，预计额外耗时约 {v.extra_minutes} 分钟")
    print("     （发行版源给不出 3.14。想快可换 Ubuntu 24.04，那里有现成 deb）")
    print("     编译期间会持续输出心跳；长时间无进展属正常，请勿中断")


def install(opts: Options) -> RunReport:
    """完整安装流程。

    ⚠️ 所有失败出口必须经 :func:`_fail`：曾经四处写成
    ``rep.failed = ...; return rep``，导致**失败原因被静默吞掉** ——
    日志干净地停在最后一步成功处、进程无声退出、退出码还是 0，
    看起来像"跑完了但没跑完"。这与 bash 时代 ``set -e`` 下
    ``wait "$pid"`` 吞掉子进程失败的形态一模一样，Python 并不天然免疫。
    """
    rep = RunReport()
    t_all = time.monotonic()

    def mark(name: str, t0: float) -> None:
        rep.timings[name] = time.monotonic() - t0

    def fail(reason: str) -> RunReport:
        rep.timings["总计"] = time.monotonic() - t_all
        rep.failed = reason
        _summary(rep, opts)          # 失败也要打耗时分布和原因，不许静默
        return rep

    _check_support(collect(), opts)

    t0 = time.monotonic()
    try:
        facts = _step1_host_baseline(opts)
    except Exception as e:  # noqa: BLE001 —— 依赖补齐的任何失败都必须带原因出报告
        return fail(f"宿主机依赖补齐失败：{e}")
    mark("1_宿主机基线", t0)

    if not facts.python_bin:
        return fail("未找到满足基线的 Python 3.14，且自动安装未能生效")

    sync_source(opts)

    print("\n=== [2/7] venv + Python 依赖 ‖ [3/7] 前端构建（并行）===")
    t0 = time.monotonic()

    def do_python() -> None:
        v = venv_mod.ensure_venv(PROJECT_ROOT / ".venv", facts.python_bin)
        venv_mod.upgrade_pip(v)
        flavor, multi = venv_mod.resolve_flavor(
            PROJECT_ROOT / "instance" / ".install-flavor",
            opts.torch_flavor if opts.torch_explicit else None,
        )
        if opts.torch_explicit:
            multi = opts.cuda_multi_mirror
        venv_mod.install_torch(v, PROJECT_ROOT, flavor,
                               cuda_multi_mirror=multi,
                               force_upstream=opts.force_torch_upstream)
        venv_mod.install_requirements(v, PROJECT_ROOT)

    def do_frontend() -> str:
        return frontend.frontend_step(PROJECT_ROOT, skip=opts.skip_frontend)

    def do_models_early() -> tuple[bool, str]:
        """返回 (是否无需兜底重试, 给用户看的结论)。

        ⚠️ skip / 脚本缺失不能再返回裸 True —— 那会让日志虚报
        "模型下载完成 ✓"（评审 P1-5），用户以为 RAG 可用。
        """
        if opts.skip_models:
            return True, "已跳过本地模型下载（--skip-models）：RAG 向量检索将不可用"
        script = PROJECT_ROOT / "scripts" / "download_models.py"
        if not script.is_file():
            return True, "未找到 scripts/download_models.py，跳过"
        res = shell.run([sys.executable, str(script), "--no-official"],
                        check=False, label="下载 RAG 本地模型（与依赖安装并行）",
                        timeout=5400, quiet_tail=40)
        return (res.ok,
                "模型下载完成 ✓（已与依赖安装并行完成）" if res.ok else "")

    with ThreadPoolExecutor(max_workers=3) as pool:
        fut_py = pool.submit(do_python)
        fut_fe = pool.submit(do_frontend)
        fut_mod = pool.submit(do_models_early)
        err_py = ""
        try:
            fut_py.result()
        except Exception as e:  # noqa: BLE001 —— 并行任务的异常必须显式收集，否则会被静默吞掉
            err_py = str(e)
        fe_msg = ""
        try:
            fe_msg = fut_fe.result()
        except Exception as e:  # noqa: BLE001 —— 同上：前端构建异常转为可读消息，不中断主流程
            fe_msg = f"ERROR: {e}"
        models_ok = True
        models_early_msg = ""
        try:
            models_ok, models_early_msg = fut_mod.result()
        except Exception as e:  # noqa: BLE001 —— 同上：模型下载失败降级为一则提示
            print(f"  [models] 并行下载异常：{e}")
            models_ok = False
    mark("2-3_依赖与前端", t0)

    if err_py:
        return fail(f"Python 依赖安装失败：{err_py}")
    if fe_msg.startswith("ERROR"):
        return fail(fe_msg)
    print(f"  [frontend] {fe_msg}")

    print("\n=== [4/7] 初始化 .env ===")
    t0 = time.monotonic()
    env_path = envfile.ensure_env(PROJECT_ROOT)
    envfile.generate_missing_keys(env_path)
    env = envfile.load_env(env_path)
    mark("4_env", t0)

    venv_py = str(PROJECT_ROOT / ".venv" / "bin" / "python")

    if models_ok:
        print("\n=== [5/7] 数据库初始化 ===")
    else:
        print("\n=== [5/7] 数据库初始化 ‖ [6/7] RAG 模型下载（并行路失败，兜底重试）===")
    t0 = time.monotonic()

    def do_models() -> str:
        if opts.skip_models:
            return "已跳过本地模型下载（--skip-models）：RAG 向量检索将不可用"
        script = PROJECT_ROOT / "scripts" / "download_models.py"
        if not script.is_file():
            return "未找到 scripts/download_models.py，跳过"
        res = shell.run([venv_py, str(script)], check=False,
                        label="下载 RAG 本地模型（兜底重试）", timeout=5400, quiet_tail=60)
        return ("模型下载完成 ✓" if res.ok else
                "模型下载失败 → RAG 功能不可用，可稍后重跑（支持断点续传）")

    def do_db() -> str:
        if opts.skip_db:
            return "已跳过数据库初始化（--skip-db）"
        cfg = db.from_env(env)
        db.init_database(cfg, venv_py, PROJECT_ROOT, env_path=env_path)
        return "数据库就绪 ✓"

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_db = pool.submit(do_db)
        fut_mod = pool.submit(do_models) if not models_ok else None
        db_err = ""
        db_msg = ""
        try:
            db_msg = fut_db.result()
        except Exception as e:  # noqa: BLE001 —— 数据库步骤异常统一收集后判定，不在此处抛出
            db_err = str(e)
        mod_msg = models_early_msg
        if fut_mod is not None:
            try:
                mod_msg = fut_mod.result()
            except Exception as e:  # noqa: BLE001 —— 同上：首次取过之后再取也走降级路径
                mod_msg = f"模型下载异常：{e}"
    mark("5-6_数据库与模型", t0)

    if db_err:
        return fail(f"数据库初始化失败：{db_err}")
    print(f"  [db] {db_msg}")
    print(f"  [models] {mod_msg}")

    t_seed = time.monotonic()
    seed_err = ""
    try:
        _import_seed(opts, rep, venv_py)
    except Exception as e:  # noqa: BLE001 —— 种子失败降级为提示，不该让安装终局失败
        seed_err = str(e)
    mark("6_种子数据", t_seed)
    if seed_err:
        print(f"  [seed] ! 种子导入失败（{seed_err}）—— 可稍后手工执行 "
              f"bash {PROJECT_ROOT / 'migrations' / 'seed_all.sh'}")

    print("\n=== [7/7] 进程托管与收尾 ===")
    t0 = time.monotonic()
    try:
        if opts.with_units:
            units.install(project_root=PROJECT_ROOT, user=opts.units_user,
                          group=opts.units_group, script=opts.units_script)
        else:
            print("  （未指定 --with-units，跳过 systemd 托管安装）")

        if not opts.dev_env:
            envfile.set_flask_env(env_path, production=True)

        if not opts.dev_env:
            remaining = production_check.verify_production_env(
                PROJECT_ROOT, venv_py, env_path,
                metrics_allowed_ips=opts.metrics_allowed_ips,
                cors_origins=opts.cors_origins,
            )
            if remaining:
                ids = ", ".join(v.id for v in remaining)
                return fail(f"生成的 .env 未通过生产配置校验（{ids}），服务将拒绝启动")
    except Exception as e:  # noqa: BLE001 —— 收尾段异常统一走 fail()，不许静默逃出
        return fail(f"收尾阶段失败：{e}")
    mark("7_收尾", t0)

    rep.timings["总计"] = time.monotonic() - t_all

    try:
        _verify_rbac_permission_codes(rep, venv_py, env_path)
    except Exception as e:  # noqa: BLE001 —— 校验失败不阻断安装
        print(f"  [rbac] ! 权限码校验异常（不阻断）：{e}")

    _summary(rep, opts)
    if not rep.failed:
        _credential_digest(rep, venv_py)
    return rep


def _import_seed(opts: Options, rep: RunReport, venv_py: str) -> None:
    """[6/7] 导入种子数据，并捕获新建管理员的初始密码。

    旧 install.sh 的这一步会把 seed_all.sh 的输出 tee 下来，再从
    ``初始密码: xxx`` 抽出明文密码写进 .credentials。编排器化时这一步
    整个丢失 —— 于是既没有管理员账号，也没有任何凭据留档。

    升级模式（``--upgrade``）默认跳过：种子幂等，但每次重跑会往留档里
    反复追加管理员明文，多次升级后文件膨胀且容易看错哪条是当前的。
    """
    if opts.skip_seed:
        if opts.upgrade:
            rbac = PROJECT_ROOT / "migrations" / "seed_rbac.py"
            if rbac.is_file():
                print("\n=== [6/7] 升级：同步 RBAC 角色/权限（幂等，重建关联）===")
                res = shell.run(
                    [venv_py, str(rbac), "--incremental"], check=False, label="RBAC 权限同步（增量）",
                    timeout=300, quiet_tail=30,
                )
                if res.ok:
                    print("  [seed] 关联已增量补齐（界面上的自定义权限调整原样保留）")
                else:
                    print("  [seed] ! RBAC 同步失败 —— 新增模块的权限码可能未入库，"
                          f"请手工执行：{venv_py} {rbac}")
            else:
                print(f"  [seed] ! 未找到 {rbac}，跳过 RBAC 同步")
            return
        print("  [seed] （--skip-seed，跳过种子导入）")
        return

    script = PROJECT_ROOT / "migrations" / "seed_all.sh"
    if not script.is_file():
        print(f"  [seed] ! 未找到 {script}，跳过种子导入")
        return

    print("\n=== [6/7] 导入种子数据（含默认管理员）===")
    res = shell.run(["bash", str(script)], check=False, label="导入种子数据",
                    timeout=1800, quiet_tail=60)
    if not res.ok:
        raise RuntimeError(
            f"seed_all.sh 退出码 {res.code}；末行："
            + " / ".join((res.stdout or "").splitlines()[-3:])
        )

    m = re.search(r"初始密码[:：]\s*(\S+)", res.stdout or "")
    if m:
        rep.admin_password = m.group(1)
        print("  [seed] 已创建默认管理员（密码见文末凭据汇总）")
    else:
        print("  [seed] 管理员已存在或种子未提供新密码，跳过密码捕获")


def _collect_permission_codes_from_source(app_dir: Path) -> set[str]:
    """扫描 ``@permission_required("code")`` 的字符串字面量引用（纯函数，可测）。

    局限：只认**字符串字面量**。变量/拼接形态引用不到 —— 那种形态本仓也没有；
    若未来出现，校验会漏报（以 WARNING 暴露，不会静默）。
    """
    import re as _re

    pattern = _re.compile(r'@permission_required\(\s*"([\w:]+)"')
    codes: set[str] = set()
    for path in sorted(app_dir.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        codes.update(pattern.findall(text))
    return codes


def _diff_rbac_codes(referenced: set[str], in_db: set[str]) -> tuple[set[str], set[str]]:
    """返回 ``(代码引用但 DB 缺失, DB 有但代码不再引用)``（纯函数，可测）。"""
    return referenced - in_db, in_db - referenced


def _query_rbac_codes(venv_py: str, env_path: Path) -> set[str]:
    """查 DB ``permissions.code`` 集合（子进程跑，读安装产出的 .env；失败返回空集）。"""
    rbac_query = "SELECT code FROM permissions"
    script = (
        "import json, os\n"
        "from dotenv import load_dotenv\n"
        f"load_dotenv({str(env_path)!r})\n"
        "import pymysql\n"
        "c = pymysql.connect(host=os.environ.get('MYSQL_HOST', 'localhost'),\n"
        "    port=int(os.environ.get('MYSQL_PORT', '3306')),\n"
        "    user=os.environ.get('MYSQL_USER', 'root'),\n"
        "    password=os.environ.get('MYSQL_PASSWORD', ''),\n"
        "    database=os.environ.get('MYSQL_DATABASE', 'ip_management'),\n"
        "    charset='utf8mb4')\n"
        f"cur = c.cursor(); cur.execute({rbac_query!r})\n"
        "print(json.dumps([r[0] for r in cur.fetchall()]))\n"
    )
    res = shell.run([venv_py, "-c", script], check=False, timeout=60,
                    label="RBAC 权限码查询")
    if not res.ok:
        return set()
    import json as _json
    try:
        return set(_json.loads((res.stdout or "").strip() or "[]"))
    except (ValueError, TypeError):
        return set()


def _verify_rbac_permission_codes(rep: RunReport, venv_py: str, env_path: Path) -> None:
    """收尾校验：**代码引用的权限码必须已入库**，否则新功能上线即 403。

    升级模式跑过 `seed_rbac.py` 后理论上应为零缺失 —— 若仍有缺失，说明**种子文件
    忘了登记新模块的权限码**（这正是本条校验的价值：把"升级完功能用不了"前移到
    安装报告里的一行 WARNING）。失败不阻断安装（DB 不可达时降级跳过）。
    """
    referenced = _collect_permission_codes_from_source(PROJECT_ROOT / "app")
    if not referenced:
        print("  [rbac] ! 未从代码扫到权限码引用（app/ 目录为空或形态变化），跳过校验")
        return
    in_db = _query_rbac_codes(venv_py, env_path)
    if not in_db:
        print("  [rbac] ! 无法读取 DB 权限码（可能 DB 未就绪），跳过校验")
        return
    missing = sorted(referenced - in_db)
    if missing:
        print(f"  [rbac] ! 代码引用了 {len(missing)} 个 DB 中不存在的权限码 —— "
              "对应接口会 403！请在 migrations/seed_rbac.py 的 PERMISSIONS 登记后重跑：")
        for code in missing:
            print(f"      - {code}")
        rep.notes.append(f"RBAC 缺失权限码 {len(missing)} 个（详见上方清单）")
    else:
        print(f"  [rbac] 代码引用的 {len(referenced)} 个权限码全部已入库 ✓")


def _credential_digest(rep: RunReport, venv_py: str) -> None:
    """凭据汇总 —— 部署最怕「装完了却不知道账号密码」。

    admin 是随机密码，MySQL/Redis 密码散落在 .env 里，事后翻文件既慢又容易
    看错环境（本机 .env 与服务器 .env 长得一样）。安装收尾必须**当场**展示
    一次，并指向留档文件与重置入口。

    [WARN] 这一段是旧 install.sh 的第 10 步，编排器化时漏掉了 —— 表现就是
    「安装报告一切正常，但 .credentials 没生成、admin 密码没处看」。
    """
    print("\n=== 凭据汇总（请立即保存）===")
    if rep.admin_password:
        user = os.environ.get("SEED_ADMIN_USERNAME", "admin")
        print(f"本次新建管理员 '{user}' 的密码: {rep.admin_password}")

    script = PROJECT_ROOT / "scripts" / "credentials.py"
    if not script.is_file():
        print("  ! 未找到 scripts/credentials.py，跳过凭据清单展示")
        return

    res = shell.run([venv_py, str(script), "show"],
                    check=False, label="凭据清单", timeout=120)
    if not res.ok:
        print(f"  ! 凭据清单展示失败，可稍后手工执行：{venv_py} scripts/credentials.py show")

    items = []
    if rep.admin_password:
        items += ["--item", f"admin_user={os.environ.get('SEED_ADMIN_USERNAME', 'admin')}",
                  "--item", f"admin_password={rep.admin_password}"]
    else:
        items += ["--item",
                  "note=本次为幂等重跑，未新建管理员密码；"
                  f"重置并留档见 {venv_py} scripts/credentials.py reset-admin"]
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    shell.run([venv_py, str(script), "record",
               "--title", f"install ({stamp})", *items],
              check=False, label="凭据留档", timeout=60)

    print(f"重置入口: {venv_py} scripts/credentials.py reset-admin   # 重置管理员密码")
    print(f"          sudo {venv_py} scripts/credentials.py reset-mysql  # 重置 MySQL 密码（并同步 .env）")
    print(f"留档文件: {PROJECT_ROOT / '.credentials'}（权限 600，含历次生成的明文凭据）")


def _summary(rep: RunReport, opts: Options) -> None:
    print("\n" + "=" * 64)
    print("安装完成" if not rep.failed else "安装未完成")
    print("=" * 64)
    print("耗时分布:")
    for name, sec in sorted(rep.timings.items(), key=lambda kv: -kv[1]):
        if name == "总计":
            continue
        print(f"    {name:24} {sec:8.1f}s")
    print(f"    {'总计':24} {rep.total():8.1f}s")
    if rep.failed:
        print(f"\n失败原因：{rep.failed}")
    for n in rep.notes:
        print(f"  · {n}")
