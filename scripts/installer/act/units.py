"""systemd 单元安装。

这里是最能体现「Shell 管做、Python 管判断」的一处：

- **动作**：渲染并安装 unit 由既有的 ``deploy/systemd/install-units.sh`` 负责，
  它已经经过了真机验证（包含 User=/Group= 占位符渲染、账号存在性守卫）。
  把它翻译成 Python 没有任何收益，只有回归风险。
- **判断**：脚本在不在、账号存不存在、要不要 sudo、`User=` 会不会与部署路径冲突，
  这些才是 Python 该做的事 —— 因为旧 benign 事故里，「判据错了但动作对了一半」
  是最贵的失败形态。

另有一条旧脚本的纪律：**默认不安装** units。接管进程属于生产变更且需要 root，
不该由"跑一次安装"这个动作附带发生。
"""

from __future__ import annotations

from pathlib import Path

from .shell import run, which

__all__ = ["locate_script", "install"]

_CANDIDATES = ("deploy/systemd/install-units.sh",)


def locate_script(project_root: Path, explicit: str = "") -> Path:
    """定位 install-units.sh。找不到就明确报错并说明缺什么。"""
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            raise FileNotFoundError(f"--units-script 指定的文件不存在: {p}")
        return p
    for rel in _CANDIDATES:
        p = project_root / rel
        if p.is_file():
            return p
    raise FileNotFoundError(
        f"未找到 systemd 安装脚本，已探测: {', '.join(_CANDIDATES)}。"
        "请确认部署副本完整，或用 --units-script 指定路径。"
    )


def _user_exists(name: str) -> bool:
    return run(["id", "-u", name], check=False, echo=False).ok


def install(project_root: Path, *, user: str = "", group: str = "", script: str = "") -> None:
    """渲染并安装 systemd units。"""
    sh = locate_script(project_root, script)

    if not which("systemctl"):
        print("[units] ⚠ 本机没有 systemctl，跳过服务托管安装")
        return
    if run(["id", "-u"], check=False, echo=False).stdout.strip() != "0":
        if not which("sudo"):
            print("[units] ⚠ 非 root 且无 sudo，无法安装 systemd unit，跳过")
            return
        print("[units] 非 root，改用 sudo 执行安装脚本")
        sudo_prefix = ["sudo"]
    else:
        sudo_prefix = []

    args = [*sudo_prefix, "bash", str(sh)]
    if user:
        args += ["--user", user]
    if group:
        args += ["--group", group]

    if user and not _user_exists(user):
        print(f"[units] ⚠ 账号 {user} 不存在，将由 install-units.sh 决定如何处理")
    else:
        target = user or "ipip"
        print(f"[units] 服务运行账号: {target}"
              f"（项目在 /root 下时应为 root，否则与 ProtectHome 加固互斥）")

    res = run(args, check=False, label="安装 systemd units", timeout=600)
    if not res.ok:
        raise RuntimeError(
            "systemd 单元安装失败（后续服务将无法由 systemd 托管，但应用本体已安装）。\n"
            f"  可手工执行：{' '.join(args)}\n"
            "  " + "\n  ".join(res.lines[-8:])
        )
    print("[units] 单元已安装。启用请执行：systemctl enable --now ipip.target")
