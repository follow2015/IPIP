# -*- coding: utf-8 -*-
"""OID 分类规则 + 设备类型推荐 + 厂商品牌 + MIB 扫描/导入。"""
from flask import request
from marshmallow import ValidationError as MarshmallowValidationError

from app.api.base import APIResponse
from app.api.monitor import (
    credential_service,
    device_repo,
    monitor_bp,
)
from app.core.enums import MonitorProtocolCode
from app.exceptions.business import BusinessLogicError
from app.exceptions.validation import ValidationError
from app.openapi.doc import doc
from app.schemas.monitor import (
    DeviceTypeRecommendUpdateSchema,
    MibScanImportSchema,
    MibScanPersistRuleSchema,
    MibScanRequestSchema,
    OidCategoryRuleCreateSchema,
    OidCategoryRuleUpdateSchema,
    VendorBrandCreateSchema,
    VendorBrandUpdateSchema,
)
from app.utils import login_required, permission_required
from app.utils.logging import get_logger
from app.utils.transactional import transactional

logger = get_logger(__name__)


def _validate_body(schema, body):
    """统一入口校验：JSON 对象 + schema.load。"""
    if not isinstance(body, dict):
        raise ValidationError("请求体必须是 JSON 对象")
    try:
        return schema.load(body)
    except MarshmallowValidationError as e:
        raise ValidationError(f"请求参数校验失败: {e.messages}")



@monitor_bp.route("/oid-category-rules", methods=["GET"])
@doc(summary="列出全部 OID 分类规则", tags=["监控"], responses={200: "OidCategoryRuleListResponse"})
@login_required
@permission_required("monitor:view")
def list_oid_category_rules():
    from app.services.monitoring.oid_category_service import list_rules
    items = list_rules()
    return APIResponse.paginated(data=items, page=1, per_page=len(items) or 1, total=len(items))


@monitor_bp.route("/oid-category-rules", methods=["POST"])
@doc(summary="新增 OID 分类规则", tags=["监控"], responses={200: "OidCategoryRuleMutationResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def create_oid_category_rule():
    data = _validate_body(OidCategoryRuleCreateSchema(), request.get_json(silent=True))
    from app.services.monitoring.oid_category_service import create_rule
    result = create_rule(data)
    return APIResponse.success(data=result)


@monitor_bp.route("/oid-category-rules/<int:rule_id>", methods=["PATCH"])
@doc(summary="更新 OID 分类规则", tags=["监控"], responses={200: "OidCategoryRuleMutationResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def update_oid_category_rule(rule_id: int):
    data = _validate_body(OidCategoryRuleUpdateSchema(), request.get_json(silent=True))
    from app.services.monitoring.oid_category_service import update_rule
    result = update_rule(rule_id, data)
    return APIResponse.success(data=result)


@monitor_bp.route("/oid-category-rules/<int:rule_id>", methods=["DELETE"])
@doc(summary="删除 OID 分类规则", tags=["监控"], responses={200: "OidCategoryRuleMutationResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def delete_oid_category_rule(rule_id: int):
    from app.services.monitoring.oid_category_service import delete_rule
    data = delete_rule(rule_id)
    return APIResponse.success(data=data)



@monitor_bp.route("/device-type-recommends", methods=["GET"])
@doc(summary="列出全部设备类型推荐配置", tags=["监控"], responses={200: "DeviceTypeRecommendListResponse"})
@login_required
@permission_required("monitor:view")
def list_device_type_recommends():
    from app.services.monitoring.oid_category_service import list_recommends
    items = list_recommends()
    return APIResponse.paginated(data=items, page=1, per_page=len(items) or 1, total=len(items))


@monitor_bp.route("/device-type-recommends/<device_type>", methods=["PUT"])
@doc(summary="更新设备类型推荐配置", tags=["监控"], responses={200: "DeviceTypeRecommendItem"})
@login_required
@permission_required("monitor:config")
@transactional
def update_device_type_recommend(device_type: str):
    data = _validate_body(DeviceTypeRecommendUpdateSchema(), request.get_json(silent=True))
    from app.services.monitoring.oid_category_service import update_recommend
    result = update_recommend(device_type, data["categories"])
    return APIResponse.success(data=result)



@monitor_bp.route("/mib-scan", methods=["POST"])
@doc(summary="MIB 扫描（对设备做 walk，返回 OID 清单）", tags=["监控"], responses={200: "MibScanResponse"})
@login_required
@permission_required("monitor:config")
def mib_scan():
    data = _validate_body(MibScanRequestSchema(), request.get_json(silent=True))
    device_id = data["device_id"]
    timeout = data["timeout"]
    device = device_repo.find_by_id_or_404(device_id)
    hardware = getattr(device, "hardware", None)
    ip = getattr(hardware, "ipmi_address", None) or getattr(device, "management_ip", None)
    if not ip:
        raise BusinessLogicError("设备未配置管理IP或BMC地址（无可用 IP 地址）", status_code=400)
    try:
        cred = credential_service.get_decrypted(device_id, MonitorProtocolCode.SNMP.value)
    except Exception:
        logger.warning("SNMP 凭据解密失败 device_id=%s", device_id, exc_info=True)
        cred = None
    if not cred:
        raise BusinessLogicError("设备未配置 SNMP 凭据", status_code=400)
    from app.services.monitoring.snmp_mib_service import scan_device_cached
    result = scan_device_cached(ip, cred, timeout=timeout)
    return APIResponse.success(data=result)


@monitor_bp.route("/mib-scan/import", methods=["POST"])
@doc(summary="批量导入 OID 为指标模板", tags=["监控"], responses={200: "MetricTemplateListResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def mib_scan_import():
    data = _validate_body(MibScanImportSchema(), request.get_json(silent=True))
    from app.services.monitoring.oid_category_service import batch_import_templates
    result = batch_import_templates(data["items"])
    return APIResponse.success(data=result)


@monitor_bp.route("/mib-scan/recommend-config", methods=["GET"])
@doc(summary="获取设备类型的推荐 category 列表", tags=["监控"], responses={200: "RecommendConfigResponse"})
@login_required
@permission_required("monitor:view")
def mib_scan_recommend_config():
    device_type = request.args.get("device_type")
    if not device_type:
        raise ValidationError("device_type 必填")
    from app.services.monitoring.oid_category_service import get_recommended_categories
    cats = get_recommended_categories(device_type)
    return APIResponse.success(data={"device_type": device_type, "categories": cats})


@monitor_bp.route("/mib-scan/persist-rule", methods=["POST"])
@doc(summary="把启发式命中的 OID 类别沉淀为规则（P1）", tags=["监控"], responses={200: "OidCategoryRuleMutationResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def mib_scan_persist_rule():
    data = _validate_body(MibScanPersistRuleSchema(), request.get_json(silent=True))
    from app.services.monitoring.oid_category_service import persist_heuristic_rule
    result = persist_heuristic_rule(
        oid=data["oid"],
        device_type=data["device_type"],
        vendor_id=data.get("vendor_id"),
    )
    return APIResponse.success(data=result)



@monitor_bp.route("/vendor-brands", methods=["GET"])
@doc(summary="列出全部厂商品牌", tags=["监控"], responses={200: "VendorBrandListResponse"})
@login_required
@permission_required("monitor:view")
def list_vendor_brands():
    from app.services.monitoring.vendor_brand_service import list_vendor_brands as _list
    device_type = request.args.get("device_type")
    rows = _list(device_type=device_type, only_enabled=False)
    return APIResponse.paginated(data=rows, page=1, per_page=len(rows) or 1, total=len(rows))


@monitor_bp.route("/vendor-brands", methods=["POST"])
@doc(summary="新增厂商品牌", tags=["监控"], responses={200: "VendorBrandMutationResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def create_vendor_brand():
    data = _validate_body(VendorBrandCreateSchema(), request.get_json(silent=True))
    from app.services.monitoring.vendor_brand_service import create_vendor_brand as _create
    brand_id = _create(data)
    return APIResponse.success(data={"id": brand_id})


@monitor_bp.route("/vendor-brands/<int:brand_id>", methods=["PATCH"])
@doc(summary="更新厂商品牌", tags=["监控"], responses={200: "VendorBrandMutationResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def update_vendor_brand(brand_id: int):
    data = _validate_body(VendorBrandUpdateSchema(), request.get_json(silent=True))
    from app.services.monitoring.vendor_brand_service import update_vendor_brand as _update
    _update(brand_id, data)
    return APIResponse.success(data={"id": brand_id})


@monitor_bp.route("/vendor-brands/<int:brand_id>", methods=["DELETE"])
@doc(summary="删除厂商品牌", tags=["监控"], responses={200: "VendorBrandMutationResponse"})
@login_required
@permission_required("monitor:config")
@transactional
def delete_vendor_brand(brand_id: int):
    from app.services.monitoring.vendor_brand_service import delete_vendor_brand as _delete
    _delete(brand_id)
    return APIResponse.success(data={"id": brand_id})
