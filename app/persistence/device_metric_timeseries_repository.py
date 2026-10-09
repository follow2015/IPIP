# -*- coding: utf-8 -*-
"""设备指标值历史时序仓库（DeviceMetricTimeseriesRepository）

每次采集后批量 INSERT（与 device_metric_latest upsert 同事务），存储指标值历史时序，
供前端趋势图查询。纯插入无 upsert（时序表无唯一键约束，每次采集都是新行）。
"""
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from app.utils.time_utils import now_utc_naive

from sqlalchemy import and_, text

from extensions import db
from app.models.device_metric_timeseries import DeviceMetricTimeseries
from app.models.device_metric_timeseries_daily import DeviceMetricTimeseriesDaily
from app.models.device_metric_timeseries_hourly import DeviceMetricTimeseriesHourly
from app.utils.logging import get_logger
from app.utils.metric_value import parse_metric_value_num, variance_from_sum_sq

logger = get_logger(__name__)

METRIC_DOWNSAMPLE_CUTOFF_DAYS = 7
METRIC_HOURLY_RETENTION_DAYS = 90
METRIC_DAILY_DOWNSAMPLE_CUTOFF_DAYS = 30
METRIC_DAILY_RETENTION_DAYS = 730
METRIC_VALUE_NUM_BATCH = 5000

_UPSERT_METRIC_HOURLY_SQL = """
INSERT INTO device_metric_timeseries_hourly
    (device_id, metric_key, index_key, hour_bucket,
     avg_value, min_value, max_value, sample_count,
     sum_sq, numeric_count,
     `last_value`, state_changes, breach_count, worst_severity)
SELECT
    s.device_id,
    s.metric_key,
    s.index_key,
    s.hour_bucket,
    AVG(s.value_num),
    MIN(s.value_num),
    MAX(s.value_num),
    COUNT(*),
    SUM(POW(s.value_num, 2)),
    COUNT(s.value_num),
    COALESCE(SUM(CASE WHEN s.prev_value IS NOT NULL
                      AND s.prev_value <> s.value THEN 1 ELSE 0 END), 0),
    COALESCE(SUM(CASE WHEN s.breached = 1 THEN 1 ELSE 0 END), 0),
    ELT(MAX(FIELD(s.severity, 'ok', 'warn', 'crit')), 'ok', 'warn', 'crit')
FROM (
    SELECT
        t.device_id,
        t.metric_key,
        t.index_key,
        DATE_FORMAT(t.collected_at, '%Y-%m-%d %H:00:00') AS hour_bucket,
        t.value_num,
        t.value,
        t.breached,
        t.severity,
        LAG(t.value) OVER (
            PARTITION BY t.device_id, t.metric_key, t.index_key
            ORDER BY t.collected_at, t.id
        ) AS prev_value,
        ROW_NUMBER() OVER (
            PARTITION BY t.device_id, t.metric_key, t.index_key,
                         DATE_FORMAT(t.collected_at, '%Y-%m-%d %H:00:00')
            ORDER BY t.collected_at DESC, t.id DESC
        ) AS rn_desc
    FROM device_metric_timeseries t
    JOIN devices d ON d.id = t.device_id
    WHERE t.collected_at >= :day_start AND t.collected_at <= :day_end
) s
GROUP BY s.device_id, s.metric_key, s.index_key, s.hour_bucket
ON DUPLICATE KEY UPDATE
    avg_value = VALUES(avg_value),
    min_value = VALUES(min_value),
    max_value = VALUES(max_value),
    sample_count = VALUES(sample_count),
    sum_sq = VALUES(sum_sq),
    numeric_count = VALUES(numeric_count),
    `last_value` = VALUES(`last_value`),
    state_changes = VALUES(state_changes),
    breach_count = VALUES(breach_count),
    worst_severity = VALUES(worst_severity)
"""

_UPSERT_METRIC_DAILY_SQL = """
INSERT INTO device_metric_timeseries_daily
    (device_id, metric_key, index_key, day_bucket,
     avg_value, min_value, max_value, sample_count,
     sum_sq, numeric_count,
     `last_value`, state_changes, breach_count, worst_severity)
SELECT
    x.device_id,
    x.metric_key,
    x.index_key,
    DATE(x.hour_bucket),
    AVG(x.avg_value),
    MIN(x.min_value),
    MAX(x.max_value),
    COUNT(*),
    SUM(x.sum_sq),
    SUM(x.numeric_count),
    COALESCE(SUM(x.state_changes), 0),
    COALESCE(SUM(x.breach_count), 0),
    ELT(MAX(FIELD(x.worst_severity, 'ok', 'warn', 'crit')), 'ok', 'warn', 'crit')
FROM (
    SELECT
        t.*,
        ROW_NUMBER() OVER (
            PARTITION BY t.device_id, t.metric_key, t.index_key, DATE(t.hour_bucket)
            ORDER BY t.hour_bucket DESC
        ) AS rn_desc
    FROM device_metric_timeseries_hourly t
    WHERE t.hour_bucket < :cutoff
) x
GROUP BY x.device_id, x.metric_key, x.index_key, DATE(x.hour_bucket)
ON DUPLICATE KEY UPDATE
    avg_value = VALUES(avg_value),
    min_value = VALUES(min_value),
    max_value = VALUES(max_value),
    sample_count = VALUES(sample_count),
    sum_sq = VALUES(sum_sq),
    numeric_count = VALUES(numeric_count),
    `last_value` = VALUES(`last_value`),
    state_changes = VALUES(state_changes),
    breach_count = VALUES(breach_count),
    worst_severity = VALUES(worst_severity)
"""


GRANULARITY_HOUR = "hour"
GRANULARITY_DAY = "day"


@dataclass(frozen=True)
class MetricSampleRow:
    """明细表的一行 —— **行 DTO，刻意不是 ORM 实例**（D1：收口 P1 的另一半）。

    为什么必须换掉 ORM 实例：把 ORM 对象交给消费方（API 序列化 / AI capability）
    等于把 session 生命周期一起交出去 —— 调用方一旦在 session 关闭后碰惰性属性，
    就是 `DetachedInstanceError`；而 CH 路线落地后**这一层要能整体替换**，
    返回 ORM 实体会把"换后端"变成"改所有消费方"。

    ``to_dict()`` 的字段与 ``DeviceMetricTimeseries.to_dict()`` **逐字段对齐**
    （含 ``collected_at`` 的 ``isoformat()``）—— 换 DTO 的验收标准就是
    "消费方拿到的 JSON 一字不差"，否则等于顺手改了对外契约。
    """

    id: int
    device_id: int
    metric_key: str
    index_key: str
    value: Optional[str]
    value_num: Optional[float]
    severity: Optional[str]
    breached: bool
    collected_at: Optional[datetime]
    created_at: Optional[datetime]

    def to_dict(self, exclude: Optional[list] = None) -> dict:
        """与 ORM 的 ``to_dict()`` 同形（含 exclude 行为）。"""
        data = {
            "id": self.id,
            "device_id": self.device_id,
            "metric_key": self.metric_key,
            "index_key": self.index_key,
            "value": self.value,
            "value_num": self.value_num,
            "severity": self.severity,
            "breached": self.breached,
            "collected_at": self.collected_at.isoformat() if self.collected_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if exclude:
            for k in exclude:
                data.pop(k, None)
        return data


@dataclass(frozen=True)
class MetricRollupPoint:
    """聚合层的一个桶 —— **行 DTO，刻意不是 ORM 实例**。

    为什么不直接返 ORM 实例：聚合层要被 AI 特征流水线批量消费，返回实体会把
    session 生命周期泄漏到消费侧（ detach / 懒加载 / 事务边界全是坑），
    且与 ``list_samples_since`` 返 tuple 的既有取向一致。

    为什么带上 ``sum_sq`` / ``numeric_count``：这两个是方差的**充分统计量**，
    DTO 上直接给 ``variance()`` / ``stdev()``，消费方不必回源明细（详见
    B1-var，计划文档 §2）。
    """

    device_id: int
    metric_key: str
    index_key: str
    bucket_start: datetime
    granularity: str
    avg_value: Optional[float]
    min_value: Optional[float]
    max_value: Optional[float]
    sample_count: int
    sum_sq: Optional[float]
    numeric_count: int
    last_value: Optional[str]
    state_changes: int
    breach_count: int
    worst_severity: Optional[str]

    def variance(self, *, sample: bool = True) -> Optional[float]:
        """桶内波动性（**不回源明细**）。输入不足时返回 ``None``。"""
        return variance_from_sum_sq(
            self.sum_sq, self.numeric_count, self.avg_value, sample=sample
        )

    def stdev(self, *, sample: bool = True) -> Optional[float]:
        """标准差；方差为 ``None`` 时同样返回 ``None``（不返回 0）。"""
        var = self.variance(sample=sample)
        return None if var is None else math.sqrt(var)

    def to_dict(self) -> Dict[str, Any]:
        """平坦化给特征流水线（方差/标准差一并带上，省得每个消费方各算一遍）。"""
        return {
            "device_id": self.device_id,
            "metric_key": self.metric_key,
            "index_key": self.index_key,
            "bucket_start": self.bucket_start,
            "granularity": self.granularity,
            "avg_value": self.avg_value,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "sample_count": self.sample_count,
            "numeric_count": self.numeric_count,
            "last_value": self.last_value,
            "state_changes": self.state_changes,
            "breach_count": self.breach_count,
            "worst_severity": self.worst_severity,
            "variance": self.variance(),
            "stdev": self.stdev(),
        }


def choose_rollup_granularity(
    from_: Optional[datetime],
    to: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> str:
    """按查询窗口自动选聚合粒度（纯函数，便于门禁直接断言边界）。

    规则（**两条都是硬约束，不是启发式**）：

    1. ``from_`` 早于 hourly 保留窗起点 ⇒ 只能 ``day``。
       hourly 只留 ``METRIC_HOURLY_RETENTION_DAYS``(90) 天，再早的数据**已被清理**，
       读 hourly 会静默少一段（不是报错，是结果不对 —— 更难发现）。
    2. 窗口跨度 > 90 天 ⇒ 退到 ``day``。hourly 全量即 90 天，跨度再大 hourly
       也覆盖不全；且 90 天 × 24 = 2160 行/指标，AI 批读没必要吃这个量级。

    边界（**刻意取闭/开不同侧，均有测试钉住**）：
    - ``from_ == floor`` ⇒ ``hour``（清理条件是 ``hour_bucket < floor``，该桶还在）；
    - 跨度 **恰好 90 天** ⇒ ``hour``，超过 1 秒 ⇒ ``day``。

    ``from_`` 为 ``None`` ⇒ 默认窗口在 90 天内 ⇒ ``hour``。
    """
    if from_ is None:
        return GRANULARITY_HOUR
    now = now or now_utc_naive()
    to = to or now
    floor = now - timedelta(days=METRIC_HOURLY_RETENTION_DAYS)
    if from_ < floor:
        return GRANULARITY_DAY
    if (to - from_) > timedelta(days=METRIC_HOURLY_RETENTION_DAYS):
        return GRANULARITY_DAY
    return GRANULARITY_HOUR


class DeviceMetricTimeseriesRepository:
    """设备指标值历史时序仓库"""

    def __init__(self, session=None):
        self.session = session or db.session

    def add_many(self, device_id: int, collected: dict, collected_at: datetime = None) -> int:
        """批量插入采集结果到时序表。

        Args:
            device_id: 设备 ID
            collected: {metric_key: {index: {"value":..., "severity":..., "breached":...}}}
            collected_at: 采集时间（缺省 now）
        Returns:
            插入行数
        """
        if not collected:
            return 0
        collected_at = collected_at or now_utc_naive()
        rows = []
        for metric_key, table in collected.items():
            for index, info in (table or {}).items():
                raw_value = info.get("value")
                rows.append({
                    "device_id": device_id,
                    "metric_key": metric_key,
                    "index_key": str(index),
                    "value": str(raw_value) if raw_value is not None else None,
                    "value_num": parse_metric_value_num(raw_value),
                    "severity": info.get("severity"),
                    "breached": bool(info.get("breached", False)),
                    "collected_at": collected_at,
                })
        if not rows:
            return 0
        self.session.bulk_insert_mappings(DeviceMetricTimeseries, rows)
        self.session.flush()
        return len(rows)

    def list_samples_since(self, since: datetime) -> List[tuple]:
        """取某时刻之后的**全部**指标样本（B-44 收敛：基线重算的唯一用点）。

        返回 ``[(device_id, metric_key, index_key, value, collected_at), ...]``：
        基线重算要按 (device, metric, index) 全量分组后再算分桶统计，逐行拉实体
        反而是浪费（这是唯一需要"跨设备全量样本"的调用点，跑在 CLI 重算路径上）。
        刻意**不设 limit**（与原实现一致）：截断样本会让基线统计静默失真。
        """
        return (
            self.session.query(
                DeviceMetricTimeseries.device_id,
                DeviceMetricTimeseries.metric_key,
                DeviceMetricTimeseries.index_key,
                DeviceMetricTimeseries.value,
                DeviceMetricTimeseries.collected_at,
            )
            .filter(DeviceMetricTimeseries.collected_at >= since)
            .all()
        )

    def list_by_metric(
        self,
        device_id: int,
        metric_key: str,
        index_key: Optional[str] = None,
        from_: Optional[datetime] = None,
        to: Optional[datetime] = None,
        limit: int = 2000,
    ) -> List[MetricSampleRow]:
        """查询设备某指标的历史时序，返回**行 DTO**（不再返回 ORM 实例）。

        Args:
            device_id: 设备 ID
            metric_key: 指标 key
            index_key: 指标实例索引（可选，None=所有 index）
            from_: 起始时间（可选）
            to: 结束时间（可选）
            limit: 最多返回行数（默认 2000，上限 5000）

        Returns:
            ``[MetricSampleRow, ...]``。**只查明确定义的列**（不 ``query(Model)``）：
        查实体等于把"要不要真的实例化 ORM 对象"这件事交给调用上下文，
        而 CH 后端将来压根没有 ORM 实体可实例化。
        """
        limit = max(1, min(limit, 5000))
        cols = (
            DeviceMetricTimeseries.id,
            DeviceMetricTimeseries.device_id,
            DeviceMetricTimeseries.metric_key,
            DeviceMetricTimeseries.index_key,
            DeviceMetricTimeseries.value,
            DeviceMetricTimeseries.value_num,
            DeviceMetricTimeseries.severity,
            DeviceMetricTimeseries.breached,
            DeviceMetricTimeseries.collected_at,
            DeviceMetricTimeseries.created_at,
        )
        conditions = [
            DeviceMetricTimeseries.device_id == device_id,
            DeviceMetricTimeseries.metric_key == metric_key,
        ]
        if index_key is not None:
            conditions.append(DeviceMetricTimeseries.index_key == index_key)
        if from_ is not None:
            conditions.append(DeviceMetricTimeseries.collected_at >= from_)
        if to is not None:
            conditions.append(DeviceMetricTimeseries.collected_at <= to)
        rows = (
            self.session.query(*cols)
            .filter(and_(*conditions))
            .order_by(DeviceMetricTimeseries.collected_at.asc())
            .limit(limit)
            .all()
        )
        return [MetricSampleRow(*r) for r in rows]

    def list_metric_keys(self, device_id: int) -> List[str]:
        """查询设备有历史时序数据的所有 metric_key（供前端指标选择器）。"""
        rows = (
            self.session.query(DeviceMetricTimeseries.metric_key)
            .filter_by(device_id=device_id)
            .distinct()
            .order_by(DeviceMetricTimeseries.metric_key.asc())
            .all()
        )
        return [r[0] for r in rows]


    def _is_mysql(self) -> bool:
        """当前连接是否为 MySQL（降采样/分区相关 SQL 仅 MySQL 生效）。"""
        bind = self.session.get_bind()
        return bool(bind) and bind.dialect.name == "mysql"

    def backfill_value_num(self, batch_size: int = METRIC_VALUE_NUM_BATCH) -> int:
        """回填存量明细的 ``value_num``（幂等；只处理 ``value_num IS NULL`` 的行）。

        为什么必须走应用层而不是一条 SQL：解析口径必须与
        ``app/utils/metric_value.py::parse_metric_value_num`` **完全一致**
        （严格解析）。MySQL 的 ``REGEXP_SUBSTR`` 无法提取捕获组，写不出等价 SQL；
        用宽松正则回填会让 ``"port 3 down"`` 变成 ``3.0`` 并污染所有聚合。

        幂等性来自"只挑 value_num IS NULL 的行"+ 解析后显式写回（含 NULL）。
        注意 NULL 也要**写回并计数**：否则下一轮仍会挑到同一批行 ⇒ 死循环。
        """
        updated = 0
        while True:
            rows = self.session.execute(
                text(
                    """
                    SELECT id, value
                    FROM device_metric_timeseries
                    WHERE value_num IS NULL
                    ORDER BY id
                    LIMIT :limit
                    """
                ),
                {"limit": batch_size},
            ).fetchall()
            if not rows:
                break
            payload = [{"id": r[0], "value_num": parse_metric_value_num(r[1])} for r in rows]
            self.session.execute(
                text(
                    """
                    UPDATE device_metric_timeseries
                    SET value_num = :value_num
                    WHERE id = :id
                    """
                ),
                payload,
            )
            self.session.commit()
            updated += len(payload)
            logger.info("value_num 回填进度：本批 %d，累计 %d", len(payload), updated)
        return updated

    def downsample_to_metric_hourly(
        self, cutoff_days: int = METRIC_DOWNSAMPLE_CUTOFF_DAYS
    ) -> int:
        """将 >cutoff_days 天的指标明细按小时聚合写入 hourly 表（幂等 upsert）。仅 MySQL。

        [WARN] SELECT **必须** ``JOIN devices``：源表 ``device_metric_timeseries`` 是
        分区表（MySQL 8.4 分区表不可有外键，error 1506）⇒ 设备删除后残留的孤儿行
        **没有数据库兜底**；而目标表有外键 ⇒ 只要存在**一行**孤儿，整条 INSERT 就以
        1452 失败 ⇒ **归档链永久中断**（与探测侧同一形态，见
        ``MonitorTimeseriesRepository.downsample_to_hourly``）。

        [WARN] 四个不可省的取舍（照抄探测侧聚合会错）：
        ① 聚合键**含 index_key** —— 跨实例平均是**错语义**不是精度损失；
        ② ``state_changes`` + ``last_value`` —— 否则"一小时内 up→down→up"
           降采样后**静默消失**；
        ③ min/max/avg 允许 NULL —— 非数值指标整桶 NULL；
        ④ ``breach_count`` / ``worst_severity`` —— 明细缩期后唯一能回答
           "这段时间是否告警过"。

        **按天分批**：源表 22M 行 / 3.7 GB，一次性聚合会产生超大事务与 undo；
        分批后每批一个事务，中断可续跑（upsert 幂等）。
        """
        if not self._is_mysql():
            return 0
        cutoff = now_utc_naive() - timedelta(days=cutoff_days)
        cutoff_s = cutoff.strftime("%Y-%m-%d %H:%M:%S")

        days = [
            r[0]
            for r in self.session.execute(
                text(
                    """
                    SELECT DISTINCT DATE(t.collected_at)
                    FROM device_metric_timeseries t
                    JOIN devices d ON d.id = t.device_id
                    WHERE t.collected_at < :cutoff
                    ORDER BY 1
                    """
                ),
                {"cutoff": cutoff_s},
            ).fetchall()
        ]
        total = 0
        for day in days:
            day_start = f"{day} 00:00:00"
            day_end = f"{day} 23:59:59"
            result = self.session.execute(
                text(_UPSERT_METRIC_HOURLY_SQL),
                {"day_start": day_start, "day_end": day_end},
            )
            self.session.commit()
            total += int(result.rowcount or 0)
        return total

    def downsample_to_metric_daily(
        self, cutoff_days: int = METRIC_DAILY_DOWNSAMPLE_CUTOFF_DAYS
    ) -> int:
        """将 >cutoff_days 天的 hourly 数据按天聚合写入 daily 表（幂等 upsert）。仅 MySQL。

        源表是 hourly（**有外键**，设备删除时 CASCADE 回收）⇒ 孤儿在上一层就被
        挡掉了，这里**不需要**再 JOIN devices（与探测侧 downsample_to_daily 同理）。
        """
        if not self._is_mysql():
            return 0
        cutoff = now_utc_naive() - timedelta(days=cutoff_days)
        result = self.session.execute(
            text(_UPSERT_METRIC_DAILY_SQL),
            {"cutoff": cutoff.strftime("%Y-%m-%d %H:%M:%S")},
        )
        self.session.commit()
        return int(result.rowcount or 0)

    def cleanup_metric_hourly(self, retention_days: int = METRIC_HOURLY_RETENTION_DAYS) -> int:
        """清理 hourly 表中 >retention_days 天的数据（跨方言）。"""
        cutoff = now_utc_naive() - timedelta(days=retention_days)
        deleted = (
            self.session.query(DeviceMetricTimeseriesHourly)
            .filter(DeviceMetricTimeseriesHourly.hour_bucket < cutoff)
            .delete(synchronize_session=False)
        )
        self.session.commit()
        return int(deleted)

    def cleanup_metric_daily(self, retention_days: int = METRIC_DAILY_RETENTION_DAYS) -> int:
        """清理 daily 表中 >retention_days 天的数据（跨方言）。

        day_bucket 由 UTC 时间聚合产出（collected_at 已是 UTC），故 cutoff 取
        UTC 日历日；用本地日会提前 1 个偏移删除有效桶（与探测侧 daily 同理）。
        """
        from app.utils.time_utils import utc_today

        cutoff = utc_today() - timedelta(days=retention_days)
        deleted = (
            self.session.query(DeviceMetricTimeseriesDaily)
            .filter(DeviceMetricTimeseriesDaily.day_bucket < cutoff)
            .delete(synchronize_session=False)
        )
        self.session.commit()
        return int(deleted)


    def list_rollup(
        self,
        device_id: int,
        metric_key: str,
        index_key: Optional[str] = None,
        from_: Optional[datetime] = None,
        to: Optional[datetime] = None,
        granularity: str = "auto",
        limit: int = 5000,
    ) -> List[MetricRollupPoint]:
        """读聚合层（hourly / daily），返回**行 DTO** 列表。

        这是 B1 ④ 重新定义后的形态（计划文档 §2 B1 改判）：不是给趋势图加
        "窗口超过明细保留期 ⇒ 读聚合"的分支 —— Q1 拍板明细留 90 天后，那个分支
        **永远为假**，写出来就是死代码。它面向的是两件真会发生的事：

        1. **730 天长周期查询**：超出 hourly(90d)、更远超明细(90d)，只能读 daily；
        2. **AI 故障预测批读特征**：要的是长窗口的统计特征，DTO 上直接给
           ``variance()`` / ``stdev()``（由 ``sum_sq`` 合成，**不必回源明细**）。

        Args:
            device_id: 设备 ID
            metric_key: 指标 key
            index_key: 指标实例索引；``None`` = **该指标的全部实例，逐实例各返回
                一条**（刻意**不做**跨实例合并 —— 跨实例平均是错语义）
            from_ / to: 窗口（桶起点落在窗口内）；``to`` 缺省 now
            granularity: ``"auto"`` / ``"hour"`` / ``"day"``。显式值优先于自动选择
                （escape hatch：明确要小时粒度时即便数据不全也照读）
            limit: 最多返回行数（默认 5000，上限 50000）

        Returns:
            ``[MetricRollupPoint, ...]``，按 ``bucket_start``、``index_key`` 升序。
        """
        to = to or now_utc_naive()
        if granularity in (GRANULARITY_HOUR, GRANULARITY_DAY):
            gran = granularity
        else:
            gran = choose_rollup_granularity(from_, to)

        if gran == GRANULARITY_HOUR:
            model = DeviceMetricTimeseriesHourly
            bucket_col = DeviceMetricTimeseriesHourly.hour_bucket
            bucket_attr = "hour_bucket"
        else:
            model = DeviceMetricTimeseriesDaily
            bucket_col = DeviceMetricTimeseriesDaily.day_bucket
            bucket_attr = "day_bucket"

        if from_ is not None and gran == GRANULARITY_DAY:
            daily_floor = now_utc_naive() - timedelta(days=METRIC_DAILY_RETENTION_DAYS)
            if from_ < daily_floor:
                logger.warning(
                    "list_rollup: from_=%s 早于 daily 保留窗（%d 天），"
                    "该段数据已被清理，返回的是窗口后半段",
                    from_,
                    METRIC_DAILY_RETENTION_DAYS,
                )

        conditions = [
            model.device_id == device_id,
            model.metric_key == metric_key,
            bucket_col <= to,
        ]
        if index_key is not None:
            conditions.append(model.index_key == index_key)
        if from_ is not None:
            conditions.append(bucket_col >= from_)

        limit = max(1, min(int(limit), 50000))
        rows = (
            self.session.query(model)
            .filter(and_(*conditions))
            .order_by(bucket_col.asc(), model.index_key.asc())
            .limit(limit)
            .all()
        )
        return [
            MetricRollupPoint(
                device_id=r.device_id,
                metric_key=r.metric_key,
                index_key=r.index_key,
                bucket_start=getattr(r, bucket_attr),
                granularity=gran,
                avg_value=r.avg_value,
                min_value=r.min_value,
                max_value=r.max_value,
                sample_count=r.sample_count,
                sum_sq=r.sum_sq,
                numeric_count=r.numeric_count,
                last_value=r.last_value,
                state_changes=r.state_changes,
                breach_count=r.breach_count,
                worst_severity=r.worst_severity,
            )
            for r in rows
        ]
