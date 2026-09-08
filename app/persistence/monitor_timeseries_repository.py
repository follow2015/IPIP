# -*- coding: utf-8 -*-
"""监控时序仓储（替代 probe_history_repository.py）

写入由 ``MonitorService.apply_result`` 在同一事务内触发（复用传入 session），
查询提供按设备 + 时间范围 + 协议的历史明细（events）与聚合统计（events / hourly）。

分区管理与降采样（DROP PARTITION / INSERT ... ON DUPLICATE）仅 MySQL 生效；
SQLite（测试）经 create_all 建普通表，相关方法按 dialect 守卫为 no-op，
不涉及分区/归档逻辑。
"""
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from app.utils.time_utils import now_utc_naive, utc_today

from sqlalchemy import distinct, func, text

from app.models.device_monitor_probe_events import DeviceMonitorProbeEvents
from app.models.device_monitor_timeseries_hourly import DeviceMonitorTimeseriesHourly
from app.models.device_monitor_timeseries_daily import DeviceMonitorTimeseriesDaily
from app.persistence.base import SQLAlchemyRepository
from app.utils.logging import get_logger

logger = get_logger(__name__)

EVENT_RETENTION_DAYS = 7
HOURLY_RETENTION_DAYS = 90
DAILY_RETENTION_DAYS = 730
PARTITION_FUTURE_DAYS = 5
PARTITION_HISTORY_BUFFER_DAYS = 30
METRIC_RETENTION_DAYS = 90
DOWNSAMPLE_CUTOFF_DAYS = 7
DAILY_DOWNSAMPLE_CUTOFF_DAYS = 30

_PARTITION_NAME_RE = re.compile(r"^p\d{8}$")

_ALLOWED_PARTITION_TABLES = frozenset({
    "device_monitor_probe_events",
    "device_metric_timeseries",
})


def _row_to_dict(r: DeviceMonitorProbeEvents) -> Dict[str, Any]:
    return {
        "id": r.id,
        "device_id": r.device_id,
        "protocol": r.protocol,
        "reachable": r.reachable,
        "latency_ms": r.latency_ms,
        "consecutive_failures": r.consecutive_failures,
        "episode": r.episode,
        "is_alert": r.is_alert,
        "error": r.error,
        "extra": r.extra,
        "probed_at": r.probed_at.isoformat() + "Z" if r.probed_at else None,
        "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
    }


class MonitorTimeseriesRepository(SQLAlchemyRepository):
    """设备监控时序仓储（events 明细 + hourly 预聚合 + 分区/归档管理）"""

    def __init__(self, session=None):
        super().__init__(DeviceMonitorProbeEvents, session)

    def add_event(
        self,
        *,
        device_id: int,
        protocol: str,
        reachable: bool,
        latency_ms: Optional[int],
        consecutive_failures: int,
        episode: int,
        is_alert: bool,
        error: Optional[str],
        extra: Optional[dict],
        probed_at,
    ) -> DeviceMonitorProbeEvents:
        """写入一行探测历史（由调用方事务提交）。"""
        row = DeviceMonitorProbeEvents(
            device_id=device_id,
            protocol=protocol,
            reachable=bool(reachable),
            latency_ms=latency_ms,
            consecutive_failures=int(consecutive_failures or 0),
            episode=int(episode or 0),
            is_alert=bool(is_alert),
            error=error,
            extra=extra,
            probed_at=probed_at,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def list_events(
        self,
        device_id: int,
        from_: Optional[Any] = None,
        to_: Optional[Any] = None,
        protocol: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """返回时间升序的探测历史明细（已序列化为 dict）。"""
        q = self.session.query(DeviceMonitorProbeEvents).filter(
            DeviceMonitorProbeEvents.device_id == device_id
        )
        if protocol:
            q = q.filter(DeviceMonitorProbeEvents.protocol == protocol)
        if from_ is not None:
            q = q.filter(DeviceMonitorProbeEvents.probed_at >= from_)
        if to_ is not None:
            q = q.filter(DeviceMonitorProbeEvents.probed_at <= to_)

        rows = (
            q.order_by(DeviceMonitorProbeEvents.probed_at.asc())
            .limit(int(limit))
            .all()
        )
        return [_row_to_dict(r) for r in rows]

    def aggregate_events(
        self,
        device_id: int,
        from_: Optional[Any] = None,
        to_: Optional[Any] = None,
        protocol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """聚合统计（供趋势卡片）：总数 / 可达 / 不可达 / uptime% / 延迟统计 / 不可达周期数。"""
        M = DeviceMonitorProbeEvents
        q = self.session.query(M).filter(M.device_id == device_id)
        if protocol:
            q = q.filter(M.protocol == protocol)
        if from_ is not None:
            q = q.filter(M.probed_at >= from_)
        if to_ is not None:
            q = q.filter(M.probed_at <= to_)

        total = q.count()
        reachable_count = q.filter(M.reachable.is_(True)).count()
        unreachable_count = total - reachable_count

        lat_q = q.filter(M.reachable.is_(True), M.latency_ms.isnot(None))
        lat_stats = lat_q.with_entities(
            func.avg(M.latency_ms),
            func.min(M.latency_ms),
            func.max(M.latency_ms),
            func.count(M.latency_ms),
        ).one_or_none()
        avg_latency = lat_stats[0] if lat_stats else None
        min_latency = lat_stats[1] if lat_stats else None
        max_latency = lat_stats[2] if lat_stats else None
        lat_count = lat_stats[3] if lat_stats else 0

        p95_latency = None
        if lat_count:
            lat_vals = [
                r[0]
                for r in lat_q.with_entities(M.latency_ms)
                .order_by(M.latency_ms.asc())
                .limit(10000)
                .all()
            ]
            if lat_vals:
                k = max(0, int(round(0.95 * (len(lat_vals) - 1))))
                p95_latency = lat_vals[k]

        down_episodes = (
            q.filter(M.reachable.is_(False), M.is_alert.is_(True))
            .with_entities(func.count(distinct(M.episode)))
            .scalar()
            or 0
        )

        uptime_pct = round(reachable_count / total * 100, 2) if total else None

        return {
            "total": total,
            "reachable": reachable_count,
            "unreachable": unreachable_count,
            "uptime_pct": uptime_pct,
            "avg_latency_ms": float(avg_latency) if avg_latency is not None else None,
            "min_latency_ms": int(min_latency) if min_latency is not None else None,
            "max_latency_ms": int(max_latency) if max_latency is not None else None,
            "p95_latency_ms": int(p95_latency) if p95_latency is not None else None,
            "latency_samples": int(lat_count),
            "down_episodes": int(down_episodes),
        }

    def aggregate_hourly(
        self,
        device_id: int,
        from_: Optional[Any] = None,
        to_: Optional[Any] = None,
        protocol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """从预聚合表聚合（事件分区表已清理的 >90 天窗口）；down_episodes/p95 为近似值。"""
        H = DeviceMonitorTimeseriesHourly
        q = self.session.query(H).filter(H.device_id == device_id)
        if from_ is not None:
            q = q.filter(H.hour_bucket >= from_)
        if to_ is not None:
            q = q.filter(H.hour_bucket <= to_)

        rows = q.all()
        reach = [r for r in rows if r.metric == "reachable"]
        lat = [r for r in rows if r.metric == "latency_ms"]

        total_samples = sum(r.sample_count for r in reach) or 0
        reachable_samples = sum(r.avg_value * r.sample_count for r in reach)
        uptime_pct = (
            round(reachable_samples / total_samples * 100, 2) if total_samples else None
        )

        lat_samples = sum(r.sample_count for r in lat)
        avg_latency = (
            sum(r.avg_value * r.sample_count for r in lat) / lat_samples
            if lat_samples
            else None
        )
        min_latency = min((r.min_value for r in lat), default=None)
        max_latency = max((r.max_value for r in lat), default=None)
        down_hours = sum(1 for r in reach if r.avg_value < 1.0)

        return {
            "total": total_samples,
            "reachable": int(round(reachable_samples)) if total_samples else 0,
            "unreachable": int(round(total_samples - reachable_samples)) if total_samples else 0,
            "uptime_pct": uptime_pct,
            "avg_latency_ms": float(avg_latency) if avg_latency is not None else None,
            "min_latency_ms": int(min_latency) if min_latency is not None else None,
            "max_latency_ms": int(max_latency) if max_latency is not None else None,
            "p95_latency_ms": None,
            "latency_samples": int(lat_samples),
            "down_episodes": int(down_hours),
        }

    def _is_mysql(self) -> bool:
        try:
            bind = self.session.get_bind()
        except Exception:  # noqa: BLE001 - 无法解析绑定时按非 MySQL 降级
            return False
        return bind is not None and bind.dialect.name == "mysql"

    @staticmethod
    def _assert_partition_table(table: str) -> None:
        """校验分区 DDL 的表名属于白名单（DDL 无法参数化，防注入 fail-fast）。"""
        if table not in _ALLOWED_PARTITION_TABLES:
            raise ValueError(
                f"非法分区表名 {table!r}，仅允许 {sorted(_ALLOWED_PARTITION_TABLES)}"
            )

    def _list_partitions(self, table: str) -> List[Tuple[str, Optional[date]]]:
        """返回 [(partition_name, upper_bound_date), ...]；upper_bound_date 为 None 表示兜底分区。"""
        self._assert_partition_table(table)
        rows = self.session.execute(
            text(
                "SELECT PARTITION_NAME, PARTITION_DESCRIPTION "
                "FROM information_schema.PARTITIONS "
                f"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{table}' "
                "AND PARTITION_NAME IS NOT NULL"
            )
        ).fetchall()
        result: List[Tuple[str, Optional[date]]] = []
        for name, desc in rows:
            if name in ("p_before", "p_future") or desc is None:
                result.append((name, None))
                continue
            try:
                result.append((name, date.fromordinal(int(desc) - 366)))
            except (ValueError, TypeError):
                result.append((name, None))
        return result

    def downsample_to_hourly(self, cutoff_days: int = DOWNSAMPLE_CUTOFF_DAYS) -> int:
        """将 >cutoff_days 天的事件数据按小时聚合写入预聚合表（幂等 upsert）。仅 MySQL。"""
        if not self._is_mysql():
            return 0
        cutoff = now_utc_naive() - timedelta(days=cutoff_days)

        self.session.execute(
            text(
                """
                INSERT INTO device_monitor_timeseries_hourly
                    (device_id, metric, hour_bucket, avg_value, min_value, max_value, sample_count)
                SELECT
                    device_id,
                    'reachable',
                    DATE_FORMAT(probed_at, '%Y-%m-%d %H:00:00'),
                    AVG(CASE WHEN reachable THEN 1 ELSE 0 END),
                    AVG(CASE WHEN reachable THEN 1 ELSE 0 END),
                    AVG(CASE WHEN reachable THEN 1 ELSE 0 END),
                    COUNT(*)
                FROM device_monitor_probe_events
                WHERE probed_at < :cutoff
                GROUP BY device_id, DATE_FORMAT(probed_at, '%Y-%m-%d %H:00:00')
                ON DUPLICATE KEY UPDATE
                    avg_value = VALUES(avg_value),
                    min_value = VALUES(min_value),
                    max_value = VALUES(max_value),
                    sample_count = VALUES(sample_count)
                """
            ),
            {"cutoff": cutoff.strftime("%Y-%m-%d %H:%M:%S")},
        )
        self.session.execute(
            text(
                """
                INSERT INTO device_monitor_timeseries_hourly
                    (device_id, metric, hour_bucket, avg_value, min_value, max_value, sample_count)
                SELECT
                    device_id,
                    'latency_ms',
                    DATE_FORMAT(probed_at, '%Y-%m-%d %H:00:00'),
                    AVG(latency_ms),
                    MIN(latency_ms),
                    MAX(latency_ms),
                    COUNT(latency_ms)
                FROM device_monitor_probe_events
                WHERE probed_at < :cutoff AND reachable = 1 AND latency_ms IS NOT NULL
                GROUP BY device_id, DATE_FORMAT(probed_at, '%Y-%m-%d %H:00:00')
                ON DUPLICATE KEY UPDATE
                    avg_value = VALUES(avg_value),
                    min_value = VALUES(min_value),
                    max_value = VALUES(max_value),
                    sample_count = VALUES(sample_count)
                """
            ),
            {"cutoff": cutoff.strftime("%Y-%m-%d %H:%M:%S")},
        )
        self.session.commit()
        return 0

    def drop_expired_event_partitions(
        self, retention_days: int = EVENT_RETENTION_DAYS
    ) -> List[str]:
        """DROP 超过 retention_days 天的事件分区（瞬间完成，无逐行删除开销）。仅 MySQL。"""
        return self._drop_expired_partitions(
            "device_monitor_probe_events", retention_days
        )

    def drop_expired_metric_partitions(
        self, retention_days: int = METRIC_RETENTION_DAYS
    ) -> List[str]:
        """DROP 超过 retention_days 天的指标值时序分区。仅 MySQL。"""
        return self._drop_expired_partitions(
            "device_metric_timeseries", retention_days
        )

    def _drop_expired_partitions(self, table: str, retention_days: int) -> List[str]:
        if not self._is_mysql():
            return []
        self._assert_partition_table(table)
        cutoff = utc_today() - timedelta(days=retention_days)
        dropped: List[str] = []
        for name, ub in self._list_partitions(table):
            if name in ("p_before", "p_future") or ub is None:
                continue
            if ub < cutoff:
                if not _PARTITION_NAME_RE.match(name):
                    logger.warning("跳过非法分区名（防注入）: %s", name)
                    continue
                self.session.execute(
                    text(f"ALTER TABLE {table} DROP PARTITION {name}")
                )
                dropped.append(name)
        if dropped:
            self.session.commit()
        logger.info("dropped partitions of %s: %s", table, dropped)
        return dropped

    def add_future_event_partitions(
        self, future_days: int = PARTITION_FUTURE_DAYS
    ) -> List[str]:
        """预创建未来 future_days 天的事件分区（幂等）。仅 MySQL。"""
        return self._add_future_partitions(
            "device_monitor_probe_events", future_days
        )

    def add_future_metric_partitions(
        self, future_days: int = PARTITION_FUTURE_DAYS
    ) -> List[str]:
        """预创建未来 future_days 天的指标值时序分区（幂等）。仅 MySQL。"""
        return self._add_future_partitions(
            "device_metric_timeseries", future_days
        )

    def _add_future_partitions(self, table: str, future_days: int) -> List[str]:
        """预建未来分区；p_future（MAXVALUE）存在时必须走 REORGANIZE。

        生产教训（2026-09-07 核实）：旧实现用 ADD PARTITION，而初始 DDL 带
        p_future MAXVALUE 兜底分区——MySQL 不允许在 MAXVALUE 分区之后 ADD
        PARTITION，预建自初始分区耗尽日起持续失败，增量数据全部堆入
        p_future（probe_events 实测 12.6 万行）。REORGANIZE 则顺带把
        p_future 存量按新分区边界正确重新落位。

        候选分区从「最后一个日分区的上界日」补建到 today+future_days：
        既覆盖日常滚动（昨日边界=today），也能把长期缺口一次性补齐。
        """
        if not self._is_mysql():
            return []
        self._assert_partition_table(table)
        parts = self._list_partitions(table)
        existing = {n for n, _ in parts}
        has_future = "p_future" in existing
        daily_ubs = [ub for _, ub in parts if ub is not None]
        start_day = max(daily_ubs) if daily_ubs else utc_today()

        wanted = []
        today = utc_today()
        d = start_day
        end = today + timedelta(days=future_days)
        while d <= end:
            pname = f"p{d.strftime('%Y%m%d')}"
            if pname not in existing:
                wanted.append((pname, d))
            d += timedelta(days=1)
        if not wanted:
            return []

        new_defs = []
        for pname, d in wanted:
            if not _PARTITION_NAME_RE.match(pname):
                logger.warning("跳过非法分区名（防注入）: %s", pname)
                continue
            next_d = (d + timedelta(days=1)).isoformat()
            new_defs.append(f"PARTITION {pname} VALUES LESS THAN (TO_DAYS('{next_d}'))")
        if not new_defs:
            return []

        if has_future:
            defs = ",\n    ".join(new_defs + ["PARTITION p_future VALUES LESS THAN MAXVALUE"])
            self.session.execute(
                text(
                    f"ALTER TABLE {table} REORGANIZE PARTITION p_future INTO (\n"
                    f"    {defs}\n)"
                )
            )
        else:
            defs = ",\n    ".join(new_defs)
            self.session.execute(
                text(f"ALTER TABLE {table} ADD PARTITION (\n    {defs}\n)")
            )
        self.session.commit()
        added = [p for p, _ in wanted]
        logger.info("added partitions of %s: %s", table, added)
        return added

    def cleanup_hourly(self, retention_days: int = HOURLY_RETENTION_DAYS) -> int:
        """清理预聚合表中 >retention_days 天的数据（跨方言；SQLite 测试亦可安全执行）。"""
        cutoff = now_utc_naive() - timedelta(days=retention_days)
        deleted = (
            self.session.query(DeviceMonitorTimeseriesHourly)
            .filter(DeviceMonitorTimeseriesHourly.hour_bucket < cutoff)
            .delete(synchronize_session=False)
        )
        self.session.commit()
        return int(deleted)


    def downsample_to_daily(self, cutoff_days: int = DAILY_DOWNSAMPLE_CUTOFF_DAYS) -> int:
        """将 >cutoff_days 天的 hourly 数据按天聚合写入 daily 表（幂等 upsert）。仅 MySQL。

        reachable：当天 24 个小时桶的 avg/min/max（小时可达占比的统计）。
        latency_ms：当天所有小时桶的 avg/min/max。
        """
        if not self._is_mysql():
            return 0
        cutoff = now_utc_naive() - timedelta(days=cutoff_days)

        self.session.execute(
            text(
                """
                INSERT INTO device_monitor_timeseries_daily
                    (device_id, metric, day_bucket, avg_value, min_value, max_value, sample_count)
                SELECT
                    device_id,
                    metric,
                    DATE(hour_bucket),
                    AVG(avg_value),
                    MIN(min_value),
                    MAX(max_value),
                    COUNT(*)
                FROM device_monitor_timeseries_hourly
                WHERE hour_bucket < :cutoff
                GROUP BY device_id, metric, DATE(hour_bucket)
                ON DUPLICATE KEY UPDATE
                    avg_value = VALUES(avg_value),
                    min_value = VALUES(min_value),
                    max_value = VALUES(max_value),
                    sample_count = VALUES(sample_count)
                """
            ),
            {"cutoff": cutoff.strftime("%Y-%m-%d %H:%M:%S")},
        )
        self.session.commit()
        return 0

    def cleanup_daily(self, retention_days: int = DAILY_RETENTION_DAYS) -> int:
        """清理 daily 表中 >retention_days 天的数据（跨方言）。"""
        cutoff = utc_today() - timedelta(days=retention_days)
        deleted = (
            self.session.query(DeviceMonitorTimeseriesDaily)
            .filter(DeviceMonitorTimeseriesDaily.day_bucket < cutoff)
            .delete(synchronize_session=False)
        )
        self.session.commit()
        return int(deleted)
