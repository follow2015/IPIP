"""前端依赖安装与构建。

这里承载两条旧脚本留下的教训：

1. **pnpm 的可用性判据必须是「真跑一次」，不是 `which`**
   corepack 会留下"可执行但一跑就崩"的 shim，``command -v pnpm`` 会误判为已安装。
   升级前还必须**删掉那个 shim** —— 否则 ``npm install -g pnpm``
   会因同名文件冲突直接拒绝安装（连 pnpx 也要删）。

2. **小包能装完 ≠ 大依赖树撑得住**
   实测官方 registry 在完整安装时会掉到 24 KiB/s 并丢失 rolldown 原生 binding，
   导致构建失败。所以首次尝试失败后，一律换镜像重试一次再判失败。
"""

from __future__ import annotations

import os
from pathlib import Path

from ..judge.sources import select_npm_source
from ..judge.version import BASELINES, ge
from .shell import run, which

__all__ = ["ensure_pnpm", "install_deps", "build", "frontend_step"]


def _pnpm_version() -> str:
    """真跑一次拿到版本号；跑不动就当没有（corepack shim 的典型症状）。"""
    if not which("pnpm"):
        return ""
    res = run(["pnpm", "--version"], check=False, echo=False, timeout=20)
    return res.stdout.strip() if res.ok else ""


def ensure_pnpm(minimum: str | None = None) -> str:
    """确保 pnpm 可用且满足基线，返回版本号。"""
    want = minimum or BASELINES["pnpm"]
    have = _pnpm_version()

    if have and ge(have, want):
        print(f"[frontend] pnpm {have} ✓ (>= {want})")
        return have

    if have:
        print(f"[frontend] pnpm 版本过低（{have} < {want}），将升级")
    else:
        print(f"[frontend] pnpm 不可用（缺失，或 corepack shim 崩了），改用 npm 全局安装 pnpm@{want}")

    pnpm_path = which("pnpm")
    if pnpm_path:
        print(f"[frontend] 移除冲突/损坏的 corepack shim: {pnpm_path}")
        for p in (Path(pnpm_path), Path(pnpm_path).with_name("pnpx")):
            try:
                p.unlink()
            except OSError:
                pass

    registry, report = select_npm_source()
    for c in report:
        mark = "✓" if c.ok else "✗"
        print(f"    {mark} {c.name:6} {c.result.mib_s:>10}")
        if c.result.reason:
            print(f"        {c.result.reason[:72]}")
    run(["npm", "install", "-g", f"pnpm@{want}", "--registry", registry,
         "--no-audit", "--no-fund"],
        check=True, label=f"安装 pnpm@{want}", timeout=600)

    new = _pnpm_version()
    if not new or not ge(new, want):
        raise RuntimeError(
            f"pnpm 安装后仍不满足基线：拿到 {new or '无'}，要求 >= {want}"
        )
    print(f"[frontend] pnpm {new} ✓")
    return new


def _registry_for_build() -> str:
    registry, _ = select_npm_source()
    return registry


def _pnpm_env() -> dict[str, str]:
    """pnpm 的执行环境：在父进程环境上叠加 ``CI=true``。

    ⚠️ ``run(..., env=...)`` 是**替换**整个环境（直接喂给 Popen），所以必须
    先合并 ``os.environ`` —— 只传 ``{"CI": "true"}`` 会连 PATH/HOME 一起抹掉。

    ``CI=true`` 不是仪式感，是**非交互安装的硬前提**：pnpm 要重建 node_modules
    （lockfile 与既有目录不一致时）会先删 modules 目录，无 TTY 时它不敢删、
    直接中止 —— ``ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY``。安装器正是
    无 TTY 场景（systemd / ssh 非交互 / CI），实测在测试机上就是这样把
    --upgrade 打成失败的，且换镜像重试多少次都一样（病因不是网络）。
    """
    env = dict(os.environ)
    env["CI"] = "true"
    return env


def install_deps(frontend_dir: Path, registry: str) -> bool:
    """安装前端依赖。返回是否成功。"""
    env = _pnpm_env()
    frozen = run(["pnpm", "install", "--frozen-lockfile", "--registry", registry],
                 cwd=str(frontend_dir), check=False, label="pnpm install (frozen)", env=env)
    if frozen.ok:
        return True
    again = run(["pnpm", "install", "--registry", registry],
                cwd=str(frontend_dir), check=False, label="pnpm install (retry)", env=env)
    return again.ok


def build(frontend_dir: Path, registry: str) -> bool:
    """执行 pnpm build。"""
    res = run(["pnpm", "build"], cwd=str(frontend_dir), check=False,
              label="pnpm build", quiet_tail=120)
    if not res.ok:
        print("[frontend] 构建失败。若报 Cannot find native binding，通常是 Node 版本\n"
              "  低于 vitel 8 / rolldown 的 engines 要求（^20.19.0 || >=22.12.0），\n"
              "  pnpm 会静默跳过 @rolldown/binding-linux-x64-gnu，到构建阶段才炸。")
        return False
    return True


def frontend_step(project_root: Path, *, skip: bool = False) -> str:
    """完整的第 3 步。返回总结字符串（供并行执行时回传）。"""
    fe = project_root / "frontend-new"
    dist = fe / "dist"

    if skip:
        if (dist / "index.html").is_file():
            return "跳过前端构建（--skip-frontend），使用已有 dist/"
        return "ERROR: frontend-new/dist 不存在，不能跳过前端构建"

    if not (fe / "package.json").is_file():
        return "ERROR: frontend-new/package.json 不存在"

    ensure_pnpm()
    registry = _registry_for_build()
    print(f"[frontend] registry: {registry}")

    if not install_deps(fe, registry):
        print("[frontend] 首次安装失败，换镜像重试一次")
        registry = "https://registry.npmmirror.com"
        if not install_deps(fe, registry):
            return f"ERROR: 前端依赖安装失败（已尝试 {registry} 重试）"

    if not build(fe, registry):
        return "ERROR: 前端构建失败"
    return "前端构建完成 ✓"
