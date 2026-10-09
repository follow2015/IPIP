# -*- coding: utf-8 -*-
"""工单插件 · 能力绑定原语（同构于 ``app/services/collector/capability.py``）。

本模块与采集侧的能力原语是**同一套思想的两次落地**，不是复制粘贴：

- 采集侧要根治的是「矩阵说支持、实现却不存在」（F6/F10，OPTICS 事故的成因）；
- 工单侧要根治的是同一形状的病：**适配器声称支持状态回写，实际方法体是 `pass`**。
  它的后果比采集侧更硬 —— 采集错了只是数据缺项，工单回写错了是**外部系统与内核
  状态长期不一致，且没人知道**。

因此这里沿用同一条裁决：**能力不是声明出来的，是由 `@implements` 标注的实现方法
在类定义期推导出来的**。手写 `capabilities = {...}` 一律拒绝，哪怕它与实现完全一致
—— 放行"当前一致的那份"等于给漂移留门（今天对，明天改实现就错了）。

与采集侧的两处**刻意差异**（不是漏抄）：

1. **能力枚举留在域内**（`TicketCapability` 在本模块，`CollectCapability` 在
   `app/core/enums.py`）。采集能力被 selector / facts / 动态配置等跨域消费，必须进核心枚举；
   工单能力只被工单内核与插件消费，放进核心枚举只会让核心文件随每个业务域膨胀。
   而 **`QualityLevel` 复用核心的** —— 它是跨领域通用的质量档位（FULL/PARTIAL/NONE），
   再造一套会让"PARTIAL 到底指什么"出现两个答案。
2. **按能力校验签名，而不是全插件统一签名**。采集侧所有 handler 都是
   `(self, device_id, timeout=None)`，可以统一；工单侧五个能力形态天然不同
   （身份解析收 external_id、建单收 payload、状态映射收字符串……）。统一成一个签名
   会逼出大量 `*args` 与内部再解析，反而把类型信息丢光。故改为**每个能力一张形参模板**
   （`HANDLER_PARAM_TEMPLATE`），校验时按模板 `Signature.bind` —— 与采集侧"证明调用成立
   而非名字对得上"的意图一致。
"""

from __future__ import annotations

import inspect
from enum import Enum
from typing import Any, Callable, Iterable, TypeVar

from app.core.enums import QualityLevel

_Fn = TypeVar("_Fn", bound=Callable[..., Any])

_CAPABILITY_ATTR = "__ticket_capability__"
_QUALITY_ATTR = "__ticket_quality__"
HANDLERS_ATTR = "__ticket_handlers__"
DERIVED_CAPABILITIES_FLAG = "__ticket_capabilities_derived__"


class TicketCapability(str, Enum):
    """工单插件的能力（插座上的孔位）。

    五个孔位刻意**只包含跨系统边界的动作**：凡是"系统内部就能完成"的事
    （发站内信、写流转日志、算 SLA）都不该做成能力 —— 那是内核的职责，
    做成能力等于把内核逻辑外包给插件，插件一下线内核就残废。

    尤其注意 **`NOTIFY` 不在其中**：企微 / 飞书 / 钉钉的**消息推送**由既有
    ``app/services/channels/`` 广播渠道承担（已在 ``app/__init__.py`` 注册），
    工单只发事件。在工单域重建一套通知渠道是第二套通知设施，不做。
    """

    IDENTITY = "identity"  # 外部身份 -> 内部 user_id
    INBOUND_CREATE = "inbound_create"  # 外部 payload -> 内核工单草稿
    INBOUND_STATUS = "inbound_status"  # 外部状态 -> 内核状态
    OUTBOUND_STATUS = "outbound_status"  # 内核状态 -> 外部状态
    PULL_SYNC = "pull_sync"  # 主动拉取外部工单（双向同步）


HANDLER_PARAM_TEMPLATE: dict[TicketCapability, tuple[str, ...]] = {
    TicketCapability.IDENTITY: ("self", "external_id"),
    TicketCapability.INBOUND_CREATE: ("self", "payload"),
    TicketCapability.INBOUND_STATUS: ("self", "external_status"),
    TicketCapability.OUTBOUND_STATUS: ("self", "kernel_status"),
    TicketCapability.PULL_SYNC: ("self", "since"),
}


class PluginContractError(TypeError):
    """插件契约违规。在**类定义（导入）期**抛出，不允许构造出违规插件。

    刻意继承 ``TypeError``（与 ``ChannelContractError`` 同口径）：契约违规是编程错误，
    不是运行期状态；调用方没有任何重试 / 降级能恢复它。让它混进普通 ``Exception``
    分支反而会被当成可恢复故障消化掉。
    """


def implements(cap: TicketCapability, quality: QualityLevel) -> Callable[[_Fn], _Fn]:
    """把「能力声明」与「实现方法」绑定成同一事实。

    ``quality`` 禁止为 ``NONE``：不实现该能力即表达 NONE。给 NONE 配一个方法体正是
    "假 advertised" 的原形态 —— 矩阵说不支持，类里却登记了实现，两侧对不上。
    """
    if not isinstance(cap, TicketCapability):
        raise PluginContractError(f"@implements 的 cap 必须是 TicketCapability，收到 {cap!r}")
    if not isinstance(quality, QualityLevel):
        raise PluginContractError(f"@implements 的 quality 必须是 QualityLevel，收到 {quality!r}")
    if quality is QualityLevel.NONE:
        raise PluginContractError(
            f"@implements 不允许声明 {cap.value}=NONE：不实现该能力即可表达 NONE；"
            "带实现体又声明 NONE 会让按矩阵判定与实际能力相反。"
        )

    def _decorate(fn: _Fn) -> _Fn:
        setattr(fn, _CAPABILITY_ATTR, cap)
        setattr(fn, _QUALITY_ATTR, quality)
        return fn

    return _decorate


def cap_value(cap: TicketCapability | str) -> str:
    """能力归一为字符串键。"""
    return cap.value if isinstance(cap, TicketCapability) else str(cap)


def as_capability(cap: TicketCapability | str) -> TicketCapability:
    """入参归一为枚举成员；未知能力**明确报错**（与采集侧同口径）。"""
    if isinstance(cap, TicketCapability):
        return cap
    try:
        return TicketCapability(str(cap))
    except ValueError:
        raise ValueError(f"未知工单插件能力：{cap!r}") from None


def collect_declarations(cls: type) -> dict[TicketCapability, tuple[QualityLevel, str]]:
    """沿 MRO（基类 -> 子类）收集 ``@implements``：``{cap: (档位, 方法名)}``。

    走 MRO 而不是只看 ``vars(cls)``：把公共能力抽到中间基类是常规做法，只看本类字典
    会把继承来的能力判成"实现了却没声明"。逆序遍历天然等价于方法覆盖语义（子类胜出）。

    同一个类体内重复标注同一个 capability 直接报错：dict 迭代会让其中一个静默胜出，
    那时"哪份实现生效"取决于定义顺序，比报错难排查得多。
    """
    found: dict[TicketCapability, tuple[QualityLevel, str]] = {}
    for klass in reversed(cls.__mro__):
        seen_in_class: dict[TicketCapability, str] = {}
        for name, member in vars(klass).items():
            cap = getattr(member, _CAPABILITY_ATTR, None)
            if cap is None:
                continue
            if previous := seen_in_class.get(cap):
                raise PluginContractError(f"{klass.__name__} 重复实现能力 {cap.value}：{previous} 与 {name}")
            seen_in_class[cap] = name
            found[cap] = (getattr(member, _QUALITY_ATTR), name)
    return found


def assert_no_manual_capabilities(cls: type, exempt: Iterable[type] = ()) -> None:
    """禁止类体里再手写 ``capabilities`` —— 那是"谎称支持"复发的入口。

    [WARN] 必须查**该类自身** ``__dict__``，不能用 ``getattr``：派生标记由
    ``__init_subclass__`` setattr 到类上、会沿 MRO 继承。getattr 写法下
    ``class X(NoopPlugin): capabilities = {...}``（父类已派生）会被判成"已派生"而放行，
    手工矩阵随后被派生结果静默覆盖 —— 正是采集侧 OPTICS 事故的形状。
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
        raise PluginContractError(
            f"{cls.__name__} 在 {manual} 中手工声明了 capabilities —— 能力矩阵只能由 @implements 推导，请删掉该字典。"
        )


def assert_handler_signature(plugin: str, cap: TicketCapability, fn: Any) -> None:
    """处理器必须能被模板方法按该能力的形参模板调用。

    三道闸，依次证明"名字对、元数对、调用成立"：

    1. 形参名前缀必须与模板一致（只验证位置参数名会导致 `payload` 与 `external_id`
       互换这类错误一路绿到运行期）；
    2. 模板之外的额外形参必须带默认值（否则模板调用必然缺参）；
    3. ``Signature.bind`` 按模板实参绑定，证明调用真的成立。

    **额外禁止 ``**kwargs``**（裁决 U3）：``to_kernel(self, payload, **kwargs)`` 这种
    写法会让"插件读了哪些外部字段"变成不可知 —— 未声明字段被静默带进内核，
    正是 OD-14 里 `/switch/options` 只给 id+name、`/rooms/name-options` 无 id
    那类"没逐个对齐字段就改调用方"事故的同一形状。字段可见性由 ``READS`` 承担，
    签名层面直接堵死透传是更硬的保证（类定义期就失败，而不是上线后才发现）。
    """
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError) as exc:  # 非可调用 / 内置对象
        raise PluginContractError(f"{plugin} 的能力 {cap.value} 处理器不可检查：{exc}") from exc

    params = list(signature.parameters.values())
    names = [p.name for p in params]
    expected = HANDLER_PARAM_TEMPLATE.get(cap)
    if expected is None:  # pragma: no cover - 新增能力忘了配模板时暴露
        raise PluginContractError(f"能力 {cap.value} 缺少形参模板，请先补 HANDLER_PARAM_TEMPLATE")

    if names[: len(expected)] != list(expected):
        raise PluginContractError(
            f"{plugin} 的能力 {cap.value} 处理器形参应为 ({', '.join(expected)})，"
            f"实际为 ({', '.join(names[: len(expected)]) or '<空>'})"
        )

    for extra in params[len(expected) :]:
        if extra.kind is inspect.Parameter.VAR_KEYWORD or extra.kind is inspect.Parameter.VAR_POSITIONAL:
            raise PluginContractError(
                f"{plugin} 的能力 {cap.value} 处理器不得使用 *args / **kwargs "
                f"（裁决 U3：字段必须经 READS 显式声明，禁止透传），实际出现 {extra.name}"
            )
        if extra.default is inspect.Parameter.empty:
            raise PluginContractError(
                f"{plugin} 的能力 {cap.value} 处理器额外形参 {extra.name} 必须带默认值，否则模板方法调用时必然缺参。"
            )

    try:
        signature.bind(*([object()] * len(expected)))
    except TypeError as exc:
        raise PluginContractError(
            f"{plugin} 的能力 {cap.value} 处理器签名不兼容模板调用 ({', '.join(expected)})：{exc}"
        ) from exc


__all__ = [
    "DERIVED_CAPABILITIES_FLAG",
    "HANDLERS_ATTR",
    "HANDLER_PARAM_TEMPLATE",
    "PluginContractError",
    "TicketCapability",
    "as_capability",
    "assert_handler_signature",
    "assert_no_manual_capabilities",
    "cap_value",
    "collect_declarations",
    "implements",
]
