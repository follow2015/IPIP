"""``.env`` 初始化与密钥生成。

这条之所以必须是 Python 而不是 shell：

> `.env` 里的随机密码**可能含 `$`**（实测生成过 `9ai$aoGx…`）。
> 一旦用 shell 的 `source` 或字符串插值去读它，`$` 后面的内容会被当成变量展开
> —— 密码被静默改写成别的值，而报错要到连 MySQL 认证失败时才出现，
> 且报错形态是「密码错了」，完全指不到真正的根因。

Python 逐字节读写、不做任何 shell 语义解析，天然免疫。
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Callable

__all__ = [
    "REQUIRED_KEYS",
    "KEY_GENERATORS",
    "DEFAULT_KEY_GENERATOR",
    "ensure_env",
    "generate_missing_keys",
    "load_env",
    "set_env_value",
]

REQUIRED_KEYS: tuple[str, ...] = (
    "SECRET_KEY",
    "JWT_SECRET_KEY",
    "SWITCH_SECRET_KEY",
)

KEY_GENERATORS: dict[str, "Callable[[], str]"] = {
    "SWITCH_SECRET_KEY": lambda: secrets.token_hex(32),
}
def DEFAULT_KEY_GENERATOR() -> str:
    """无长度约束的随机串（会话类密钥用）。"""
    return secrets.token_urlsafe(48)


def _generate_key(key: str) -> str:
    """按密钥类型选生成器（见 ``KEY_GENERATORS`` 的 [WARN] 说明）。"""
    return KEY_GENERATORS.get(key, DEFAULT_KEY_GENERATOR)()

PLACEHOLDER_PREFIXES: tuple[str, ...] = ("change-me",)


def ensure_env(project_root: Path) -> Path:
    """确保 .env 存在（从 .env.example 拷贝，权限 600）。"""
    env_path = project_root / ".env"
    if env_path.is_file():
        print(f"[env] 已存在 {env_path}，跳过初始化")
        return env_path

    example = project_root / ".env.example"
    if not example.is_file():
        raise FileNotFoundError(
            f"找不到模板 {example}，也无法初始化 .env —— 请确认部署副本完整。"
        )
    env_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    env_path.chmod(0o600)
    print(f"[env] 已从 .env.example 创建 {env_path}（权限 600）")
    print("      请编辑该文件填写实际的数据库/Redis 密码后重跑本安装器。")
    return env_path


def is_unset(value: str | None) -> bool:
    """密钥是否尚未配置。

    三种形态都算未配置 —— 只看「键在不在」会漏掉后两种：

    1. 键缺失
    2. 值为空（``SWITCH_SECRET_KEY=`` 在模板里就是这样）
    3. 值仍是占位符（模板写的是 ``change-me-to-a-...``）
    """
    if value is None:
        return True
    v = value.strip().strip('"').strip("'")
    return (not v) or v.lower().startswith(PLACEHOLDER_PREFIXES)


def _entries(lines: list[str]) -> dict[str, str]:
    """解析出 ``KEY -> 原始值``（同 load_env，不做 shell 语义解析）。"""
    out: dict[str, str] = {}
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def generate_missing_keys(env_path: Path) -> list[str]:
    """为尚未配置的密钥补随机值（**已配置的不覆盖**）。

    幂等是硬要求：重跑安装器不应把线上正在用的密钥换成新的 ——
    那等于一次静默的全站登出 + 令牌失效。
    """
    lines = env_path.read_text(encoding="utf-8").splitlines()
    values = _entries(lines)
    todo = [k for k in REQUIRED_KEYS if is_unset(values.get(k))]
    if not todo:
        print("[env] 三把密钥均已有效配置，未覆盖")
        return []

    secrets_map = {k: _generate_key(k) for k in todo}
    out: list[str] = []
    written: set[str] = set()
    for ln in lines:
        s = ln.strip()
        key = s.split("=", 1)[0].strip() if "=" in s and not s.startswith("#") else ""
        if key in secrets_map:
            out.append(f"{key}={secrets_map[key]}")
            written.add(key)
        else:
            out.append(ln)
    for key in sorted(todo):
        if key not in written:
            out.append(f"{key}={secrets_map[key]}")

    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    env_path.chmod(0o600)
    print(f"[env] 已生成随机密钥: {', '.join(sorted(todo))}")
    return sorted(todo)


def load_env(env_path: Path) -> dict[str, str]:
    """读取 .env 为 dict，**不做任何 shell 语义解析**。

    这是本项目最关键的一条安全约束：值里的 `$`、反引号、空格原样保留。
    """
    data: dict[str, str] = {}
    for ln in env_path.read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def set_env_value(env_path: Path, key: str, value: str) -> None:
    """幂等地写入/更新一个键。写完收紧到 0600（.env 含密钥与密码）。"""
    lines = env_path.read_text(encoding="utf-8").splitlines()
    hit = False
    for i, ln in enumerate(lines):
        if ln.split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={value}"
            hit = True
            break
    if not hit:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        env_path.chmod(0o600)
    except OSError:
        pass


def set_flask_env(env_path: Path, *, production: bool = True) -> None:
    """收尾时把 FLASK_ENV 切到 production（--dev-env 时跳过）。"""
    set_env_value(env_path, "FLASK_ENV", "production" if production else "development")
    print(f"[env] FLASK_ENV = {'production' if production else 'development'}")
