# -*- coding: utf-8 -*-
"""上架方案查询 API（Phase 1 只读）。

POST /api/deployment/plan：输入机房/台数/U高/功率/带宽/端口速率，
输出推荐方案（机柜+U位、IP 建议、交换机端口、限速建议、出口判定）。
count 缺省 = 容量模式（返回还能上多少台）。
纯推荐零副作用——不分配 IP、不登记连接、不下发限速（Phase 2 再议）。
"""
from app.utils.logging import get_logger

from flask import Blueprint, request
from marshmallow import Schema, ValidationError, fields, validate

from app.api.base import APIResponse
from app.openapi.doc import doc
from app.services.deployment_plan_service import DeploymentPlanError
from app.utils import login_required, permission_required, rate_limit_api

logger = get_logger(__name__)

deployment_plan_bp = Blueprint("deployment_plan", __name__)


class DeploymentPlanRequestSchema(Schema):
    """上架方案查询入参"""
    room_id = fields.Int(load_default=None, metadata={"description": "机房ID（可选，缺省全机房择优）"})
    count = fields.Int(allow_none=True, load_default=None, validate=validate.Range(min=1),
                       metadata={"description": "上架台数（缺省=容量模式，返回还能上多少台）"})
    u_height = fields.Int(load_default=2, validate=validate.Range(min=1, max=48),
                          metadata={"description": "单台U高，默认2"})
    power_per_unit = fields.Int(load_default=750, validate=validate.Range(min=1),
                                metadata={"description": "单台功率W，默认750（仅参考）"})
    bandwidth_mbps = fields.Int(load_default=None, validate=validate.Range(min=1),
                                metadata={"description": "单台带宽需求Mbps（可选；缺省不给限速建议）"})
    port_speed = fields.Str(required=True,
                            metadata={"description": "服务器端口速率：如 1000M/1G/10G"})
    ip_scope = fields.Str(load_default=None, validate=validate.OneOf(["public", "private"]),
                          metadata={"description": "IP 类型过滤：public 仅公网 / private 仅内网（缺省不限，推荐序公网优先）"})
    ip_examples = fields.Int(load_default=0, validate=validate.Range(min=0, max=50),
                             metadata={"description": "额外返回的「可分配 IP 样例」数量（0=不返回样例；容量模式默认给 10 个）"})
    ip_pool_scope = fields.Str(load_default="auto", validate=validate.OneOf(["auto", "room"]),
                               metadata={"description": "地址池口径：auto 先本机房后二层域跨机房 / room 只用本机房地址"})


@deployment_plan_bp.route("/plan", methods=["POST"])
@doc(summary="上架方案查询（只读推荐）", tags=["Deployment"],
     responses={200: "ApiResponse", 400: "ApiError", 401: "ApiError"})
@login_required
@permission_required("cabinet:view")
@rate_limit_api
def create_deployment_plan():
    """生成上架推荐方案（纯推荐，零副作用）

    Body Parameters:
        room_id (int): 机房ID，可选，缺省在全部机房中择优
        count (int): 上架台数，可选；缺省=容量模式（返回还能上多少台）
        u_height (int): 单台U高，默认 2
        power_per_unit (int): 单台功率W，默认 750，仅参考不阻断
        bandwidth_mbps (int): 单台带宽需求Mbps，可选；缺省不给限速建议
        port_speed (str): 服务器端口速率，必填：如 1000M/1G/10G
        ip_scope (str): IP 类型过滤，可选：public 仅公网 / private 仅内网
        ip_examples (int): 额外返回的「可分配 IP 样例」数量（0=不要样例）
        ip_pool_scope (str): 地址池口径，可选：auto 先本机房后跨机房 / room 只用本机房
    """
    payload = request.get_json(silent=True) or {}
    try:
        params = DeploymentPlanRequestSchema().load(payload)
    except ValidationError as exc:
        return APIResponse.error(message=f"参数校验失败: {exc.messages}", status_code=400)

    from app.services.deployment_plan_service import build_plan

    try:
        plan = build_plan(
            count=params["count"],
            bandwidth_mbps=params["bandwidth_mbps"],
            port_speed_raw=params["port_speed"],
            u_height=params["u_height"],
            power_per_unit=params["power_per_unit"],
            room_id=params["room_id"],
            ip_scope=params["ip_scope"],
            ip_examples=params["ip_examples"],
            ip_pool_scope=params["ip_pool_scope"],
        )
    except DeploymentPlanError as exc:
        return APIResponse.error(message=str(exc), status_code=400)

    return APIResponse.success(data=plan, message="上架方案生成成功")
