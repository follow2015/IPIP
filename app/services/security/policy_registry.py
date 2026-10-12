# -*- coding: utf-8 -*-
"""安全策略注册表：每个策略项的单一真源（类型 / 默认值 / 范围 / 失败语义）。

设计依据：一期文档 §5、总纲 §4.2。


1. **默认值 = 现状**：`security_policies` 表只存管理员改过的项，读不到就走这里的
   `default`。因此默认值直接决定"升级后行为是否变化"——`snmp.mode` 若默认 `enforce`，
   升级瞬间所有 v2c 凭据都拒存，且没有任何数据变更能提示。测试专门钉住这一点。
2. **`on_error` 决定读不到策略时的回退方向**：密码类 `fail_closed`（回最严默认，
   宁可要求改密也不放宽），SNMP/告警类 `fail_open`（回现状，避免因缓存故障误拦业务）。
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PolicyItem:
    """一个策略项的声明。"""

    key: str
    type: str                        # int / bool / string / json / choice
    default: Any
    description: str
    min: int | None = None
    max: int | None = None
    choices: tuple = ()
    on_error: str = "fail_open"      # fail_open：读不到视为默认；fail_closed：回最严默认
    editable: bool = True
    tag: str = field(default="", repr=False)  # 前端分组标签：password/snmp/login/user/audit


POLICIES: dict = {
    "password.min_length": PolicyItem(
        key="password.min_length", type="int", default=8, min=8, max=128,
        description="密码最小长度（不得低于现有强度规则下限 8）",
        tag="password", on_error="fail_closed"),
    "password.require_classes": PolicyItem(
        key="password.require_classes", type="int", default=0, min=0, max=4,
        description="要求字符类别数（0=沿用现有强度规则）",
        tag="password", on_error="fail_closed"),
    "password.max_age_days": PolicyItem(
        key="password.max_age_days", type="int", default=0, min=0, max=3650,
        description="密码有效期（天），0 表示不过期",
        tag="password", on_error="fail_closed"),
    "password.min_age_days": PolicyItem(
        key="password.min_age_days", type="int", default=0, min=0, max=365,
        description="两次改密最小间隔（天），0 表示不限制",
        tag="password", on_error="fail_closed"),
    "password.expire_warn_days": PolicyItem(
        key="password.expire_warn_days", type="int", default=7, min=0, max=90,
        description="到期前提前提示天数",
        tag="password", on_error="fail_open"),
    "password.force_change_on_reset": PolicyItem(
        key="password.force_change_on_reset", type="bool", default=False,
        description="管理员重置密码后强制用户下次登录改密",
        tag="password", on_error="fail_open"),
    "snmp.allowed_versions": PolicyItem(
        key="snmp.allowed_versions", type="json", default=["v2c", "v3"],
        description='允许的 SNMP 版本列表，设为 ["v3"] 即"强制 v3"', tag="snmp"),
    "snmp.forbid_default_community": PolicyItem(
        key="snmp.forbid_default_community", type="bool", default=False,
        description="禁止 public/private/空 community（仅在允许 v2c 时有意义）", tag="snmp"),
    "snmp.mode": PolicyItem(
        key="snmp.mode", type="choice", default="off", choices=("off", "audit", "enforce"),
        description="SNMP 策略模式：off 不检查 / audit 放行并记 finding / enforce 拒绝",
        tag="snmp", on_error="fail_open"),
    "login.remote_access.mode": PolicyItem(
        key="login.remote_access.mode", type="choice", default="off",
        choices=("off", "audit", "enforce"),
        description=("异地登录：off 不启用 / audit 仅记 finding / enforce 记 finding 并发 "
                     "critical 告警（一期不阻断登录）"),
        tag="login"),
    "login.trusted_networks": PolicyItem(
        key="login.trusted_networks", type="json", default=[],
        description="可信网段 CIDR 列表；空列表 = 异地检测不启用", tag="login"),
    "login.brute_force_threshold": PolicyItem(
        key="login.brute_force_threshold", type="int", default=10, min=1, max=1000,
        description="窗口内登录失败次数阈值（超阈值产生 finding）", tag="login"),
    "login.brute_force_window_hours": PolicyItem(
        key="login.brute_force_window_hours", type="int", default=24, min=1, max=168,
        description="爆破统计窗口（小时）", tag="login"),
    "user.dormant_days": PolicyItem(
        key="user.dormant_days", type="int", default=90, min=0, max=3650,
        description="账号休眠阈值（天），0 表示不检测", tag="user"),
    "audit.retention_days": PolicyItem(
        key="audit.retention_days", type="int", default=180, min=30, max=3650,
        description="审计日志要求留存天数（不达标产生 finding；清理归运维任务）", tag="audit"),
}


def get_item(key: str) -> PolicyItem:
    """取策略项声明。

    Raises:
        KeyError: 未知 key（刻意不返回默认值——防拼写错误静默生效）。
    """
    return POLICIES[key]


def items_by_tag(tag: str) -> list:
    """按分组取策略项（前端分组渲染用）。"""
    return [item for item in POLICIES.values() if item.tag == tag]
