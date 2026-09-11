"""LDAP 配置与角色目标自检（企业身份集成 T3 的上线检查项）。

为什么这不是数据迁移：``LDAP_GROUP_ROLE_MAP`` 是**环境配置**，它引用的角色是
RBAC 业务数据（带 ``data_scope`` 等治理属性），每个客户映射的角色集合都不同；
迁移只承载产品级种子数据（``admin/operator/viewer/user``，见 0000_baseline）。
把某个环境的角色烧进迁移，会污染所有其它部署。

真正的系统性防护是**部署期 fail-fast**：映射目标角色缺失/停用若只在登录时
以 WARNING 跳过，就要等第一个用户登录异常才暴露（且部分缺失时子集静默生效）。
本模块提供纯逻辑检查函数，``flask ldap-check`` 命令消费之——上线检查清单里
一条命令验完：必填项、映射语法、以及映射表与默认角色指向的每个角色都存在且启用。
关闭态（``LDAP_ENABLED=false``）不做任何校验，与 ``_assert_ldap_config`` 口径一致。
"""

from __future__ import annotations

from typing import Any, Mapping

from app.services.ldap_role_mapper import GroupRoleMapError, parse_group_role_map


def collect_ldap_check_issues(
    config: Mapping[str, Any], role_repository: Any
) -> list[str]:
    """收集 LDAP 配置问题；返回**人类可读**的问题列表，空列表 = 通过。

    Args:
        config: Flask ``app.config`` 或等价映射（读取 ``LDAP_*`` 键）。
        role_repository: 提供 ``find_by_name(name)`` 的角色仓储（可注入替身）。

    Returns:
        每个元素是一条可直接展示给运维的问题描述。
    """
    if not config.get("LDAP_ENABLED"):
        return []  # 关闭态不做校验（存量部署升级后行为不变）

    issues: list[str] = []

    server = config.get("LDAP_SERVER") or ""
    base_dn = config.get("LDAP_BASE_DN") or ""
    if not (server and base_dn):
        issues.append(
            "LDAP_ENABLED=true 但 LDAP_SERVER / LDAP_BASE_DN 未配置"
        )

    raw_map = config.get("LDAP_GROUP_ROLE_MAP") or ""
    mapping: dict[str, str] = {}
    if raw_map:
        try:
            mapping = parse_group_role_map(raw_map)
        except GroupRoleMapError as exc:
            issues.append(f"LDAP_GROUP_ROLE_MAP 无法解析：{exc}")

    targets: list[str] = list(mapping.values())
    if mapping:
        default_role = str(config.get("LDAP_DEFAULT_ROLE") or "").strip()
        if default_role:
            targets.append(default_role)

    seen: set[str] = set()
    for role in targets:
        name = role.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        try:
            row = role_repository.find_by_name(name)
        except Exception as exc:  # noqa: BLE001 - 查询失败按问题上报，不中断其余检查
            issues.append(f"查询角色 {name} 失败：{exc}")
            continue
        if row is None:
            issues.append(
                f"映射目标角色不存在：{name}"
                "（先在 RBAC 中创建该角色，或修正 LDAP_GROUP_ROLE_MAP）"
            )
        elif getattr(row, "status", 0) != 0:
            issues.append(f"映射目标角色已停用：{name}")

    return issues
