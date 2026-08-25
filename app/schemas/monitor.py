# -*- coding: utf-8 -*-
"""监控请求验证 Schema

供 API 层和 Service 层共同引用，消除 service → api 的反向依赖。
"""

from marshmallow import Schema, fields, validate, EXCLUDE, validates_schema, ValidationError
from app.core.enums import MonitorProtocolCode
from app.services.monitoring.protocol_registry import (
    protocol_required_fields,
)
from app.services.monitoring.snmp_versions import SNMP_REQUIRED_BY_VERSION


def _validate_zabbix_api_url(value):
    if not isinstance(value, str) or not value:
        raise ValidationError("api_url 不能为空")
    if not (value.startswith("http://") or value.startswith("https://")):
        raise ValidationError("api_url 必须以 http:// 或 https:// 开头")
    return True


class MonitorCredentialUpsertSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    protocol = fields.Str(
        required=True,
        validate=validate.OneOf(
            [e.value for e in MonitorProtocolCode],
            error="protocol 必须为 " + "/".join(e.value for e in MonitorProtocolCode),
        ),
    )
    payload = fields.Dict(required=True)
    name = fields.Str(required=True, validate=validate.Length(min=1, max=128, error="凭据名称长度须在 1-128 之间"))
    device_ids = fields.List(fields.Int(), required=False, allow_none=True)

    @validates_schema
    def validate_payload_by_protocol(self, data, **kwargs):
        protocol = data.get("protocol")
        payload = data.get("payload")
        if protocol is None or payload is None:
            return

        errors: dict = {}
        if protocol == MonitorProtocolCode.SNMP.value:
            version = payload.get("version") or payload.get("snmp_version") or "v2c"
            if version not in SNMP_REQUIRED_BY_VERSION:
                errors["payload"] = "snmp 必须包含合法的 version（v2c 或 v3）"
            else:
                required = SNMP_REQUIRED_BY_VERSION[version]
                missing = [
                    k for k in required
                    if not isinstance(payload.get(k), str) or not payload.get(k)
                ]
                if missing:
                    errors["payload"] = (
                        f"snmp({version}) 缺少必填字段: {', '.join(missing)}"
                    )
        elif protocol == MonitorProtocolCode.ZABBIX.value:
            zerr = ZabbixCredentialSchema().validate(payload)
            if zerr:
                errors["payload"] = "; ".join(
                    f"{k}: {' '.join(v) if isinstance(v, list) else v}"
                    for k, v in zerr.items()
                )
        else:
            required = protocol_required_fields(protocol)
            missing = [
                k for k in required
                if not isinstance(payload.get(k), str) or not payload.get(k)
            ]
            if missing:
                errors["payload"] = (
                    f"{protocol} 缺少必填字段: {', '.join(missing)}"
                )

        if errors:
            raise ValidationError(errors)


class MonitorCredentialPayloadUpdateSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    payload = fields.Dict(
        required=True,
        keys=fields.Str(),
        values=fields.Raw(),
    )
    name = fields.Str(required=False, allow_none=True)

    @validates_schema
    def _check_not_empty(self, data, **kwargs):
        payload = data.get("payload")
        if not isinstance(payload, dict) or len(payload) == 0:
            raise ValidationError({"payload": "payload 不能为空对象"})


class ZabbixCredentialSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    api_url = fields.Str(required=True, validate=_validate_zabbix_api_url)
    api_token = fields.Str(
        required=True,
        validate=validate.Length(min=1, error="api_token 不能为空"),
    )
    verify_ssl = fields.Bool(required=False, allow_none=True)
    match_by = fields.Str(
        required=False,
        validate=validate.OneOf(
            ["host", "ip"], error="match_by 必须为 host 或 ip"
        ),
    )


class MonitorCheckBatchSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    device_ids = fields.List(
        fields.Int(),
        required=True,
        validate=validate.Length(min=1, max=50, error="device_ids 须含 1-50 个设备 id"),
    )


class MonitorAlertListQuerySchema(Schema):

    class Meta:
        unknown = EXCLUDE

    alert_type = fields.Str(
        required=False, allow_none=True,
        validate=validate.OneOf(
            ["device_unreachable", "device_recovered"],
            error="alert_type 必须为 device_unreachable / device_recovered",
        ),
    )
    severity = fields.Str(
        required=False, allow_none=True,
        validate=validate.OneOf(
            ["info", "warning", "critical"],
            error="severity 必须为 info / warning / critical",
        ),
    )
    status = fields.Str(
        required=False, allow_none=True,
        validate=validate.OneOf(
            ["pending", "sent", "failed"],
            error="status 必须为 pending / sent / failed",
        ),
    )
    device_id = fields.Int(required=False, allow_none=True)
    start_date = fields.DateTime(required=False, allow_none=True)
    end_date = fields.DateTime(required=False, allow_none=True)
    page = fields.Int(required=False, allow_none=True, validate=validate.Range(min=1))
    per_page = fields.Int(required=False, allow_none=True, validate=validate.Range(min=1, max=200))
    scope = fields.Str(
        required=False, allow_none=True,
        validate=validate.OneOf(
            ["all", "mine"],
            error="scope 必须为 all / mine",
        ),
    )
    metric_key = fields.Str(required=False, allow_none=True, validate=validate.Length(max=64))
    index_key = fields.Str(required=False, allow_none=True, validate=validate.Length(max=128))

    @validates_schema
    def _check_range(self, data, **kwargs):
        sd, ed = data.get("start_date"), data.get("end_date")
        if sd and ed and sd > ed:
            raise ValidationError({"start_date": "start_date 不能晚于 end_date"})


class MonitorDeviceMonitorEnabledSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    enabled = fields.Bool(required=True)


class MonitorBatchMonitorEnabledSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    device_ids = fields.List(
        fields.Int(),
        required=True,
        validate=validate.Length(min=1, max=200, error="device_ids 须含 1-200 个设备 id"),
    )
    enabled = fields.Bool(required=True)


class MonitorConfigUpdateSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    updates = fields.Dict(keys=fields.Str(), values=fields.Raw(), required=True)

    @validates_schema
    def _validate(self, data, **kwargs):
        from app.services.monitoring.dynamic_config import CAMEL_TO_KEY, all_entries

        errors = {}
        for camel, value in (data.get("updates") or {}).items():
            key = CAMEL_TO_KEY.get(camel)
            if key is None:
                errors[camel] = "未知或不可配置的配置项"
                continue
            entry = all_entries().get(key)
            if entry is None or not entry.editable:
                errors[camel] = "该配置项不可在线修改（需重启服务）"
                continue
            if entry.type == "int":
                if isinstance(value, bool) or not isinstance(value, int):
                    errors[camel] = "必须为整数"
                    continue
                if entry.min is not None and value < entry.min:
                    errors[camel] = f"不得小于 {entry.min}"
                elif entry.max is not None and value > entry.max:
                    errors[camel] = f"不得大于 {entry.max}"
            elif entry.type == "string":
                if not isinstance(value, str) or value.strip() == "":
                    errors[camel] = "必须为非空字符串"
            elif entry.type == "bool":
                if not isinstance(value, bool):
                    errors[camel] = "必须为布尔值"
        if errors:
            raise ValidationError(errors)


class MonitorSilenceRuleCreateSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    name = fields.Str(required=True, validate=validate.Length(min=1, max=128))
    device_ids = fields.List(fields.Int(), required=False, allow_none=True)
    alert_types = fields.List(fields.Str(), required=False, allow_none=True)
    silence_from = fields.Str(required=True)
    silence_until = fields.Str(required=True)
    reason = fields.Str(required=False, allow_none=True, validate=validate.Length(max=255))
    enabled = fields.Bool(required=False, load_default=True)


class MonitorSilenceRuleUpdateSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    name = fields.Str(required=False, validate=validate.Length(min=1, max=128))
    device_ids = fields.List(fields.Int(), required=False, allow_none=True)
    alert_types = fields.List(fields.Str(), required=False, allow_none=True)
    silence_from = fields.Str(required=False)
    silence_until = fields.Str(required=False)
    reason = fields.Str(required=False, allow_none=True, validate=validate.Length(max=255))
    enabled = fields.Bool(required=False)


class MonitorAlertDependencyRuleCreateSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    name = fields.Str(required=True, validate=validate.Length(min=1, max=128))
    upstream_device_id = fields.Int(required=True)
    downstream_device_id = fields.Int(required=True)
    alert_types = fields.List(fields.Str(), required=False, allow_none=True)
    reason = fields.Str(required=False, allow_none=True, validate=validate.Length(max=255))
    enabled = fields.Bool(required=False, load_default=True)


class MonitorAlertDependencyRuleUpdateSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    name = fields.Str(required=False, validate=validate.Length(min=1, max=128))
    upstream_device_id = fields.Int(required=False)
    downstream_device_id = fields.Int(required=False)
    alert_types = fields.List(fields.Str(), required=False, allow_none=True)
    reason = fields.Str(required=False, allow_none=True, validate=validate.Length(max=255))
    enabled = fields.Bool(required=False)


class MonitorSlaTargetCreateSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    name = fields.Str(required=True, validate=validate.Length(min=1, max=128))
    target_device_ids = fields.List(fields.Int(), required=True, validate=validate.Length(min=1))
    target_ratio = fields.Float(required=True, validate=validate.Range(min=0, max=1, min_inclusive=False, max_inclusive=True))
    window_days = fields.Int(required=False, load_default=30, validate=validate.Range(min=1))
    description = fields.Str(required=False, allow_none=True, validate=validate.Length(max=255))
    enabled = fields.Bool(required=False, load_default=True)


class MonitorSlaTargetUpdateSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    name = fields.Str(required=False, validate=validate.Length(min=1, max=128))
    target_device_ids = fields.List(fields.Int(), required=False)
    target_ratio = fields.Float(required=False, validate=validate.Range(min=0, max=1, min_inclusive=False, max_inclusive=True))
    window_days = fields.Int(required=False, validate=validate.Range(min=1))
    description = fields.Str(required=False, allow_none=True, validate=validate.Length(max=255))
    enabled = fields.Bool(required=False)


class DeviceMetricOverrideUpsertSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    device_id = fields.Int(required=True)
    metric_key = fields.Str(required=True, validate=validate.Length(min=1, max=64))
    threshold = fields.Dict(required=True)
    enabled = fields.Bool(required=False, load_default=True)
    note = fields.Str(required=False, allow_none=True, validate=validate.Length(max=255))


class MonitorEscalationStepInputSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    step_no = fields.Int(required=False, validate=validate.Range(min=1))
    wait_minutes = fields.Int(required=True, validate=validate.Range(min=1))
    escalate_severity = fields.Str(required=False, allow_none=True, validate=validate.Length(max=32))
    escalate_to_role_id = fields.Int(required=False, allow_none=True)
    escalate_webhook_url = fields.Str(required=False, allow_none=True, validate=validate.Length(max=512))
    enabled = fields.Bool(required=False, load_default=True)


class MonitorEscalationPolicyCreateSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    name = fields.Str(required=True, validate=validate.Length(min=1, max=128))
    alert_type = fields.Str(required=False, allow_none=True, validate=validate.Length(max=64))
    severity = fields.Str(required=False, allow_none=True, validate=validate.Length(max=32))
    wait_minutes = fields.Int(required=False, load_default=30, validate=validate.Range(min=1))
    escalate_severity = fields.Str(required=False, allow_none=True, validate=validate.Length(max=32))
    escalate_to_role_id = fields.Int(required=False, allow_none=True)
    escalate_webhook_url = fields.Str(required=False, allow_none=True, validate=validate.Length(max=512))
    repeat_minutes = fields.Int(required=False, load_default=60, validate=validate.Range(min=1))
    enabled = fields.Bool(required=False, load_default=True)
    steps = fields.List(fields.Nested(MonitorEscalationStepInputSchema), required=False, allow_none=True)


class MonitorEscalationPolicyUpdateSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    name = fields.Str(required=False, validate=validate.Length(min=1, max=128))
    alert_type = fields.Str(required=False, allow_none=True, validate=validate.Length(max=64))
    severity = fields.Str(required=False, allow_none=True, validate=validate.Length(max=32))
    wait_minutes = fields.Int(required=False, validate=validate.Range(min=1))
    escalate_severity = fields.Str(required=False, allow_none=True, validate=validate.Length(max=32))
    escalate_to_role_id = fields.Int(required=False, allow_none=True)
    escalate_webhook_url = fields.Str(required=False, allow_none=True, validate=validate.Length(max=512))
    repeat_minutes = fields.Int(required=False, validate=validate.Range(min=1))
    enabled = fields.Bool(required=False)
    steps = fields.List(fields.Nested(MonitorEscalationStepInputSchema), required=False, allow_none=True)


class OidCategoryRuleCreateSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    prefix = fields.Str(required=True, validate=validate.Length(min=1, max=128))
    category = fields.Str(required=True, validate=validate.Length(min=1, max=32))
    label = fields.Str(required=False, allow_none=True, validate=validate.Length(max=64))
    device_type = fields.Str(required=False, allow_none=True, validate=validate.Length(max=16))
    vendor_id = fields.Str(required=False, allow_none=True, validate=validate.Length(max=32))
    priority = fields.Int(required=False, load_default=100)
    enabled = fields.Bool(required=False, load_default=True)


class OidCategoryRuleUpdateSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    prefix = fields.Str(required=False, validate=validate.Length(min=1, max=128))
    category = fields.Str(required=False, validate=validate.Length(min=1, max=32))
    label = fields.Str(required=False, allow_none=True, validate=validate.Length(max=64))
    device_type = fields.Str(required=False, allow_none=True, validate=validate.Length(max=16))
    vendor_id = fields.Str(required=False, allow_none=True, validate=validate.Length(max=32))
    priority = fields.Int(required=False)
    enabled = fields.Bool(required=False)


class DeviceTypeRecommendUpdateSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    categories = fields.List(fields.Str(), required=True)


class MibScanImportSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    items = fields.List(fields.Dict(), required=True, validate=validate.Length(min=1, error="items 不能为空"))


class MibScanPersistRuleSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    oid = fields.Str(required=True, validate=validate.Length(min=1, error="oid 不能为空"))
    device_type = fields.Str(required=True, validate=validate.Length(min=1, max=16))
    vendor_id = fields.Str(required=False, allow_none=True, validate=validate.Length(max=32))


class MibScanRequestSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    device_id = fields.Int(required=True, validate=validate.Range(min=1))
    timeout = fields.Int(required=False, load_default=30, validate=validate.Range(min=1, max=300))


class VendorBrandCreateSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    enterprise_no = fields.Str(required=True, validate=validate.Length(min=1, max=32))
    brand_name = fields.Str(required=True, validate=validate.Length(min=1, max=64))
    label = fields.Str(required=True, validate=validate.Length(min=1, max=64))
    device_type = fields.Str(required=True, validate=validate.Length(min=1, max=16))
    enabled = fields.Bool(required=False, load_default=True)
    sort_order = fields.Int(required=False, load_default=0)


class VendorBrandUpdateSchema(Schema):

    class Meta:
        unknown = EXCLUDE

    enterprise_no = fields.Str(required=False, validate=validate.Length(min=1, max=32))
    brand_name = fields.Str(required=False, validate=validate.Length(min=1, max=64))
    label = fields.Str(required=False, validate=validate.Length(min=1, max=64))
    device_type = fields.Str(required=False, validate=validate.Length(min=1, max=16))
    enabled = fields.Bool(required=False)
    sort_order = fields.Int(required=False)
