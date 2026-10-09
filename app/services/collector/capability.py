# -*- coding: utf-8 -*-
"""多通道采集 · 能力绑定原语（T0.4 / 契约层规格 决策 3：F6 + F10）。

本模块是 ``app/services/collector/`` 的**最底层**之一（与 ``contract.py`` 同级）：
只做一件事 —— 把「能力矩阵声明」与「实现方法」绑成同一个事实，并在**类定义期**
校验。``base_channel.py`` 依赖它，它不依赖任何别的采集层模块。

为什么把装饰器和校验从 ``base_channel.py`` 拆出来：两者都是纯粹的类元编程
（属性标记 + MRO 扫描 + 签名绑定），不含任何采集语义。拆开后 ``base_channel.py``
只剩"通道长什么样"与"collect 怎么编排"，单文件能控制在 300 行以内；更重要的是
"能力如何约束"与"数据如何采集"是两个变更理由，混在一个文件里会互相干扰。

治理点前移到类定义期的成本极低（多扫一次类字典），收益是消灭 F6/F10 那一整类
缺陷 —— 这正是契约层规格 §3.4 决策 3 的落地。
"""
from __future__ import annotations

import inspect
from typing import Any, Callable, Iterable, TypeVar

from app.core.enums import CollectCapability, QualityLevel
from app.services.collector.facts import CAP_FIELD_BY_VALUE

_Fn = TypeVar("_Fn", bound=Callable[..., Any])

_CAPABILITY_ATTR = "__collector_capability__"
_QUALITY_ATTR = "__collector_quality__"
HANDLERS_ATTR = "__collector_handlers__"
DERIVED_CAPABILITIES_FLAG = "__collector_capabilities_derived__"


class ChannelContractError(TypeError):
    """通道契约违规。在类定义（导入）期抛出，不允许构造出违规通道。

    刻意继承 ``TypeError``：契约违规是**编程错误**（类写错了），不是运行期状态；
    调用方没有任何重试/降级能恢复它。让它混进 ``Exception`` 的普通分支反而会被
    上层当成可恢复故障处理 —— F10 的教训正是"把编程错误当成运行态来消化"。
    """


def implements(cap: CollectCapability, quality: QualityLevel) -> Callable[[_Fn], _Fn]:
    """把「能力声明」与「实现方法」绑定成同一事实（F6/F10 的结构性根治）。

    被装饰方法签名必须为 ``(self, device_id: int, timeout: float | None = None)``，
    由 :func:`assert_handler_signature` 在类定义期校验。

    ``quality`` 禁止为 ``NONE``：不实现该能力即表达 NONE。给 ``NONE`` 配一个方法体
    正是"假 advertised"的原形态 —— 矩阵说不支持，类里却登记了实现，两侧都对不上。
    """
    if not isinstance(cap, CollectCapability):
        raise ChannelContractError(f"@implements 的 cap 必须是 CollectCapability，收到 {cap!r}")
    if not isinstance(quality, QualityLevel):
        raise ChannelContractError(f"@implements 的 quality 必须是 QualityLevel，收到 {quality!r}")
    if quality is QualityLevel.NONE:
        raise ChannelContractError(
            f"@implements 不允许声明 {cap.value}=NONE：不实现该能力即可表达 NONE；"
            "带实现体又声明 NONE 会让按矩阵判定与实际能力相反。"
        )

    def _decorate(fn: _Fn) -> _Fn:
        setattr(fn, _CAPABILITY_ATTR, cap)
        setattr(fn, _QUALITY_ATTR, quality)
        return fn

    return _decorate


def cap_value(cap: CollectCapability | str) -> str:
    """能力归一为 ``outcomes`` / ``meta`` 里使用的字符串键。"""
    return cap.value if isinstance(cap, CollectCapability) else str(cap)


def as_capability(cap: CollectCapability | str) -> CollectCapability:
    """入参归一为枚举成员；未知能力**明确报错**（与 ``CollectedFacts.get`` 同口径）。"""
    if isinstance(cap, CollectCapability):
        return cap
    try:
        return CollectCapability(str(cap))
    except ValueError:
        raise ValueError(f"未知采集能力：{cap!r}") from None


def field_of(cap: CollectCapability) -> str:
    """能力 -> ``CollectedFacts`` 字段名（唯一映射表取自 facts 模块，不另起一份）。"""
    field_name = CAP_FIELD_BY_VALUE.get(cap.value)
    if field_name is None:
        raise ValueError(f"未知采集能力：{cap!r}")
    return field_name


def collect_declarations(cls: type) -> dict[CollectCapability, tuple[QualityLevel, str]]:
    """沿 MRO（基类 -> 子类）收集 ``@implements``：``{cap: (档位, 方法名)}``。

    走 MRO 而不是只看 ``vars(cls)``：把公共能力抽到**中间基类**是常规做法，只看本类
    字典会把继承来的能力判成"实现了却没声明"。子类覆盖基类实现时**子类胜出** ——
    逆序遍历天然等价于方法覆盖语义。

    同一个类体内重复标注同一个 capability 直接报错：dict 迭代会让其中一个静默胜出，
    那时"哪份实现生效"取决于定义顺序，比报错难排查得多。
    """
    found: dict[CollectCapability, tuple[QualityLevel, str]] = {}
    for klass in reversed(cls.__mro__):
        seen_in_class: dict[CollectCapability, str] = {}
        for name, member in vars(klass).items():
            cap = getattr(member, _CAPABILITY_ATTR, None)
            if cap is None:
                continue
            if previous := seen_in_class.get(cap):
                raise ChannelContractError(
                    f"{klass.__name__} 重复实现能力 {cap.value}：{previous} 与 {name}"
                )
            seen_in_class[cap] = name
            found[cap] = (getattr(member, _QUALITY_ATTR), name)
    return found


def assert_no_manual_capabilities(cls: type, exempt: Iterable[type] = ()) -> None:
    """禁止类体里再手写 ``capabilities`` —— 那是 F6 复发的入口。

    旧口径允许"手写矩阵 + 手写方法"并存，两者可以合法地不一致（正是 OPTICS 事故的
    成因）。裁决 3 之后矩阵的唯一来源是被装饰的实现，手工字典一律拒绝 —— 哪怕它与
    实现完全一致。放行"当前一致的那份"等于给漂移留门：今天对，明天改实现就错了。
    """
    allowed = {id(base) for base in exempt}
    manual = [
        klass.__name__
        for klass in cls.__mro__
        if id(klass) not in allowed
        and klass is not object
        and not vars(klass).get(DERIVED_CAPABILITIES_FLAG, False)
        and "capabilities" in vars(klass)
    ]
    if manual:
        raise ChannelContractError(
            f"{cls.__name__} 在 {manual} 中手工声明了 capabilities —— "
            "能力矩阵只能由 @implements 推导，请删掉该字典。"
        )


def assert_handler_signature(channel: str, cap: CollectCapability, fn: Any) -> None:
    """处理器必须能被模板方法按 ``(device_id, timeout=...)`` 调用。

    用 ``Signature.bind`` 而不是逐个参数名比对：后者只证明"名字对"，前者证明"调用
    成立"。摸不到但真实存在的坑是缺 ``timeout`` 参数的处理器 —— 名字都对，却在模板
    传入剩余预算时缺参报错，而那次报错会被记成 FAILED，伪装成设备故障。
    """
    parameters = list(inspect.signature(fn).parameters)
    if not parameters or parameters[0] != "self":
        raise ChannelContractError(
            f"{channel} 的能力 {cap.value} 处理器必须是实例方法（首个参数名须为 self），"
            f"实际为 {parameters[0] if parameters else '<无参数>'!r}"
        )
    try:
        inspect.signature(fn).bind(object(), 1, timeout=None)
    except TypeError as exc:
        raise ChannelContractError(
            f"{channel} 的能力 {cap.value} 处理器签名不兼容模板调用 "
            f"(self, device_id, timeout=None)：{exc}"
        ) from exc


__all__ = [
    "DERIVED_CAPABILITIES_FLAG",
    "HANDLERS_ATTR",
    "ChannelContractError",
    "as_capability",
    "assert_handler_signature",
    "assert_no_manual_capabilities",
    "cap_value",
    "collect_declarations",
    "field_of",
    "implements",
]
