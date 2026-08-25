# -*- coding: utf-8 -*-
"""
客户API

提供客户管理的RESTful API端点。
"""
from flask import Blueprint, request, g
import hashlib
from app.utils.logging import get_logger
from marshmallow import Schema, fields, validate, EXCLUDE

from app.services import CustomerService
from app.persistence.customer_repository import CustomerRepository
from app.core.enums import CustomerStatus
from app.api.base import APIResponse
from app.utils import (
    login_required,
    permission_required,
    rate_limit_api,
    validation_manager,
)
from app.utils.transactional import transactional
from app.utils.auth import get_current_user_id
from app.openapi.doc import doc, public

customer_bp = Blueprint("customer", __name__)
customer_service = CustomerService(CustomerRepository())
logger = get_logger(__name__)


class CustomerCreateSchema(Schema):
    
    class Meta:
        unknown = EXCLUDE

    customer_name = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    customer_status = fields.Int(load_default=CustomerStatus.ACTIVE.value)
    contact_person = fields.Str(allow_none=True, validate=validate.Length(max=50))
    contact_phone = fields.Str(allow_none=True, validate=validate.Length(max=20))
    email = fields.Email(allow_none=True)
    address = fields.Str(allow_none=True, validate=validate.Length(max=200))
    notes = fields.Str(allow_none=True, validate=validate.Length(max=500))


class CustomerUpdateSchema(Schema):
    
    class Meta:
        unknown = EXCLUDE

    customer_name = fields.Str(validate=validate.Length(min=1, max=100))
    customer_status = fields.Int()
    contact_person = fields.Str(allow_none=True, validate=validate.Length(max=50))
    contact_phone = fields.Str(allow_none=True, validate=validate.Length(max=20))
    email = fields.Email(allow_none=True)
    address = fields.Str(allow_none=True, validate=validate.Length(max=200))
    notes = fields.Str(allow_none=True, validate=validate.Length(max=500))


@customer_bp.route("/", methods=["GET"])
@doc(summary="获取客户列表", tags=["客户"], parameters=[{"name": "page", "in": "query", "schema": {"type": "integer", "default": 1}}, {"name": "per_page", "in": "query", "schema": {"type": "integer", "default": 20}}, {"name": "search", "in": "query", "schema": {"type": "string"}}, {"name": "status", "in": "query", "schema": {"type": "string"}}], responses={200: "CustomerResponse", 500: "ApiError"})
@login_required
@permission_required("customer:view")
@rate_limit_api
def list_customers():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 1000)
    search = request.args.get("search", type=str)
    status = request.args.get("status", type=str)

    try:
        if search:
            filters = {}
            if status:
                filters["status"] = status
            result = customer_service.customer_repository.search(
                search_fields=["customer_name", "contact_person", "email"],
                keyword=search,
                filters=filters,
                page=page,
                page_size=per_page,
            )
            customers = result.get("data", [])
            total = result.get("total_count", 0)
        else:
            filters = {}
            if status:
                filters["status"] = status
            customers, total = customer_service.get_paginated(page=page, per_page=per_page, filters=filters)

        return APIResponse.paginated(
            data=[customer.to_dict() for customer in customers],
            page=page,
            per_page=per_page,
            total=total,
            message="获取客户列表成功",
        )
    except Exception as e:
        logger.error(f"获取客户列表失败: {e}")
        return APIResponse.error(message="获取客户列表失败", error_code="CUSTOMER_LIST_ERROR", status_code=500)


@customer_bp.route("/<int:customer_id>", methods=["GET"])
@doc(summary="获取客户详情", tags=["客户"], parameters=[{"name": "customer_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "CustomerResponse", 404: "ApiError"})
@login_required
@permission_required("customer:view")
@rate_limit_api
def get_customer(customer_id):
    customer = customer_service.get_by_id(customer_id)

    if not customer:
        return APIResponse.error(message="客户不存在", error_code="CUSTOMER_NOT_FOUND", status_code=404)

    return APIResponse.success(data=customer.to_dict(), message="获取客户信息成功")


@customer_bp.route("/", methods=["POST"])
@doc(summary="创建客户", tags=["客户"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/CustomerCreate"}}}}, responses={201: "CustomerResponse", 400: "ApiError", 409: "ApiError"})
@login_required
@permission_required("customer:create")
@rate_limit_api
@transactional
def create_customer():
    data = validation_manager.validate_schema(request.json, CustomerCreateSchema())

    if "contact_phone" in data and data["contact_phone"]:
        if not validation_manager.validate_phone(data["contact_phone"]):
            return APIResponse.error(message="联系电话格式无效", error_code="INVALID_PHONE", status_code=400)

    existing = customer_service.get_by_name(data["customer_name"])
    if existing:
        return APIResponse.error(message="客户名称已存在", error_code="CUSTOMER_NAME_EXISTS", status_code=409)

    customer = customer_service.create_customer(data)

    return APIResponse.success(data=customer.to_dict(), message="客户创建成功", status_code=201)


@customer_bp.route("/<int:customer_id>", methods=["PUT"])
@doc(summary="更新客户信息", tags=["客户"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/CustomerUpdate"}}}}, parameters=[{"name": "customer_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "CustomerResponse", 400: "ApiError", 404: "ApiError", 409: "ApiError"})
@login_required
@permission_required("customer:update")
@rate_limit_api
@transactional
def update_customer(customer_id):
    data = validation_manager.validate_schema(request.json, CustomerUpdateSchema())

    customer = customer_service.get_by_id(customer_id)
    if not customer:
        return APIResponse.error(message="客户不存在", error_code="CUSTOMER_NOT_FOUND", status_code=404)

    if "customer_status" in data:
        new_status = data["customer_status"]
        old_status = customer.customer_status
        if old_status == CustomerStatus.TERMINATED.value and new_status != CustomerStatus.TERMINATED.value:
            return APIResponse.error(
                message="客户已终止，状态不可逆，禁止流转到其他状态",
                error_code="CUSTOMER_TERMINATED_NOT_REVERSIBLE",
                status_code=409,
            )
        if old_status != CustomerStatus.TERMINATED.value and new_status == CustomerStatus.TERMINATED.value:
            operator_id = get_current_user_id()
            reason = data.get("reason")
            terminated = customer_service.terminate_customer(customer_id, operator_id, reason)
            return APIResponse.success(data=terminated.to_dict(), message="客户已终止")

    if "contact_phone" in data and data["contact_phone"]:
        if not validation_manager.validate_phone(data["contact_phone"]):
            return APIResponse.error(message="联系电话格式无效", error_code="INVALID_PHONE", status_code=400)

    if "customer_name" in data:
        existing = customer_service.get_by_name(data["customer_name"])
        if existing and existing.id != customer_id:
            return APIResponse.error(message="客户名称已存在", error_code="CUSTOMER_NAME_EXISTS", status_code=409)

    updated_customer = customer_service.update_customer(customer_id, data)

    return APIResponse.success(data=updated_customer.to_dict(), message="客户更新成功")


@customer_bp.route("/<int:customer_id>", methods=["DELETE"])
@doc(summary="删除客户", tags=["客户"], parameters=[{"name": "customer_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError", 409: "ApiError"})
@login_required
@permission_required("customer:delete")
@rate_limit_api
@transactional
def delete_customer(customer_id):
    customer = customer_service.get_by_id(customer_id)
    if not customer:
        return APIResponse.error(message="客户不存在", error_code="CUSTOMER_NOT_FOUND", status_code=404)

    if customer.cabinets or customer.devices:
        return APIResponse.error(
            message="客户下还有机柜或设备，无法删除", error_code="CUSTOMER_HAS_RESOURCES", status_code=409
        )

    customer_service.delete_customer(customer_id)

    return APIResponse.success(message="客户删除成功")


@customer_bp.route("/<int:customer_id>/cabinets", methods=["GET"])
@doc(summary="获取客户的机柜列表", tags=["客户"], parameters=[{"name": "customer_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "CabinetResponse", 404: "ApiError"})
@login_required
@permission_required("customer:view")
@rate_limit_api
def get_customer_cabinets(customer_id):
    customer = customer_service.get_by_id(customer_id)
    if not customer:
        return APIResponse.error(message="客户不存在", error_code="CUSTOMER_NOT_FOUND", status_code=404)

    cabinets = customer_service.get_cabinets(customer_id)

    return APIResponse.success(
        data=[cabinet.to_dict() for cabinet in cabinets], message="获取机柜列表成功"
    )


@customer_bp.route("/<int:customer_id>/devices", methods=["GET"])
@doc(summary="获取客户的设备列表", tags=["客户"], parameters=[{"name": "customer_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("customer:view")
@rate_limit_api
def get_customer_devices(customer_id):
    customer = customer_service.get_by_id(customer_id)
    if not customer:
        return APIResponse.error(message="客户不存在", error_code="CUSTOMER_NOT_FOUND", status_code=404)

    devices = customer_service.get_devices(customer_id)

    return APIResponse.success(data=[device.to_dict() for device in devices], message="获取设备列表成功")


@customer_bp.route("/<int:customer_id>/statistics", methods=["GET"])
@doc(summary="获取客户统计信息", tags=["客户"], parameters=[{"name": "customer_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("customer:view")
@rate_limit_api
def get_customer_statistics(customer_id):
    customer = customer_service.get_by_id(customer_id)
    if not customer:
        return APIResponse.error(message="客户不存在", error_code="CUSTOMER_NOT_FOUND", status_code=404)

    stats = customer_service.get_customer_resources(customer_id)

    return APIResponse.success(data=stats, message="获取统计信息成功")


@customer_bp.route("/<int:customer_id>/assets", methods=["GET"])
@doc(summary="获取客户资产统计", tags=["客户"], parameters=[{"name": "customer_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 500: "ApiError"})
@login_required
def get_customer_assets(customer_id):
    try:
        assets = customer_service.get_customer_assets(customer_id)
        return APIResponse.success(
            data=assets,
            message="获取客户资产统计成功"
        )
    except Exception as e:
        logger.error(f"获取客户资产统计失败: {e}")
        return APIResponse.error(
            message="服务器内部错误",
            error_code="INTERNAL_ERROR",
            status_code=500
        )


@customer_bp.route("/<int:customer_id>/assets-export", methods=["GET"])
@doc(summary="导出客户资源Excel", tags=["客户"], parameters=[{"name": "customer_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError", 500: "ApiError"})
@login_required
def export_customer_assets(customer_id):
    from flask import send_file
    from datetime import datetime

    try:
        output = customer_service.generate_customer_assets_excel(customer_id)
        customer = customer_service.get_by_id(customer_id)
        customer_name = customer.customer_name if customer else f"customer_{customer_id}"
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"{customer_name}_资源统计_{datetime.now().strftime('%Y%m%d')}.xlsx",
        )
    except Exception as e:
        logger.error("导出客户资源Excel失败: %s", str(e))
        return APIResponse.error(message="导出失败", status_code=500)


@customer_bp.route("/batch-delete", methods=["POST"])
@doc(summary="批量删除客户", tags=["客户"], request_body={"content": {"application/json": {"schema": {"$ref": "#/components/schemas/BatchDelete"}}}}, responses={200: "ApiResponse", 400: "ApiError"})
@login_required
@permission_required("customer:delete")
@rate_limit_api
@transactional
def batch_delete_customers():
    from app.services.customer_service import CustomerService
    
    data = request.get_json()
    if not data or "ids" not in data:
        return APIResponse.error(message="请提供要删除的客户ID列表", status_code=400)
    
    ids = data.get("ids", [])
    if not isinstance(ids, list):
        return APIResponse.error(message="ID列表格式错误", status_code=400)
    
    customer_service = CustomerService(CustomerRepository())
    deleted_count = 0
    failed_ids = []
    
    for customer_id in ids:
        try:
            result = customer_service.delete_customer(customer_id)
            if result:
                deleted_count += 1
            else:
                failed_ids.append(customer_id)
        except Exception as e:
            logger.error(f"删除客户 {customer_id} 失败: {str(e)}")
            failed_ids.append(customer_id)
    
    message = f"成功删除 {deleted_count} 个客户"
    if failed_ids:
        message += f"，{len(failed_ids)} 个删除失败"
    
    return APIResponse.success(
        data={
            "deleted_count": deleted_count,
            "failed_count": len(failed_ids),
            "failed_ids": failed_ids
        },
        message=message
    )
@doc(summary="下载客户导入模板", tags=["客户"], responses={200: "ApiResponse"})
@login_required
@permission_required("customer:view")
def download_customer_import_template():
    import pandas as pd
    from io import BytesIO

    columns = [
        "name", "contact_person", "contact_phone", "email", "address", "notes",
    ]
    example_rows = [
        {
            "name": "示例客户A", "contact_person": "张三", "contact_phone": "13800138000",
            "email": "zhangsan@example.com", "address": "北京市海淀区", "notes": "VIP客户",
        },
    ]
    df = pd.DataFrame(example_rows, columns=columns)
    from app.core.enums import EN_TO_CN_CUSTOMER_IMPORT
    cn_columns = [EN_TO_CN_CUSTOMER_IMPORT.get(col, col) for col in columns]
    df.columns = cn_columns
    buffer = BytesIO()
    df.to_excel(buffer, index=False, sheet_name="客户导入模板")
    buffer.seek(0)

    from flask import send_file
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="customer_import_template.xlsx",
    )


@customer_bp.route("/<int:customer_id>/terminate", methods=["POST"])
@doc(summary="终止客户（主入口，原子释放全部资源）", tags=["客户"], responses={200: "CustomerResponse", 404: "ApiError", 409: "ApiError"})
@login_required
@permission_required("customer:terminate")
@rate_limit_api
@transactional
def terminate_customer(customer_id):
    data = request.get_json(silent=True) or {}
    reason = data.get("reason")
    operator_id = get_current_user_id()
    try:
        customer = customer_service.terminate_customer(customer_id, operator_id, reason)
    except Exception as e:
        from app.exceptions.business import BusinessLogicError
        from app.exceptions.data_access import RecordNotFoundError
        if isinstance(e, RecordNotFoundError):
            return APIResponse.error(message=str(e), error_code="CUSTOMER_NOT_FOUND", status_code=404)
        if isinstance(e, BusinessLogicError):
            return APIResponse.error(message=str(e), error_code=e.code, status_code=e.status_code)
        raise
    return APIResponse.success(data=customer.to_dict(), message="客户已终止")


@customer_bp.route("/<int:customer_id>/termination-preview", methods=["GET"])
@doc(summary="终止前置预览（不执行释放）", tags=["客户"], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("customer:view")
def termination_preview(customer_id):
    customer = customer_service.get_by_id(customer_id)
    if not customer:
        return APIResponse.error(message="客户不存在", error_code="CUSTOMER_NOT_FOUND", status_code=404)
    assets = customer_service.get_customer_assets(customer_id)
    return APIResponse.success(data={
        "customer": customer.to_dict(),
        "assets": assets,
        "will_terminate": customer.customer_status != CustomerStatus.TERMINATED.value,
    })


@customer_bp.route("/<int:customer_id>/termination-archive", methods=["GET"])
@doc(summary="下载最近一份终止存档 PDF", tags=["客户"], parameters=[{"name": "customer_id", "in": "path", "required": True, "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError", 409: "ApiError"})
@login_required
@permission_required("customer:view")
def download_termination_archive(customer_id):
    from flask import send_file
    from io import BytesIO
    from datetime import datetime
    from app.persistence.customer_termination_archive_repository import CustomerTerminationArchiveRepository

    archive_repo = CustomerTerminationArchiveRepository()
    archive = archive_repo.find_latest_by_customer_id(customer_id)
    if not archive:
        return APIResponse.error(message="该客户无终止存档", error_code="ARCHIVE_NOT_FOUND", status_code=404)
    if not archive.pdf_blob:
        return APIResponse.error(
            message="存档 PDF 尚未生成，请使用 rebuild 接口补生成",
            error_code="PDF_NOT_READY", status_code=409,
        )
    buf = BytesIO(archive.pdf_blob)
    customer_name = archive.customer.customer_name if archive.customer else f"customer_{customer_id}"
    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{customer_name}_终止存档_{archive.created_at.strftime('%Y%m%d')}.pdf",
    )


@customer_bp.route("/<int:customer_id>/termination-archives", methods=["GET"])
@doc(summary="查询历史终止存档列表（元数据，不含 BLOB）", tags=["客户"], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("customer:view")
def list_termination_archives(customer_id):
    from app.persistence.customer_termination_archive_repository import CustomerTerminationArchiveRepository

    archive_repo = CustomerTerminationArchiveRepository()
    archives = archive_repo.find_by_customer_id(customer_id)
    return APIResponse.success(data=[
        {
            "id": a.id,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "operator_id": a.operator_id,
            "operator_name": a.operator.username if a.operator else None,
            "pdf_size": a.pdf_size,
            "reason": a.reason,
            "has_pdf": a.pdf_blob is not None,
            "summary": (a.summary_json or {}).get("summary", {}),
        }
        for a in archives
    ])


@customer_bp.route("/<int:customer_id>/termination-archive/rebuild", methods=["POST"])
@doc(summary="重建终止存档 PDF（凭 summary_json）", tags=["客户"], responses={200: "ApiResponse", 404: "ApiError"})
@login_required
@permission_required("customer:terminate")
@transactional
def rebuild_termination_archive(customer_id):
    from app.persistence.customer_termination_archive_repository import CustomerTerminationArchiveRepository

    archive_repo = CustomerTerminationArchiveRepository()
    archive = archive_repo.find_latest_by_customer_id(customer_id)
    if not archive:
        return APIResponse.error(message="该客户无终止存档", error_code="ARCHIVE_NOT_FOUND", status_code=404)
    customer = customer_service.get_by_id(customer_id)
    if not customer:
        return APIResponse.error(message="客户不存在", error_code="CUSTOMER_NOT_FOUND", status_code=404)
    try:
        pdf_buf = customer_service.generate_customer_termination_pdf(customer, archive.summary_json)
        pdf_bytes = pdf_buf.read()
        archive.pdf_blob = pdf_bytes
        archive.pdf_size = len(pdf_bytes)
        archive_repo.save(archive)
    except Exception as e:
        logger.error("重建终止存档 PDF 失败: %s", str(e))
        return APIResponse.error(message="PDF 重建失败", status_code=500)
    return APIResponse.success(message="PDF 重建成功", data={"pdf_size": archive.pdf_size})
