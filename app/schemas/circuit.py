# -*- coding: utf-8 -*-
"""线路 / 运营商请求验证 Schema

按 `app/schemas/device.py` 已确立的约定：被 `app/openapi/spec.py` 引用的 Schema
不在 `app/api/` 下就地定义。

带宽入参约定（`docs/design/G1-线路管理-数据模型设计文档-20260928.md` §6）：
`{value, unit}` 与 `{mbps}` **二选一**，同时出现返回 400（AC-C-15）。
该互斥是跨字段校验，放在 `@validates_schema` 里——marshmallow 的字段级
validator 看不到兄弟字段。
"""
from marshmallow import EXCLUDE, Schema, ValidationError, fields, validate, validates_schema

from app.core.enums import (
    BANDWIDTH_STEP_IEC,
    BANDWIDTH_STEP_SI,
    BillingMode,
    CarrierStatus,
    CarrierType,
    CircuitStatus,
)

_BILLING_MODES = [m.value for m in BillingMode]
_CIRCUIT_STATUSES = [s.value for s in CircuitStatus]
_CARRIER_TYPES = [t.value for t in CarrierType]
_CARRIER_STATUSES = [s.value for s in CarrierStatus]
_STEPS = [BANDWIDTH_STEP_SI, BANDWIDTH_STEP_IEC]


class _BandwidthFieldsMixin:
    """带宽入参的三个字段 + 二选一互斥校验。

    为什么允许两种写法：`{value, unit}` 是**人**的输入形态（表单里填 10 G），
    `{mbps}` 是**机**的输入形态（脚本按绝对 Mbps 灌数据）。强制其一会让另一类
    调用方在客户端做换算，换算口径一旦各写一份必然漂移。
    """

    bandwidth_value = fields.Float(allow_none=True, validate=validate.Range(min=0))
    bandwidth_unit = fields.Str(allow_none=True, validate=validate.OneOf(["M", "G", "T", "P"]))
    bandwidth_mbps = fields.Int(allow_none=True, validate=validate.Range(min=0))
    bandwidth_step = fields.Int(allow_none=True, validate=validate.OneOf(_STEPS))

    @validates_schema
    def _validate_bandwidth_mutually_exclusive(self, data, **kwargs):
        has_pair = data.get("bandwidth_value") is not None or data.get("bandwidth_unit") is not None
        has_mbps = data.get("bandwidth_mbps") is not None
        if has_pair and has_mbps:
            raise ValidationError(
                "带宽入参只能二选一：{bandwidth_value, bandwidth_unit} 或 bandwidth_mbps，不能同时给",
                field_name="bandwidth_mbps",
            )
        if data.get("bandwidth_value") is not None and not data.get("bandwidth_unit"):
            raise ValidationError(
                "给出了 bandwidth_value 时必须同时给出 bandwidth_unit",
                field_name="bandwidth_unit",
            )


class _CommittedFieldsMixin(Schema):
    """保底带宽双形态入参（与带宽 `{value, unit}`/`{mbps}` 同款互斥语义）

    换算同样在后端（parse_bandwidth，SI/IEC 由 bandwidth_step 裁定）——
    前端只收集不换算，避免换算口径出现第二个真源。
    """

    committed_value = fields.Float(allow_none=True, validate=validate.Range(min=0))
    committed_unit = fields.Str(allow_none=True, validate=validate.OneOf(["M", "G", "T", "P"]))

    @validates_schema
    def _validate_committed_mutually_exclusive(self, data, **kwargs):
        has_pair = (
            data.get("committed_value") is not None
            or data.get("committed_unit") is not None
        )
        has_mbps = data.get("committed_mbps") is not None
        if has_pair and has_mbps:
            raise ValidationError(
                "保底带宽入参只能二选一：{committed_value, committed_unit} 或 committed_mbps，不能同时给",
                field_name="committed_mbps",
            )
        if data.get("committed_value") is not None and not data.get("committed_unit"):
            raise ValidationError(
                "给出了 committed_value 时必须同时给出 committed_unit",
                field_name="committed_unit",
            )


class CircuitCreateSchema(_BandwidthFieldsMixin, _CommittedFieldsMixin, Schema):
    """创建线路请求"""

    class Meta:
        unknown = EXCLUDE

    circuit_no = fields.Str(required=True, validate=validate.Length(min=1, max=64))
    name = fields.Str(allow_none=True, validate=validate.Length(max=100))
    carrier_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    customer_id = fields.Int(allow_none=True, validate=validate.Range(min=1))

    billing_mode = fields.Str(allow_none=True, validate=validate.OneOf(_BILLING_MODES))
    committed_mbps = fields.Int(allow_none=True, validate=validate.Range(min=0))
    monthly_fee = fields.Float(allow_none=True, validate=validate.Range(min=0))
    overage_unit_price = fields.Float(allow_none=True, validate=validate.Range(min=0))
    traffic_unit_price = fields.Float(allow_none=True, validate=validate.Range(min=0))
    currency = fields.Str(allow_none=True, validate=validate.Length(min=3, max=3))

    access_type = fields.Str(allow_none=True, validate=validate.Length(max=20))
    status = fields.Str(allow_none=True, validate=validate.OneOf(_CIRCUIT_STATUSES))
    sla_level = fields.Str(allow_none=True, validate=validate.Length(max=20))
    start_date = fields.Date(allow_none=True)
    end_date = fields.Date(allow_none=True)
    contract_no = fields.Str(allow_none=True, validate=validate.Length(max=100))

    a_end_room_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    z_end_room_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    a_end_device_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    z_end_device_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    a_end_port_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    z_end_port_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    a_end_desc = fields.Str(allow_none=True, validate=validate.Length(max=200))
    z_end_desc = fields.Str(allow_none=True, validate=validate.Length(max=200))
    notes = fields.Str(allow_none=True)


class CircuitUpdateSchema(_BandwidthFieldsMixin, _CommittedFieldsMixin, Schema):
    """更新线路请求（全字段可选）"""

    class Meta:
        unknown = EXCLUDE

    circuit_no = fields.Str(validate=validate.Length(min=1, max=64))
    name = fields.Str(allow_none=True, validate=validate.Length(max=100))
    carrier_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    customer_id = fields.Int(allow_none=True, validate=validate.Range(min=1))

    billing_mode = fields.Str(allow_none=True, validate=validate.OneOf(_BILLING_MODES))
    committed_mbps = fields.Int(allow_none=True, validate=validate.Range(min=0))
    monthly_fee = fields.Float(allow_none=True, validate=validate.Range(min=0))
    overage_unit_price = fields.Float(allow_none=True, validate=validate.Range(min=0))
    traffic_unit_price = fields.Float(allow_none=True, validate=validate.Range(min=0))
    currency = fields.Str(allow_none=True, validate=validate.Length(min=3, max=3))

    access_type = fields.Str(allow_none=True, validate=validate.Length(max=20))
    status = fields.Str(allow_none=True, validate=validate.OneOf(_CIRCUIT_STATUSES))
    sla_level = fields.Str(allow_none=True, validate=validate.Length(max=20))
    start_date = fields.Date(allow_none=True)
    end_date = fields.Date(allow_none=True)
    contract_no = fields.Str(allow_none=True, validate=validate.Length(max=100))

    a_end_room_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    z_end_room_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    a_end_device_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    z_end_device_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    a_end_port_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    z_end_port_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    a_end_desc = fields.Str(allow_none=True, validate=validate.Length(max=200))
    z_end_desc = fields.Str(allow_none=True, validate=validate.Length(max=200))
    notes = fields.Str(allow_none=True)


class CircuitSegmentItemSchema(Schema):
    """分段项（整批替换的单元）"""

    class Meta:
        unknown = EXCLUDE

    connection_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    device_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    port_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    hop_desc = fields.Str(allow_none=True, validate=validate.Length(max=200))
    notes = fields.Str(allow_none=True, validate=validate.Length(max=500))


class CircuitSegmentsReplaceSchema(Schema):
    """整批替换分段请求

    只提供"整批替换"一种写形态（设计文档 §5.3 决策）：有序序列的逐条 CRUD
    会产生序号空洞与重复中间态。
    """

    class Meta:
        unknown = EXCLUDE

    segments = fields.List(
        fields.Nested(CircuitSegmentItemSchema), required=True, validate=validate.Length(max=200)
    )


class CarrierCreateSchema(Schema):
    """创建运营商请求"""

    class Meta:
        unknown = EXCLUDE

    name = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    short_name = fields.Str(allow_none=True, validate=validate.Length(max=50))
    carrier_type = fields.Str(allow_none=True, validate=validate.OneOf(_CARRIER_TYPES))
    status = fields.Str(allow_none=True, validate=validate.OneOf(_CARRIER_STATUSES))
    contact_person = fields.Str(allow_none=True, validate=validate.Length(max=100))
    contact_phone = fields.Str(allow_none=True, validate=validate.Length(max=50))
    hotline = fields.Str(allow_none=True, validate=validate.Length(max=50))
    email = fields.Email(allow_none=True, validate=validate.Length(max=100))
    default_sla_level = fields.Str(allow_none=True, validate=validate.Length(max=20))
    qualification_no = fields.Str(allow_none=True, validate=validate.Length(max=100))
    notes = fields.Str(allow_none=True)


class CarrierUpdateSchema(Schema):
    """更新运营商请求"""

    class Meta:
        unknown = EXCLUDE

    name = fields.Str(validate=validate.Length(min=1, max=100))
    short_name = fields.Str(allow_none=True, validate=validate.Length(max=50))
    carrier_type = fields.Str(allow_none=True, validate=validate.OneOf(_CARRIER_TYPES))
    status = fields.Str(allow_none=True, validate=validate.OneOf(_CARRIER_STATUSES))
    contact_person = fields.Str(allow_none=True, validate=validate.Length(max=100))
    contact_phone = fields.Str(allow_none=True, validate=validate.Length(max=50))
    hotline = fields.Str(allow_none=True, validate=validate.Length(max=50))
    email = fields.Email(allow_none=True, validate=validate.Length(max=100))
    default_sla_level = fields.Str(allow_none=True, validate=validate.Length(max=20))
    qualification_no = fields.Str(allow_none=True, validate=validate.Length(max=100))
    notes = fields.Str(allow_none=True)
