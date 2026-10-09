# -*- coding: utf-8 -*-
"""
业务逻辑异常模块

定义业务逻辑相关的异常类。
"""

from typing import Any, Dict, Optional

from .base import BaseAppException


class BusinessLogicError(BaseAppException):
    """业务逻辑异常基类

    当业务规则验证失败或业务逻辑错误时抛出此类异常。
    """

    def __init__(
        self, message: str, code: Optional[str] = None, details: Optional[Dict[str, Any]] = None, status_code: int = 400
    ):
        """初始化业务逻辑异常

        Args:
            message: 异常消息
            code: 异常代码
            details: 异常详情
            status_code: HTTP状态码
        """
        super().__init__(message=message, code=code or "BUSINESS_LOGIC_ERROR", details=details, status_code=status_code)


class UserNotFoundError(BusinessLogicError):
    """用户不存在异常

    当查找的用户不存在时抛出此异常。
    """

    def __init__(self, user_identifier: Optional[str] = None, message: Optional[str] = None):
        """初始化用户不存在异常

        Args:
            user_identifier: 用户标识符（ID、用户名等）
            message: 自定义异常消息
        """
        if not message:
            if user_identifier:
                message = f"用户不存在：{user_identifier}"
            else:
                message = "用户不存在"

        details = {}
        if user_identifier:
            details["user_identifier"] = user_identifier

        super().__init__(message=message, code="USER_NOT_FOUND", details=details, status_code=404)


class DuplicateUserError(BusinessLogicError):
    """用户重复异常

    当尝试创建已存在的用户时抛出此异常。
    """

    def __init__(self, field: str, value: str, message: Optional[str] = None):
        """初始化用户重复异常

        Args:
            field: 重复的字段名（如username、email）
            value: 重复的值
            message: 自定义异常消息
        """
        if not message:
            field_names = {"username": "用户名", "email": "邮箱", "phone": "手机号"}
            field_display = field_names.get(field, field)
            message = f"{field_display}已存在"

        super().__init__(message=message, code="DUPLICATE_USER", details={"field": field}, status_code=409)


class InsufficientPermissionError(BusinessLogicError):
    """权限不足异常

    当用户没有足够权限执行操作时抛出此异常。
    """

    def __init__(
        self, required_permission: Optional[str] = None, resource: Optional[str] = None, message: Optional[str] = None
    ):
        """初始化权限不足异常

        Args:
            required_permission: 所需权限
            resource: 相关资源
            message: 自定义异常消息
        """
        if not message:
            if required_permission and resource:
                message = f"权限不足，需要 {required_permission} 权限访问 {resource}"
            elif required_permission:
                message = f"权限不足，需要 {required_permission} 权限"
            else:
                message = "权限不足"

        details = {}
        if required_permission:
            details["required_permission"] = required_permission
        if resource:
            details["resource"] = resource

        super().__init__(message=message, code="INSUFFICIENT_PERMISSION", details=details, status_code=403)


class InvalidOperationError(BusinessLogicError):
    """无效操作异常

    当尝试执行无效或不允许的操作时抛出此异常。
    """

    def __init__(self, operation: str, reason: Optional[str] = None, message: Optional[str] = None):
        """初始化无效操作异常

        Args:
            operation: 操作名称
            reason: 无效的原因
            message: 自定义异常消息
        """
        if not message:
            if reason:
                message = f"无效操作 {operation}：{reason}"
            else:
                message = f"无效操作：{operation}"

        details = {"operation": operation}
        if reason:
            details["reason"] = reason

        super().__init__(message=message, code="INVALID_OPERATION", details=details)


class ResourceConflictError(BusinessLogicError):
    """资源冲突异常

    当资源处于冲突状态时抛出此异常。
    """

    def __init__(
        self,
        resource_type: str,
        resource_id: Optional[str] = None,
        conflict_reason: Optional[str] = None,
        message: Optional[str] = None,
    ):
        """初始化资源冲突异常

        Args:
            resource_type: 资源类型
            resource_id: 资源ID
            conflict_reason: 冲突原因
            message: 自定义异常消息
        """
        if not message:
            if resource_id and conflict_reason:
                message = f"{resource_type} {resource_id} 冲突：{conflict_reason}"
            elif resource_id:
                message = f"{resource_type} {resource_id} 存在冲突"
            else:
                message = f"{resource_type} 存在冲突"

        details = {"resource_type": resource_type}
        if resource_id:
            details["resource_id"] = resource_id
        if conflict_reason:
            details["conflict_reason"] = conflict_reason

        super().__init__(message=message, code="RESOURCE_CONFLICT", details=details, status_code=409)


class LayoutMarkerVersionConflict(BusinessLogicError):
    """占位标记乐观锁版本冲突（WP-7）

    批量编辑端点的 CAS（UPDATE 谓词带期望版本）未命中时抛出：
    标记在"读-改-写"窗口内被他人改过，继续写会静默覆盖（lost-update）。
    API 层映射为 409 + ``ROOM_MARKER_VERSION_CONFLICT``（可编程识别），
    ``conflicts`` 列出每个冲突标记的 (marker_id, expected, current)。

    .. note:: ``current`` 是**尽力而为**值（评审 20260924 §2.4）：CAS 未命中后
        是在**同一个 REPEATABLE READ 事务**内回读的，若本事务此前已开始读，
        拿到的是快照版本而不是对方刚写入的新版本。行为正确性不受影响（整批仍
        回滚），但**不要把它当成"真实现状"写进用户可见文案** —— 那会编数据。
    """

    def __init__(self, conflicts):
        """Args:
        conflicts: [(marker_id, expected_version, current_version), ...]
        """
        self.conflicts = list(conflicts)
        detail = "；".join(f"标记#{mid}（提交基于 v{exp}）" for mid, exp, _cur in self.conflicts)
        super().__init__(
            message=f"以下标记已被他人修改，请刷新布局后重试：{detail}",
            code="LAYOUT_MARKER_VERSION_CONFLICT",
            details={"conflicts": self.conflicts},
            status_code=409,
        )


class CabinetVersionConflict(BusinessLogicError):
    """机柜乐观锁版本冲突（迁移 0020）

    批量换位端点的 CAS（UPDATE 谓词带期望版本）未命中时抛出：机柜在"读-改-写"
    窗口内被他人改过，继续写会静默覆盖（lost-update）。API 层映射为 409 +
    ``CABINET_VERSION_CONFLICT``（可编程识别），``conflicts`` 列出每个冲突机柜
    的 (cabinet_id, expected, current)。

    与 ``LayoutMarkerVersionConflict`` 同型但独立：两者的错误码与前端处理动作
    不同（标记冲突重拉布局，机柜冲突重拉机柜列表），混用会让前端无法分派。

    ``current`` 同样是**尽力而为**值（同 §2.4，RR 快照回读），见
    ``LayoutMarkerVersionConflict`` 的说明。
    """

    def __init__(self, conflicts):
        """Args:
        conflicts: [(cabinet_id, expected_version, current_version), ...]
        """
        self.conflicts = list(conflicts)
        detail = "；".join(f"机柜#{cid}（提交基于 v{exp}）" for cid, exp, _cur in self.conflicts)
        super().__init__(
            message=f"以下机柜已被他人修改，请刷新平面图后重试：{detail}",
            code="CABINET_VERSION_CONFLICT",
            details={"conflicts": self.conflicts},
            status_code=409,
        )


class BusinessRuleViolationError(BusinessLogicError):
    """业务规则违反异常

    当违反业务规则时抛出此异常。
    """

    def __init__(self, rule_name: str, rule_description: Optional[str] = None, message: Optional[str] = None):
        """初始化业务规则违反异常

        Args:
            rule_name: 规则名称
            rule_description: 规则描述
            message: 自定义异常消息
        """
        if not message:
            if rule_description:
                message = f"违反业务规则 {rule_name}：{rule_description}"
            else:
                message = f"违反业务规则：{rule_name}"

        details = {"rule_name": rule_name}
        if rule_description:
            details["rule_description"] = rule_description

        super().__init__(message=message, code="BUSINESS_RULE_VIOLATION", details=details)


class DeviceNotSupported(BusinessLogicError):
    """设备不支持异常

    当尝试对不支持的设备类型执行操作时抛出。
    """

    def __init__(self, device_type: str = "", message: Optional[str] = None):
        """初始化设备不支持异常"""
        if not message:
            message = f"不支持的设备类型：{device_type}" if device_type else "不支持的设备类型"
        super().__init__(message=message, code="DEVICE_NOT_SUPPORTED", details={"device_type": device_type})


class DeviceLockUnavailable(BusinessLogicError):
    """设备锁不可用：拿不到**分布式**互斥，拒绝在无互斥保证下执行写操作。

    触发条件（见 ``app.services.device_op_lock``）：Redis 不可用，而本次是
    ``mode="write"``（SSH 配置下发），且部署形态未显式声明"单进程"。

    为什么是 503 而不是 409/500
    ---------------------------
    - 409 已被"设备忙（有别的 SSH 操作在跑）"占用，两者处置方式完全不同：
      设备忙是**重试即可**，锁不可用是**重试无用**（Redis 不恢复就一直失败）；
    - 500 会把"依赖组件缺失"混同为"程序缺陷"，运维看到 500 的第一反应是
      查代码而不是查 Redis。

    为什么不继承 ``DeviceOperationConflict``
    ----------------------------------------
    后者定义在 service 层，调用方普遍用 ``except DeviceOperationConflict``
    表达"设备正忙，稍后重试"。若本类继承它，Redis 故障会被**静默翻译成**
    "稍后重试"：诊断降级成 supported:false、配置采集降级成"设备繁忙"，
    故障期间既不下发也不告警，病因永远浮不出来。

    消息自带逃生阀：单进程部署（无 gunicorn 多 worker、无 Celery prefork）
    可显式声明 ``DEVICE_OP_LOCK_REQUIRE_REDIS=0`` 恢复进程内锁行为。
    """

    POLICY_ENV = "DEVICE_OP_LOCK_REQUIRE_REDIS"

    def __init__(
        self,
        device_id: Optional[int] = None,
        lock_key: Optional[str] = None,
        message: Optional[str] = None,
    ):
        if not message:
            target = f"设备 {device_id}" if device_id is not None else "设备"
            message = (
                f"{target} 的设备操作锁不可用：Redis 不可用，无法建立跨进程互斥，"
                f"已拒绝执行配置下发（并发下发会导致配置乱序）。"
                f"若为单进程部署，可设置 {self.POLICY_ENV}=0 恢复进程内锁；"
                f"否则请先恢复 Redis 再重试。"
            )
        super().__init__(
            message=message,
            code="DEVICE_LOCK_UNAVAILABLE",
            details={"device_id": device_id, "lock_key": lock_key},
            status_code=503,
        )


class IPAlreadyBannedException(BusinessLogicError):
    """IP 已被封禁异常"""

    def __init__(self, ip_address: str = "", message: Optional[str] = None):
        """初始化 IP 已封禁异常"""
        if not message:
            message = f"IP {ip_address} 已处于封禁状态" if ip_address else "IP 已处于封禁状态"
        super().__init__(message=message, code="IP_ALREADY_BANNED", status_code=409)


class IPNotBannedException(BusinessLogicError):
    """IP 未被封禁异常"""

    def __init__(self, ip_address: str = "", message: Optional[str] = None):
        """初始化 IP 未封禁异常"""
        if not message:
            message = f"IP {ip_address} 未处于封禁状态" if ip_address else "IP 未处于封禁状态"
        super().__init__(message=message, code="IP_NOT_BANNED")


class NoCoreSwitch(BusinessLogicError):
    """无核心交换机异常"""

    def __init__(self, room_id: Optional[int] = None, message: Optional[str] = None):
        """初始化无核心交换机异常"""
        if not message:
            message = f"机房 {room_id} 无可用核心交换机" if room_id else "无可用核心交换机"
        super().__init__(message=message, code="NO_CORE_SWITCH")


class BanCommandFailed(BusinessLogicError):
    """封禁命令执行失败异常"""

    def __init__(self, reason: str = "", message: Optional[str] = None):
        """初始化封禁命令失败异常"""
        if not message:
            message = f"封禁命令执行失败：{reason}" if reason else "封禁命令执行失败"
        super().__init__(message=message, code="BAN_COMMAND_FAILED")


class BanConfigNotFoundError(BusinessLogicError):
    """解封时交换机配置不存在（路由/ARP条目已消失），视为已通过其他方式解封"""

    def __init__(self, reason: str = "", message: Optional[str] = None):
        if not message:
            message = (
                f"交换机上未找到对应配置，该IP可能已通过其他方式解封：{reason}"
                if reason
                else "交换机上未找到对应配置，该IP可能已通过其他方式解封"
            )
        super().__init__(message=message, code="BAN_CONFIG_NOT_FOUND")


class ServiceError(BusinessLogicError):
    """Service 层统一异常

    当 Service 层捕获底层异常（如 DataAccessError）后，
    转换为此异常抛出，避免上层直接暴露 data access 层异常细节。
    原始异常通过 __cause__ 链保留，便于日志追踪。
    """

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 500,
    ):
        """初始化 Service 层异常

        Args:
            message: 异常消息
            code: 异常代码
            details: 异常详情
            status_code: HTTP状态码
        """
        super().__init__(
            message=message,
            code=code or "SERVICE_ERROR",
            details=details,
            status_code=status_code,
        )


class BatchItemsLimitExceeded(BusinessLogicError):
    """批量端点 items 条数超限（评审 20260924 §2.3）。

    当一次批量请求的 ``items`` 条数超过 ``app.core.batch_limits.MAX_BATCH_ITEMS``
    时抛出。由 ``ensure_batch_size_within_limit()`` 在各批量端点统一触发。

    为什么要有这个上限：批量端点是**单事务 + 逐条 CAS**，条数无上限时超大
    payload 会形成长事务、久持行锁；叠加循环内的读写放大，一条请求就能把
    同机房的其它编辑全挡住。上限把最坏情况压在有界范围。

    为什么单独一个异常类：前端需要**编程识别**并给出可执行的下一步（拆批 /
    减少勾选），靠 message 文案匹配既脆又不可本地化；专用 ``code`` 是稳定契约。
    """

    def __init__(self, count: int, max_items: int, endpoint: str = "批量操作"):
        """初始化批量条数超限异常。

        Args:
            count: 本次请求的 items 条数
            max_items: 允许的最大条数（= ``MAX_BATCH_ITEMS``）
            endpoint: 端点名称，用于把文案说人话（哪个操作被拒了）
        """
        super().__init__(
            message=(f"{endpoint}单次最多 {max_items} 条，本次提交了 {count} 条，请分批提交"),
            code="BATCH_ITEMS_LIMIT_EXCEEDED",
            details={
                "max_items": max_items,
                "requested_count": count,
                "endpoint": endpoint,
            },
            status_code=400,
        )


class PaginationLimitExceeded(BusinessLogicError):
    """深分页超限异常（P0-3c 深度封顶）。

    当分页请求的 ``offset`` 超过 ``app.core.pagination_limits.MAX_OFFSET`` 时抛出。
    由 ``ensure_offset_within_limit()`` 在仓储层各分页点统一触发。

    为什么单独一个异常类、而不是复用 ``InvalidOperationError``：前端需要能
    **编程识别**这一情形并降级提示（把「共 N 条」位置换成"结果过多，请用筛选缩小
    范围"）。靠 ``message`` 文案匹配既脆又不可本地化；专用 ``code`` 是稳定契约。
    ``code`` 用 ``UPPER_SNAKE`` 字面量，与本模块既有惯例（``USER_NOT_FOUND`` /
    ``INVALID_OPERATION`` / …）一致。
    """

    def __init__(self, offset: int, max_offset: int):
        """初始化分页超限异常。

        Args:
            offset: 请求的偏移量（实际会发给数据库的那个）
            max_offset: 允许的最大偏移量（= ``MAX_OFFSET``）
        """
        super().__init__(
            message=(f"结果过多，请使用筛选条件缩小范围（单次翻页最多到第 {max_offset} 条）"),
            code="PAGINATION_LIMIT_EXCEEDED",
            details={"max_offset": max_offset, "requested_offset": offset},
            status_code=400,
        )


class TicketTransitionError(BusinessLogicError):
    """工单状态机非法转换（code = ``INVALID_TRANSITION``）。

    为什么单独一个异常类、而不是复用 ``InvalidOperationError``：与
    ``PaginationLimitExceeded`` 同一条理由 —— 前端需要能**编程识别**这一情形。
    工单卡片上的按钮是按当前状态渲染的，用户在另一个标签页把单子推走之后再点
    旧按钮，就会撞上非法转换；这时前端要的是"刷新后重试"而不是一条通用报错。
    ``INVALID_OPERATION`` 覆盖太宽（权限、参数、状态全在里面），分不出来。

    ``details`` 带上 ``from`` / ``to`` / ``action`` / ``reason``：
    运维排查"为什么这张单子推不动"时，这四个字段不需要再翻日志。
    """

    def __init__(
        self,
        from_status: Optional[str],
        action: str,
        reason: str,
        to_status: Optional[str] = None,
        message: Optional[str] = None,
    ):
        """初始化非法转换异常。

        Args:
            from_status: 当前状态（建单动作为 ``None``，表示无前态）
            action: 尝试执行的动作
            reason: 拒绝原因码（由状态机守卫给出，如 ``SELF_APPROVAL_DENIED``）
            to_status: 期望到达的状态（未知边时为 ``None``）
            message: 自定义异常消息
        """
        self.from_status = from_status
        self.action = action
        self.reason = reason
        self.to_status = to_status

        if not message:
            where = f"{from_status} --{action}-->" if from_status else f"--{action}-->"
            message = f"工单状态不允许该操作（{where}）：{reason}"

        super().__init__(
            message=message,
            code="INVALID_TRANSITION",
            details={
                "from": from_status,
                "to": to_status,
                "action": action,
                "reason": reason,
            },
            status_code=400,
        )
