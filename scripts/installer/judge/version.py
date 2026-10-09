"""版本比较。

替掉 bash 版那个 awk 实现的 ``ver_ge``。行为等价，但可以被 pytest 覆盖 ——
顺带说明基线为什么定在这些数字：

- Python 3.14：**DIE** 级。``realtime_gateway`` 用了 ``asyncio.AsyncGenerator``，
  该属性 3.14 才存在。旧脚本"找不到 3.14 就降级继续"，会把必然崩溃压缩成
  一行 WARN，直到部署完成后 gateway 起不来才被发现。
- Node 26.7：**DIE** 级。vite 8 / rolldown 的 engines 是 ``^20.19.0 || >=22.12.0``；
  Node 20.18.x 能过粗放的主版本检查，但 pnpm 会**静默跳过**不满足 engines 的
  原生依赖 ``@rolldown/binding-linux-x64-gnu``，到构建阶段才报
  ``Cannot find native binding`` —— 报错点离根因极远。
- MySQL 8.4 / Redis 8.0 / pnpm 10.34.5：WARN 级，仅记录偏差。
"""

from __future__ import annotations

import re

__all__ = ["parse", "ge", "gt", "BASELINES"]


def parse(text: str) -> tuple[int, ...]:
    """把 ``"8.0.36-28"`` / ``"v26.7.0"`` / ``"3.14.0rc1"`` 解析成可比较元组。

    只取数字段，非数字后缀一律丢弃 —— 发行版包的版本号后缀非常自由
    （``-28``、``+deb11u1``、``rc1``），严格解析会把合法版本误判为不可用。
    """
    m = re.search(r"\d+(?:\.\d+)*", text or "")
    if not m:
        return ()
    parts: list[int] = []
    for seg in m.group(0).split("."):
        head = re.match(r"\d+", seg)
        parts.append(int(head.group()) if head else 0)
    return tuple(parts)


def ge(cur: str, minimum: str) -> bool:
    """``cur`` >= ``minimum``。缺位按 0 补（``3.14`` 与 ``3.14.0`` 相等）。"""
    a, b = parse(cur), parse(minimum)
    if not a:
        return False
    n = max(len(a), len(b))
    return tuple(a) + (0,) * (n - len(a)) >= tuple(b) + (0,) * (n - len(b))


def gt(cur: str, minimum: str) -> bool:
    a, b = parse(cur), parse(minimum)
    if not a:
        return False
    n = max(len(a), len(b))
    return tuple(a) + (0,) * (n - len(a)) > tuple(b) + (0,) * (n - len(b))


BASELINES: dict[str, str] = {
    "python": "3.14",
    "node": "26.7",
    "pnpm": "10.34.5",
    "mysql": "8.4",
    "redis": "8.0",
}
