# -*- coding: utf-8 -*-
"""安全中心 API（一期）。

与 `app/api/security_routes.py` 的关系：那个蓝图只承载匿名 CSP 上报
（`POST /csp-report`），本蓝图承载需鉴权的安全中心业务；两者共用 `/api/security`
前缀但路径不重叠（避免给同一蓝图加装饰器时误伤匿名上报，见总纲 §8）。

分层：本模块**不直查** `db.session` / `Model.query` ——
`tests/test_api_layer_session_budget.py` 对 `app/api/**` 的 `db.session` 引用
按文件钉死（只减不增，新增即红），故查询一律经仓储。

权限码：`security:read`（浏览）/ `security:config`（改策略、触发巡检）。
"""
from flask import Blueprint, g, request

from app.api.base import APIResponse, RequestValidator
from app.persistence.security_finding_repository import SecurityFindingRepository
from app.services.auth.decorators import permission_required
from app.services.security import scanner
from app.services.security.policy_service import get_all_items, set_value

security_center_bp = Blueprint("security_center", __name__)

_DEFAULT_PAGE_SIZE = 20


def _paging() -> tuple:
    """从 query 解析分页（夹紧到全站上限）。

    必须走 `RequestValidator.validate_pagination_params()`：它是本仓 HTTP 边界的
    **唯一**分页入口，同时夹紧 `per_page(<=100)` 与 `page(<=1000)`。
    自己写 `request.args.get("per_page", ...)` 会被
    `tests/test_pagination_bound_gate.py` 判红 —— 分页参数直接进 SQL 的
    LIMIT/OFFSET，无上限即外部可控的资源耗尽（评审 M2 定性为 P0）；
    且这里只夹 per_page 不夹 page 的话，`?page=99999999` 仍能造成超大 OFFSET。
    """
    return RequestValidator.validate_pagination_params(default_per_page=_DEFAULT_PAGE_SIZE)


@security_center_bp.route("/overview", methods=["GET"])
@permission_required("security:read")
def security_overview():
    """概览：各检测项状态（open findings 按 rule 聚合）+ 合规汇总。"""
    rows = SecurityFindingRepository().open_counts_by_rule()
    counts = {rule_id: {"severity": severity, "count": cnt} for rule_id, severity, cnt in rows}
    items = []
    for spec in scanner.iter_checks():
        info = counts.get(spec.rule_id, {"severity": spec.severity, "count": 0})
        items.append({"rule_id": spec.rule_id, "severity": info["severity"],
                      "violation_count": info["count"], "status": "open" if info["count"] else "ok"})
    violated = sum(1 for it in items if it["violation_count"])
    return APIResponse.success(data={
        "compliance": {"total": len(items), "ok": len(items) - violated, "violated": violated},
        "items": items,
    })


@security_center_bp.route("/policies", methods=["GET"])
@permission_required("security:read")
def list_policies():
    """全部策略项（当前值 / 默认值 / 范围 / 说明）。"""
    return APIResponse.success(data={"items": get_all_items()})


@security_center_bp.route("/policies/<key>", methods=["PUT"])
@permission_required("security:config")
def update_policy(key: str):
    """改单个策略项（乐观锁 + 审计 detail before/after）。"""
    body = request.get_json(silent=True) or {}
    if "value" not in body:
        return APIResponse.error("缺少参数 value", status_code=400)
    g._audit_severity = "critical"          # 策略变更按 critical 级别留痕
    result = set_value(key, body["value"], updated_by=g.current_user.get("user_id"),
                       expected_version=body.get("version"))
    return APIResponse.success(data=result, message="策略已更新")


@security_center_bp.route("/findings", methods=["GET"])
@permission_required("security:read")
def list_findings():
    """发现项列表（可按 rule / severity / status / subject_type 过滤）。"""
    page, size = _paging()
    filters = {field: request.args.get(field) for field in
               ("rule_id", "severity", "status", "subject_type")}
    rows, total = SecurityFindingRepository().list_paged(filters, page, size)
    return APIResponse.success(data={"items": [r.to_dict() for r in rows],
                                     "total": total, "page": page, "per_page": size})


@security_center_bp.route("/scan", methods=["POST"])
@permission_required("security:config")
def trigger_scan():
    """手动巡检；dry_run=true 同步返回将产生的 findings、不落库（enforce 前影响预览）。"""
    body = request.get_json(silent=True) or {}
    result = scanner.run_scan(dry_run=bool(body.get("dry_run")))
    return APIResponse.success(data=result)


@security_center_bp.route("/remote-logins", methods=["GET"])
@permission_required("security:read")
def list_remote_logins():
    """异地登录记录（按 用户×IP 聚合）；异地检测未启用时返回 enabled=false。

    "未启用"的口径与检测器 `login.remote_access` **完全一致**（mode=off 或可信网段
    为空都算不启用），否则会出现"页面说有数据、巡检不报"这类自相矛盾。
    """
    import datetime as _dt

    from app.persistence.user_log_repository import UserLogRepository
    from app.services.security.checks.login_checks import is_trusted_ip
    from app.services.security.policy_service import get_value
    from app.utils.time_utils import now_utc_naive

    mode = get_value("login.remote_access.mode")
    networks = get_value("login.trusted_networks") or []
    if mode == "off" or not networks:
        return APIResponse.success(data={"items": [], "total": 0, "enabled": False})

    days = min(max(1, int(request.args.get("days", 7) or 7)), 90)
    since = now_utc_naive() - _dt.timedelta(days=days)
    rows = UserLogRepository().remote_login_rows_since(since)

    grouped: dict = {}
    for user_id, ip, ts, username in rows:
        if is_trusted_ip(ip, networks):
            continue
        entry = grouped.setdefault((user_id, ip), {"count": 0, "last_time": None, "username": username})
        entry["count"] += 1
        entry["username"] = username
        if entry["last_time"] is None or ts > entry["last_time"]:
            entry["last_time"] = ts

    items = sorted(
        ({"user_id": uid, "ip": ip, "username": v["username"], "count": v["count"],
          "last_time": v["last_time"].isoformat() if v["last_time"] else None}
         for (uid, ip), v in grouped.items()),
        key=lambda x: x["last_time"] or "", reverse=True)
    page, size = _paging()
    return APIResponse.success(data={"items": items[(page - 1) * size: page * size],
                                     "total": len(items), "enabled": True})


@security_center_bp.route("/users/<int:user_id>/lock", methods=["POST"])
@permission_required("security:session")
def lock_user(user_id: int):
    """锁定账号（需原因；禁自锁、禁锁死最后一个可用 admin）。"""
    from app.services.security.account_lock_service import lock_account

    body = request.get_json(silent=True) or {}
    g._audit_severity = "critical"          # 锁定账号按 critical 级别留痕
    return APIResponse.success(data=lock_account(user_id, body.get("reason", ""),
                                                 g.current_user.get("user_id")),
                               message="账号已锁定")


@security_center_bp.route("/users/<int:user_id>/unlock", methods=["POST"])
@permission_required("security:session")
def unlock_user(user_id: int):
    """解锁账号（幂等）。"""
    from app.services.security.account_lock_service import unlock_account

    g._audit_severity = "critical"          # 解锁同样留痕（谁能把人放回来是审计重点）
    return APIResponse.success(data=unlock_account(user_id, g.current_user.get("user_id")),
                               message="账号已解锁")
