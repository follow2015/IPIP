# -*- coding: utf-8 -*-
"""
客户导入导出 API

从 app/api/customer.py 拆分而来，仅承担 HTTP 管道职责。
核心业务逻辑下沉至 app/services/import_export_service.py 通用模块。
"""

from app.utils.logging import get_logger
from flask import Blueprint, request, g
from app.openapi.doc import doc
from app.api.base import APIResponse
from app.utils import (
    login_required,
    permission_required,
    rate_limit_api,
)
from app.utils.transactional import transactional
from app.exceptions.validation import ValidationError as AppValidationError, RequiredFieldError
from app.services import import_export_service
from app.core.enums import CUSTOMER_IMPORT_CN_TO_EN, EN_TO_CN_CUSTOMER_IMPORT

logger = get_logger(__name__)

customer_import_bp = Blueprint("customer_import", __name__)

CUSTOMER_COLUMNS = [
    "name", "contact_person", "contact_phone", "email", "address", "notes",
]
CUSTOMER_EXAMPLE_ROWS = [
    {
        "name": "示例客户A", "contact_person": "张三", "contact_phone": "13800138000",
        "email": "zhangsan@example.com", "address": "北京市海淀区", "notes": "VIP客户",
    },
]
CUSTOMER_REQUIRED_COLUMNS = ["name"]


@customer_import_bp.route("/import-template", methods=["GET"])
@doc(summary="下载客户导入模板", tags=["客户"], responses={200: "ApiResponse"})
@login_required
@permission_required("customer:view")
def download_import_template():
    from flask import send_file

    buffer = import_export_service.build_template(
        columns=CUSTOMER_COLUMNS,
        example_rows=CUSTOMER_EXAMPLE_ROWS,
        en_to_cn=EN_TO_CN_CUSTOMER_IMPORT,
        sheet_name="客户导入模板",
    )
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="customer_import_template.xlsx",
    )


@customer_import_bp.route("/batch-import", methods=["POST"])
@doc(summary="批量导入客户", tags=["客户"], request_body={"content": {"multipart/form-data": {"schema": {"type": "object", "required": ["file"], "properties": {"file": {"type": "string", "format": "binary"}}}}}}, responses={200: "ApiResponse", 400: "ApiError", 500: "ApiError"})
@login_required
@permission_required("customer:create")
@rate_limit_api
@transactional
def batch_import_customers():
    if "file" not in request.files:
        return APIResponse.error(message="请上传文件", status_code=400)

    file = request.files["file"]
    if file.filename == "":
        return APIResponse.error(message="未选择文件", status_code=400)

    from app.utils.idempotency import _get_redis_client

    def _do_import(df):
        from app.services.customer_service import CustomerService
        from app.persistence.customer_repository import CustomerRepository
        customer_service = CustomerService(CustomerRepository())
        return import_export_service.import_rows(
            df=df,
            create_func=customer_service.create_customer,
            required_columns=CUSTOMER_REQUIRED_COLUMNS,
            entity_name="客户",
        )

    try:
        outcome = import_export_service.run_batch_import(
            file_bytes=file.read(),
            filename=file.filename,
            user_id=str(g.current_user.get("user_id", "anon")),
            idem_scope="import_customers",
            parse_fn=lambda b, fn: import_export_service.parse_file_to_df(
                file_bytes=b, filename=fn, cn_to_en=CUSTOMER_IMPORT_CN_TO_EN
            ),
            import_fn=_do_import,
            redis_client=_get_redis_client(),
        )
    except import_export_service.FileTooLargeError as e:
        return APIResponse.error(message=e.message, status_code=413)
    except import_export_service.IdempotencyConflictError as e:
        return APIResponse.error(e.message, error_code="IDEMPOTENCY_CONFLICT", status_code=409)
    except RequiredFieldError as e:
        return APIResponse.error(message=str(e), status_code=400)
    except AppValidationError as e:
        return APIResponse.error(message=str(e), status_code=400)

    return APIResponse.success(
        data={"imported_count": outcome.imported_count, "failed_count": outcome.failed_count, "failed_rows": outcome.failed_rows},
        message=outcome.message,
    )


@customer_import_bp.route("/export", methods=["GET"])
@doc(summary="导出客户数据", tags=["客户"], responses={200: "ApiResponse", 404: "ApiError", 500: "ApiError"})
@login_required
@permission_required("customer:view")
@rate_limit_api
def export_customers():
    from flask import send_file
    from datetime import datetime

    try:
        from app.services.customer_service import CustomerService
        from app.persistence.customer_repository import CustomerRepository

        customer_service = CustomerService(CustomerRepository())
        customers = customer_service.get_all_customers_list()

        output = import_export_service.export_to_excel(customers, "客户数据")
    except import_export_service.EmptyExportError:
        return APIResponse.error(message="没有可导出的客户数据", status_code=404)
    except Exception as e:
        logger.error("导出客户数据失败: %s", str(e))
        return APIResponse.error(message="操作失败", status_code=500)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'customers_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
    )
