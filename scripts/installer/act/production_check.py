"""生产配置闭环自检 —— 在安装的最后一步确认 ``.env`` 真的能让服务起来。

**为什么需要这一层（而不是继续给每个配置项打补丁）**

继 SECRET_KEY 占位符事故之后，同一形态的问题第二次咬人：installer 老老实实
按模板写出了 ``.env``，但**没人回头校验它是否满足服务启动时的生产约束** ——
于是安装报告打印了「安装完成」，健康检查却发现::

    ValueError: 生产环境 /metrics 默认开启且免鉴权 ⇒ 必须至少限制一项

报错出现在整条安装的最后一步，与真正该负责的配置生成相距极远。

逐条打补丁会被下一次新增的检查再教一遍做人：``ProductionConfig`` 的检查注册表
已经有 6 条，每一条都可以成为下一次安装的拦路石。所以这里的做法是**复用判据
本身**：子进程调用 ``scripts/precheck_prod_config.py`` —— 它消费 ``config.py``
里同一份 ``_PRODUCTION_CHECKS`` 注册表，判据单一真源、不会各自漂移。installer
只负责「读结果 → 能安全补的就补 → 重跑复验」。

这样带来一个单向但很重要的收益：**config 以后新增第 7 条检查时，installer
无需改动就能拒绝这次安装并打印修复建议**，而不是让服务在第一次
``systemctl restart`` 时才炸给运维看。

**为什么走子进程而不是 import**

``ProductionConfig`` 的类属性在 **import 时**从 ``os.environ`` 求值
（``SECRET_KEY = os.getenv("SECRET_KEY")`` 写在类体里）。这意味着同一进程内
无法「改了 .env 再重新校验一次」——类属性早就算完了，改环境变量不生效。
走子进程是唯一诚实的做法：每轮校验都是全新解释器、全新求值。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import envfile, shell

__all__ = ["Violation", "verify_production_env"]

_LINE = re.compile(r"^\s*✗\s*\[([A-Za-z0-9_]+)\]\s*(.*\S)\s*$")
_SUGGEST = re.compile(r"^\s*建议：(.*\S)\s*$")

AUTO_FIXABLE: dict[str, str] = {
    "METRICS_EXPOSURE": "METRICS_ALLOWED_IPS",
}

_LOCALHOST_CORS = re.compile(r"^(https?://)?(localhost|127\.0\.0\.1)(:\d+)?$", re.I)


@dataclass
class Violation:
    """一条生产配置缺陷。"""

    id: str
    message: str
    suggestion: str = ""


def _precheck(project_root: Path, venv_py: str, env_path: Path) -> list[Violation]:
    """跑一次离线预检，返回缺陷列表（空列表 = 通过）。"""
    script = project_root / "scripts" / "precheck_prod_config.py"
    if not script.is_file():
        raise FileNotFoundError(
            f"预检脚本不存在：{script}\n"
            "  它是生产配置约束的唯一真源（消费 config._PRODUCTION_CHECKS）。\n"
            "  没有它就无法判断 .env 能否通过服务启动校验 —— 宁可明确失败。"
        )

    res = shell.run(
        [venv_py, str(script), "--env-file", str(env_path)],
        check=False, echo=False, label="生产配置预检", timeout=180,
    )
    if res.code == 2:
        raise RuntimeError(f"预检脚本报告用法/文件错误（退出码 2）：\n{res.stdout}")
    if res.code not in (0, 1):
        raise RuntimeError(
            f"预检脚本异常退出（退出码 {res.code}），判据不可信：\n{res.stdout}"
        )

    out: list[Violation] = []
    pending: Violation | None = None
    for ln in res.lines:
        m = _LINE.match(ln)
        if m:
            pending = Violation(id=m.group(1), message=m.group(2))
            out.append(pending)
            continue
        m = _SUGGEST.match(ln)
        if m and pending is not None:
            pending.suggestion = m.group(1)

    if res.code == 1 and not out:
        raise RuntimeError(
            "预检报告存在配置缺陷（退出码 1）但解析不出任何条目，"
            "输出格式可能已漂移：\n" + res.stdout
        )
    return out


def _autofix(env_path: Path, violations: list[Violation], *,
             metrics_allowed_ips: str) -> list[str]:
    """对可安全自动补齐的项写回 .env，返回人类可读的修复描述。

    ⚠️ 只写**与现值不同**的键（评审 P2）：曾无条件重写全部 AUTO_FIXABLE，
    当 METRICS 因其他原因失败时每轮重复写同一值，烧满重试轮数也修不好。
    """
    current = envfile.load_env(env_path)
    values: dict[str, str] = {}
    for v in violations:
        key = AUTO_FIXABLE.get(v.id)
        if key and current.get(key) != metrics_allowed_ips:
            values[key] = metrics_allowed_ips
    if not values:
        return []
    for key, value in values.items():
        envfile.set_env_value(env_path, key, value)
    return [f"{k}={v}" for k, v in values.items()]


def _handle_cors(env_path: Path, cors_origins: str, env: dict[str, str]) -> None:
    """处理「检查能过、但装完不能用」的 CORS_ORIGINS。

    `.env.example` 给的是 ``http://localhost:5173``：它满足 CORS_ORIGINS 检查
    （非空、非 ``*``），所以预检不会报错；但从其他机器打开页面时被浏览器跨域
    拦下 —— **服务正常、页面全白，报错只在浏览器控制台里**。这类缺陷自动化
    检查抓不到，只能在明确知道部署域名时替用户写对。
    """
    current = [c.strip() for c in env.get("CORS_ORIGINS", "").split(",") if c.strip()]
    is_local_only = bool(current) and all(_LOCALHOST_CORS.match(c) for c in current)

    if cors_origins:
        if current and not is_local_only:
            print(f"[precheck] CORS_ORIGINS 已是 {env.get('CORS_ORIGINS')}，"
                  "未覆盖 --cors-origins（检测到手工配置）")
            return
        envfile.set_env_value(env_path, "CORS_ORIGINS", cors_origins)
        print(f"[precheck] 已写入 CORS_ORIGINS={cors_origins}")
        return

    if is_local_only:
        print(
            f"[precheck] ⚠️  CORS_ORIGINS={env.get('CORS_ORIGINS')} 只含本机地址\n"
            "      它能通过配置校验，但从其他机器打开页面会被浏览器跨域拦下\n"
            "      （服务正常、页面白屏，报错只在浏览器控制台里）。\n"
            "      前端与后端同机部署可忽略；否则重跑时加 "
            "--cors-origins https://你的域名"
        )


def verify_production_env(
    project_root: Path,
    venv_py: str,
    env_path: Path,
    *,
    metrics_allowed_ips: str = "127.0.0.1/32",
    cors_origins: str = "",
    max_rounds: int = 3,
) -> list[Violation]:
    """闭环校验：跑预检 → 能补的补 → 重跑复验。返回仍存在的缺陷（空 = 通过）。

    补完必须复验，而不是「补了就算通过」——写入本身也可能没生效
    （同名 KEY 重复、值被模板注释等），只有重跑判据才算数。
    """
    if cors_origins:
        try:
            _handle_cors(env_path, cors_origins, envfile.load_env(env_path))
        except OSError as e:
            print(f"[precheck] ⚠ CORS_ORIGINS 写入失败（{e}）；"
                  "跨机访问将受限，请手工检查 .env 中的 CORS_ORIGINS")

    for round_no in range(1, max_rounds + 1):
        violations = _precheck(project_root, venv_py, env_path)
        if not violations:
            print("[precheck] ✓ 生产配置校验通过：本次 .env 不会被服务启动校验拒绝")
            try:
                _handle_cors(env_path, "", envfile.load_env(env_path))
            except OSError:
                pass
            return []

        print(f"[precheck] ✗ 第 {round_no} 轮发现 {len(violations)} 项配置缺陷"
              f"（服务启动会被 fail-fast 拒绝）：")
        for v in violations:
            print(f"    [{v.id}] {v.message}")
            if v.suggestion:
                print(f"           建议：{v.suggestion}")

        fixed = _autofix(env_path, violations,
                         metrics_allowed_ips=metrics_allowed_ips)
        if not fixed:
            print(
                "[precheck] 以上缺陷无法在安装器内自动补齐"
                "（需要只有你才知道的信息），\n"
                f"           请手工编辑 {env_path} 后重跑安装器。"
            )
            return violations
        print(f"[precheck] 已自动补齐：{', '.join(fixed)}")

    print(f"[precheck] ✗ {max_rounds} 轮校验后仍有缺陷，安装判定为失败 —— "
          "否则会交付一个起不来的服务。")
    return _precheck(project_root, venv_py, env_path)
