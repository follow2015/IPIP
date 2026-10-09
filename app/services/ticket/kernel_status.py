# -*- coding: utf-8 -*-
"""工单内核 · 状态机（9 态 / 19 条边 / 守卫）。

权威定义来自 ``docs/design/IPIP-通用工单系统设计文档.md`` §4.1–§4.2（v1.3，内核结论沿用）。
本模块是那份表格的**可执行形态**：表格改了必须改这里，这里改了必须回写表格 ——
两份不允许各自演化。契约测试会数边数（19），漏一条或多一条立刻转红。

三件事刻意做成现在这个形状：

1. **转换表集中定义，禁止散落 if-else**。
   状态机一旦散进业务方法，"当前一共允许哪些转换"就没有一个地方能回答，
   审计时只能靠读代码归纳 —— 而 §11 的审计链要的正是"能被机器回答"。

2. **守卫是纯函数，返回拒绝原因码而不是抛异常**。
   抛异常会把"能不能做"和"去做"绑成一件事，于是前端想预先置灰按钮就得
   try/except 探一次。拆开之后 ``can_transition`` 用于渲染、``resolve_transition``
   用于执行，两边共用同一套守卫，不可能对不上。

3. **拒绝原因码是可编程识别的常量**，不是中文文案。
   前端要按 reason 决定提示语（"请刷新后重试" vs "不能审批自己的单子"），
   靠 message 匹配既脆又不可本地化。

[WARN] ``TicketStatus`` **当前未纳入** ``app/core/enums.py`` 的 ``GENERATED_ENUMS``。
理由与 ``TicketCapability`` 同源：现在没有任何前端消费方、也没有落库的表，
纳管会让 ``make sync-enums`` 产出无人使用的前端符号，并被
``tests/test_frontend_enum_drift.py`` 判为缺 i18n 节点。
**Task 6 前端真正消费状态时再纳管并补 zh-CN / en-US 词条** —— 那才是它该进注册表的时点。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from app.exceptions.business import TicketTransitionError



class TicketType(str, Enum):
    """工单类型（v1.3 §2：incident / change / service_request / task）。"""

    INCIDENT = "incident"
    CHANGE = "change"
    SERVICE_REQUEST = "service_request"
    TASK = "task"


class TicketStatus(str, Enum):
    """内核工单状态（9 态，v1.3 §4.1）。

    [WARN] ``resolved`` / ``closed`` **不是状态**，它们是 ``tickets`` 上的两个时间戳
    字段（``resolved_at`` / ``closed_at``）。把它们当状态是 PM 底稿的形状，
    已由裁决 A3 否决 —— 存量 ``applied`` 映射的是 ``completed``，不是
    "resolved → closed"这条不存在的路径。
    """

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    PENDING_VERIFICATION = "pending_verification"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TicketAction(str, Enum):
    """状态机动作（13 个）。"""

    CREATE = "create"
    SUBMIT = "submit"
    CANCEL = "cancel"
    APPROVE = "approve"
    REJECT = "reject"
    START = "start"
    REOPEN = "reopen"
    SUBMIT_VERIFICATION = "submit_verification"
    HOLD = "hold"
    RESUME = "resume"
    ACCEPT = "accept"
    REJECT_VERIFICATION = "reject_verification"
    CREATE_AUTO = "create_auto"


class RejectReason(str, Enum):
    """守卫拒绝原因码（前端按它选提示语，不要用文案匹配）。"""

    UNKNOWN_EDGE = "UNKNOWN_EDGE"
    TITLE_REQUIRED = "TITLE_REQUIRED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    CI_REQUIRED = "CI_REQUIRED"
    CI_TYPE_NOT_DEVICE = "CI_TYPE_NOT_DEVICE"
    BACKUP_REQUIRED = "BACKUP_REQUIRED"
    SELF_APPROVAL_DENIED = "SELF_APPROVAL_DENIED"
    COMMENT_REQUIRED = "COMMENT_REQUIRED"
    HOLD_REASON_REQUIRED = "HOLD_REASON_REQUIRED"
    NO_DISPATCHABLE_COMMAND = "NO_DISPATCHABLE_COMMAND"
    APPLY_NOT_SUCCESS = "APPLY_NOT_SUCCESS"
    NOT_ALERT_AUTO_INCIDENT = "NOT_ALERT_AUTO_INCIDENT"


TERMINAL_STATUSES = frozenset({TicketStatus.COMPLETED, TicketStatus.CANCELLED})

TICKET_STATUSES: frozenset[str] = frozenset(s.value for s in TicketStatus)

SOURCE_ALERT_AUTO = "alert_auto"




@dataclass(frozen=True)
class TransitionContext:
    """守卫判定所需的全部事实。

    刻意做成**扁平的只读快照**而不是传 ORM 实体：状态机是纯逻辑层，
    传实体进来就等于让它能摸数据库，单测必须建表；而"审批人是不是申请人"
    这类判定根本不需要实体。

    [WARN] ``permissions`` 是**调用方已解析好的权限集合**，不是 user_id：
    状态机不做权限查询。谁有 ``ticket:approve`` 由 RBAC 决定（v1.3 §7），
    状态机只回答"拿着这些权限能不能走这条边"。
    """

    ticket_type: TicketType = TicketType.TASK
    title: str = ""
    has_primary_ci: bool = False
    primary_ci_type: Optional[str] = None
    has_backup: bool = False
    can_snapshot: bool = False
    has_dispatchable_command: bool = False
    apply_status: Optional[str] = None
    requester_id: Optional[int] = None
    actor_id: Optional[int] = None
    comment: str = ""
    source: Optional[str] = None
    permissions: frozenset[str] = field(default_factory=frozenset)



_Guard = Callable[[TransitionContext], Optional[RejectReason]]


def _require_permission(code: str) -> _Guard:
    """权限守卫工厂。

    [WARN] 必须用工厂显式绑定权限点，不要写成"守卫读 ctx.permission_code"：
    那样权限点就从转换表里消失了，"这条边需要什么权限"又变成一个需要读代码
    归纳的问题 —— 与集中定义转换表的初衷相悖。
    """

    def _guard(ctx: TransitionContext) -> Optional[RejectReason]:
        return None if code in ctx.permissions else RejectReason.PERMISSION_DENIED

    return _guard


def _title_required(ctx: TransitionContext) -> Optional[RejectReason]:
    return None if ctx.title.strip() else RejectReason.TITLE_REQUIRED


def _comment_required(ctx: TransitionContext) -> Optional[RejectReason]:
    return None if ctx.comment.strip() else RejectReason.COMMENT_REQUIRED


def _hold_reason_required(ctx: TransitionContext) -> Optional[RejectReason]:
    return None if ctx.comment.strip() else RejectReason.HOLD_REASON_REQUIRED


def _not_self_approval(ctx: TransitionContext) -> Optional[RejectReason]:
    """审批人不得是申请人。

    继承存量 ``device_config_service`` 的禁自审语义 —— 那条规则在旧实现里就存在，
    迁移后必须原样落到统一状态机，不能因为"重写"就丢掉。
    """
    if ctx.requester_id is not None and ctx.requester_id == ctx.actor_id:
        return RejectReason.SELF_APPROVAL_DENIED
    return None


def _change_ci_constraints(ctx: TransitionContext) -> Optional[RejectReason]:
    """change 的 CI 约束（v1.3 §3.3 分级：只有 change 强制）。

    [WARN] 必须在**应用层**判定，绝不能写成主表的 NOT NULL 列约束 ——
    否则巡检（机房级）与批量上架（room 级）这类没有 device 的场景直接做不出来。
    """
    if ctx.ticket_type is not TicketType.CHANGE:
        return None
    if not ctx.has_primary_ci:
        return RejectReason.CI_REQUIRED
    if ctx.primary_ci_type != "device":
        return RejectReason.CI_TYPE_NOT_DEVICE
    return None


def _change_backup_or_snapshot(ctx: TransitionContext) -> Optional[RejectReason]:
    """change 提交须有备份或可现采快照。"""
    if ctx.ticket_type is not TicketType.CHANGE:
        return None
    return None if (ctx.has_backup or ctx.can_snapshot) else RejectReason.BACKUP_REQUIRED


def _dispatchable_command_required(ctx: TransitionContext) -> Optional[RejectReason]:
    if ctx.ticket_type is not TicketType.CHANGE:
        return None
    return None if ctx.has_dispatchable_command else RejectReason.NO_DISPATCHABLE_COMMAND


def _apply_success_required(ctx: TransitionContext) -> Optional[RejectReason]:
    if ctx.ticket_type is not TicketType.CHANGE:
        return None
    return None if ctx.apply_status == "success" else RejectReason.APPLY_NOT_SUCCESS


def _alert_auto_incident_only(ctx: TransitionContext) -> Optional[RejectReason]:
    """自动建单只认告警源 + incident（v1.3 §4.2 M03）。

    缺这条守卫时，自动建单要么全量被拒、要么绕过状态机直写字段 ——
    后者会摧毁整条审计链。
    """
    if ctx.source == SOURCE_ALERT_AUTO and ctx.ticket_type is TicketType.INCIDENT:
        return None
    return RejectReason.NOT_ALERT_AUTO_INCIDENT




@dataclass(frozen=True)
class _Edge:
    to_status: TicketStatus
    guards: tuple[_Guard, ...] = ()


_TRANSITIONS: dict[tuple[Optional[TicketStatus], TicketAction], _Edge] = {
    (None, TicketAction.CREATE): _Edge(TicketStatus.DRAFT, (_require_permission("ticket:create"), _title_required)),
    (TicketStatus.DRAFT, TicketAction.SUBMIT): _Edge(
        TicketStatus.PENDING_APPROVAL, (_change_ci_constraints, _change_backup_or_snapshot)
    ),
    (TicketStatus.DRAFT, TicketAction.CANCEL): _Edge(TicketStatus.CANCELLED),
    (TicketStatus.PENDING_APPROVAL, TicketAction.APPROVE): _Edge(
        TicketStatus.APPROVED, (_require_permission("ticket:approve"), _not_self_approval)
    ),
    (TicketStatus.PENDING_APPROVAL, TicketAction.REJECT): _Edge(
        TicketStatus.REJECTED, (_require_permission("ticket:approve"), _comment_required)
    ),
    (TicketStatus.PENDING_APPROVAL, TicketAction.CANCEL): _Edge(TicketStatus.CANCELLED),
    (TicketStatus.APPROVED, TicketAction.START): _Edge(TicketStatus.IN_PROGRESS, (_dispatchable_command_required,)),
    (TicketStatus.APPROVED, TicketAction.CANCEL): _Edge(TicketStatus.CANCELLED),
    (TicketStatus.REJECTED, TicketAction.REOPEN): _Edge(TicketStatus.DRAFT),
    (TicketStatus.REJECTED, TicketAction.CANCEL): _Edge(TicketStatus.CANCELLED),
    (TicketStatus.IN_PROGRESS, TicketAction.SUBMIT_VERIFICATION): _Edge(
        TicketStatus.PENDING_VERIFICATION, (_apply_success_required,)
    ),
    (TicketStatus.IN_PROGRESS, TicketAction.HOLD): _Edge(TicketStatus.ON_HOLD, (_hold_reason_required,)),
    (TicketStatus.IN_PROGRESS, TicketAction.CANCEL): _Edge(TicketStatus.CANCELLED),
    (TicketStatus.ON_HOLD, TicketAction.RESUME): _Edge(TicketStatus.IN_PROGRESS),
    (TicketStatus.ON_HOLD, TicketAction.CANCEL): _Edge(TicketStatus.CANCELLED),
    (TicketStatus.PENDING_VERIFICATION, TicketAction.ACCEPT): _Edge(TicketStatus.COMPLETED),
    (TicketStatus.PENDING_VERIFICATION, TicketAction.REJECT_VERIFICATION): _Edge(
        TicketStatus.IN_PROGRESS, (_comment_required,)
    ),
    (TicketStatus.PENDING_VERIFICATION, TicketAction.CANCEL): _Edge(TicketStatus.CANCELLED),
    (None, TicketAction.CREATE_AUTO): _Edge(TicketStatus.IN_PROGRESS, (_alert_auto_incident_only,)),
}

SPEC_TRANSITION_COUNT = 19




def _coerce_status(status: TicketStatus | str | None) -> Optional[TicketStatus]:
    if status is None:
        return None
    return TicketStatus(status) if isinstance(status, str) else status


def _coerce_action(action: TicketAction | str) -> TicketAction:
    return TicketAction(action) if isinstance(action, str) else action


def get_edge(
    from_status: TicketStatus | str | None,
    action: TicketAction | str,
) -> Optional[_Edge]:
    """取转换边；不存在返回 ``None``（**不抛**，供渲染与预检查用）。"""
    return _TRANSITIONS.get((_coerce_status(from_status), _coerce_action(action)))


def allowed_actions(from_status: TicketStatus | str | None) -> tuple[TicketAction, ...]:
    """该状态下所有可行动作（按转换表定义顺序）。"""
    current = _coerce_status(from_status)
    return tuple(a for (f, a) in _TRANSITIONS if f is current)


def is_terminal(status: TicketStatus | str) -> bool:
    """是否终态。终态 = 没有任何出边（不额外维护清单，见 ``TERMINAL_STATUSES`` 注释）。"""
    return not allowed_actions(status)


def can_transition(
    from_status: TicketStatus | str | None,
    action: TicketAction | str,
    ctx: Optional[TransitionContext] = None,
) -> tuple[bool, Optional[RejectReason]]:
    """能不能走这条边。返回 ``(是否允许, 拒绝原因)`` —— 不抛异常。

    ``ctx`` 为 ``None`` 时只判**边是否存在**，不跑守卫（用于"这个动作在当前状态
    至少是合法形状吗"这类粗筛）。
    """
    edge = get_edge(from_status, action)
    if edge is None:
        return False, RejectReason.UNKNOWN_EDGE
    if ctx is None:
        return True, None
    for guard in edge.guards:
        if (reason := guard(ctx)) is not None:
            return False, reason
    return True, None


def resolve_transition(
    from_status: TicketStatus | str | None,
    action: TicketAction | str,
    ctx: Optional[TransitionContext] = None,
) -> TicketStatus:
    """执行转换判定，返回目标状态；不允许则抛 ``TicketTransitionError``。

    这是**唯一**应该被服务层调用的入口：渲染用 ``can_transition``、执行用本函数，
    两者共用同一套守卫，不可能出现"按钮亮着但一点就报错"。
    """
    current = _coerce_status(from_status)
    action = _coerce_action(action)
    edge = get_edge(current, action)
    if edge is None:
        raise TicketTransitionError(
            from_status=current.value if current else None,
            action=action.value,
            reason=RejectReason.UNKNOWN_EDGE.value,
        )
    for guard in edge.guards:
        if (reason := guard(ctx or TransitionContext())) is not None:
            raise TicketTransitionError(
                from_status=current.value if current else None,
                action=action.value,
                reason=reason.value,
                to_status=edge.to_status.value,
            )
    return edge.to_status


def transitions() -> tuple[tuple[Optional[TicketStatus], TicketAction, TicketStatus], ...]:
    """全量转换表的只读快照（供测试与审计导出，业务代码不要依赖它做判定）。"""
    return tuple((f, a, e.to_status) for (f, a), e in _TRANSITIONS.items())


__all__ = [
    "RejectReason",
    "SOURCE_ALERT_AUTO",
    "SPEC_TRANSITION_COUNT",
    "TERMINAL_STATUSES",
    "TICKET_STATUSES",
    "TicketAction",
    "TicketStatus",
    "TicketType",
    "TransitionContext",
    "allowed_actions",
    "can_transition",
    "get_edge",
    "is_terminal",
    "resolve_transition",
    "transitions",
]
