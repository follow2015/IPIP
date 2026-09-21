# -*- coding: utf-8 -*-
"""分页偏移量上限（P0-3c 深度封顶）—— 跨层单一真源。


列表翻页全链路走 ``LIMIT ? OFFSET ?``（实测 24 处 / 16 文件），**此前没有任何上限**：
翻到第 N 页时数据库仍要先扫掉前面 ``(N-1)*page_size`` 行再丢弃。当前暴露面为 0
（走分页的表最大 3,927 行，见 ``docs/IPIP-导入导出与深分页评估报告.md`` §0.2），
但采集层落地后数据会增长，而"增长"不会自己带来保护 —— 本模块把"无上限"
变成"有明确边界"，并把超限翻译成**用户可执行的下一步**（改用筛选）。


截断（``offset = min(offset, MAX_OFFSET)``）看起来更友好，实际是**静默改语义**：
用户请求第 500 页、拿到第 101 页的内容，且分页器仍显示 500 —— 数据"看起来"对不上，
没有任何信号说明发生了什么。本仓对此已有明确取舍先例（导出加固选择
``MAX_EXPORT_ROWS`` 熔断而非截断）。故这里抛异常，由接口层返回 400 + 可操作文案。


≈ 100 页 × 100 条 —— 远超正常人的翻页耐心，同时把最坏情况的扫描量压在有界范围。
调这个值只需改这里一处（前端降级阈值由 ``tests/test_pagination_offset_limit.py``
的契约用例与 ``frontend-new/src/components/DataTable/serverPagination.ts`` 同步钉住）。


这是**路线 (c)**：零契约变更、立即生效、随数据增长自动兜底。它同时是路线 (b)
（keyset 游标）的**严格子集路径** —— 将来若某张表真的长到需要 keyset，本模块的
调用点就是改造落点，不会白做。
"""
from __future__ import annotations

from app.exceptions.business import PaginationLimitExceeded

__all__ = [
    "MAX_OFFSET",
    "PaginationLimitExceeded",
    "ensure_offset_within_limit",
]

MAX_OFFSET = 10_000


def ensure_offset_within_limit(offset: int) -> None:
    """偏移量守卫：``offset > MAX_OFFSET`` 时抛 ``PaginationLimitExceeded``。

    调用位置：**算完 offset、执行查询之前**（``persistence`` 层各分页点）。
    放这里而非 API 层的理由：API 层的 ``page`` 参数解析分散在 20+ 个文件里各写各的
    （``request.args.get("page", 1, type=int)``），没有统一入口；而 offset 在仓储层
    是**确切值**，判据不受 ``per_page`` 默认值差异影响。

    边界为**闭区间**：``offset == MAX_OFFSET`` 放行。写成 ``>=`` 会让
    "恰好 10001 条" 的表少翻一页 —— 这类差一错误没有测试是发现不了的
    （见 ``tests/test_pagination_offset_limit.py::TestOffsetLimitPredicate``）。
    """
    if offset > MAX_OFFSET:
        raise PaginationLimitExceeded(offset=offset, max_offset=MAX_OFFSET)
