# -*- coding: utf-8 -*-
"""
统一导入导出编排层

抽取设备/机柜/客户导入导出的「共性管道」逻辑，提供可复用的基础能力：
- 文件解析（csv/xlsx）+ NaN 清洗 + 中文列名映射（parse_file_to_df）
- 模板生成（英文列名 → 中文表头）（build_template）
- 逐行导入 + 结果汇总（import_rows，供简单实体使用）
- Excel 导出（export_to_excel）
- 通用批量导入编排骨架（run_batch_import）：文件大小校验 → 内容 hash →
  幂等两阶段(pending→确认) → 调 parse_fn/import_fn → 按结果置/清幂等键

两种集成形态（并非所有实体都走简单模板）：
- 简单实体（机柜/客户）：定义 columns + cn_to_en，提供 create_func，
  调用 parse_file_to_df + import_rows 即可。
- 复杂实体（设备）：保留独立的 build_device_df（含 device_type 推断）与
  parse_and_import_devices（两遍导入 + 节点 parent_device_name 关联 +
  枚举校验），仅复用 run_batch_import 的管道，并通过 outcome.raw["imported_ids"]
  触发 SSE。设备逻辑不被压平进本模块。
"""

import hashlib
import pandas as pd
from dataclasses import dataclass
from io import BytesIO
from typing import Callable, Optional

from app.utils.logging import get_logger
from app.exceptions.business import InvalidOperationError
from app.exceptions.validation import (
    RequiredFieldError,
    InvalidFormatError,
    ValidationError as AppValidationError,
)

logger = get_logger(__name__)


MAX_IMPORT_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


class FileTooLargeError(InvalidFormatError):
    """上传文件超过大小上限。"""


class IdempotencyConflictError(Exception):
    """幂等冲突：文件已导入（"1"）或正在导入（"pending"）。

    路由层统一映射为 409（error_code=IDEMPOTENCY_CONFLICT）。
    """

    def __init__(self, message: str, in_progress: bool = False):
        self.message = message
        self.in_progress = in_progress
        super().__init__(message)


@dataclass
class ImportOutcome:
    """批量导入编排结果。"""

    imported_count: int
    failed_count: int
    failed_rows: list
    message: str
    raw: Optional[dict] = None  # 业务层的完整返回（如设备导入的 imported_ids）


def run_batch_import(
    file_bytes: bytes,
    filename: str,
    user_id: str,
    idem_scope: str,
    parse_fn: Callable[[bytes, str], "pd.DataFrame"],
    import_fn: Callable[["pd.DataFrame"], dict],
    redis_client=None,
) -> ImportOutcome:
    """通用批量导入编排（设备/机柜/客户路由共用，脱离具体实体、可单测）。

    负责整条 HTTP 无关的导入管道：
        文件大小校验 → 内容 hash → 幂等两阶段(pending→确认) →
        解析(parse_fn) → 导入(import_fn) → 按结果置/清幂等键。

    业务差异通过回调注入，使本函数只承载通用流程：
        - parse_fn(bytes, filename) -> DataFrame
        - import_fn(df) -> {"imported_count", "failed_count", "failed_rows", ...}

    幂等语义（与历史行为一致）：幂等键按「文件内容 hash」计算。只要有成功行即
    确认键(长 TTL=86400)。重导同一文件会被 409 拦截，避免把已成功的行重复导入
    产生重复数据；部分成功时前端提示用户仅重导失败行（失败行存为独立文件后 hash
    不同，不触发冲突）。

    Args:
        file_bytes: 上传文件原始字节
        filename: 原始文件名
        user_id: 当前用户ID（参与幂等键）
        idem_scope: 幂等键业务域，如 "import_devices"
        parse_fn: (bytes, filename) -> DataFrame
        import_fn: (df) -> 结果 dict
        redis_client: 可选 Redis 客户端（None 时跳过幂等）

    Returns:
        ImportOutcome

    Raises:
        FileTooLargeError: 文件超限（路由→413）
        IdempotencyConflictError: 已导入/导入中（路由→409）
        RequiredFieldError: 缺必需列（import_fn 内抛出，路由→400）
        AppValidationError: 解析格式错误（ValueError/KeyError 包装，路由→400）
        Exception: 其他异常（路由→500，已清占位键）
    """
    validate_file_size(file_bytes)

    file_hash = hashlib.md5(file_bytes).hexdigest()
    idem_key = f"ipm:idem:{idem_scope}:{user_id}:{file_hash}"
    idem_acquired = False
    if redis_client:
        existing = redis_client.get(idem_key)
        if existing == "1":
            raise IdempotencyConflictError("该文件已导入，请勿重复提交", in_progress=False)
        if existing == "pending":
            raise IdempotencyConflictError("该文件正在导入中，请稍后再试", in_progress=True)
        idem_acquired = redis_client.set(idem_key, "pending", nx=True, ex=300)

    try:
        df = parse_fn(file_bytes, filename)
        result = import_fn(df)
    except RequiredFieldError:
        if redis_client and idem_acquired:
            redis_client.delete(idem_key)
        raise
    except (ValueError, KeyError) as e:
        logger.error("批量导入文件解析失败: %s", str(e))
        if redis_client and idem_acquired:
            redis_client.delete(idem_key)
        raise AppValidationError(f"文件格式错误: {str(e)}")
    except Exception:
        if redis_client and idem_acquired:
            redis_client.delete(idem_key)
        raise

    imported_count = result.get("imported_count", 0)
    failed_rows = result.get("failed_rows", [])

    if redis_client and idem_acquired:
        if imported_count > 0:
            redis_client.set(idem_key, "1", ex=86400)
        else:
            redis_client.delete(idem_key)

    message = f"成功导入 {imported_count} 条"
    if failed_rows:
        message += f"，{len(failed_rows)} 行导入失败"

    return ImportOutcome(
        imported_count=imported_count,
        failed_count=result.get("failed_count", len(failed_rows)),
        failed_rows=failed_rows,
        message=message,
        raw=result,
    )


def validate_file_size(file_bytes: bytes, max_bytes: int = MAX_IMPORT_FILE_BYTES) -> None:
    """校验上传文件字节大小，超限抛出 FileTooLargeError（路由层转 413）。"""
    if len(file_bytes) > max_bytes:
        mb = max_bytes // (1024 * 1024)
        raise FileTooLargeError(
            field="file",
            expected_format=f"≤ {mb} MB",
            actual_value=f"{len(file_bytes)} bytes",
            message=f"文件过大（{len(file_bytes)} 字节），请分批导入，单文件上限 {mb} MB",
        )


class EmptyExportError(InvalidOperationError):
    """导出时没有任何数据。"""

    def __init__(self, message: str = "没有可导出的数据"):
        super().__init__(operation="export", reason=message, message=message)
        self.status_code = 404


def export_to_excel(rows: list, sheet_name: str) -> BytesIO:
    """将记录列表统一导出为 Excel 字节流（设备/机柜/客户共用）。

    统一职责：空数据检查 + DataFrame 构造 + ExcelWriter 拼装，使三个实体的
    导出构造路径一致；数据获取（含是否需要分页）由调用方决定——
    大数据量的设备走分页循环，机柜/客户量小直接全量取，分页是数据量驱动而非风格差异。

    Args:
        rows: 已序列化为 dict 的记录列表（如 get_all_*_list 返回 List[Dict]）
        sheet_name: Excel 工作表名

    Returns:
        可被 flask.send_file 直接消费的 BytesIO 缓冲

    Raises:
        EmptyExportError: rows 为空时
    """
    if not rows:
        raise EmptyExportError()
    df = pd.DataFrame(rows)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    output.seek(0)
    return output



def parse_file_to_df(
    file_bytes: bytes,
    filename: str,
    cn_to_en: Optional[dict] = None,
) -> pd.DataFrame:
    """将上传的文件字节流解析为标准化 DataFrame。

    包含：扩展名选择解析方式、NaN 清洗、中文列名→英文列名映射。

    Args:
        file_bytes: 上传文件的原始字节
        filename: 原始文件名（用于判断 csv/xlsx）
        cn_to_en: 中文→英文列名映射字典（可选）

    Returns:
        清洗并映射后的 DataFrame
    """
    buf = BytesIO(file_bytes)
    fname = (filename or "").lower()
    if fname.endswith(".csv"):
        df = pd.read_csv(buf, encoding="utf-8-sig")
    else:
        df = pd.read_excel(buf)

    df = df.where(df.notna(), None)

    if cn_to_en:
        df.rename(columns=cn_to_en, inplace=True)

    return df



def build_template(
    columns: list[str],
    example_rows: list[dict],
    en_to_cn: dict,
    sheet_name: str,
) -> BytesIO:
    """生成导入模板字节流（含中文表头+示例行）。

    Args:
        columns: 英文列名列表（定义列顺序）
        example_rows: 示例行数据（英文 key）
        en_to_cn: 英文→中文列名映射
        sheet_name: Excel Sheet 名称

    Returns:
        可被 flask.send_file 直接消费的 BytesIO 缓冲
    """
    df = pd.DataFrame(example_rows, columns=columns)
    cn_columns = [en_to_cn.get(col, col) for col in columns]
    df.columns = cn_columns
    buffer = BytesIO()
    df.to_excel(buffer, index=False, sheet_name=sheet_name)
    buffer.seek(0)
    return buffer



def import_rows(
    df: pd.DataFrame,
    create_func: Callable[[dict], any],
    required_columns: list[str],
    entity_name: str = "记录",
    name_column: str = "name",
) -> dict:
    """逐行导入 DataFrame 数据。

    Args:
        df: 已解析并映射好的 DataFrame
        create_func: 单行创建回调，接收 dict 返回创建的对象（或抛异常）
        required_columns: 必需列名列表
        entity_name: 实体中文名（用于日志）
        name_column: 名称列名（用于失败行详情，如 "name"/"device_name"）

    Returns:
        {
            "imported_count": int,
            "failed_count": int,
            "failed_rows": [{"row": int, "name": str, "error": str}, ...],
        }

    Raises:
        RequiredFieldError: 缺少必需列时
    """
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise RequiredFieldError(
            missing_fields=missing_columns,
            message=f"缺少必需列: {', '.join(missing_columns)}",
        )

    imported_count = 0
    failed_rows = []

    for index, row in df.iterrows():
        from extensions import db
        savepoint = db.session.begin_nested()
        try:
            row_data = {k: v for k, v in row.to_dict().items() if not pd.isna(v) and v is not None and v != ''}
            create_func(row_data)
            imported_count += 1
        except Exception as e:
            from app.exceptions.data_access import DataAccessError
            original = getattr(e, "original_error", None) if isinstance(e, DataAccessError) else None
            error_msg = str(original) if original else str(e)

            is_integrity = "IntegrityError" in error_msg or (original and "IntegrityError" in type(original).__name__)
            if is_integrity:
                if "foreign key constraint" in error_msg.lower():
                    error_msg = "外键约束失败（关联记录不存在）"
                elif "Duplicate" in error_msg or "duplicate" in error_msg:
                    error_msg = "记录重复（唯一约束冲突）"
                else:
                    error_msg = "数据完整性约束失败"
            elif isinstance(e, DataAccessError):
                error_msg = e.message
            elif "ValidationError" in type(e).__name__ or "RequiredField" in type(e).__name__:
                error_msg = str(e)
            elif len(error_msg) > 200:
                error_msg = error_msg[:200] + "..."

            row_name = row.get(name_column, "")
            if pd.isna(row_name) or row_name is None:
                row_name = ""

            logger.error("导入%s第 %d 行失败: %s", entity_name, index + 1, error_msg)
            failed_rows.append({
                "row": index + 1,
                "name": str(row_name),
                "error": error_msg,
            })
            savepoint.rollback()

    return {
        "imported_count": imported_count,
        "failed_count": len(failed_rows),
        "failed_rows": failed_rows,
    }
