# -*- coding: utf-8 -*-
"""DeviceMonitorStatus 仓储

提供原子 upsert（MySQL INSERT ... ON DUPLICATE KEY UPDATE），
避免并发探测（monitor_worker）与手动 POST /check 触发之间的非原子先查后写丢更新。
"""
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import case, func
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.models.device import Device
from app.models.device_monitor_status import DeviceMonitorStatus
from app.persistence.base import SQLAlchemyRepository


class DeviceMonitorStatusRepository(SQLAlchemyRepository):

    def __init__(self, session=None):
        super().__init__(DeviceMonitorStatus, session)

    def upsert(self, **fields) -> None:
        if self.session.get_bind().dialect.name == "mysql":
            stmt = mysql_insert(DeviceMonitorStatus).values(**fields)
            update_fields = {k: stmt.inserted[k] for k in fields if k != "device_id"}
            stmt = stmt.on_duplicate_key_update(**update_fields)
            self.session.execute(stmt)
        else:
            existing = self.find_by_device(fields["device_id"])
            if existing is None:
                obj = DeviceMonitorStatus(**fields)
                self.session.add(obj)
            else:
                for k, v in fields.items():
                    if k != "device_id":
                        setattr(existing, k, v)
            self.session.flush()

    def find_by_device(self, device_id: int) -> Optional[DeviceMonitorStatus]:
        return (
            self.session.query(DeviceMonitorStatus)
            .filter(DeviceMonitorStatus.device_id == device_id)
            .first()
        )

    def find_by_device_ids(self, device_ids: list) -> dict:
        if not device_ids:
            return {}
        rows = (
            self.session.query(DeviceMonitorStatus)
            .filter(DeviceMonitorStatus.device_id.in_(device_ids))
            .all()
        )
        return {r.device_id: r for r in rows}

    def mark_stale(self, device_id: int) -> None:
        self.session.query(DeviceMonitorStatus).filter(
            DeviceMonitorStatus.device_id == device_id
        ).delete(synchronize_session=False)
        self.session.flush()

    def mark_stale_batch(self, device_ids: "list[int]") -> int:
        if not device_ids:
            return 0
        deleted = (
            self.session.query(DeviceMonitorStatus)
            .filter(DeviceMonitorStatus.device_id.in_(device_ids))
            .delete(synchronize_session=False)
        )
        self.session.flush()
        return int(deleted)


    def overview_stats(self, failure_threshold: int = 2) -> Dict[str, Any]:
        reachable_true = case((DeviceMonitorStatus.reachable.is_(True), 1), else_=0)
        down_alerted_true = case(
            (DeviceMonitorStatus.reachable.is_(False)
             & DeviceMonitorStatus.down_alerted.is_(True), 1),
            else_=0,
        )
        flapping = case(
            (DeviceMonitorStatus.reachable.is_(False)
             & DeviceMonitorStatus.down_alerted.is_(False)
             & (DeviceMonitorStatus.consecutive_failures > 0), 1),
            else_=0,
        )
        never_reachable = case(
            (DeviceMonitorStatus.ever_reachable.is_(False), 1), else_=0,
        )

        row = (
            self.session.query(
                func.count().label("total"),
                func.sum(reachable_true).label("reachable"),
                func.sum(down_alerted_true).label("unreachable"),
                func.sum(flapping).label("flapping"),
                func.sum(never_reachable).label("never_reachable"),
            )
            .select_from(DeviceMonitorStatus)
            .join(Device, Device.id == DeviceMonitorStatus.device_id)
            .filter(Device.deleted_at.is_(None))
            .one()
        )

        blindspot_q = (
            self.session.query(func.count())
            .select_from(DeviceMonitorStatus)
            .join(Device, Device.id == DeviceMonitorStatus.device_id)
            .filter(Device.deleted_at.is_(None))
            .filter(DeviceMonitorStatus.extra["alert_blindspot_at"].isnot(None))
        )
        blindspot = blindspot_q.scalar() or 0

        return {
            "total_monitored": row.total or 0,
            "reachable": int(row.reachable or 0),
            "unreachable": int(row.unreachable or 0),
            "flapping": int(row.flapping or 0),
            "never_reachable": int(row.never_reachable or 0),
            "alert_blindspot": int(blindspot),
        }

    def distribution_by_protocol(self) -> Dict[str, int]:
        rows = (
            self.session.query(
                DeviceMonitorStatus.protocol,
                func.count(),
            )
            .select_from(DeviceMonitorStatus)
            .join(Device, Device.id == DeviceMonitorStatus.device_id)
            .filter(Device.deleted_at.is_(None))
            .group_by(DeviceMonitorStatus.protocol)
            .all()
        )
        return {proto: cnt for proto, cnt in rows if proto}

    def distribution_by_device_type(self) -> Dict[str, int]:
        rows = (
            self.session.query(
                Device.device_type,
                func.count(),
            )
            .select_from(DeviceMonitorStatus)
            .join(Device, Device.id == DeviceMonitorStatus.device_id)
            .filter(Device.deleted_at.is_(None))
            .group_by(Device.device_type)
            .all()
        )
        return {dtype: cnt for dtype, cnt in rows if dtype}

    def recent_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        from app.models.device_hardware import DeviceHardware
        from sqlalchemy import case, func

        display_ip = func.coalesce(
            case(
                (Device.device_type == "server", DeviceHardware.ipmi_address),
                else_=Device.management_ip,
            ),
            Device.management_ip,
        )

        rows = (
            self.session.query(
                DeviceMonitorStatus.device_id,
                Device.device_name,
                Device.device_type,
                display_ip.label("management_ip"),
                DeviceMonitorStatus.protocol,
                DeviceMonitorStatus.down_episode,
                DeviceMonitorStatus.consecutive_failures,
                DeviceMonitorStatus.last_checked_at,
                DeviceMonitorStatus.extra,
            )
            .select_from(DeviceMonitorStatus)
            .join(Device, Device.id == DeviceMonitorStatus.device_id)
            .outerjoin(DeviceHardware, DeviceHardware.device_id == Device.id)
            .filter(Device.deleted_at.is_(None))
            .filter(DeviceMonitorStatus.down_alerted.is_(True))
            .order_by(DeviceMonitorStatus.last_checked_at.desc())
            .limit(limit)
            .all()
        )
        result: List[Dict[str, Any]] = []
        for r in rows:
            extra = r.extra or {}
            result.append({
                "device_id": r.device_id,
                "device_name": r.device_name,
                "device_type": r.device_type,
                "management_ip": r.management_ip,
                "protocol": r.protocol,
                "episode": r.down_episode,
                "consecutive_failures": r.consecutive_failures,
                "last_checked_at": r.last_checked_at.isoformat() + "Z" if r.last_checked_at else None,
                "last_alerted_at": extra.get("last_alerted_at"),
                "re_alert_seq": extra.get("re_alert_seq", 0),
                "alert_blindspot": bool(extra.get("alert_blindspot_at")),
            })
        return result


    def list_with_device(
        self,
        status_filter: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        device_ids: Optional[List[int]] = None,
        keyword: Optional[str] = None,
    ) -> Tuple[int, List[Dict[str, Any]]]:
        from app.models.device_hardware import DeviceHardware
        from sqlalchemy import case, func, or_

        display_ip = func.coalesce(
            case(
                (Device.device_type == "server", DeviceHardware.ipmi_address),
                else_=Device.management_ip,
            ),
            Device.management_ip,
        )

        q = (
            self.session.query(
                DeviceMonitorStatus.device_id,
                Device.device_name,
                Device.device_type,
                display_ip.label("management_ip"),
                DeviceMonitorStatus.protocol,
                DeviceMonitorStatus.reachable,
                DeviceMonitorStatus.ever_reachable,
                DeviceMonitorStatus.down_alerted,
                DeviceMonitorStatus.down_episode,
                DeviceMonitorStatus.consecutive_failures,
                DeviceMonitorStatus.latency_ms,
                DeviceMonitorStatus.last_checked_at,
                DeviceMonitorStatus.last_reachable_at,
                DeviceMonitorStatus.last_unreachable_at,
                DeviceMonitorStatus.last_error,
                DeviceMonitorStatus.monitor_enabled,
                DeviceMonitorStatus.extra,
            )
            .select_from(DeviceMonitorStatus)
            .join(Device, Device.id == DeviceMonitorStatus.device_id)
            .outerjoin(DeviceHardware, DeviceHardware.device_id == Device.id)
            .filter(Device.deleted_at.is_(None))
        )

        if keyword:
            kw = f"%{keyword.strip()}%"
            q = q.filter(
                or_(
                    Device.device_name.ilike(kw),
                    Device.management_ip.ilike(kw),
                    DeviceHardware.ipmi_address.ilike(kw),
                )
            )

        if status_filter == "unreachable":
            q = q.filter(
                DeviceMonitorStatus.reachable.is_(False),
                DeviceMonitorStatus.down_alerted.is_(True),
            )
        elif status_filter == "flapping":
            q = q.filter(
                DeviceMonitorStatus.reachable.is_(False),
                DeviceMonitorStatus.down_alerted.is_(False),
                DeviceMonitorStatus.consecutive_failures > 0,
            )
        elif status_filter == "blindspot":
            q = q.filter(DeviceMonitorStatus.extra["alert_blindspot_at"].isnot(None))
        if device_ids:
            q = q.filter(DeviceMonitorStatus.device_id.in_(device_ids))

        total = q.count()
        rows = (
            q.order_by(
                DeviceMonitorStatus.monitor_enabled.desc(),
                DeviceMonitorStatus.last_checked_at.desc(),
            )
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        items: List[Dict[str, Any]] = []
        for r in rows:
            extra = r.extra or {}
            items.append({
                "device_id": r.device_id,
                "device_name": r.device_name,
                "device_type": r.device_type,
                "management_ip": r.management_ip,
                "protocol": r.protocol,
                "reachable": r.reachable,
                "ever_reachable": r.ever_reachable,
                "down_alerted": r.down_alerted,
                "down_episode": r.down_episode,
                "consecutive_failures": r.consecutive_failures,
                "latency_ms": r.latency_ms,
                "last_checked_at": r.last_checked_at.isoformat() + "Z" if r.last_checked_at else None,
                "last_reachable_at": r.last_reachable_at.isoformat() + "Z" if r.last_reachable_at else None,
                "last_unreachable_at": r.last_unreachable_at.isoformat() + "Z" if r.last_unreachable_at else None,
                "last_error": r.last_error,
                "monitor_enabled": r.monitor_enabled,
                "alert_blindspot": bool(extra.get("alert_blindspot_at")),
            })
        return total, items
