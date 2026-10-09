# -*- coding: utf-8 -*-
"""批量端点 items 条数上限 —— 跨层单一真源（评审 20260924 §2.3）。


批量端点（占位标记批量编辑、机柜批量换位…）都是**单事务 + 逐条 CAS**：
条数无上限时，一个超大 payload 会形成长事务、久持行锁，叠加循环内的读写
放大，单条请求就能把同机房的其它编辑全挡住。此前只校验了 ``items`` 非空，
长度完全放任。


与 ``pagination_limits`` 同一取舍：截断（只处理前 200 条）会让用户以为
全批都生效了，而剩下的改动悄悄丢了 —— 这比直接拒绝危险得多。故抛异常，
由接口层返回 400 + 可操作文案（拆批提交）。


平面图一屏的标记/机柜量级在几十条；一次拖拽编辑最多也就这个数。200 留出
一倍以上余量，同时把最坏事务规模压在有界范围。**改这个值只需改这里一处**：
前端在 ``frontend-new/src/services/room.ts`` 镜像了同一个常量，由
``tests/test_batch_items_limit.py`` 钉住两边必须相等 —— 与 ``MAX_OFFSET``
的前后端同钉是同一套做法。


闭区间：``count == MAX_BATCH_ITEMS`` 放行（``>`` 才拒）。写成 ``>=`` 会让
"恰好 200 条"的正常批次被拒。
"""
from __future__ import annotations

from app.exceptions.business import BatchItemsLimitExceeded

__all__ = [
    "MAX_BATCH_ITEMS",
    "BatchItemsLimitExceeded",
    "ensure_batch_size_within_limit",
]

MAX_BATCH_ITEMS = 200


def ensure_batch_size_within_limit(
    count: int, *, endpoint: str = "批量操作"
) -> None:
    """条数守卫：``count > MAX_BATCH_ITEMS`` 时抛 ``BatchItemsLimitExceeded``。

    调用位置：**解析完 items、进业务方法之前**（API 层）。放这里而不是服务层
    的理由：条数是**请求形状**问题，不是业务规则；在 API 层拒绝可以完全避免
    开事务、避免任何一次数据库往返，也避免把"请求太大"混进业务异常语义。

    Args:
        count: items 条数
        endpoint: 端点名称，仅用于把 400 文案说人话

    Raises:
        BatchItemsLimitExceeded: 条数超过上限（HTTP 400）
    """
    if count > MAX_BATCH_ITEMS:
        raise BatchItemsLimitExceeded(
            count=count, max_items=MAX_BATCH_ITEMS, endpoint=endpoint
        )
