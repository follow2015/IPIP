# -*- coding: utf-8 -*-
"""
机柜导入导出 API

从 app/api/cabinet.py 拆分而来，仅承担 HTTP 管道职责。
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
from app.core.enums import CABINET_IMPORT_CN_TO_EN, EN_TO_CN_CABINET_IMPORT

logger = get_logger(__name__)

cabinet_import_bp = Blueprint("cabinet_import", __name__)

CABINET_COLUMNS = [
    "name", "room_id", "location", "row", "col", "total_u", "total_power",
    "max_weight", "status", "customer_id", "notes",
]
CABINET_EXAMPLE_ROWS = [
    {
        "name": "A01", "room_id": 1, "location": "A区01号", "row": 1, "col": 1,
        "total_u": 42, "total_power": 10000, "max_weight": 800, "status": 1,
        "customer_id": "", "notes": "标准机柜",
    },
]
CABINET_REQUIRED_COLUMNS = ["name", "room_id"]


@cabinet_import_bp.route("/import-template", methods=["GET"])
@doc(summary="下载机柜导入模板", tags=["机柜"], responses={200: "ApiResponse"})
@login_required
@permission_required("cabinet:view")
def download_import_template():
    """下载机柜导入模板（含表头+示例行）"""
    from flask import send_file

    buffer = import_export_service.build_template(
        columns=CABINET_COLUMNS,
        example_rows=CABINET_EXAMPLE_ROWS,
        en_to_cn=EN_TO_CN_CABINET_IMPORT,
        sheet_name="机柜导入模板",
    )
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="cabinet_import_template.xlsx",
    )


@cabinet_import_bp.route("/batch-import", methods=["POST"])
@doc(summary="批量导入机柜", tags=["机柜"], request_body={"content": {"multipart/form-data": {"schema": {"type": "object", "required": ["file"], "properties": {"file": {"type": "string", "format": "binary"}}}}}}, responses={200: "ApiResponse", 400: "ApiError", 500: "ApiError"})
@login_required
@permission_required("cabinet:create")
@rate_limit_api
@transactional
def batch_import_cabinets():
    """批量导入机柜"""
    if "file" not in request.files:
        return APIResponse.error(message="请上传文件", status_code=400)

    file = request.files["file"]
    if file.filename == "":
        return APIResponse.error(message="未选择文件", status_code=400)

    from app.utils.idempotency import _get_redis_client

    def _do_import(df):
        from app.services.cabinet_service import CabinetService
        from app.persistence.cabinet_repository import CabinetRepository
        cabinet_service = CabinetService(CabinetRepository())
        return import_export_service.import_rows(
            df=df,
            create_func=cabinet_service.create_cabinet,
            required_columns=CABINET_REQUIRED_COLUMNS,
            entity_name="机柜",
        )

    try:
        outcome = import_export_service.run_batch_import(
            file_bytes=file.read(),
            filename=file.filename,
            user_id=str(g.current_user.get("user_id", "anon")),
            idem_scope="import_cabinets",
            parse_fn=lambda b, fn: import_export_service.parse_file_to_df(
                file_bytes=b, filename=fn, cn_to_en=CABINET_IMPORT_CN_TO_EN
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


@cabinet_import_bp.route("/export", methods=["GET"])
@doc(summary="导出机柜数据", tags=["机柜"], parameters=[{"name": "room_id", "in": "query", "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError", 500: "ApiError"})
@login_required
@permission_required("cabinet:view")
@rate_limit_api
def export_cabinets():
    """导出机柜数据"""
    from flask import send_file
    from datetime import datetime

    room_id = request.args.get("room_id", type=int)

    try:
        from app.services.cabinet_service import CabinetService
        from app.persistence.cabinet_repository import CabinetRepository
        cabinet_service = CabinetService(CabinetRepository())
        if room_id:
            cabinets = cabinet_service.get_cabinets_by_room(room_id)
        else:
            cabinets = cabinet_service.get_all_cabinets_list()

        output = import_export_service.export_to_excel(cabinets, "机柜数据")
    except import_export_service.EmptyExportError:
        return APIResponse.error(message="没有可导出的机柜数据", status_code=404)
    except Exception as e:
        logger.error("导出机柜数据失败: %s", str(e))
        return APIResponse.error(message="操作失败", status_code=500)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'cabinets_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
    )
