# -*- coding: utf-8 -*-
"""IP 管理请求验证 Schema（T3.1：`ip_routes.py` 12 个写路由的 request_body 契约）。

字段来源：逐条取自各 handler 实际读取的 `data.get(...)`，必填性取自 handler 内的
显式校验（如 `if not ip_address: return 400`）与 docstring 中的请求体示例——
**不按接口名臆测**。约定同 `app/schemas/device.py`。

**12 个写路由中另有 2 个不读请求体**（`detect_ip_endpoint`、`ping_ip`：仅凭路径
参数即可执行，属 action 端点），故有意不声明 `request_body`。
"""
from marshmallow import Schema, fields, validate, EXCLUDE


class IPBanRequestSchema(Schema):
    """封禁 / 解封单个 IP（`POST /ip/ban`、`POST /ip/unban`）。

    handler docstring：`{"ip_address": "10.10.1.100"}`，`room_id` 可选，
    为空时自动查找该 IP 所在机房。
    """
    class Meta:
        unknown = EXCLUDE

    ip_address = fields.Str(required=True, validate=validate.Length(max=45))
    room_id = fields.Int(allow_none=True)


class IPBatchBanRequestSchema(Schema):
    """批量封禁 / 解封（`POST /ip/ban/batch`、`POST /ip/unban/batch`）。"""
    class Meta:
        unknown = EXCLUDE

    ip_list = fields.List(fields.Str(), required=True)
    room_id = fields.Int(allow_none=True)


class IPCustomerUpdateRequestSchema(Schema):
    """更新单个 IP 的客户归属（`PUT /ip/<ip_address>/customer`）。"""
    class Meta:
        unknown = EXCLUDE

    customer_id = fields.Int(allow_none=True)   # 允许置空（解除归属）
    room_id = fields.Int(allow_none=True)


class IPNotesUpdateRequestSchema(Schema):
    """更新单个 IP 的备注（`PUT /ip/<ip_address>/notes`）。"""
    class Meta:
        unknown = EXCLUDE

    notes = fields.Str(allow_none=True)
    room_id = fields.Int(allow_none=True)


class IPBatchCustomerUpdateRequestSchema(Schema):
    """批量更新 IP 客户归属（`POST /ip/batch/customer`）。"""
    class Meta:
        unknown = EXCLUDE

    ip_list = fields.List(fields.Str(), required=True)
    customer_id = fields.Int(allow_none=True)
    room_id = fields.Int(allow_none=True)


class IPBatchNotesUpdateRequestSchema(Schema):
    """批量更新 IP 备注（`POST /ip/batch/notes`）。"""
    class Meta:
        unknown = EXCLUDE

    ip_list = fields.List(fields.Str(), required=True)
    notes = fields.Str(allow_none=True)
    room_id = fields.Int(allow_none=True)


class IPScanPortsRequestSchema(Schema):
    """扫描指定 IP 的端口（`POST /ip/<ip_address>/ports/scan`）。

    `ports` 省略时后端用 `Config.COMMON_PORTS` 作默认端口集
    （`IPCrudService.scan_ports`：`ports if ports else list(Config.COMMON_PORTS)`），
    故非必填。
    """
    class Meta:
        unknown = EXCLUDE

    ports = fields.List(fields.Int(), allow_none=True)


class IPScanNetworkRequestSchema(Schema):
    """全网段扫描（`POST /ip/scan/network`）。

    handler 显式校验：`if not ip_network or room_id is None: return 400`，
    故二者**均为必填**。
    """
    class Meta:
        unknown = EXCLUDE

    ip_network = fields.Str(required=True)      # 例：10.10.1.0/24
    room_id = fields.Int(required=True)
