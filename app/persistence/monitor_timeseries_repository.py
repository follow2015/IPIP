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
DOWNSAMPLE_CUTOFF_DAYS = 7
DAILY_DOWNSAMPLE_CUTOFF_DAYS = 30

_PARTITION_NAME_RE = re.compile(r"^p\d{8}$")


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
        bind = self.session.bind
        return bind is not None and bind.dialect.name == "mysql"

    def _list_event_partitions(self) -> List[Tuple[str, Optional[date]]]:
        rows = self.session.execute(
            text(
                "SELECT PARTITION_NAME, PARTITION_DESCRIPTION "
                "FROM information_schema.PARTITIONS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'device_monitor_probe_events' "
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
        if not self._is_mysql():
            return 0
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=cutoff_days)

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
        if not self._is_mysql():
            return []
        cutoff = date.today() - timedelta(days=retention_days)
        dropped: List[str] = []
        for name, ub in self._list_event_partitions():
            if name in ("p_before", "p_future") or ub is None:
                continue
            if ub < cutoff:
                if not _PARTITION_NAME_RE.match(name):
                    logger.warning("跳过非法分区名（防注入）: %s", name)
                    continue
                self.session.execute(
                    text(f"ALTER TABLE device_monitor_probe_events DROP PARTITION {name}")
                )
                dropped.append(name)
        if dropped:
            self.session.commit()
        logger.info("dropped event partitions: %s", dropped)
        return dropped

    def add_future_event_partitions(
        self, future_days: int = PARTITION_FUTURE_DAYS
    ) -> List[str]:
        if not self._is_mysql():
            return []
        existing = {n for n, _ in self._list_event_partitions()}
        added: List[str] = []
        today = date.today()
        for offset in range(1, future_days + 1):
            d = today + timedelta(days=offset)
            pname = f"p{d.strftime('%Y%m%d')}"
            if pname in existing:
                continue
            if not _PARTITION_NAME_RE.match(pname):
                logger.warning("跳过非法分区名（防注入）: %s", pname)
                continue
            next_d = (d + timedelta(days=1)).isoformat()
            self.session.execute(
                text(
                    f"ALTER TABLE device_monitor_probe_events ADD PARTITION ("
                    f"PARTITION {pname} VALUES LESS THAN (TO_DAYS('{next_d}')))"
                )
            )
            added.append(pname)
        if added:
            self.session.commit()
        logger.info("added event partitions: %s", added)
        return added

    def cleanup_hourly(self, retention_days: int = HOURLY_RETENTION_DAYS) -> int:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=retention_days)
        deleted = (
            self.session.query(DeviceMonitorTimeseriesHourly)
            .filter(DeviceMonitorTimeseriesHourly.hour_bucket < cutoff)
            .delete(synchronize_session=False)
        )
        self.session.commit()
        return int(deleted)


    def downsample_to_daily(self, cutoff_days: int = DAILY_DOWNSAMPLE_CUTOFF_DAYS) -> int:
        if not self._is_mysql():
            return 0
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=cutoff_days)

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
        cutoff = date.today() - timedelta(days=retention_days)
        deleted = (
            self.session.query(DeviceMonitorTimeseriesDaily)
            .filter(DeviceMonitorTimeseriesDaily.day_bucket < cutoff)
            .delete(synchronize_session=False)
        )
        self.session.commit()
        return int(deleted)
