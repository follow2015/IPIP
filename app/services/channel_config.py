# -*- coding: utf-8 -*-
"""多通道采集的**运行期开关读取器**（执行计划 T0.8）。

为什么单独一个模块、且不放在 ``app/services/collector/`` 下面
---------------------------------------------------------------
ADR-004 把通道层定为独立成层，只允许它单向依赖监控侧的 **L1 底层原语**
（``snmp_adapter`` / ``snmp_port_collector``），而 ``MonitorDynamicConfig`` 属于
**L2 注册表与编排**。让 ``selector.py`` 直接 import 它，等于在通道层里开一个
通向监控编排的洞，边界门禁（``tests/test_collector_boundary_guard.py`` B1）会转红。

于是职责这样切：

  * 本模块（上层）：读 ``MonitorDynamicConfig`` → 产出**纯值对象**
    ``ChannelRuntimeConfig``；
  * 通道层：只认注入进来的纯值（``ChannelSelector(budget_seconds=…,
    circuit_threshold=…)``），不知道开关从哪来。

这条切分额外换来一个好处：通道层的单测不必起 Redis / app context。

灰度口径（设计文档 §19.2）
--------------------------
``SCAN_CHANNEL_SNMP_DEVICE_IDS`` / ``SCAN_CHANNEL_SNMP_ROOM_IDS`` 是**并集**关系：
命中设备ID **或** 命中机房ID 即放行 SNMP；两个都留空 = 没有任何设备走 SNMP
（"空 = 不启用"）。默认全空 + 总开关 false，即**安装完默认不启用 SNMP**，
与 G6「现有行为零变更」一致 —— 想启用必须显式放开，不会出现"升级后悄悄变了"。

脏值处理沿用 P2-5 的口径：解析不出来的片段**忽略并告警**，而不是抛异常。
开关的作用域是"少采一项能力"，不该因为一行手写的脏数据让整轮扫描失败。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Iterable, Optional, Sequence

from app.services.collector.circuit_breaker import RedisCircuitStore
from app.utils.logging import get_logger

if TYPE_CHECKING:  # 仅类型标注：避免本模块在 worker 启动早期就把通道层拉起来
    from app.services.collector.base_channel import BaseChannel

logger = get_logger(__name__)

KEY_ENABLED = "SCAN_CHANNEL_ENABLED"
KEY_PRIORITY = "SCAN_CHANNEL_PRIORITY"
KEY_SNMP_DEVICE_IDS = "SCAN_CHANNEL_SNMP_DEVICE_IDS"
KEY_SNMP_ROOM_IDS = "SCAN_CHANNEL_SNMP_ROOM_IDS"
KEY_BUDGET_SECONDS = "SCAN_CHANNEL_BUDGET_SECONDS"
KEY_CIRCUIT_THRESHOLD = "SCAN_CHANNEL_CIRCUIT_THRESHOLD"
KEY_AUTO_ENABLED = "SCAN_CHANNEL_AUTO_ENABLED"
KEY_SNMP_VR_IDS = "SCAN_CHANNEL_SNMP_VR_IDS"
KEY_SNMP_SUBTYPES = "SCAN_CHANNEL_SNMP_SUBTYPES"
KEY_SNMP_SNAPSHOT = "SCAN_CHANNEL_SNMP_SNAPSHOT"

DEFAULT_SNMP_SNAPSHOT_ENABLED = False

ALL_KEYS: tuple[str, ...] = (
    KEY_ENABLED,
    KEY_PRIORITY,
    KEY_SNMP_DEVICE_IDS,
    KEY_SNMP_ROOM_IDS,
    KEY_BUDGET_SECONDS,
    KEY_CIRCUIT_THRESHOLD,
    KEY_AUTO_ENABLED,
    KEY_SNMP_SNAPSHOT,
)

DEFAULT_ENABLED = False
DEFAULT_PRIORITY = "cli,snmp"
DEFAULT_BUDGET_SECONDS = 60.0
DEFAULT_CIRCUIT_THRESHOLD = 5
DEFAULT_AUTO_ENABLED = False


def _parse_code_list(raw: str) -> tuple[str, ...]:
    """解析逗号分隔的通道代码串，去空白、去空段、保序去重。"""
    out: list[str] = []
    for tok in (raw or "").split(","):
        code = tok.strip().lower()
        if code and code not in out:
            out.append(code)
    return tuple(out)


def _parse_int_set(raw: str, what: str) -> frozenset[int]:
    """解析逗号分隔的 ID 串；非整数片段忽略并告警（P2-5 脏值不致命）。

    忽略而非报错的理由：这是**灰度白名单**，写错一个 token 的后果应当只是
    "这台没进灰度"，而不是"整轮扫描起不来"。
    """
    out: set[int] = set()
    for tok in (raw or "").split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            out.add(int(tok))
        except ValueError:
            logger.warning("通道开关 %s 含非整数片段 %r，已忽略", what, tok)
    return frozenset(out)


@dataclass(frozen=True)
class ChannelRuntimeConfig:
    """通道层的运行期开关快照（**纯值**，可跨层传递、可单测直构）。"""

    enabled: bool = DEFAULT_ENABLED
    priority: tuple[str, ...] = ()
    snmp_device_ids: frozenset[int] = field(default_factory=frozenset)
    snmp_room_ids: frozenset[int] = field(default_factory=frozenset)
    snmp_vr_ids: frozenset[int] = field(default_factory=frozenset)
    snmp_subtypes: frozenset[str] = field(default_factory=frozenset)
    budget_seconds: float = DEFAULT_BUDGET_SECONDS
    circuit_threshold: int = DEFAULT_CIRCUIT_THRESHOLD
    auto_enabled: bool = DEFAULT_AUTO_ENABLED
    snmp_snapshot_enabled: bool = DEFAULT_SNMP_SNAPSHOT_ENABLED

    def __post_init__(self) -> None:
        if isinstance(self.priority, str):
            object.__setattr__(self, "priority", _parse_code_list(self.priority))
        else:
            object.__setattr__(self, "priority", tuple(self.priority))
        if not isinstance(self.snmp_device_ids, frozenset):
            object.__setattr__(self, "snmp_device_ids", frozenset(self.snmp_device_ids))
        if not isinstance(self.snmp_room_ids, frozenset):
            object.__setattr__(self, "snmp_room_ids", frozenset(self.snmp_room_ids))

    def snmp_allowed(self, device_id: int | None = None, room_id: int | None = None,
                     virtual_room_id: int | None = None) -> bool:
        """该设备本轮是否允许使用 SNMP 通道。

        三个白名单都为空 ⇒ **不放行**（"空 = 不启用"）。任一非空时按**并集**判定：
        命中 设备ID / 机房ID / **虚拟机房ID**（跨机房灰度维度，2026-10-06 补）其一即可。
        """
        if not self.snmp_device_ids and not self.snmp_room_ids and not self.snmp_vr_ids:
            return False
        if device_id is not None and device_id in self.snmp_device_ids:
            return True
        if room_id is not None and room_id in self.snmp_room_ids:
            return True
        if virtual_room_id is not None and virtual_room_id in self.snmp_vr_ids:
            return True
        return False

    def allowed_channels(self, available: Iterable[str]) -> list[str]:
        """按优先级过滤出本轮**允许参与**的通道代码（顺序 = 优先级）。

        总开关关闭时返回空列表 —— 调用方据此直接走改造前的 CLI 路径，
        这是 G6 的回退点：不需要发版，把开关拨回 false 即可。
        """
        if not self.enabled:
            return []
        have = {c.strip().lower() for c in available}
        ordered = [c for c in self.priority if c in have]
        ordered.extend(c for c in available if c not in self.priority)
        return ordered

    def selector_kwargs(self) -> dict[str, Any]:
        """注入 ``ChannelSelector`` 的构造参数。

        ``circuit_store`` 用 Redis 版（评审 I-6）：进程内计数的致命点是**多 worker
        各算各的、重启清零** —— 生产上扫描进程往往多副本，那等于每个副本都要各自
        踩一遍坑才会熔断。Redis 不可用时 ``RedisCircuitStore`` 内部降级为"不熔断"
        并留 warning，不会把整轮扫描打挂（与它自己的取舍一致）。构造不做 I/O
        （客户端是延迟获取的），因此这里直接 new 一个实例是安全的。
        """
        return {
            "budget_seconds": float(self.budget_seconds),
            "circuit_threshold": int(self.circuit_threshold),
            "circuit_store": RedisCircuitStore(),
        }


def load_channel_runtime_config(
    *,
    reader: Optional[Callable[[str], Any]] = None,
    session: Any = None,
) -> ChannelRuntimeConfig:
    """从动态配置读取一次快照。

    Args:
        reader: 可选注入的读取函数 ``(key) -> value``（**单测用它绕开 Redis /
            app context**）。缺省走 ``MonitorDynamicConfig.get``，需要 app context。
        session: 透传给 ``MonitorDynamicConfig.get`` 的可选 SQLAlchemy Session。

    读不到（Redis 与 DB 皆 miss）时回退本模块的默认值 —— 与 ``get_all()``
    的"miss 回退 default"口径一致，保证**开关没配 = 行为不变**。
    """
    if reader is None:
        from app.services.monitoring.dynamic_config import MonitorDynamicConfig

        def reader(key: str) -> Any:  # type: ignore[misc]
            return MonitorDynamicConfig.get(key, session=session)

    def _get(key: str, default: Any) -> Any:
        try:
            val = reader(key)
        except Exception as e:  # noqa: BLE001 -- 通道开关读取失败退化为默认值（不启用）：不得让采集起不来
            logger.warning("通道开关读取失败 key=%s: %s，按默认值处理", key, e)
            return default
        return default if val is None else val

    enabled = bool(_get(KEY_ENABLED, DEFAULT_ENABLED))
    priority = _parse_code_list(str(_get(KEY_PRIORITY, DEFAULT_PRIORITY)))
    device_ids = _parse_int_set(str(_get(KEY_SNMP_DEVICE_IDS, "")), KEY_SNMP_DEVICE_IDS)
    room_ids = _parse_int_set(str(_get(KEY_SNMP_ROOM_IDS, "")), KEY_SNMP_ROOM_IDS)
    budget = float(_get(KEY_BUDGET_SECONDS, DEFAULT_BUDGET_SECONDS))
    threshold = int(_get(KEY_CIRCUIT_THRESHOLD, DEFAULT_CIRCUIT_THRESHOLD))
    auto_enabled = bool(_get(KEY_AUTO_ENABLED, DEFAULT_AUTO_ENABLED))
    vr_ids = _parse_int_set(str(_get(KEY_SNMP_VR_IDS, "")), KEY_SNMP_VR_IDS)
    subtypes = frozenset(
        s.strip().lower()
        for s in str(_get(KEY_SNMP_SUBTYPES, "")).split(",")
        if s.strip()
    )
    snapshot_enabled = bool(_get(KEY_SNMP_SNAPSHOT, DEFAULT_SNMP_SNAPSHOT_ENABLED))

    return ChannelRuntimeConfig(
        enabled=enabled,
        priority=priority,
        snmp_device_ids=device_ids,
        snmp_room_ids=room_ids,
        snmp_vr_ids=vr_ids,
        snmp_subtypes=subtypes,
        budget_seconds=budget,
        circuit_threshold=threshold,
        auto_enabled=auto_enabled,
        snmp_snapshot_enabled=snapshot_enabled,
    )


def order_by_priority(
    channels: Sequence["BaseChannel"],
    priority: Iterable[str],
) -> list["BaseChannel"]:
    """按优先级串给通道对象排序（供 T-G1 接入点构造 ``ChannelSelector`` 用）。

    未出现在 ``priority`` 里的通道**排到末尾**并保持原相对顺序：新通道没来得及
    登记优先级时，让它排最后（最保守）而不是悄悄跑到 CLI 前面。
    """
    ranks = {code: i for i, code in enumerate(_parse_code_list(",".join(priority)))}
    big = len(ranks)
    return sorted(channels, key=lambda ch: (ranks.get(ch.code, big),))
