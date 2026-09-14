# -*- coding: utf-8 -*-
"""批量导入的 HTTP 管道（cabinet / customer / device 三个导入端点共用）。

背景（整改 T2.6）
----------------
三个导入端点各自复制了一份「取文件 → run_batch_import → 4 类异常映射 →
成功响应」骨架（约 25 行 × 3）。真实差异只有 3 个参数（幂等 scope / 解析函数 /
导入函数）与 device 的 SSE 后置通知，其余逐字相同 —— 尤其是 4 类异常到 HTTP
状态码的映射，散在三处时**新增一类异常必须记得改三处**。

落点说明（**有意偏离计划**）
--------------------------
计划写的是 `app/utils/import_pipeline.py`。但本管道要构造 `APIResponse`、
读取 `g.current_user`、处理 Flask 上传对象 —— 全是 **API 层**职责；放进
`app/utils/` 会形成 utils → api / services 的分层倒置（`app/utils/` 现无任何
导入 `app.services` 的先例）。故落在 `app/api/`。

不做的部分
----------
`_do_import` **不试图统一**：cabinet / customer 是「通用 import_rows + 各自
service」，device 则是「两遍导入 + 枚举校验 + 节点 parent 关联」的领域实现，
强行抽象只会得到一个什么都不是的回调协议。本管道只把它当 `import_fn` 回调传入，
由各端点自己决定。
"""
from typing import Any, Callable, Optional

from flask import g

from app.api.base import APIResponse
from app.exceptions.validation import RequiredFieldError
from app.exceptions.validation import ValidationError as AppValidationError
from app.services import import_export_service
from app.utils.logging import get_logger

logger = get_logger(__name__)


def run_import(
    *,
    file,
    idem_scope: str,
    parse_fn: Callable[[bytes, str], Any],
    import_fn: Callable[[Any], Any],
    redis_client,
    after_success: Optional[Callable[[Any], None]] = None,
):
    """执行一次批量导入，统一「异常 → 响应」映射与成功响应结构。

    Args:
        file: Flask FileStorage（调用方已校验存在且 filename 非空）。
        idem_scope: 幂等作用域，须与路由 `@idempotent(prefix=...)` 一致。
        parse_fn: `(file_bytes, filename) -> DataFrame` 解析函数。
        import_fn: `(df) -> ImportOutcome` 导入函数（各实体自有实现）。
        redis_client: 幂等 / 锁用 Redis 客户端，可为 None。
        after_success: 成功后的旁路钩子（device 用于发 SSE 刷新通知）；
            约定为**不抛异常**的轻量通知，抛错不影响已完成的导入结果。

    Returns:
        Flask Response：成功为 `APIResponse.success(...)`；
        文件过大 413 / 幂等冲突 409 / 字段缺失或校验失败 400。
    """
    try:
        outcome = import_export_service.run_batch_import(
            file_bytes=file.read(),
            filename=file.filename,
            user_id=str(g.current_user.get("user_id", "anon")),
            idem_scope=idem_scope,
            parse_fn=parse_fn,
            import_fn=import_fn,
            redis_client=redis_client,
        )
    except import_export_service.FileTooLargeError as e:
        return APIResponse.error(message=e.message, status_code=413)
    except import_export_service.IdempotencyConflictError as e:
        return APIResponse.error(e.message, error_code="IDEMPOTENCY_CONFLICT", status_code=409)
    except RequiredFieldError as e:
        return APIResponse.error(message=str(e), status_code=400)
    except AppValidationError as e:
        return APIResponse.error(message=str(e), status_code=400)

    if after_success is not None:
        try:
            after_success(outcome)
        except Exception:  # noqa: BLE001 - 旁路钩子失败不得影响已成功的导入响应
            logger.exception("after_success 钩子抛异常（导入已成功，忽略）: scope=%s", idem_scope)

    return APIResponse.success(
        data={
            "imported_count": outcome.imported_count,
            "failed_count": outcome.failed_count,
            "failed_rows": outcome.failed_rows,
        },
        message=outcome.message,
    )
