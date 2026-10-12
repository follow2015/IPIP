# -*- coding: utf-8 -*-
"""登录类检测器：异地登录 / 账号休眠 / 爆破统计。

**异地检测默认关闭**（`login.remote_access.mode="off"` 且 `login.trusted_networks=[]`）：
二者是**"与"关系**，缺任一即完全不检测。这不是保守，而是必需 —— 如果"白名单为空"
被当成"所有 IP 都不可信"，升级后每个登录过的账号都会被刷一条 high 告警，
安全中心第一天就变成噪音源。设计文档 §5 的开启路径是：
先录网段 → `mode=audit` 观察 → 再转告警。

**异地判定的地基是 `users_log.login_ip` 的可信化**（TRUSTED_PROXIES 口径，
Task 0 已统一四条写入路径）。地基不可信，本项无意义 —— 所以本文件不自己造
取 IP 的逻辑，只读已经写进库的值。

**爆破统计读审计日志，不读 `users_log`**：登录失败**不写** `users_log`（那张表只记
成功登录），失败事件只落在 `audit_logs.action='auth.login.failed'`。一期该项
"只告警不拦截"（拦截仍由 `api/auth.py` 既有的 Redis 计数兜底，5 次/300s）。

查询同样收进仓储（同 Task 7/8：`Model.query` 台账预算为 0）。
"""
import datetime as dt
import ipaddress
from collections import defaultdict

from app.persistence.audit_log_repository import AuditLogRepository
from app.persistence.user_log_repository import UserLogRepository
from app.persistence.user_repository import UserRepository
from app.services.security.policy_service import get_value
from app.services.security.scanner import Violation, register_check
from app.utils.time_utils import now_utc_naive

_REMOTE_WINDOW_DAYS = 7


def is_trusted_ip(ip: str, networks: list) -> bool:
    """IP 是否落在任一可信网段内。

    **解析失败一律视为不可信**（`False`）：一条形如 `garbage` 或空的来源 IP，
    放行它等于给伪造/缺失来源开后门；而判为不可信最多是多看一条告警，
    方向上是安全的。网段串本身解析失败则跳过该条（配置笔误不应让整项失效）。
    """
    try:
        addr = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return False
    for cidr in networks or []:
        try:
            if addr in ipaddress.ip_network(str(cidr), strict=False):
                return True
        except ValueError:
            continue
    return False


@register_check("login.remote_access", severity="high", subject_type="user")
def check_remote_access() -> list:
    """近 7 天有不可信来源 IP 的账号（mode=off 或白名单为空 ⇒ 不检测）。"""
    if get_value("login.remote_access.mode") == "off":
        return []
    networks = get_value("login.trusted_networks") or []
    if not networks:
        return []
    since = now_utc_naive() - dt.timedelta(days=_REMOTE_WINDOW_DAYS)
    by_user = defaultdict(set)
    for user_id, ip in UserLogRepository().login_ips_since(since):
        if not is_trusted_ip(ip, networks):
            by_user[user_id].add(ip)
    return [
        Violation(
            subject_id=user_id,
            detail={"untrusted_ips": sorted(ips)[:5],
                    "window_days": _REMOTE_WINDOW_DAYS},
        )
        for user_id, ips in by_user.items()
    ]


@register_check("user.dormant_account", severity="low", subject_type="user")
def check_dormant_account() -> list:
    """最后登录早于 `user.dormant_days` 的账号（0 = 不检测）。

    **从未登录过的账号不算休眠**：那是"从未启用"，与"长期不用"处置方式不同，
    混进同一份名单会让管理员把一批压根没开通过的账号当成要清理的对象。
    """
    days = get_value("user.dormant_days")
    if not days or days <= 0:
        return []
    deadline = now_utc_naive() - dt.timedelta(days=int(days))
    users = UserRepository()
    out = []
    for user_id, last_login in UserLogRepository().last_login_times_by_user():
        if last_login is None or last_login >= deadline:
            continue
        user = users.get_by_id(user_id)
        if user is None:  # 账号已删除 ⇒ 没有可处置对象
            continue
        out.append(Violation(
            subject_id=user_id,
            detail={"username": user.username, "last_login": last_login.isoformat()},
        ))
    return out


@register_check("login.brute_force_stats", severity="medium", subject_type="user")
def check_brute_force_stats() -> list:
    """时间窗内失败登录次数达阈值的账号（只告警，不拦截）。"""
    threshold = get_value("login.brute_force_threshold") or 10
    hours = get_value("login.brute_force_window_hours") or 24
    since = now_utc_naive() - dt.timedelta(hours=int(hours))
    rows = AuditLogRepository().count_login_failures_since(since)
    return [
        Violation(subject_id=user_id,
                  detail={"failed_count": count, "window_hours": int(hours)})
        for user_id, count in rows if count >= threshold
    ]
