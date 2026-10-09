# -*- coding: utf-8 -*-
"""线路 API —— G1

Blueprint `circuit_bp` 挂载 `/api/circuits`，权限 `circuit:{view,create,update,delete}`。

权限动词用 `update` 而非 `edit`：`migrations/seed_rbac.py` 里 20+ 条权限全部用
`update`，`edit` 出现 0 次（设计文档 §6）。
"""
from flask import Blueprint, request

from app.api.base import APIResponse, RequestValidator
from app.exceptions import PresetResponseError
from app.exceptions.validation import ValidationError
from app.openapi.doc import doc
from app.persistence.circuit_repository import CircuitRepository
from app.schemas.circuit import (
    CircuitCreateSchema,
    CircuitSegmentsReplaceSchema,
    CircuitUpdateSchema,
)
from app.services.circuit_service import CircuitService
from app.services.auth import login_required, permission_required
from app.utils import rate_limit_api
from app.utils.bandwidth import bandwidth_display_pair, parse_bandwidth
from app.utils.logging import get_logger
from app.utils.transactional import transactional

logger = get_logger(__name__)

circuit_bp = Blueprint("circuit", __name__)
circuit_service = CircuitService(CircuitRepository())


def _serialize_segments(rows) -> list:
    """分段序列化：注入 anchor_lost（AC-C-31/32 判据）与跳接引用名称。

    device_name/port_name 供详情页人读展示；引用已删除时下发
    *_missing=True（软引用值保留原 id，前端据此显示「已不存在」）。
    """
    items = [
        {**s.to_dict(), "anchor_lost": bool(s.connection_id_lost)} for s in rows
    ]
    device_names, port_names = circuit_service.repository.resolve_hop_refs(
        [it.get("device_id") for it in items],
        [it.get("port_id") for it in items],
    )
    for it in items:
        device_name = device_names.get(it.get("device_id"))
        port_name = port_names.get(it.get("port_id"))
        it["device_name"] = device_name
        it["port_name"] = port_name
        it["device_missing"] = it.get("device_id") is not None and device_name is None
        it["port_missing"] = it.get("port_id") is not None and port_name is None
    return items


def _serialize(circuit, carrier_names=None, customer_names=None) -> dict:
    """线路详情序列化。

    同时下发**绝对值** `bandwidth_mbps` 与**格式化串** `bandwidth_display`：
    前端无需重复实现换算即可展示，需要比较/聚合时仍取绝对值（设计文档 §6）。

    注入归属名称 `carrier_name` / `customer_name`（详情页直接展示名称）；
    调用方经 repository.resolve_owner_names 批量预取后传入，未传则为 None
    （次要端点如 impact / expiring 前端只消费 circuit_no，不取名称）。

    买断模式（`billing_mode == flat`）下 `committed_mbps` 落库为 NULL，
    此处按 R2 推导返回"保底 = 端口带宽"，让调用方不必自己记这条规则。
    """
    data = circuit.to_dict()
    data.update(bandwidth_display_pair(circuit.bandwidth_mbps, circuit.bandwidth_step))
    data["carrier_name"] = (carrier_names or {}).get(circuit.carrier_id)
    data["customer_name"] = (customer_names or {}).get(circuit.customer_id)
    if circuit.billing_mode == "flat":
        data["committed_mbps"] = circuit.bandwidth_mbps
        data["committed_is_derived"] = True
    else:
        data["committed_is_derived"] = False
    return data


def _resolve_bandwidth(payload: dict) -> dict:
    """把 `{value, unit}` 归一化成绝对 Mbps 后并入 payload。

    抽出来是因为 create 与 update 都要做——只在一处做是常见漏洞：
    更新时给了 `10 G` 却没换算，会直接把 10 当成 10 Mbps 落库。
    """
    out = dict(payload)
    value = out.pop("bandwidth_value", None)
    unit = out.pop("bandwidth_unit", None)
    if value is not None and unit:
        out["bandwidth_mbps"] = parse_bandwidth(value, unit, out.get("bandwidth_step"))
    return out


def _resolve_committed(payload: dict, fallback_step: int | None = None) -> dict:
    """把保底带宽的 `{committed_value, committed_unit}` 换算成绝对 Mbps。

    与 `_resolve_bandwidth` 对称（互斥语义见 _CommittedFieldsMixin）。
    换算步进优先取本次 payload 里的 bandwidth_step，更新场景 payload
    未带 step 时回落到既有线路的 bandwidth_step——否则 IEC 设备按 SI
    换算会差 2.4%。
    """
    out = dict(payload)
    value = out.pop("committed_value", None)
    unit = out.pop("committed_unit", None)
    if value is not None and unit:
        step = out.get("bandwidth_step") or fallback_step
        out["committed_mbps"] = parse_bandwidth(value, unit, step)
    return out


@circuit_bp.route("/", methods=["GET"])
@doc(summary="获取线路列表", tags=["线路"], responses={200: "ApiResponse", 500: "ApiError"})
@login_required
@permission_required("circuit:view")
@rate_limit_api
def list_circuits():
    """线路列表（分页 + 多维筛选）"""
    page, per_page = RequestValidator.validate_pagination_params()

    filters = {}
    for key in ("status", "billing_mode"):
        val = request.args.get(key)
        if val:
            filters[key] = val
    for key in ("carrier_id", "customer_id", "room_id"):
        val = request.args.get(key, type=int)
        if val:
            filters[key] = val
    val = request.args.get("expiring_in_days", type=int)
    if val:
        filters["expiring_in_days"] = val
    keyword = request.args.get("keyword")
    if keyword:
        filters["keyword"] = keyword

    result = circuit_service.repository.list_with_filters(
        filters, page=page, per_page=per_page
    )
    carrier_names, customer_names = circuit_service.repository.resolve_owner_names(
        (c.carrier_id for c in result["items"]),
        (c.customer_id for c in result["items"]),
    )
    return APIResponse.success(
        data={
            "items": [
                _serialize(c, carrier_names, customer_names) for c in result["items"]
            ],
            "total": result["total"],
            "page": result["page"],
            "per_page": result["per_page"],
        }
    )


@circuit_bp.route("/", methods=["POST"])
@doc(summary="创建线路", tags=["线路"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/CircuitCreate"}}}}, responses={201: "CircuitResponse", 400: "ApiError", 409: "ApiError"})
@login_required
@permission_required("circuit:create")
@rate_limit_api
@transactional
def create_circuit():
    """创建线路

    电路号重复返回 409（AC-C-01）。计费规则 R0–R6 由服务层统一裁决。
    """
    payload = CircuitCreateSchema().load(request.get_json() or {})
    payload = _resolve_bandwidth(payload)
    payload = _resolve_committed(payload, payload.get("bandwidth_step"))

    if circuit_service.repository.get_by_circuit_no(payload["circuit_no"]):
        return APIResponse.error(
            message=f"电路号 {payload['circuit_no']} 已存在",
            error_code="CIRCUIT_NO_CONFLICT",
            status_code=409,
        )

    CircuitService.validate_customer_ref(payload.get("customer_id"))
    payload = CircuitService.apply_billing_rules(payload)
    CircuitService.validate_dates(payload)

    circuit = circuit_service.repository.create(payload)
    logger.info("创建线路 id=%s circuit_no=%s", circuit.id, circuit.circuit_no)
    carrier_names, customer_names = circuit_service.repository.resolve_owner_names(
        [circuit.carrier_id], [circuit.customer_id]
    )
    return APIResponse.success(
        data=_serialize(circuit, carrier_names, customer_names),
        message="线路创建成功",
        status_code=201,
    )


@circuit_bp.route("/<int:circuit_id>", methods=["GET"])
@doc(summary="获取线路详情", tags=["线路"], responses={200: "CircuitResponse", 404: "ApiError"})
@login_required
@permission_required("circuit:view")
@rate_limit_api
def get_circuit(circuit_id):
    """线路详情（含分段）"""
    circuit = circuit_service.repository.find_by_id(circuit_id)
    if not circuit:
        return APIResponse.error(message="线路不存在", error_code="CIRCUIT_NOT_FOUND", status_code=404)

    carrier_names, customer_names = circuit_service.repository.resolve_owner_names(
        [circuit.carrier_id], [circuit.customer_id]
    )
    data = _serialize(circuit, carrier_names, customer_names)
    data["segments"] = _serialize_segments(
        circuit_service.repository.list_segments(circuit_id)
    )
    data["affected_device_ids"] = circuit_service.affected_device_ids(circuit_id)
    return APIResponse.success(data=data)


@circuit_bp.route("/<int:circuit_id>", methods=["PUT"])
@doc(summary="更新线路", tags=["线路"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/CircuitUpdate"}}}}, responses={200: "CircuitResponse", 400: "ApiError", 404: "ApiError"})
@login_required
@permission_required("circuit:update")
@rate_limit_api
@transactional
def update_circuit(circuit_id):
    """更新线路

    状态变更走状态机校验（AC-C-05）；计费字段变更后**重新**应用 R0–R6——
    只在新创建时跑规则是常见漏洞（改了 billing_mode 却没重算 committed_mbps）。
    """
    circuit = circuit_service.repository.find_by_id(circuit_id)
    if not circuit:
        return APIResponse.error(message="线路不存在", error_code="CIRCUIT_NOT_FOUND", status_code=404)

    payload = CircuitUpdateSchema().load(request.get_json() or {})
    payload = _resolve_bandwidth(payload)
    payload = _resolve_committed(payload, circuit.bandwidth_step)

    if payload.get("status") and payload["status"] != circuit.status:
        CircuitService.validate_transition(circuit.status, payload["status"])

    if "customer_id" in payload:
        CircuitService.validate_customer_ref(payload["customer_id"])

    merged = {
        "billing_mode": circuit.billing_mode,
        "bandwidth_mbps": circuit.bandwidth_mbps,
        "committed_mbps": circuit.committed_mbps,
        "overage_unit_price": circuit.overage_unit_price,
        "traffic_unit_price": circuit.traffic_unit_price,
    }
    merged.update({k: v for k, v in payload.items() if k in merged})
    normalized = CircuitService.apply_billing_rules(merged)
    payload.update(
        {k: normalized[k] for k in
         ("billing_mode", "bandwidth_mbps", "committed_mbps",
          "overage_unit_price", "traffic_unit_price")}
    )

    if "start_date" in payload or "end_date" in payload:
        CircuitService.validate_dates(
            {
                "start_date": payload.get("start_date", circuit.start_date),
                "end_date": payload.get("end_date", circuit.end_date),
            }
        )

    updated = circuit_service.repository.update(circuit_id, payload)
    carrier_names, customer_names = circuit_service.repository.resolve_owner_names(
        [updated.carrier_id], [updated.customer_id]
    )
    return APIResponse.success(
        data=_serialize(updated, carrier_names, customer_names),
        message="线路更新成功",
    )


@circuit_bp.route("/<int:circuit_id>", methods=["DELETE"])
@doc(summary="删除线路", tags=["线路"], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("circuit:delete")
@rate_limit_api
@transactional
def delete_circuit(circuit_id):
    """软删线路（同一事务内物理删分段，AC-C-06）"""
    try:
        circuit_service.delete_circuit(circuit_id)
    except ValidationError as e:
        raise PresetResponseError(message=e.message, status_code=404) from e
    return APIResponse.success(message="线路删除成功")


@circuit_bp.route("/<int:circuit_id>/segments", methods=["GET"])
@doc(summary="获取线路分段", tags=["线路"], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("circuit:view")
@rate_limit_api
def list_segments(circuit_id):
    if not circuit_service.repository.find_by_id(circuit_id):
        return APIResponse.error(message="线路不存在", error_code="CIRCUIT_NOT_FOUND", status_code=404)
    items = _serialize_segments(circuit_service.repository.list_segments(circuit_id))
    return APIResponse.success(data={"items": items, "total": len(items)})


@circuit_bp.route("/<int:circuit_id>/segments", methods=["PUT"])
@doc(summary="整批替换线路分段", tags=["线路"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/CircuitSegmentsReplace"}}}}, responses={200: "ApiResponse", 400: "ApiError", 404: "ApiError"})
@login_required
@permission_required("circuit:update")
@rate_limit_api
@transactional
def replace_segments(circuit_id):
    """整批替换分段（不提供逐条 CRUD，避免序号空洞与重复中间态）"""
    if not circuit_service.repository.find_by_id(circuit_id):
        return APIResponse.error(message="线路不存在", error_code="CIRCUIT_NOT_FOUND", status_code=404)

    payload = CircuitSegmentsReplaceSchema().load(request.get_json() or {})
    CircuitService.validate_segment_refs(payload["segments"])
    circuit_service.repository.replace_segments(circuit_id, payload["segments"])
    return APIResponse.success(message="分段已更新")


@circuit_bp.route("/<int:circuit_id>/devices", methods=["GET"])
@doc(summary="线路关联设备", tags=["线路"], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("circuit:view")
@rate_limit_api
def circuit_devices(circuit_id):
    """线路分段关联的全部设备（AC-C-02）

    判据挂在"状态变更为 fault"上，故该端点对**任意状态**都可用——
    只在 fault 时开放会让故障前的巡检排查无处可查。
    """
    if not circuit_service.repository.find_by_id(circuit_id):
        return APIResponse.error(message="线路不存在", error_code="CIRCUIT_NOT_FOUND", status_code=404)
    items = circuit_service.affected_devices(circuit_id)
    return APIResponse.success(data={"items": items, "total": len(items)})


@circuit_bp.route("/expiring", methods=["GET"])
@doc(summary="获取即将到期线路", tags=["线路"], responses={200: "ApiResponse"})
@login_required
@permission_required("circuit:view")
@rate_limit_api
def list_expiring_circuits():
    """即将到期线路（AC-C-03）。日期口径 `utc_today()`，见仓储层。"""
    within = request.args.get("within_days", 30, type=int)
    items = [ _serialize(c) for c in circuit_service.list_expiring(within) ]
    return APIResponse.success(data={"items": items, "total": len(items)})


@circuit_bp.route("/impact", methods=["GET"])
@doc(summary="线路影响面反查", tags=["线路"], responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("circuit:view")
@rate_limit_api
def circuit_impact():
    """按连接 / 设备 / 客户反查受影响的线路（AC-C-04 / AC-C-28）"""
    connection_id = request.args.get("connection_id", type=int)
    if connection_id:
        result = circuit_service.impact_by_connection(connection_id)
        return APIResponse.success(
            data={
                "connection_id": result["connection_id"],
                "shared_by": result["shared_by"],
                "items": [_serialize(c) for c in result["circuits"]],
                "customer_ids": result["customer_ids"],
                "total": len(result["circuits"]),
            }
        )

    device_id = request.args.get("device_id", type=int)
    if device_id:
        rows = (
            circuit_service.repository.session.query(circuit_service.repository.model_class)
            .filter(
                (circuit_service.repository.model_class.a_end_device_id == device_id)
                | (circuit_service.repository.model_class.z_end_device_id == device_id),
                circuit_service.repository.model_class.deleted_at.is_(None),
            )
            .all()
        )
        return APIResponse.success(
            data={"items": [_serialize(c) for c in rows], "total": len(rows)}
        )

    customer_id = request.args.get("customer_id", type=int)
    if customer_id:
        rows = circuit_service.repository.list_by_customer(customer_id)
        return APIResponse.success(
            data={"items": [_serialize(c) for c in rows], "total": len(rows)}
        )

    return APIResponse.error(
        message="请提供 connection_id / device_id / customer_id 之一", status_code=400
    )
