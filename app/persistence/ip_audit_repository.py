# -*- coding: utf-8 -*-
"""IP 审计 Repository

跨 ip_allocation_logs（归属变更 allocate/release）与 ip_ban_records
（封禁/解封 ban/unban）的合并查询 DAO。

为什么不继承 BaseRepository：本类没有单一 model_class，CRUD 基类不适用；
且基类 __init_subclass__ 会把子类登记进仓储自动注册表 _REGISTRY（面向单表
仓储），跨表聚合 DAO 不应混入。故这里只复用 session 约定，保持轻量。

SQL 兼容性（重要）：
    单元测试跑在 SQLite 内存库（tests/conftest_api.py），生产为 MySQL。
    因此本文件只用两者共同支持的语法——不使用 CONCAT()、JSON_EXTRACT()
    等 MySQL 专有函数。所有字段加工（row_key 拼接、JSON 解析、时间格式化）
    一律放在 Python 层，由 Service 完成。
"""
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.models.ip_allocation_log import IPAllocationLog
from app.utils.logging import get_logger

logger = get_logger(__name__)

_ALLOC_SELECT = """
SELECT 'allocation' AS source, id, ip_address, room_id, action, operator_id,
       created_at, detail AS payload, NULL AS ban_mode, NULL AS switch_id
FROM ip_allocation_logs
WHERE action IN ('allocate', 'release')
"""

_BAN_SELECT = """
SELECT 'ban' AS source, id, ip_address, room_id, action, operator_id,
       created_at, ban_meta AS payload, ban_mode, switch_id
FROM ip_ban_records
WHERE action IN ('ban', 'unban')
"""

_ORDER_BY = "ORDER BY created_at DESC"


def _build_conditions(
    action: Optional[str] = None,
    ip_address: Optional[str] = None,
    room_id: Optional[int] = None,
    operator_id: Optional[int] = None,
    start_time: Optional[Any] = None,
    end_time: Optional[Any] = None,
) -> Tuple[str, Dict[str, Any]]:
    """构造两表共用的 WHERE 过滤子句（值一律走参数绑定，防 SQL 注入）

    Args:
        action: 动作（allocate/release/ban/unban），不属于本表的动作会自然查空
        ip_address: IP 精确匹配
        room_id: 机房 ID
        operator_id: 操作人 ID
        start_time: 起始时间（含）
        end_time: 结束时间（含）

    Returns:
        Tuple[str, Dict]: (SQL 片段, 绑定参数)
    """
    clauses: List[str] = []
    params: Dict[str, Any] = {}

    if action:
        clauses.append("AND action = :action")
        params["action"] = action
    if ip_address:
        clauses.append("AND ip_address = :ip_address")
        params["ip_address"] = ip_address
    if room_id is not None:
        clauses.append("AND room_id = :room_id")
        params["room_id"] = room_id
    if operator_id is not None:
        clauses.append("AND operator_id = :operator_id")
        params["operator_id"] = operator_id
    if start_time is not None:
        clauses.append("AND created_at >= :start_time")
        params["start_time"] = start_time
    if end_time is not None:
        clauses.append("AND created_at <= :end_time")
        params["end_time"] = end_time

    return " ".join(clauses), params


class IPAuditRepository:
    """IP 审计 DAO

    职责两部分：
    - 跨表合并查询（UNION ip_allocation_logs + ip_ban_records）
    - 归属变更日志写入（只写 ip_allocation_logs）

    封禁/解封由 ip_ban_service 自行写入 ip_ban_records，本类只读不写。
    """

    def __init__(self, session=None):
        """初始化

        Args:
            session: 数据库会话，默认使用全局 session
        """
        from extensions import db

        self.session = session or db.session

    def query(
        self,
        action: Optional[str] = None,
        ip_address: Optional[str] = None,
        room_id: Optional[int] = None,
        operator_id: Optional[int] = None,
        start_time: Optional[Any] = None,
        end_time: Optional[Any] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """合并查询两表审计记录（分页在 SQL 层完成）

        Args:
            action: 动作过滤
            ip_address: IP 精确匹配
            room_id: 机房 ID
            operator_id: 操作人 ID
            start_time: 起始时间（含）
            end_time: 结束时间（含）
            page: 页码（从 1 开始）
            per_page: 每页条数

        Returns:
            Tuple[List[Dict], int]: (当前页行记录(dict), 符合条件的总条数)
        """
        where, params = _build_conditions(
            action=action,
            ip_address=ip_address,
            room_id=room_id,
            operator_id=operator_id,
            start_time=start_time,
            end_time=end_time,
        )

        page = max(1, page)
        per_page = max(1, min(per_page, 100))

        total = self._count(where, params)
        if total == 0:
            return [], 0

        rows = self._fetch(where, params, page, per_page)
        return rows, total

    def insert_allocation(self, row: Dict[str, Any]) -> IPAllocationLog:
        """写入单条归属变更日志

        Args:
            row: 字段字典（ip_address/room_id/action/operator_id/detail）

        Returns:
            IPAllocationLog: 已 flush 的日志对象
        """
        log = IPAllocationLog(**row)
        self.session.add(log)
        self.session.flush()
        return log

    def bulk_insert_allocations(self, rows: List[Dict[str, Any]]) -> int:
        """批量写入归属变更日志（一次 flush，避免 N 次 insert 拖慢主流程）

        网段级分配一次可能涉及数千个 IP，逐条 insert 会显著拉长事务。

        Args:
            rows: 字段字典列表

        Returns:
            int: 写入条数
        """
        if not rows:
            return 0
        self.session.add_all([IPAllocationLog(**row) for row in rows])
        self.session.flush()
        return len(rows)

    def _count(self, where: str, params: Dict[str, Any]) -> int:
        """统计符合条件的总条数（UNION 结果整体计数）"""
        sql = f"""
            SELECT COUNT(*) AS total FROM (
                {_ALLOC_SELECT} {where}
                UNION ALL
                {_BAN_SELECT} {where}
            ) AS combined
        """
        result = self.session.execute(text(sql), params)
        return int(result.scalar() or 0)

    def _fetch(
        self, where: str, params: Dict[str, Any], page: int, per_page: int,
    ) -> List[Dict[str, Any]]:
        """取当前页数据（排序 + 分页在 SQL 层，保证分页正确）"""
        sql = f"""
            {_ALLOC_SELECT} {where}
            UNION ALL
            {_BAN_SELECT} {where}
            {_ORDER_BY}
            LIMIT :limit OFFSET :offset
        """
        bind = dict(params)
        bind["limit"] = per_page
        bind["offset"] = (page - 1) * per_page

        result = self.session.execute(text(sql), bind)
        return [dict(row._mapping) for row in result]
