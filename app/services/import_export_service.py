# -*- coding: utf-8 -*-
"""
统一导入导出编排层

抽取设备/机柜/客户导入导出的「共性管道」逻辑，提供可复用的基础能力：
- 文件解析（csv/xlsx）+ NaN 清洗 + 中文列名映射（parse_file_to_df）
- 模板生成（英文列名 → 中文表头）（build_template）
- 逐行导入 + 结果汇总（import_rows，供简单实体使用）
- Excel 导出（export_to_excel，**write_only 流式写出**）
- 通用批量导入编排骨架（run_batch_import）：文件大小校验 → 内容 hash →
  幂等两阶段(pending→确认) → 调 parse_fn → **行数闸** → 调 import_fn → 置/清幂等键

两侧共用的"资源闸"都在本模块，且**判定点唯一**：
- 体积（``validate_file_size`` / ``MAX_IMPORT_FILE_BYTES``）
- 导入行数（``ensure_import_rows_within_limit`` / ``MAX_IMPORT_ROWS``）
- 导出行数（``export_to_excel`` 的 ``max_rows`` / ``MAX_EXPORT_ROWS``）
体积与行数是**正交**维度——实测 10 MB 预算可装 65 万行窄表（见 ``MAX_IMPORT_ROWS``
注释），故两者缺一不可。

两种集成形态（并非所有实体都走简单模板）：
- 简单实体（机柜/客户）：定义 columns + cn_to_en，提供 create_func，
  调用 parse_file_to_df + import_rows 即可。
- 复杂实体（设备）：保留独立的 build_device_df（含 device_type 推断）与
  parse_and_import_devices（两遍导入 + 节点 parent_device_name 关联 +
  枚举校验），仅复用 run_batch_import 的管道，并通过 outcome.raw["imported_ids"]
  触发 SSE。设备逻辑不被压平进本模块。
"""

import hashlib
import os
import zipfile
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

ALLOWED_IMPORT_EXT = {".csv", ".xlsx"}

_MAX_XLSX_ENTRIES = 5000
_MAX_XLSX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024

MAX_EXPORT_ROWS = 200_000

MAX_IMPORT_ROWS = 50_000


class FileTooLargeError(InvalidFormatError):
    """上传文件超过大小上限。"""


class ImportTooLargeError(InvalidOperationError):
    """单次导入行数超过 ``MAX_IMPORT_ROWS``（路由层统一转 413）。

    由**编排层**（``run_batch_import``）在解析完成后、调用 ``import_fn`` **之前**
    抛出 —— 拒绝必须发生在任何写入之前，否则"先导了 3 行、第 4 行才发现超限"
    会留下部分写入（且幂等键还会被确认成长 TTL）。
    """

    def __init__(self, rows: int, max_rows: int = MAX_IMPORT_ROWS):
        super().__init__(
            operation="import",
            reason=f"导入行数超过单次上限（检测到 {rows} 行，上限 {max_rows} 行）",
            message=(
                f"导入行数过多（检测到 {rows} 行，单次上限 {max_rows} 行），"
                "请将文件按行拆分为多个文件后分批导入"
            ),
        )
        self.status_code = 413
        self.rows = rows
        self.max_rows = max_rows


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
        ImportTooLargeError: 解析后行数超限（路由→413）；在 import_fn 之前抛出
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
        if not idem_acquired:
            raise IdempotencyConflictError("该文件正在导入中，请稍后再试", in_progress=True)

    try:
        df = parse_fn(file_bytes, filename)
        ensure_import_rows_within_limit(len(df))
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


def ensure_import_rows_within_limit(row_count: int, max_rows: Optional[int] = None) -> None:
    """导入行数闸 —— 全仓**唯一**判定点（编排层 ``run_batch_import`` 调用）。

    与 ``ensure_offset_within_limit`` 同型：判据单一真源，接受方只负责调用。

    为什么判在**解析之后**而不是"先数换行符省掉解析"：CSV 允许字段内含换行，
    数换行符会把合法文件**误判超限**；10 MB 体积闸已经把解析期内存锁在有限
    范围内，"晚一点但判得准"胜过早一步但会误伤。

    Args:
        row_count: 已解析出的数据行数
        max_rows: 上限；None 时取当前 ``MAX_IMPORT_ROWS``（运行期读取，便于统一调参）

    Raises:
        ImportTooLargeError: 行数超过上限（路由→413）
    """
    if max_rows is None:
        max_rows = MAX_IMPORT_ROWS
    if row_count > max_rows:
        raise ImportTooLargeError(row_count, max_rows)


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


class ExportTooLargeError(InvalidOperationError):
    """单次导出结果集超过 ``MAX_EXPORT_ROWS``（路由层统一转 413）。

    由**取数侧**在累计到上限时立即抛出，而不是等结果集物化完再判断——后者
    内存已经炸了。调用方（各导出路由）应捕获本异常并回一条可操作的提示。
    """

    def __init__(self, rows: int, max_rows: int = MAX_EXPORT_ROWS):
        super().__init__(
            operation="export",
            reason=f"结果集超过单次导出上限（检测到 {rows} 行，上限 {max_rows} 行）",
            message=(
                f"导出数据量过大（检测到 {rows} 行，单次上限 {max_rows} 行），"
                "请收窄筛选条件（如按机柜 / 客户 / 机房）后分批导出"
            ),
        )
        self.status_code = 413
        self.rows = rows
        self.max_rows = max_rows


_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _escape_formula_cell(v):
    """以公式前缀开头的字符串单元格加单引号前缀（仅处理 str，数值列不受影响）。"""
    if isinstance(v, str) and v[:1] in _FORMULA_PREFIXES:
        return "'" + v
    return v


def escape_export_df(df: pd.DataFrame) -> pd.DataFrame:
    """对 DataFrame 全部字符串单元格做公式注入转义。

    入库数据可能含攻击者可控字符串（如设备名 "=HYPERLINK(...)"），
    管理员导出打开时会被 Excel 当公式执行。导出侧统一中和。

    ⚠️ 本函数**已被 ``export_to_excel`` 弃用**（那条路径改走 write_only 流式写出，
    转义由 ``_prepare_export_cell`` 逐格完成，避免为了转义而多留一份 DataFrame 拷贝）。
    保留是因为**客户资源导出（5 Sheet）**仍在用：
    ``customer_service.generate_customer_assets_excel`` → ``escape_export_df``。
    该路径尚未改流式（单客户数据量有界），改的时候一并把本函数退场。
    """
    return df.map(_escape_formula_cell)


def _is_blank_export_value(v) -> bool:
    """单元格是否为空值（None / NaN / NaT / pd.NA / Decimal('NaN') 统一口径）。

    刻意不走"逐类型 isinstance"：pandas 的空值是一族（``np.nan`` / ``pd.NaT`` /
    ``pd.NA`` / ``Decimal('NaN')``），逐个枚举必然漏。``pd.isna`` 是唯一真源，
    对非标量（list/dict）会返回数组，此处按"非空值"处理。
    """
    if v is None:
        return True
    if isinstance(v, (str, bytes, bytearray, bool, int)):
        return False
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _prepare_export_cell(v):
    """导出单元格归一：空值→None（Excel 空单元格），numpy 标量→Python 标量，
    字符串再过公式注入转义。

    为什么必须归一 numpy 标量：``np.int64`` / ``np.datetime64`` 不是 ``int`` /
    ``datetime`` 的子类，openpyxl 遇到会抛 "Cannot convert"，症状是"导出偶发
    500 且只在某些数据类型下出现"。
    """
    if _is_blank_export_value(v):
        return None
    if hasattr(v, "item") and not isinstance(v, (str, bytes, bytearray)):
        try:
            v = v.item()
        except (AttributeError, ValueError):
            pass
        if _is_blank_export_value(v):
            return None
    return _escape_formula_cell(v)


def ordered_export_columns(rows: list) -> list:
    """列序 = 键**首现**顺序。

    这不是自选规则，而是必须与"改造前 `pd.DataFrame(rows)` 的列序"**逐字一致**：
    前端/用户的列顺序预期来自改造前的产物，改列序等于改了交付物。实测
    ``pd.DataFrame([{...}, {...}])`` 的列序 = 全量键的首次出现顺序。
    """
    cols: list = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                cols.append(k)
    return cols


def write_rows_to_sheet(buf, sheet_name: str, rows: list) -> None:
    """把行列表以 **write_only 流式模式**写成单 Sheet xlsx。

    内存与行数解耦的关键：openpyxl 普通模式会把每个单元格物化成常驻 Python 对象
    （20 万行 × 22 列 ＝ 440 万个 Cell），write_only 模式逐行落盘、不保留单元格。
    实测（``code_review/export_memory_probe.py``，22 列 / 20 万行）：

        df.to_excel + 普通模式  峰值 RSS 1,986 MB   「写出增量」1,302 MB
        write_only 流式         峰值 RSS   709 MB   「写出增量」    26 MB

    剩余 709 MB 几乎全是调用方已经持有的 ``rows`` 列表本身（不可由本函数消除）。

    Args:
        buf: 可写缓冲（如 BytesIO）
        sheet_name: 工作表名
        rows: 行字典列表（键集合可逐行不同，缺失键写空单元格）
    """
    from openpyxl import Workbook

    cols = ordered_export_columns(rows)
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(sheet_name)
    if cols:
        ws.append(cols)
        for r in rows:
            ws.append([_prepare_export_cell(r.get(c)) for c in cols])
    wb.save(buf)


def ensure_export_rows_within_limit(row_count: int, max_rows: Optional[int] = None) -> None:
    """导出侧行数闸 —— **编排层唯一判定点**。

    与导入侧的 ``ensure_import_rows_within_limit`` 对称。为什么值得抽成一个小函数：
    导出侧有**多条**产出路径（单 Sheet 的 ``export_to_excel``、多 Sheet 的
    ``generate_customer_assets_excel``），若各自内联一份 ``> MAX_EXPORT_ROWS``
    判断，新增入口时**极易漏加**，而"漏加"的表现是生产 OOM —— 功能测试看不见。
    判定点收敛到一处后，新增路径只需调它。

    ⚠️ 上限值只在**与写出侧实现能力配对**时才是保护：上限保证"不会比上限更大"，
    保证不了"上限本身扛得住"（普通模式 20 万行峰值 RSS 1,986 MB，见
    ``write_rows_to_sheet`` docstring）。

    Args:
        row_count: 本次导出累计行数（多 Sheet 路径传**各 Sheet 行数之和**）
        max_rows: 上限；None 时取当前 ``MAX_EXPORT_ROWS``（运行期读取，便于测试）

    Raises:
        ExportTooLargeError: row_count 超过上限（路由统一映射 413）
    """
    if max_rows is None:
        max_rows = MAX_EXPORT_ROWS
    if row_count > max_rows:
        raise ExportTooLargeError(row_count, max_rows)


def export_to_excel(rows: list, sheet_name: str, max_rows: Optional[int] = None) -> BytesIO:
    """将记录列表统一导出为 Excel 字节流（设备/机柜/客户共用）。

    统一职责：空数据检查 + 行数上限检查 + xlsx 流式写出，使三个实体的导出构造
    路径一致；数据获取（含是否需要分页）由调用方决定——大数据量的设备走分页循环，
    机柜/客户量小直接全量取，分页是数据量驱动而非风格差异。

    本函数里的上限是**兜底**：调用方（尤其分页取数循环）应在取数过程中就熔断，
    否则结果集已经先物化进内存了，这里再拦为时已晚。

    ⚠️ **写出侧必须保持流式（write_only）**。上限能保证"不会比上限更大"，保证不了
    "上限本身扛得住"：普通模式下 20 万行的峰值 RSS 是 1,986 MB，比上限设成多少
    更致命。`tests/test_export_streaming.py::TestExportDoesNotMaterialiseFullFrame`
    钉住这一条——功能测试无法发现该回退，它只在生产 OOM。

    Args:
        rows: 已序列化为 dict 的记录列表（如 get_all_*_list 返回 List[Dict]）
        sheet_name: Excel 工作表名
        max_rows: 单次导出允许的最大行数；None 时取当前 ``MAX_EXPORT_ROWS``
            （运行期读取，便于统一调参与测试）

    Returns:
        可被 flask.send_file 直接消费的 BytesIO 缓冲

    Raises:
        EmptyExportError: rows 为空时
        ExportTooLargeError: rows 超过 max_rows 时（路由→413）
    """
    if not rows:
        raise EmptyExportError()
    ensure_export_rows_within_limit(len(rows), max_rows)
    output = BytesIO()
    write_rows_to_sheet(output, sheet_name, rows)
    output.seek(0)
    return output



def _validate_import_type(file_bytes: bytes, filename: str) -> str:
    """导入文件类型校验：扩展名白名单 + 内容 magic bytes 双重检查。

    Args:
        file_bytes: 上传文件的原始字节
        filename: 原始文件名

    Returns:
        归一化后的扩展名（".csv" / ".xlsx"）

    Raises:
        AppValidationError: 扩展名不在白名单，或内容与声明类型不符
    """
    fname = (filename or "").lower()
    ext = os.path.splitext(fname)[1]
    if ext not in ALLOWED_IMPORT_EXT:
        allowed = " / ".join(sorted(ALLOWED_IMPORT_EXT))
        raise AppValidationError(f"不支持的文件类型 {ext or '(无扩展名)'}，仅支持 {allowed}")

    if ext == ".csv":
        if b"\x00" in file_bytes[:8192]:
            raise AppValidationError("文件内容不是合法的 CSV 文本")
    else:
        if file_bytes[:2] != b"PK":
            raise AppValidationError("文件内容不是合法的 xlsx（缺少 ZIP 头）")
        try:
            with zipfile.ZipFile(BytesIO(file_bytes)) as zf:
                names = zf.namelist()
                if len(names) > _MAX_XLSX_ENTRIES:
                    raise AppValidationError(
                        f"xlsx 内部条目过多（{len(names)}），疑似 zip bomb，已拒绝解析")
                total = sum(info.file_size for info in zf.infolist())
                if total > _MAX_XLSX_UNCOMPRESSED_BYTES:
                    raise AppValidationError(
                        f"xlsx 解压后体积过大（{total} 字节），疑似 zip bomb，已拒绝解析")
        except zipfile.BadZipFile as e:
            raise AppValidationError("文件内容不是合法的 xlsx（ZIP 结构损坏）") from e
    return ext


def _read_tabular_df(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """类型校验后按扩展名解析为 DataFrame（csv / xlsx 双分支唯一收敛点）。

    设备（build_device_df）与客户/机柜（parse_file_to_df）共用，
    非白名单类型在此统一拒绝，不再落入 read_excel 的无差别解析。
    """
    ext = _validate_import_type(file_bytes, filename)
    buf = BytesIO(file_bytes)
    if ext == ".csv":
        return pd.read_csv(buf, encoding="utf-8-sig")
    return pd.read_excel(buf)


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
    df = _read_tabular_df(file_bytes, filename)

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
            savepoint.commit()
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
            if savepoint.is_active:
                savepoint.rollback()

    return {
        "imported_count": imported_count,
        "failed_count": len(failed_rows),
        "failed_rows": failed_rows,
    }
