# -*- coding: utf-8 -*-
"""统一时间工具（全仓时间口径的收敛点）。

背景：此前各处时间口径不一——
- API 响应用 UTC（`datetime.now(timezone.utc)`）；
- 日志、错误统计、健康检查用本地 naive 时间（`datetime.now()`）。

结果是接口返回的 `timestamp` 比服务端日志早 8 小时，排障时两边对不上
（真实反馈：报错显示 01:07，而日志是 09:07）。

约定（新增代码请按此取时间）：
- **数据库写入 / 与库内时间比较**：`now_utc_naive()`（UTC naive）。
  列类型保持 **DATETIME**（无时区），MySQL 会话时区由 extensions.py 的
  连接事件固定为 UTC，使 DEFAULT CURRENT_TIMESTAMP / ON UPDATE / NOW()
  全部落 UTC——四层口径一致。
  ⚠️ 决策记录（2026-09-08）：评估过"迁移为 TIMESTAMP 列"并否决——
  TIMESTAMP 读写按每个连接的会话时区转换，任何旁路连接（CLI/脚本/工具）
  会话时区≠UTC 时写入即错 8 小时，且有 2038 上限；DATETIME 原样存储、
  口径完全由应用层控制，行为最可预测。
  ⚠️ 任何绕过应用直连 MySQL 的工具/脚本，务必 `SET time_zone='+00:00'`。
- **对外输出**（日志 / 排障上下文 / 错误统计）：`now_iso()`，
  本地时区 + UTC 偏移（如 `2026-09-08T09:07:05.123456+08:00`）——
  既与本地日志直接对齐，又保留绝对时刻供其它时区还原。
- **对外输出·API 响应**：`now_iso_utc()`（UTC，带 `Z`）。响应信封的
  `timestamp` 与数据字段一律 UTC，避免同一 payload 里出现两种时区。
- **前端消费**：后端 datetime 字段一律是 UTC（2026-09-08 起序列化走
  `to_iso_utc()`，带 `Z`；`frontend/src/utils/format.ts` 的
  `parseServerTime`/`ensureUtc` 统一解析），显示时转浏览器本地时区。
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple




def now_utc() -> datetime:
    """当前 UTC aware datetime（做时间比较/换算用）。"""
    return datetime.now(timezone.utc)


def now_utc_naive() -> datetime:
    """数据库写入 / 与库内时间比较统一用这个：UTC naive datetime。

    等价于旧的 `datetime.now()` 位置，但语义明确为 UTC。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_iso_utc(dt: Optional[datetime]) -> Optional[str]:
    """序列化用：库里的 naive（视为 UTC）→ 带 `Z` 的 ISO 字符串。

    前端 `ensureUtc()` 对已带 Z/+00:00 的字符串不重复处理，故输出带 Z 后
    由 dayjs 正确换算为本地时间显示。
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def now_local() -> datetime:
    """当前本地时区的 aware datetime（带 UTC 偏移）。"""
    return datetime.now().astimezone()


def now_iso() -> str:
    """对外输出用：本地时区 ISO8601 字符串（带 UTC 偏移）。"""
    return now_local().isoformat()


def now_iso_utc() -> str:
    """对外输出用：UTC ISO8601 字符串（带 Z 后缀）。

    与 `to_iso_utc(now_utc_naive())` 等价，用于 API 响应顶层 timestamp 等
    需明确标识为 UTC 的场景，与数据字段（naive UTC）口径一致。
    """
    return to_iso_utc(now_utc_naive())


def utc_today() -> date:
    """UTC 日历日的日期对象（分区命名 / 日界计算用）。

    注意：不要用 date.today()——那按服务器本地日历取日，与 UTC 时序数据
    的分区边界（TO_DAYS(collected_at)）会差一个偏移（东八区 8 小时）。
    """
    return now_utc_naive().date()


def from_ts(ts: float) -> datetime:
    """POSIX 时间戳 → 本地 aware datetime（日志/统计用）。"""
    return datetime.fromtimestamp(ts).astimezone()


def to_utc_naive(dt: Optional[datetime]) -> Optional[datetime]:
    """任意 aware datetime → UTC naive；本身就是 naive 则按 UTC 原样返回。

    用于把入参（可能是 aware +08:00 / +00:00，也可能是 naive）统一到
    与库内 DATETIME 比较所需的 UTC naive，避免
    `can't compare offset-naive and offset-aware datetimes`。
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def local_to_utc_naive(dt: Optional[datetime]) -> Optional[datetime]:
    """把按**服务器本地时区**表达的 naive datetime 换算为 UTC naive。

    用途：入参是"业务日"（如 DatePicker 选的 2026-09-08），而库内比较走 UTC
    naive 时，先把本地日边界换算成 UTC 区间，避免一天的起止偏一个时区偏移。
    """
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def local_day_range(day: str) -> Tuple[datetime, datetime]:
    """业务日（YYYY-MM-DD，本地日历）→ 当天的 [起, 止) UTC naive 区间。

    统一"—天"的语义口径：业务日按用户感知（本地日历），比较时换算成 UTC。
    """
    start_local = datetime.strptime(day, "%Y-%m-%d")
    end_local = start_local + timedelta(days=1)
    return (local_to_utc_naive(start_local), local_to_utc_naive(end_local))


def parse_iso(value: str) -> Optional[datetime]:
    """解析 ISO8601 字符串为 aware datetime；无法解析返回 None。

    naive 字符串按 **UTC** 补齐偏移——与"库内 naive 一律视作 UTC"的存储口径
    一致（2026-09-08 前曾按本地时区补齐，是 timezone 收敛点的语义陷阱）。
    需要按本地时区解析的场景请显式传入带偏移的字符串。
    """
    if not value:
        return None
    try:
        raw = value[:-1] + "+00:00" if value.endswith("Z") else value
        dt = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
