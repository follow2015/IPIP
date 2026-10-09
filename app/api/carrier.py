# -*- coding: utf-8 -*-
"""运营商 API —— G1

Blueprint `carrier_bp` 挂载 `/api/carriers`，权限 `carrier:{view,create,update,delete}`。
"""
from flask import Blueprint, request

from app.api.base import APIResponse, RequestValidator
from app.exceptions import PresetResponseError
from app.exceptions.validation import ValidationError
from app.openapi.doc import doc
from app.persistence.carrier_repository import CarrierRepository
from app.persistence.circuit_repository import CircuitRepository
from app.schemas.circuit import CarrierCreateSchema, CarrierUpdateSchema
from app.services.circuit_service import CarrierService
from app.services.auth import login_required, permission_required
from app.utils import rate_limit_api
from app.utils.logging import get_logger
from app.utils.transactional import transactional

logger = get_logger(__name__)

carrier_bp = Blueprint("carrier", __name__)
carrier_service = CarrierService(CarrierRepository(), CircuitRepository())


@carrier_bp.route("/", methods=["GET"])
@doc(summary="获取运营商列表", tags=["运营商"], responses={200: "ApiResponse", 500: "ApiError"})
@login_required
@permission_required("carrier:view")
@rate_limit_api
def list_carriers():
    page, per_page = RequestValidator.validate_pagination_params()
    filters = {}
    if request.args.get("status"):
        filters["status"] = request.args.get("status")
    if request.args.get("carrier_type"):
        filters["carrier_type"] = request.args.get("carrier_type")
    if request.args.get("keyword"):
        filters["keyword"] = request.args.get("keyword")

    result = carrier_service.repository.list_with_filters(filters, page=page, per_page=per_page)

    counts = carrier_service.repository.stats_by_ids([c.id for c in result["items"]])
    items = []
    for c in result["items"]:
        d = c.to_dict()
        d["circuit_count"] = counts.get(c.id, 0)
        items.append(d)

    return APIResponse.success(
        data={"items": items, "total": result["total"], "page": result["page"],
              "per_page": result["per_page"]}
    )


@carrier_bp.route("/", methods=["POST"])
@doc(summary="创建运营商", tags=["运营商"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/CarrierCreate"}}}}, responses={201: "CarrierResponse", 400: "ApiError", 409: "ApiError"})
@login_required
@permission_required("carrier:create")
@rate_limit_api
@transactional
def create_carrier():
    """创建运营商。重名返回 409（AC-C-19）"""
    payload = CarrierCreateSchema().load(request.get_json() or {})
    if carrier_service.repository.get_by_name(payload["name"]):
        raise PresetResponseError(
            message=f"运营商「{payload['name']}」已存在",
            error_code="CARRIER_NAME_CONFLICT",
            status_code=409,
        )
    carrier = carrier_service.repository.create(payload)
    logger.info("创建运营商 id=%s name=%s", carrier.id, carrier.name)
    return APIResponse.success(data=carrier.to_dict(), message="运营商创建成功", status_code=201)


@carrier_bp.route("/<int:carrier_id>", methods=["PUT"])
@doc(summary="更新运营商", tags=["运营商"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/CarrierUpdate"}}}}, responses={200: "CarrierResponse", 404: "ApiError", 409: "ApiError"})
@login_required
@permission_required("carrier:update")
@rate_limit_api
@transactional
def update_carrier(carrier_id):
    carrier = carrier_service.repository.find_by_id(carrier_id)
    if not carrier:
        raise PresetResponseError(
            message="运营商不存在",
            error_code="CARRIER_NOT_FOUND",
            status_code=404,
        )

    payload = CarrierUpdateSchema().load(request.get_json() or {})
    if payload.get("name") and payload["name"] != carrier.name:
        if carrier_service.repository.get_by_name(payload["name"]):
            raise PresetResponseError(
                message=f"运营商「{payload['name']}」已存在",
                error_code="CARRIER_NAME_CONFLICT",
                status_code=409,
            )
    updated = carrier_service.repository.update(carrier_id, payload)
    return APIResponse.success(data=updated.to_dict(), message="运营商更新成功")


@carrier_bp.route("/<int:carrier_id>", methods=["DELETE"])
@doc(summary="删除运营商", tags=["运营商"], responses={200: "ApiResponse", 404: "ApiError", 409: "ApiError"})
@login_required
@permission_required("carrier:delete")
@rate_limit_api
@transactional
def delete_carrier(carrier_id):
    """软删运营商

    **有未终止线路挂靠时拒绝 409**（AC-C-20）。阻断在服务层而非靠 DB 的
    `ON DELETE RESTRICT`：`Carrier` 是软删模型且全仓无 `purge` 入口，
    数据库级 RESTRICT 永不触发（评审 B-8）。
    """
    try:
        carrier_service.delete_carrier(carrier_id)
    except ValidationError as e:
        if e.field == "id":
            raise PresetResponseError(message=e.message, status_code=404) from e
        raise PresetResponseError(
            message=e.message,
            error_code="CARRIER_HAS_CIRCUITS",
            status_code=409,
            details=getattr(e, "details", None),
        ) from e
    return APIResponse.success(message="运营商删除成功")
