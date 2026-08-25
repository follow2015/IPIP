# -*- coding: utf-8 -*-
"""监控凭据 CRUD + 链接 + 密文部分更新。"""
from flask import request

from app.api.base import APIResponse, ErrorCode
from app.exceptions.business import BusinessLogicError
from app.exceptions.validation import ValidationError
from app.api.monitor import (
    _ALLOWED_PROTOCOLS,
    _audit_credential_change,
    _credential_payload_schema,
    _credential_upsert_schema,
    credential_service,
    monitor_bp,
)
from app.openapi.doc import doc
from app.utils import login_required, permission_required
from app.utils.transactional import transactional


@monitor_bp.route("/credentials", methods=["POST"])
@doc(summary="批量配置共享监控凭据", tags=["监控"], responses={200: "MonitorCredentialConfigResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def post_credentials():
    """创建共享凭据，并可选地关联到多台设备。"""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")

    errors = _credential_upsert_schema.validate(body)
    if errors:
        raise ValidationError(f"请求参数校验失败: {errors}")

    device_ids = body.get("device_ids") or []
    protocol = body["protocol"]
    payload = body["payload"]
    name = body["name"]

    if device_ids:
        for did in device_ids:
            credential_service.upsert(did, protocol, payload, name)
    else:
        credential_service.create_shared_credential(protocol, payload, name)

    _audit_credential_change(
        "monitor_credential:upsert",
        {"protocol": protocol, "device_ids": device_ids, "count": len(device_ids), "name": name},
    )
    return APIResponse.success(data={"configured": True, "protocol": protocol, "linked": len(device_ids)})


@monitor_bp.route("/credentials", methods=["GET"])
@doc(summary="查询共享监控凭据列表", tags=["监控"], responses={200: "MonitorCredentialListItem"})
@login_required
@permission_required("monitor:view")
def list_credentials():
    """返回共享凭据列表（id/name/protocol/enabled/linked_count），永不回显密文。"""
    from app.services.monitoring.credential_service import list_credentials as _list
    rows = _list()
    return APIResponse.success(data=rows)


@monitor_bp.route("/credentials/<int:credential_id>/devices", methods=["GET"])
@doc(summary="查询共享凭据关联的设备", tags=["监控"], responses={200: "LinkedDevicesResponse"})
@login_required
@permission_required("monitor:view")
def list_linked_devices(credential_id: int):
    """返回某共享凭据关联的设备列表。"""
    if not credential_service.credential_exists(credential_id):
        raise BusinessLogicError("共享凭据不存在", status_code=404)
    devices = credential_service.linked_devices_detail(credential_id)
    return APIResponse.success(data=devices)


@monitor_bp.route("/credentials/<int:credential_id>", methods=["PATCH"])
@doc(summary="更新共享凭据（启停/改名）", tags=["监控"], responses={200: "MonitorCredentialPatchResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def patch_credential(credential_id: int):
    """更新共享凭据的启用状态或名称（不触及密文）。"""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")

    if not credential_service.credential_exists(credential_id):
        raise BusinessLogicError("共享凭据不存在", status_code=404)

    enabled = body.get("enabled")
    name = body.get("name")
    if enabled is None and name is None:
        raise ValidationError("至少提供 enabled 或 name 字段")

    credential_service.patch_credential(credential_id, enabled=enabled, name=name)
    _audit_credential_change(
        "monitor_credential:patch",
        {"credential_id": credential_id, "enabled": enabled, "name": name},
    )
    return APIResponse.success(data={"updated": True, "credential_id": credential_id})


@monitor_bp.route("/credentials/<int:credential_id>", methods=["DELETE"])
@doc(summary="删除共享凭据", tags=["监控"], responses={200: "MonitorCredentialDeleteResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def delete_credential(credential_id: int):
    """删除共享凭据（须先取消所有设备关联）。"""
    if not credential_service.credential_exists(credential_id):
        raise BusinessLogicError("共享凭据不存在", status_code=404)

    linked = credential_service.linked_device_ids(credential_id)
    if linked:
        raise BusinessLogicError(
            f"该凭据仍关联 {len(linked)} 台设备，请先取消关联后再删除",
            status_code=409,
        )

    credential_service.delete_shared_credential(credential_id)
    _audit_credential_change(
        "monitor_credential:delete_shared",
        {"credential_id": credential_id},
    )
    return APIResponse.success(data={"deleted": True, "credential_id": credential_id})


@monitor_bp.route("/credentials/batch-delete", methods=["POST"])
@doc(summary="批量删除共享凭据", tags=["监控"])
@login_required
@permission_required("monitor:config")
@transactional
def batch_delete_credentials():
    """批量删除共享凭据（须先取消所有设备关联）。

    替代前端串行 for...of + await + 静默 catch，返回失败明细供前端展示。
    """
    data = request.get_json(silent=True) or {}
    ids = data.get("ids") or []
    if not isinstance(ids, list):
        raise ValidationError("ids 必须为列表")

    deleted = 0
    failed = []
    for cred_id in ids:
        try:
            if not credential_service.credential_exists(cred_id):
                failed.append({"id": cred_id, "reason": "凭据不存在"})
                continue
            linked = credential_service.linked_device_ids(cred_id)
            if linked:
                failed.append({
                    "id": cred_id,
                    "reason": f"仍关联 {len(linked)} 台设备，请先取消关联",
                })
                continue
            credential_service.delete_shared_credential(cred_id)
            deleted += 1
        except Exception as e:
            failed.append({"id": cred_id, "reason": str(e)[:200]})

    if deleted > 0:
        _audit_credential_change(
            "monitor_credential:batch_delete",
            {"deleted": deleted, "failed_count": len(failed)},
        )
    return APIResponse.success(data={"deleted": deleted, "failed": failed})


@monitor_bp.route("/credentials/<int:credential_id>/link", methods=["POST"])
@doc(summary="关联设备到已有共享凭据", tags=["监控"],
     responses={200: "MonitorCredentialConfigResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def link_existing_credentials(credential_id: int):
    """把一批设备关联到已存在的共享凭据。"""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    device_ids = body.get("device_ids") or []
    if not device_ids:
        raise ValidationError("device_ids 不能为空")
    if not credential_service.credential_exists(credential_id):
        raise BusinessLogicError("共享凭据不存在", status_code=404)
    credential_service.link_existing(credential_id, device_ids)
    _audit_credential_change(
        "monitor_credential:link",
        {"credential_id": credential_id, "device_ids": device_ids, "count": len(device_ids)},
    )
    return APIResponse.success(
        data={"linked": True, "credential_id": credential_id, "count": len(device_ids)}
    )


@monitor_bp.route("/credentials/<int:credential_id>/payload", methods=["PUT"])
@doc(
    summary="共享凭据密文部分更新（影响所有关联设备）",
    tags=["监控"],
    responses={200: "MonitorCredentialPayloadUpdateResponse"},
)
@login_required
@permission_required("monitor:config")
@transactional
def put_shared_credential_payload(credential_id: int):
    """按共享凭据维度部分更新密文：解密→合并→加密，影响该凭据全部关联设备。"""
    body = request.get_json(silent=True) or {}
    errors = _credential_payload_schema.validate(body)
    if errors:
        raise ValidationError(f"参数校验失败: {errors}")

    updated_fields, migrated, new_cred_id, protocol = credential_service.update_shared_payload(
        credential_id, body["payload"], name=body.get("name")
    )

    _audit_credential_change(
        "monitor_credential:update_payload_shared",
        {"credential_id": credential_id, "updated_fields": updated_fields},
    )
    return APIResponse.success(
        data={
            "id": new_cred_id,
            "protocol": protocol,
            "updated_fields": updated_fields,
            "credential_migrated": migrated,
        }
    )


@monitor_bp.route(
    "/devices/<int:device_id>/credentials/<int:credential_id>/payload",
    methods=["PUT"],
)
@doc(
    summary="单设备凭据密文部分更新（只影响本设备）",
    tags=["监控"],
    responses={200: "MonitorCredentialPayloadUpdateResponse"},
)
@login_required
@permission_required("monitor:config")
@transactional
def put_device_credential_payload(device_id: int, credential_id: int):
    """按设备维度部分更新密文：只迁移 device_id 这一台设备。"""
    body = request.get_json(silent=True) or {}
    errors = _credential_payload_schema.validate(body)
    if errors:
        raise ValidationError(f"参数校验失败: {errors}")

    if not credential_service.device_exists(device_id):
        raise BusinessLogicError("设备不存在", status_code=404)

    updated_fields, migrated, new_cred_id, protocol = credential_service.update_payload(
        device_id, credential_id, body["payload"], name=body.get("name")
    )

    _audit_credential_change(
        "monitor_credential:update_payload_device",
        {"device_id": device_id, "credential_id": credential_id, "updated_fields": updated_fields},
    )
    return APIResponse.success(
        data={
            "id": new_cred_id,
            "protocol": protocol,
            "updated_fields": updated_fields,
            "credential_migrated": migrated,
        }
    )


@monitor_bp.route(
    "/devices/<int:device_id>/credentials/<protocol>", methods=["DELETE"]
)
@doc(summary="删除监控凭据", tags=["监控"], responses={200: "MonitorCredentialDeleteResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def delete_credentials(device_id: int, protocol: str):
    """删除某设备的指定协议凭据（不存在则为 no-op）。"""
    if protocol not in _ALLOWED_PROTOCOLS:
        raise ValidationError(f"protocol 必须为 {'/'.join(sorted(_ALLOWED_PROTOCOLS))}")

    credential_service.delete(device_id, protocol)
    _audit_credential_change(
        "monitor_credential:delete",
        {"device_id": device_id, "protocol": protocol},
    )
    return APIResponse.success(data={"deleted": True, "protocol": protocol})
