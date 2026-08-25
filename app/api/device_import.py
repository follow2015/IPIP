# -*- coding: utf-8 -*-
"""
设备导入导出 API

从 app/api/device.py 拆分而来，仅承担 HTTP 管道职责：
- 取文件 / 查询参数
- 鉴权 / 权限 / 限流 / 事务装饰器
- 幂等键（redis）
- SSE 通知
- 响应包装

核心业务逻辑下沉至 app/services/device_import_service.py，首次可脱离
HTTP 上下文进行单元测试。路由路径与 device.py 时期完全一致，前端零改动。
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
from app.services import device_import_service
from app.services import import_export_service
from app.services.switch_events import emit_resource_change_global

logger = get_logger(__name__)

device_import_bp = Blueprint("device_import", __name__)


@device_import_bp.route("/import-template", methods=["GET"])
@doc(summary="下载设备导入模板", tags=["设备"], parameters=[{"name": "type", "in": "query", "schema": {"type": "string", "default": "server"}, "description": "设备类型: server/network/other"}], responses={200: "ApiResponse"})
@login_required
@permission_required("device:view")
def download_import_template():
    from flask import send_file

    template_type = request.args.get("type", "server").lower()
    buffer = device_import_service.build_import_template(template_type)

    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="device_import_template.xlsx",
    )


@device_import_bp.route("/batch-import", methods=["POST"])
@doc(summary="批量导入设备", tags=["设备"], request_body={"content": {"multipart/form-data": {"schema": {"type": "object", "required": ["file"], "properties": {"file": {"type": "string", "format": "binary"}}}}}}, responses={200: "ApiResponse", 400: "ApiError", 500: "ApiError"})
@login_required
@permission_required("device:create")
@rate_limit_api
@transactional
def batch_import_devices():
    if "file" not in request.files:
        return APIResponse.error(message="请上传文件", status_code=400)

    file = request.files["file"]
    if file.filename == "":
        return APIResponse.error(message="未选择文件", status_code=400)

    from app.utils.idempotency import _get_redis_client

    def _do_import(df):
        return device_import_service.parse_and_import_devices(df)

    try:
        outcome = import_export_service.run_batch_import(
            file_bytes=file.read(),
            filename=file.filename,
            user_id=str(g.current_user.get("user_id", "anon")),
            idem_scope="import_devices",
            parse_fn=device_import_service.build_device_df,
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

    if outcome.imported_count > 0:
        imported_ids = (outcome.raw or {}).get("imported_ids", [])
        emit_resource_change_global("device", "batch_create", ids=imported_ids)

    return APIResponse.success(
        data={
            "imported_count": outcome.imported_count,
            "failed_count": outcome.failed_count,
            "failed_rows": outcome.failed_rows,
        },
        message=outcome.message,
    )


@device_import_bp.route("/export", methods=["GET"])
@doc(summary="导出设备数据", tags=["设备"], parameters=[{"name": "cabinet_id", "in": "query", "schema": {"type": "integer"}}, {"name": "customer_id", "in": "query", "schema": {"type": "integer"}}], responses={200: "ApiResponse", 404: "ApiError", 500: "ApiError"})
@login_required
@permission_required("device:view")
@rate_limit_api
def export_devices():
    from flask import send_file
    from datetime import datetime

    cabinet_id = request.args.get("cabinet_id", type=int)
    customer_id = request.args.get("customer_id", type=int)

    try:
        output = device_import_service.export_devices_to_excel(
            cabinet_id=cabinet_id, customer_id=customer_id
        )
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"devices_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )
    except ImportError as e:
        logger.error("导出依赖缺失: %s", str(e))
        return APIResponse.error(message="导出功能依赖未安装，请联系管理员", status_code=500)
    except device_import_service.EmptyExportError:
        return APIResponse.error(message="没有可导出的设备数据", status_code=404)
    except Exception as e:
        logger.error("导出设备数据失败: %s", str(e))
        return APIResponse.error(message="操作失败", status_code=500)
