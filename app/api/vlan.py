# -*- coding: utf-8 -*-
"""
VLAN API

提供VLAN管理的 RESTful API 端点。
"""
from app.utils.logging import get_logger

from flask import Blueprint, request
from marshmallow import Schema, fields, validate

from app.api.base import APIResponse
from app.services.vlan_service import VLANService
from app.persistence.vlan_repository import VLANRepository
from app.exceptions.validation import ValidationError
from app.exceptions.data_access import RecordNotFoundError
from app.openapi.doc import doc, public
from app.utils import login_required, permission_required, rate_limit_api
from app.utils.transactional import transactional

logger = get_logger(__name__)

vlan_bp = Blueprint("vlan", __name__)

_vlan_service = VLANService(VLANRepository())


class VLANCreateSchema(Schema):
    vlan_id = fields.Int(required=True, validate=validate.Range(min=1, max=4094))
    name = fields.Str(required=True, validate=validate.Length(min=1, max=64))
    purpose = fields.Str(load_default=None, validate=validate.Length(max=200))
    subnet_id = fields.Int(load_default=None)
    room_id = fields.Int(load_default=None)
    device_id = fields.Int(required=True)
    status = fields.Int(load_default=1)


class VLANUpdateSchema(Schema):
    name = fields.Str(validate=validate.Length(min=1, max=64))
    purpose = fields.Str(validate=validate.Length(max=200))
    subnet_id = fields.Int()
    room_id = fields.Int()
    status = fields.Int()


@vlan_bp.route("/", methods=["GET"])
@doc(summary="查询VLAN列表", tags=["VLAN"], responses={200: "VLANResponse", 401: "ApiError"})
@login_required
@permission_required("switch:view")
@rate_limit_api
def list_vlans():
    from app.models.vlan import VLAN
    from app.persistence.switch_ext_repository import SwitchExtRepository

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', type=str)
    device_id = request.args.get('device_id', type=int)
    room_id = request.args.get('room_id', type=int)

    vlan_repo = VLANRepository()
    result = vlan_repo.paginate_with_search(
        search=search,
        device_id=device_id,
        room_id=room_id,
        page=page,
        per_page=per_page,
    )
    data_list = result["data"]
    total_count = result["total_count"]

    dev_ids = {v.device_id for v in data_list if v.device_id}
    sc_map = {}
    if dev_ids:
        switch_ext_repo = SwitchExtRepository()
        sc_map = switch_ext_repo.get_has_ssh_map(list(dev_ids))

    items = []
    for vlan_obj in data_list:
        d = vlan_obj.to_dict()
        d['has_ssh'] = sc_map.get(d.get('device_id'), False)
        items.append(d)

    total_pages = (total_count + per_page - 1) // per_page
    return APIResponse.paginated(items, page, per_page, total_count)


@vlan_bp.route("/<int:vlan_id>", methods=["GET"])
@doc(summary="获取VLAN详情", tags=["VLAN"], responses={200: "VLANResponse", 404: "ApiError"})
@login_required
@permission_required("switch:view")
def get_vlan(vlan_id):
    vlan = _vlan_service.get_by_id(vlan_id)
    if not vlan:
        return APIResponse.error("VLAN不存在", error_code="VLAN_NOT_FOUND", status_code=404)
    return APIResponse.success(data=vlan.to_dict(), message="获取VLAN详情成功")


@vlan_bp.route("/", methods=["POST"])
@doc(summary="创建VLAN", tags=["VLAN"], responses={201: "VLANResponse", 409: "ApiError"})
@login_required
@permission_required("switch:create")
@transactional
def create_vlan():
    schema = VLANCreateSchema()
    data = schema.load(request.get_json())
    try:
        vlan = _vlan_service.create(data)
        return APIResponse.success(data=vlan.to_dict(), message="VLAN创建成功", status_code=201)
    except ValidationError as e:
        return APIResponse.error(str(e), error_code="VLAN_CONFLICT", status_code=409)


@vlan_bp.route("/<int:vlan_id>", methods=["PUT"])
@doc(summary="更新VLAN", tags=["VLAN"], responses={200: "VLANResponse", 404: "ApiError"})
@login_required
@permission_required("switch:update")
@transactional
def update_vlan(vlan_id):
    schema = VLANUpdateSchema()
    data = schema.load(request.get_json())
    try:
        vlan = _vlan_service.update(vlan_id, data)
        return APIResponse.success(data=vlan.to_dict(), message="VLAN更新成功")
    except RecordNotFoundError as e:
        return APIResponse.error(str(e), error_code="VLAN_NOT_FOUND", status_code=404)
    except ValidationError as e:
        return APIResponse.error(str(e), error_code="VALIDATION_ERROR", status_code=422)


@vlan_bp.route("/<int:vlan_id>", methods=["DELETE"])
@doc(summary="删除VLAN", tags=["VLAN"], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("switch:delete")
@transactional
def delete_vlan(vlan_id):
    if _vlan_service.delete(vlan_id):
        return APIResponse.success(message="VLAN删除成功")
    return APIResponse.error("VLAN不存在", error_code="VLAN_NOT_FOUND", status_code=404)
