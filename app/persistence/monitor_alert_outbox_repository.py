# -*- coding: utf-8 -*-
"""MonitorAlertOutbox 仓储（发件箱读写）

提供 add（入箱）/ find_pending（取待发）/ mark_sent / mark_failed（发件轮询器回写）。
提交决策权交给调用方（apply_result 的 @transactional / 独立 Session，或发件器的会话）。
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import case, func, update as sa_update

from app.models.device import Device
from app.models.device_hardware import DeviceHardware
from app.models.monitor_alert_outbox import MonitorAlertOutbox
from app.persistence.base import SQLAlchemyRepository


def _backoff_seconds(attempts: int) -> int:
    """指数退避间隔：2^attempts 秒，上限 300s（5 分钟）。

    attempts=1 → 2s, 2 → 4s, 3 → 8s, 4 → 16s, 5 → 32s ... 上限 300s。
    """
    return min(2 ** attempts, 300)


def _safe_loads(s: Optional[str]) -> Optional[Any]:
    """安全解析 JSON 字符串，失败返回 None。"""
    if not s:
        return None
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return None


class MonitorAlertOutboxRepository(SQLAlchemyRepository):
    """监控告警发件箱仓储"""

    def __init__(self, session=None):
        super().__init__(MonitorAlertOutbox, session)

    def add(self, device_id: int, alert_type: str, severity: str,
            dedup_key: str, payload: dict) -> MonitorAlertOutbox:
        """入箱一条待发告警（与状态 upsert 同事务提交）。"""
        row = MonitorAlertOutbox(
            device_id=device_id,
            alert_type=alert_type,
            severity=severity,
            dedup_key=dedup_key,
            payload_json=json.dumps(payload, ensure_ascii=False),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def find_pending(self, limit: int = 100) -> List[MonitorAlertOutbox]:
        """按 id 升序取最多 limit 条待发行（先进先出）。

        并发说明（P0-3）：此处**刻意不加** ``FOR UPDATE SKIP LOCKED``。发件器
        ``send_pending`` 为隔离失败行采用「逐行 commit」（见 P8 回归测试），第一次
        commit 就会释放本批次剩余行的行锁，SKIP LOCKED 只能保护到第一行，属于
        「看似安全实则半失效」的写法。进程间互斥改由发件器的 Redis 锁
        ``monitor:lock:outbox`` 提供（见 ``MonitorOutboxSender._acquire_round_lock``），
        与逐行提交语义正交。
        """
        return (
            self.session.query(MonitorAlertOutbox)
            .filter(
                MonitorAlertOutbox.status == "pending",
                (MonitorAlertOutbox.next_retry_at.is_(None))
                | (MonitorAlertOutbox.next_retry_at <= datetime.now(timezone.utc).replace(tzinfo=None)),
            )
            .order_by(MonitorAlertOutbox.id.asc())
            .limit(limit)
            .all()
        )

    def find_unacknowledged_sent(self, limit: int = 200) -> List[MonitorAlertOutbox]:
        """查询已发送但未确认的告警（供 escalation_service 升级扫描使用）。"""
        return (
            self.session.query(MonitorAlertOutbox)
            .filter(
                MonitorAlertOutbox.acknowledged_at.is_(None),
                MonitorAlertOutbox.status == "sent",
            )
            .order_by(MonitorAlertOutbox.created_at.asc())
            .limit(limit)
            .all()
        )

    def mark_sent(self, row_id: int, sent_at) -> None:
        """标记投递成功并累加尝试次数。"""
        row = self.session.get(MonitorAlertOutbox, row_id)
        if row is None:
            return
        row.status = "sent"
        row.sent_at = sent_at
        row.attempts = (row.attempts or 0) + 1
        self.session.flush()

    def mark_failed(self, row_id: int, error: str, max_attempts: int = 5) -> None:
        """标记投递失败：累加尝试次数，设置指数退避 next_retry_at，达上限后置 failed。"""
        row = self.session.get(MonitorAlertOutbox, row_id)
        if row is None:
            return
        row.attempts = (row.attempts or 0) + 1
        row.last_error = (error or "")[:2000]
        if row.attempts >= max_attempts:
            row.status = "failed"
            row.next_retry_at = None  # 已 failed，不再重试
        else:
            row.next_retry_at = (
                datetime.now(timezone.utc).replace(tzinfo=None)
                + timedelta(seconds=_backoff_seconds(row.attempts))
            )
        self.session.flush()


    def list_with_device(
        self,
        alert_type: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        device_id: Optional[int] = None,
        start_date: Optional[Any] = None,
        end_date: Optional[Any] = None,
        page: int = 1,
        per_page: int = 20,
        device_ids: Optional[list] = None,
        metric_key: Optional[str] = None,
        index_key: Optional[str] = None,
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """分页查询告警投递记录（outerjoin devices 取展示字段）。

        device_id 外键为 ON DELETE SET NULL，设备删除后该行 device_id 置空、
        device_name/type/ip 为 None，历史行本身保留，供告警历史页查阅。

        G6: device_ids 为可见设备 ID 集合（非 None 时按集合过滤，None 表示无限制）。
        """
        display_ip = func.coalesce(
            case(
                (Device.device_type == "server", DeviceHardware.ipmi_address),
                else_=Device.management_ip,
            ),
            Device.management_ip,
        )
        q = (
            self.session.query(
                MonitorAlertOutbox.id,
                MonitorAlertOutbox.device_id,
                Device.device_name,
                Device.device_type,
                display_ip.label("management_ip"),
                MonitorAlertOutbox.alert_type,
                MonitorAlertOutbox.severity,
                MonitorAlertOutbox.dedup_key,
                MonitorAlertOutbox.payload_json,
                MonitorAlertOutbox.status,
                MonitorAlertOutbox.attempts,
                MonitorAlertOutbox.last_error,
                MonitorAlertOutbox.created_at,
                MonitorAlertOutbox.sent_at,
                MonitorAlertOutbox.acknowledged_by,
                MonitorAlertOutbox.acknowledged_at,
                MonitorAlertOutbox.ack_note,
                MonitorAlertOutbox.closed_by,
                MonitorAlertOutbox.closed_at,
                MonitorAlertOutbox.close_reason,
            )
            .select_from(MonitorAlertOutbox)
            .outerjoin(Device, Device.id == MonitorAlertOutbox.device_id)
            .outerjoin(DeviceHardware, DeviceHardware.device_id == Device.id)
        )
        if alert_type:
            q = q.filter(MonitorAlertOutbox.alert_type == alert_type)
        if severity:
            q = q.filter(MonitorAlertOutbox.severity == severity)
        if status:
            q = q.filter(MonitorAlertOutbox.status == status)
        if device_id is not None:
            q = q.filter(MonitorAlertOutbox.device_id == device_id)
        if device_ids is not None:
            if not device_ids:
                return 0, []
            q = q.filter(MonitorAlertOutbox.device_id.in_(device_ids))
        if start_date is not None:
            q = q.filter(MonitorAlertOutbox.created_at >= start_date)
        if end_date is not None:
            q = q.filter(MonitorAlertOutbox.created_at <= end_date)
        if metric_key:
            q = q.filter(self._payload_metric_key_filter(metric_key))
        if index_key:
            q = q.filter(self._payload_index_key_filter(index_key))

        page = page or 1
        per_page = per_page or 20
        total = q.count()
        rows = (
            q.order_by(
                MonitorAlertOutbox.created_at.desc(),
                MonitorAlertOutbox.id.desc(),
            )
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        items: List[Dict[str, Any]] = []
        for r in rows:
            items.append({
                "id": r.id,
                "device_id": r.device_id,
                "device_name": r.device_name,
                "device_type": r.device_type,
                "management_ip": r.management_ip,
                "alert_type": r.alert_type,
                "severity": r.severity,
                "dedup_key": r.dedup_key,
                "payload_json": r.payload_json,
                "status": r.status,
                "attempts": r.attempts,
                "last_error": r.last_error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                "acknowledged_by": r.acknowledged_by,
                "acknowledged_at": r.acknowledged_at.isoformat() if r.acknowledged_at else None,
                "ack_note": r.ack_note,
                "closed_by": r.closed_by,
                "closed_at": r.closed_at.isoformat() if r.closed_at else None,
                "close_reason": r.close_reason,
            })
        return total, items

    @staticmethod
    def _payload_metric_key_filter(metric_key: str):
        """P1-7: 按 payload.payload.metric_key 过滤。

        MySQL 8.0+ 用 JSON_EXTRACT；SQLite（测试）无 JSON 函数，回退到 dedup_key LIKE。
        dedup_key 格式：{alert_type}:{device_id}:{metric_key}:{index}:{raise|recover}
        """
        try:
            from extensions import db
            dialect = db.session.bind.dialect.name
        except Exception:
            dialect = "sqlite"
        if dialect == "mysql":
            from sqlalchemy import func
            return func.json_extract(MonitorAlertOutbox.payload_json, "$.payload.metric_key") == metric_key
        return MonitorAlertOutbox.dedup_key.like(f"%:{metric_key}:%")

    @staticmethod
    def _payload_index_key_filter(index_key: str):
        """P1-7: 按 payload.payload.index 过滤。"""
        try:
            from extensions import db
            dialect = db.session.bind.dialect.name
        except Exception:
            dialect = "sqlite"
        if dialect == "mysql":
            from sqlalchemy import func
            return func.json_extract(MonitorAlertOutbox.payload_json, "$.payload.index") == index_key
        return MonitorAlertOutbox.dedup_key.like(f"%:{index_key}:%")

    def get_by_id_with_device(self, alert_id: int) -> Optional[Dict[str, Any]]:
        """P1-6: 查询单条告警详情（含 device 展示字段 + acknowledged_* 完整字段）。

        device_id 外键为 ON DELETE SET NULL，设备删除后 device_* 为 None。
        """
        display_ip = func.coalesce(
            case(
                (Device.device_type == "server", DeviceHardware.ipmi_address),
                else_=Device.management_ip,
            ),
            Device.management_ip,
        )
        r = (
            self.session.query(
                MonitorAlertOutbox.id,
                MonitorAlertOutbox.device_id,
                Device.device_name,
                Device.device_type,
                display_ip.label("management_ip"),
                MonitorAlertOutbox.alert_type,
                MonitorAlertOutbox.severity,
                MonitorAlertOutbox.dedup_key,
                MonitorAlertOutbox.payload_json,
                MonitorAlertOutbox.status,
                MonitorAlertOutbox.attempts,
                MonitorAlertOutbox.last_error,
                MonitorAlertOutbox.created_at,
                MonitorAlertOutbox.sent_at,
                MonitorAlertOutbox.acknowledged_by,
                MonitorAlertOutbox.acknowledged_at,
                MonitorAlertOutbox.ack_note,
            )
            .select_from(MonitorAlertOutbox)
            .outerjoin(Device, Device.id == MonitorAlertOutbox.device_id)
            .outerjoin(DeviceHardware, DeviceHardware.device_id == Device.id)
            .filter(MonitorAlertOutbox.id == alert_id)
            .one_or_none()
        )
        if r is None:
            return None
        return {
            "id": r.id,
            "device_id": r.device_id,
            "device_name": r.device_name,
            "device_type": r.device_type,
            "management_ip": r.management_ip,
            "alert_type": r.alert_type,
            "severity": r.severity,
            "dedup_key": r.dedup_key,
            "payload_json": r.payload_json,
            "payload": _safe_loads(r.payload_json),
            "status": r.status,
            "attempts": r.attempts,
            "last_error": r.last_error,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            "acknowledged_by": r.acknowledged_by,
            "acknowledged_at": r.acknowledged_at.isoformat() if r.acknowledged_at else None,
            "ack_note": r.ack_note,
        }

    def reset_to_pending(self, row_id: int) -> bool:
        """乐观锁重试：仅当 status=='failed' 时重置为 pending 并保留 attempts/last_error。

        返回 True 表示重置成功；若行不存在或已非 failed（被并发重试/已处理）返回 False，
        借此防止并发重试竞态导致的重复投递。

        注意：不清零 attempts，避免无限重试。调用方可通过 max_attempts 参数
        在 mark_failed 中控制重试上限。
        """
        result = self.session.execute(
            sa_update(MonitorAlertOutbox)
            .where(
                MonitorAlertOutbox.id == row_id,
                MonitorAlertOutbox.status == "failed",
            )
            .values(status="pending", last_error=None)
        )
        self.session.flush()
        return result.rowcount > 0

    def acknowledge(self, row_id: int, user: str, note: Optional[str] = None,
                    now=None) -> Optional[MonitorAlertOutbox]:
        """G9: 人工确认/认领告警。

        幂等：已确认的告警再次确认将更新 note 与 acknowledged_at（不阻断重复确认）。
        返回更新后的行；行不存在返回 None。
        """
        from datetime import datetime, timezone
        ts = now if now is not None else datetime.now(timezone.utc).replace(tzinfo=None)
        result = self.session.execute(
            sa_update(MonitorAlertOutbox)
            .where(MonitorAlertOutbox.id == row_id)
            .values(
                acknowledged_by=user,
                acknowledged_at=ts,
                ack_note=note,
            )
        )
        self.session.flush()
        if result.rowcount == 0:
            return None
        return self.session.get(MonitorAlertOutbox, row_id)

    def batch_acknowledge(
        self,
        ids: List[int],
        user: str,
        note: Optional[str] = None,
        now=None,
    ) -> dict:
        """G9 批量确认：对 ids 中的行填充 acknowledged_by/at/note。

        幂等：已确认的行再次确认将刷新 acknowledged_at 与 ack_note。
        返回 {"acknowledged": N, "not_found": M}。
        """
        from datetime import datetime, timezone
        if not ids:
            return {"acknowledged": 0, "not_found": 0}
        ts = now if now is not None else datetime.now(timezone.utc).replace(tzinfo=None)
        result = self.session.execute(
            sa_update(MonitorAlertOutbox)
            .where(MonitorAlertOutbox.id.in_(ids))
            .values(
                acknowledged_by=user,
                acknowledged_at=ts,
                ack_note=note,
            )
        )
        self.session.flush()
        acknowledged = result.rowcount
        return {"acknowledged": acknowledged, "not_found": len(ids) - acknowledged}

    def batch_reset_to_pending(self, ids: List[int]) -> dict:
        """批量乐观锁重试：仅当 status=='failed' 时重置为 pending。

        返回 {"retried": N, "skipped": M}（skipped 含非 failed 行与不存在行）。
        """
        if not ids:
            return {"retried": 0, "skipped": 0}
        result = self.session.execute(
            sa_update(MonitorAlertOutbox)
            .where(
                MonitorAlertOutbox.id.in_(ids),
                MonitorAlertOutbox.status == "failed",
            )
            .values(status="pending", last_error=None)
        )
        self.session.flush()
        retried = result.rowcount
        return {"retried": retried, "skipped": len(ids) - retried}

    def close_alert(self, row_id: int, user: str, reason: Optional[str] = None, now=None) -> Optional[MonitorAlertOutbox]:
        """P2-16: 手动关闭告警。

        幂等：已关闭的告警再次关闭将更新 reason 与 closed_at。
        返回更新后的行；行不存在返回 None。
        """
        from datetime import datetime, timezone
        ts = now if now is not None else datetime.now(timezone.utc).replace(tzinfo=None)
        result = self.session.execute(
            sa_update(MonitorAlertOutbox)
            .where(MonitorAlertOutbox.id == row_id)
            .values(closed_by=user, closed_at=ts, close_reason=reason)
        )
        self.session.flush()
        if result.rowcount == 0:
            return None
        return self.session.get(MonitorAlertOutbox, row_id)

    def batch_close(self, ids: List[int], user: str, reason: Optional[str] = None, now=None) -> dict:
        """P2-16: 批量手动关闭告警。"""
        from datetime import datetime, timezone
        if not ids:
            return {"closed": 0, "not_found": 0}
        ts = now if now is not None else datetime.now(timezone.utc).replace(tzinfo=None)
        result = self.session.execute(
            sa_update(MonitorAlertOutbox)
            .where(MonitorAlertOutbox.id.in_(ids))
            .values(closed_by=user, closed_at=ts, close_reason=reason)
        )
        self.session.flush()
        closed = result.rowcount
        return {"closed": closed, "not_found": len(ids) - closed}

    def find_failed(self, limit: int = 50) -> List[MonitorAlertOutbox]:
        """按 id 升序取最多 limit 条失败行（死信恢复用）。"""
        return (
            self.session.query(MonitorAlertOutbox)
            .filter(MonitorAlertOutbox.status == "failed")
            .order_by(MonitorAlertOutbox.id.asc())
            .limit(limit)
            .all()
        )

    def reset_all_failed(self, max_age_hours: int = 24,
                         max_attempts: int = 5, extra_resets: int = 3) -> int:
        """批量重置超过 max_age_hours 小时的失败行为 pending（死信恢复）。

        M5 修复：增加收敛上限。原实现无条件把**所有** failed 行重置重投，
        webhook URL 配错这类配置型失败的告警每 24h 被永久复活，max_attempts
        语义被击穿，风暴永不收敛。

        现以 `attempts` 字段承载复位预算：只有 attempts < max_attempts +
        extra_resets 的行才允许被复活。每轮「复位→投递失败→mark_failed」都会
        累加 attempts，故最多额外重投 extra_resets 轮（默认 3，即约 3 天），
        之后保持 failed 等待人工处置（模型已有 acknowledged_by/ack_note/
        close_reason 供人工闭环），无需新增数据库列。

        注意：复活行的 attempts 已 >= max_attempts，mark_failed 会立即重新置
        failed——即每轮复位只有**一次**投递机会、无退避重试。
        """
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=max_age_hours)
        result = self.session.execute(
            sa_update(MonitorAlertOutbox)
            .where(
                MonitorAlertOutbox.status == "failed",
                MonitorAlertOutbox.created_at < cutoff,
                MonitorAlertOutbox.attempts < max_attempts + extra_resets,
            )
            .values(status="pending", last_error=None)
        )
        self.session.flush()
        return result.rowcount

    def cleanup_expired(
        self,
        sent_retention_days: int = 30,
        failed_retention_days: int = 90,
        batch_size: int = 1000,
    ) -> dict:
        """批量清理超期 sent/failed 行，避免 outbox 无限增长。

        - sent 行保留 sent_retention_days 天（默认 30）
        - failed 行保留 failed_retention_days 天（默认 90，便于事后排查）
        - 按 created_at 批量 DELETE，每批 batch_size 行，避免长事务锁表
        - pending 行**不清理**（未投递完成）

        返回 {"sent_deleted": N, "failed_deleted": M}。
        """
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        sent_cutoff = now - timedelta(days=sent_retention_days)
        failed_cutoff = now - timedelta(days=failed_retention_days)

        sent_deleted = 0
        failed_deleted = 0

        while True:
            rows = (
                self.session.query(MonitorAlertOutbox.id)
                .filter(
                    MonitorAlertOutbox.status == "sent",
                    MonitorAlertOutbox.created_at < sent_cutoff,
                )
                .order_by(MonitorAlertOutbox.id.asc())
                .limit(batch_size)
                .all()
            )
            if not rows:
                break
            ids = [r.id for r in rows]
            self.session.query(MonitorAlertOutbox).filter(
                MonitorAlertOutbox.id.in_(ids)
            ).delete(synchronize_session=False)
            self.session.flush()
            sent_deleted += len(ids)

        while True:
            rows = (
                self.session.query(MonitorAlertOutbox.id)
                .filter(
                    MonitorAlertOutbox.status == "failed",
                    MonitorAlertOutbox.created_at < failed_cutoff,
                )
                .order_by(MonitorAlertOutbox.id.asc())
                .limit(batch_size)
                .all()
            )
            if not rows:
                break
            ids = [r.id for r in rows]
            self.session.query(MonitorAlertOutbox).filter(
                MonitorAlertOutbox.id.in_(ids)
            ).delete(synchronize_session=False)
            self.session.flush()
            failed_deleted += len(ids)

        return {"sent_deleted": sent_deleted, "failed_deleted": failed_deleted}

    def aggregate_alerts(
        self,
        window_minutes: int = 5,
        start_date=None,
        end_date=None,
        severity: Optional[str] = None,
        only_active: bool = True,
        max_groups: int = 50,
    ) -> List[Dict[str, Any]]:
        """P2-10: 告警聚合 — 按 (alert_type, severity, device_id) 在时间窗口内聚类。

        - window_minutes: 聚类时间窗口（分钟），同一 (type,severity,device) 在窗口内的告警归为一组
        - only_active: 仅聚合未关闭告警（closed_at IS NULL）
        - 返回每组: {alert_type, severity, device_id, device_name, count, first_at, last_at,
                   sample_ids: [最多 5 条], root_device_id}
        - 按 count 降序，最多 max_groups 组
        """
        from datetime import datetime, timedelta

        q = (
            self.session.query(
                MonitorAlertOutbox.alert_type,
                MonitorAlertOutbox.severity,
                MonitorAlertOutbox.device_id,
                Device.device_name,
                func.count(MonitorAlertOutbox.id).label("count"),
                func.min(MonitorAlertOutbox.created_at).label("first_at"),
                func.max(MonitorAlertOutbox.created_at).label("last_at"),
            )
            .select_from(MonitorAlertOutbox)
            .outerjoin(Device, Device.id == MonitorAlertOutbox.device_id)
        )
        if only_active:
            q = q.filter(MonitorAlertOutbox.closed_at.is_(None))
        if start_date is not None:
            q = q.filter(MonitorAlertOutbox.created_at >= start_date)
        if end_date is not None:
            q = q.filter(MonitorAlertOutbox.created_at <= end_date)
        if severity:
            q = q.filter(MonitorAlertOutbox.severity == severity)

        rows = (
            q.group_by(
                MonitorAlertOutbox.alert_type,
                MonitorAlertOutbox.severity,
                MonitorAlertOutbox.device_id,
            )
            .order_by(func.count(MonitorAlertOutbox.id).desc())
            .limit(max_groups)
            .all()
        )

        groups: List[Dict[str, Any]] = []
        for r in rows:
            groups.append(
                {
                    "alert_type": r.alert_type,
                    "severity": r.severity,
                    "device_id": r.device_id,
                    "device_name": r.device_name,
                    "count": int(r.count),
                    "first_at": r.first_at.isoformat() if r.first_at else None,
                    "last_at": r.last_at.isoformat() if r.last_at else None,
                    "window_minutes": window_minutes,
                }
            )

        for g in groups:
            sample_q = self.session.query(MonitorAlertOutbox.id).filter(
                MonitorAlertOutbox.alert_type == g["alert_type"],
                MonitorAlertOutbox.severity == g["severity"],
            )
            if g["device_id"] is not None:
                sample_q = sample_q.filter(MonitorAlertOutbox.device_id == g["device_id"])
            else:
                sample_q = sample_q.filter(MonitorAlertOutbox.device_id.is_(None))
            if only_active:
                sample_q = sample_q.filter(MonitorAlertOutbox.closed_at.is_(None))
            sample = sample_q.order_by(MonitorAlertOutbox.created_at.desc()).limit(5).all()
            g["sample_ids"] = [s.id for s in sample]
            g["root_device_id"] = g["device_id"]

        return groups


    def statistics(
        self,
        start_date=None,
        end_date=None,
        device_id: Optional[int] = None,
        severity: Optional[str] = None,
        bucket: str = "hour",
        top_n: int = 10,
    ) -> Dict[str, Any]:
        """P2-15: 告警多维度统计。

        返回:
        - summary: {total, active, acknowledged, closed, failed}
        - by_severity: [{severity, count}]
        - by_type: [{alert_type, count}]
        - by_status: [{status, count}]
        - mttr_seconds: 平均恢复时间（closed_at - created_at 均值，秒；无关闭告警返回 None）
        - ack_rate: 确认率（acknowledged / total，0~1）
        - close_rate: 关闭率（closed / total，0~1）
        - top_devices: [{device_id, device_name, count}]（Top N 告警设备）
        - top_types: [{alert_type, count}]（Top N 告警类型，与 by_type 同源但限 N）
        - density: [{bucket_start, count}]（按 hour/day 桶的告警密度时序）
        """
        from datetime import datetime, timedelta

        q_base = self.session.query(MonitorAlertOutbox)
        if start_date is not None:
            q_base = q_base.filter(MonitorAlertOutbox.created_at >= start_date)
        if end_date is not None:
            q_base = q_base.filter(MonitorAlertOutbox.created_at <= end_date)
        if device_id is not None:
            q_base = q_base.filter(MonitorAlertOutbox.device_id == device_id)
        if severity:
            q_base = q_base.filter(MonitorAlertOutbox.severity == severity)

        total = q_base.count()
        active = q_base.filter(MonitorAlertOutbox.closed_at.is_(None)).count()
        acknowledged = q_base.filter(MonitorAlertOutbox.acknowledged_at.isnot(None)).count()
        closed = q_base.filter(MonitorAlertOutbox.closed_at.isnot(None)).count()
        failed = q_base.filter(MonitorAlertOutbox.status == "failed").count()

        by_sev_rows = (
            q_base.with_entities(MonitorAlertOutbox.severity, func.count(MonitorAlertOutbox.id))
            .group_by(MonitorAlertOutbox.severity)
            .all()
        )
        by_severity = [{"severity": r[0], "count": int(r[1])} for r in by_sev_rows]

        by_type_rows = (
            q_base.with_entities(MonitorAlertOutbox.alert_type, func.count(MonitorAlertOutbox.id))
            .group_by(MonitorAlertOutbox.alert_type)
            .order_by(func.count(MonitorAlertOutbox.id).desc())
            .all()
        )
        by_type = [{"alert_type": r[0], "count": int(r[1])} for r in by_type_rows]

        by_status_rows = (
            q_base.with_entities(MonitorAlertOutbox.status, func.count(MonitorAlertOutbox.id))
            .group_by(MonitorAlertOutbox.status)
            .all()
        )
        by_status = [{"status": r[0], "count": int(r[1])} for r in by_status_rows]

        mttr_seconds = None
        if closed > 0:
            closed_rows = q_base.filter(MonitorAlertOutbox.closed_at.isnot(None)).with_entities(
                MonitorAlertOutbox.created_at, MonitorAlertOutbox.closed_at
            ).all()
            deltas = [
                (r[1] - r[0]).total_seconds()
                for r in closed_rows
                if r[0] and r[1] and r[1] > r[0]
            ]
            if deltas:
                mttr_seconds = round(sum(deltas) / len(deltas), 2)

        ack_rate = round(acknowledged / total, 4) if total > 0 else 0.0
        close_rate = round(closed / total, 4) if total > 0 else 0.0

        top_dev_rows = (
            q_base.with_entities(
                MonitorAlertOutbox.device_id,
                Device.device_name,
                func.count(MonitorAlertOutbox.id).label("cnt"),
            )
            .outerjoin(Device, Device.id == MonitorAlertOutbox.device_id)
            .group_by(MonitorAlertOutbox.device_id, Device.device_name)
            .order_by(func.count(MonitorAlertOutbox.id).desc())
            .limit(top_n)
            .all()
        )
        top_devices = [
            {"device_id": r[0], "device_name": r[1], "count": int(r[2])}
            for r in top_dev_rows
        ]

        top_types = by_type[:top_n]

        density: List[Dict[str, Any]] = []
        if total > 0:
            if bucket == "day":
                rows = (
                    q_base.with_entities(
                        func.date(MonitorAlertOutbox.created_at).label("b"),
                        func.count(MonitorAlertOutbox.id).label("c"),
                    )
                    .group_by(func.date(MonitorAlertOutbox.created_at))
                    .order_by(func.date(MonitorAlertOutbox.created_at).asc())
                    .all()
                )
                for r in rows:
                    density.append({"bucket_start": str(r[0]), "count": int(r[1])})
            else:
                rows = q_base.with_entities(MonitorAlertOutbox.created_at).all()
                buckets: Dict[str, int] = {}
                for r in rows:
                    if not r[0]:
                        continue
                    dt = r[0]
                    if isinstance(dt, str):
                        dt = datetime.fromisoformat(dt)
                    bucket_key = dt.replace(minute=0, second=0, microsecond=0).isoformat()
                    buckets[bucket_key] = buckets.get(bucket_key, 0) + 1
                density = [
                    {"bucket_start": k, "count": v}
                    for k, v in sorted(buckets.items())
                ]

        return {
            "summary": {
                "total": total,
                "active": active,
                "acknowledged": acknowledged,
                "closed": closed,
                "failed": failed,
            },
            "by_severity": by_severity,
            "by_type": by_type,
            "by_status": by_status,
            "mttr_seconds": mttr_seconds,
            "ack_rate": ack_rate,
            "close_rate": close_rate,
            "top_devices": top_devices,
            "top_types": top_types,
            "density": density,
        }
