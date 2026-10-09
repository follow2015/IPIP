"""``python -m installer`` 入口。

参数与旧 ``install.sh`` **完全兼容**，运维的手感不该因为重写而改变。
新增的只有「缺省时会自动补齐宿主机依赖」这一条 —— 这正是这次重写要补的缺口。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .steps import Options, PROJECT_ROOT, install

EPILOG = """
示例:
  bash scripts/installer/bootstrap.sh        # 推荐入口：前置守卫（零 Python）+ 自动备好 Python 3.14 + 进编排器
  python -m installer                        # 完整安装（含自动补齐 MySQL/Redis/Node；需已有 Python 3.14）
  python -m installer --skip-frontend        # 跳过前端构建
  cd scripts/ && python -m installer ...      # ⚠ 必须在 scripts/ 下执行（包在此层）
  python -m installer --skip-models          # 跳过 RAG 模型（省约 1.2GB）
  python -m installer --skip-syspkg          # 不碰宿主机依赖
  python -m installer --with-units --units-user root

判据层自检（不改动系统，只看「有没有 / 够不够快」）:
  python -m installer --selftest
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cd scripts && python -m installer",
        description="ipip 安装器（Shell 管做、Python 管判断）",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--source-root", default=str(Path(__file__).resolve().parents[2]),
                   help=f"代码副本目录（默认按本文件位置推导），安装目标恒为 {PROJECT_ROOT}")

    p.add_argument("--skip-syspkg", action="store_true",
                   help="跳过宿主机依赖补齐（Python/Node/MySQL/Redis/g++）")
    p.add_argument("--mysql-upgrade", choices=["ask", "yes", "no"], default="ask",
                   help="已有低版本 MySQL 时：ask=交互询问（默认）/ yes=直接升级 / "
                        "no=保持不动。非交互环境下 ask 等同 no")
    p.add_argument("--force-unsupported", action="store_true",
                   help="系统不在支持矩阵中时仍继续（默认拒绝，防半安装状态）")
    p.add_argument("--skip-frontend", action="store_true", help="跳过前端构建")
    p.add_argument("--skip-db", action="store_true", help="跳过数据库初始化")
    p.add_argument("--skip-seed", action="store_true", help="跳过种子导入")
    p.add_argument("--skip-models", action="store_true", help="跳过 RAG 模型下载")

    p.add_argument("--cpu", action="store_true", help="显式指定 CPU 版 torch（默认）")
    p.add_argument("--gpu", action="store_true", help="使用 GPU(CUDA) 版 torch")
    p.add_argument("--gpu-fast", action="store_true", help="GPU 版并启用多镜像分散预取")
    p.add_argument("--torch-upstream", action="store_true",
                   help="torch 强制走官方源（通常慢数倍；镜像与官方已实测同步版本）")

    p.add_argument("--with-units", action="store_true", help="安装 systemd 单元")
    p.add_argument("--units-user", default="", help="服务运行账号（项目在 /root 下应为 root）")
    p.add_argument("--units-group", default="", help="服务运行组")
    p.add_argument("--units-script", default="", help="指定 install-units.sh 路径")

    p.add_argument("--dev-env", action="store_true", help="收尾不切 FLASK_ENV=production")
    p.add_argument("--upgrade", action="store_true", help="升级模式：沿用已装 flavor、跳过种子")
    p.add_argument("--metrics-allowed-ips", default="127.0.0.1/32",
                   help="/metrics 抓取来源白名单（默认只本机可抓；"
                        "Prometheus 在别的机器时填它的 IP/CIDR）")
    p.add_argument("--cors-origins", default="",
                   help="前端域名（如 https://ipip.corp.local）；"
                        "不给则沿用模板的 localhost 默认值，仅同机部署可用")
    p.add_argument("--selftest", action="store_true", help="只跑判据层自检，不改动系统")
    return p


def _selftest() -> int:
    from concurrent.futures import ThreadPoolExecutor

    from .judge.facts import check_baselines, collect
    from .judge.sources import select_npm_source, select_pip_source
    from .judge.torch_source import select_cpu_index

    f = collect()
    print(f"发行版 {f.distro} {f.distro_version} ({f.arch})   {f.pkg_manager}")
    print(f"Python {f.python_display} (ABI {f.cp_tag or '未达基线'})   "
          f"node {f.node_version or '-'}   pnpm {f.pnpm_version or '-'}")
    print(f"mysql {f.mysql_version or '-'}   redis {f.redis_version or '-'}   "
          f"g++={f.has_gpp}   root={f.is_root}")
    for i in check_baselines(f):
        print(f"  {i}")

    print(f"\nwheel 平台标签: {f.wheel_arch_tag or '(未知架构)'}")

    def torch_job() -> tuple[str | None, list]:
        return select_cpu_index(
            candidates=["https://mirrors.nju.edu.cn/pytorch/whl/cpu",
                        "https://download.pytorch.org/whl/cpu"],
            cp_tag=f.cp_tag or "cp314",
            arch_tag=f.wheel_arch_tag or "manylinux_2_28_x86_64",
        )

    with ThreadPoolExecutor(max_workers=3) as pool:
        ft = pool.submit(torch_job)
        fp = pool.submit(select_pip_source)
        fn = pool.submit(select_npm_source)
        chosen, report = ft.result()
        pip_url, pip_rep = fp.result()
        npm_url, npm_rep = fn.result()

    print("\n--- torch CPU 索引 ---")
    for url, r in report:
        print(f"  [{'OK' if r.ok else 'NG'}] {url:50} {r.mib_s:>10}")
        if r.reason:
            print(f"        {r.reason[:70]}")
    print(f"  -> {chosen}")

    print("\n--- pip 源 ---")
    for c in pip_rep:
        print(f"  [{'OK' if c.ok else 'NG'}] {c.name:6} {c.result.mib_s:>10}")
        if c.result.reason:
            print(f"        {c.result.reason[:70]}")
    print(f"  -> {pip_url}")

    print("\n--- npm registry ---")
    for c in npm_rep:
        print(f"  [{'OK' if c.ok else 'NG'}] {c.name:6} {c.result.mib_s:>10}")
        if c.result.reason:
            print(f"        {c.result.reason[:70]}")
    print(f"  -> {npm_url}")
    return 0


def _torch_cli(args) -> tuple[str, bool, str]:
    """把 ``--cpu/--gpu/--gpu-fast`` 折算成 ``(flavor, explicit, multi)``。

    单独抽出来是为了可测：这条映射曾经出过事故 —— ``--gpu-fast`` 被
    折叠成 ``--gpu`` 后，多镜像预取开关在编排器里静默失效。
    """
    flavor = "cpu"
    explicit = False
    if args.gpu or args.gpu_fast:
        flavor = "gpu"
        explicit = True
    elif args.cpu:
        explicit = True
    return flavor, explicit, ("1" if args.gpu_fast else "0")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.selftest:
        return _selftest()

    flavor, explicit, multi = _torch_cli(args)

    opts = Options(
        source_root=Path(args.source_root),
        skip_syspkg=args.skip_syspkg,
        mysql_upgrade=args.mysql_upgrade,
        force_unsupported=args.force_unsupported,
        skip_frontend=args.skip_frontend,
        skip_db=args.skip_db,
        skip_seed=args.skip_seed or args.upgrade,   # 升级模式默认跳过种子，沿用旧口径
        skip_models=args.skip_models,
        torch_flavor=flavor,
        torch_explicit=explicit,
        cuda_multi_mirror=multi,
        force_torch_upstream=args.torch_upstream,
        with_units=args.with_units,
        units_user=args.units_user,
        units_group=args.units_group,
        units_script=args.units_script,
        dev_env=args.dev_env,
        upgrade=args.upgrade,
        metrics_allowed_ips=args.metrics_allowed_ips,
        cors_origins=args.cors_origins,
    )

    try:
        rep = install(opts)
    except KeyboardInterrupt:
        print("\n[abort] 用户中断")
        return 130
    except Exception as e:  # noqa: BLE001 —— CLI 顶层兜底：任何异常都必须转成非零退出码并回显，此处正是"最后一层网"
        print(f"\n[FATAL] {e}")
        return 1
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
