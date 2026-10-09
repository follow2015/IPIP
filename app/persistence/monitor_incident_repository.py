# -*- coding: utf-8 -*-
"""监控事件仓储

项目 C5 约束：DB 访问必须走 Repository 层，禁止在 Service 内裸写 query。
"""
from datetime import datetime
from typing import List, Optional
from app.utils.time_utils import now_utc_naive


from app.models.monitor_alert_outbox import MonitorAlertOutbox
from app.models.monitor_incident import MonitorIncident
from app.models.monitor_suppressed_alert_log import MonitorSuppressedAlertLog
from extensions import db
from sqlalchemy import or_
from app.core.pagination_limits import ensure_offset_within_limit

_LIKE_ESCAPE = "\\"


def _escape_like(value: str) -> str:
    """转义 LIKE 通配符（含转义字符自身，顺序不可颠倒）。"""
    return (
        value.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", _LIKE_ESCAPE + "%")
        .replace("_", _LIKE_ESCAPE + "_")
    )


class IncidentRepository:
    """事件的读写封装"""

    def __init__(self, session=None):
        self.session = session or db.session

    def create(
        self,
        incident_key: str,
        title: str,
        severity: str,
        root_device_id: Optional[int],
        reason_code: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> MonitorIncident:
        """新建事件（alert_count / device_count 从 1 起算）。

        Args:
            now: 事件首末告警时间（测试注入）；None 取当前 UTC 时间。

        创建时一并落 ``root_device_name`` 快照：本列在设备彻底删除前会由
        ``DeviceService.dispose_monitor_trace`` 刷成最终名，但若创建时不写，
        整个"设备还活着"的期间事件列表都只能显示裸 ID —— 而那是绝大多数时间。
        设备不存在时不编造，保持 NULL（读取面回落 ID）。
        """
        ts = now if now is not None else now_utc_naive()
        inc = MonitorIncident(
            incident_key=incident_key,
            title=title,
            severity=severity,
            status="active",
            reason_code=reason_code,
            root_device_id=root_device_id,
            root_device_name=self._device_name_of(root_device_id),
            alert_count=1,
            device_count=1,
            first_alert_at=ts,
            last_alert_at=ts,
        )
        self.session.add(inc)
        self.session.flush()
        return inc

    def _device_name_of(self, device_id: Optional[int]) -> Optional[str]:
        """取设备名用于写快照列；设备不存在时 None。"""
        if not device_id:
            return None
        from app.models.device import Device

        return (
            self.session.query(Device.device_name)
            .filter(Device.id == device_id)
            .scalar()
        ) or None

    def find_active_by_key(self, incident_key: str) -> Optional[MonitorIncident]:
        """按归并键查活跃事件（status != closed）。

        只返回活跃事件：已关闭的事件不应再被新告警命中，否则一起新故障
        会被错误地归到历史事故上。
        """
        return (
            self.session.query(MonitorIncident)
            .filter(
                MonitorIncident.incident_key == incident_key,
                MonitorIncident.status != "closed",
            )
            .order_by(MonitorIncident.id.desc())
            .first()
        )

    def get(self, incident_id: int) -> Optional[MonitorIncident]:
        return self.session.get(MonitorIncident, incident_id)

    def touch(self, incident_id: int, device_id: Optional[int] = None,
              now: Optional[datetime] = None) -> None:
        """事件被新告警命中：累加计数并刷新 last_alert_at。

        Args:
            incident_id: 事件 ID。
            device_id: 本次告警的设备（用于刷新影响设备数）。
            now: 本次告警时间（测试注入）；None 取当前 UTC 时间。
        """
        inc = self.get(incident_id)
        if inc is None:
            return
        inc.alert_count = (inc.alert_count or 0) + 1
        inc.last_alert_at = now if now is not None else now_utc_naive()
        self.session.flush()
        if device_id is not None:
            self.refresh_device_count(incident_id)

    def refresh_device_count(self, incident_id: int) -> int:
        """重算并写回影响设备数。

        影响面 = 根因设备 ∪ 入箱告警涉及的设备 ∪ 被抑制留痕涉及的设备（去重）。

        - 仅靠入箱告警会严重低估影响：一次上游宕机下游 30 台的告警全部
          被依赖抑制、根本没入箱。
        - 必须显式并入 root_device_id：告警入箱与事件关联存在先后顺序，
          刚创建事件时 outbox 行尚未回填 incident_id，若不包含根因设备
          会短暂出现 device_count=0。

        Returns:
            重算后的设备数。
        """
        inc = self.get(incident_id)
        if inc is None:
            return 0

        outbox_q = (
            self.session.query(MonitorAlertOutbox.device_id)
            .filter(
                MonitorAlertOutbox.incident_id == incident_id,
                MonitorAlertOutbox.device_id.isnot(None),
            )
            .distinct()
        )
        log_q = (
            self.session.query(MonitorSuppressedAlertLog.device_id)
            .filter(
                MonitorSuppressedAlertLog.incident_id == incident_id,
                MonitorSuppressedAlertLog.device_id.isnot(None),
            )
            .distinct()
        )
        query = outbox_q.union(log_q)
        count = query.count()
        if inc.root_device_id is not None:
            present = (
                self.session.query(MonitorAlertOutbox.device_id)
                .filter(
                    MonitorAlertOutbox.incident_id == incident_id,
                    MonitorAlertOutbox.device_id == inc.root_device_id,
                )
                .first()
            ) is not None or (
                self.session.query(MonitorSuppressedAlertLog.device_id)
                .filter(
                    MonitorSuppressedAlertLog.incident_id == incident_id,
                    MonitorSuppressedAlertLog.device_id == inc.root_device_id,
                )
                .first()
            ) is not None
            if not present:
                count += 1
        inc.device_count = count
        self.session.flush()
        return count

    def close(self, incident_id: int) -> None:
        """关闭事件（不再被新告警命中）。"""
        inc = self.get(incident_id)
        if inc is None:
            return
        inc.status = "closed"
        inc.closed_at = now_utc_naive()
        self.session.flush()

    def close_by_key(self, incident_key: str, now: Optional[datetime] = None) -> int:
        """关闭该归并键下的**全部**活跃事件，返回关闭条数。

        用于「条件已解除」路径（连通性恢复 / 指标恢复通知），是事件生命周期的
        闭合端：``aggregate_alert`` 建/续事件，本方法关事件。

        用批量 UPDATE 而非 ``close()`` 逐条：
        - ``find_active_by_key`` 只取最新一条，真库曾出现同键多条活跃行
          （聚合器竞态 / 人工干预），逐条关会留下半开状态；
        - 恢复发生在探测热路径上，一次 UPDATE 比"查-改-flush"更省往返。

        ``synchronize_session="evaluate"``（而非 ``False``）：恢复通知与事件聚合
        可能在同一事务内已加载过该事件行，用 False 会让会话里留着 status='active'
        的旧对象 —— 后续若有人读它就会看到"已是活跃"的假象。evaluate 在 Python 侧
        按同一条件同步**已加载**的属性（无额外 SQL）。

        [WARN] 同步只覆盖已加载的属性：``closed_at`` 这类尚未加载过的列不会被填，
        对象上读到的仍是 None，直到会话刷新/过期。真值在 DB —— 本仓同类场景
        （``set_diagnosis_backfill``）也是这个口径，读侧必须以库为准。
        commit 由调用方收口。

        Args:
            incident_key: 归并键（``{alert_type}:{device_id}``）。
            now: 关闭时间（测试注入）；None 取当前 UTC（naive，与列一致）。
        """
        ts = now if now is not None else now_utc_naive()
        return (
            self.session.query(MonitorIncident)
            .filter(
                MonitorIncident.incident_key == incident_key,
                MonitorIncident.status != "closed",
            )
            .update({"status": "closed", "closed_at": ts},
                    synchronize_session="evaluate")
        )

    def close_stale_active(
        self, older_than: datetime, limit: int = 500, now: Optional[datetime] = None,
    ) -> int:
        """关闭 ``last_alert_at`` 早于 ``older_than`` 的活跃事件（停滞清扫）。

        返回关闭条数；上限 ``limit`` 保证单轮工作量有界（真库积压几百条时
        一轮扫完，不会因 UPDATE 长时间持锁阻塞告警写入）。

        先取 id 再按 id 批量 UPDATE，而不是 ``UPDATE ... LIMIT``：MySQL 与
        SQLite 对 ``UPDATE ... ORDER BY ... LIMIT`` 的支持不一致，SQLAlchemy
        的 ``Query.update()`` 也不接受 limit/order_by。两步走跨方言一致。

        同步策略同 ``close_by_key``（evaluate）：只同步已加载属性；``closed_at``
        未加载时对象上读到 None，真值在 DB。

        Args:
            older_than: 停滞判据（naive UTC，与 ``last_alert_at`` 列同口径）。
            limit: 单次最多关闭条数。
            now: 写入 ``closed_at`` 的时间（测试注入）；None 取当前 UTC。
        """
        ids = [
            row[0]
            for row in (
                self.session.query(MonitorIncident.id)
                .filter(
                    MonitorIncident.status != "closed",
                    MonitorIncident.last_alert_at < older_than,
                )
                .order_by(MonitorIncident.id.asc())
                .limit(limit)
                .all()
            )
        ]
        if not ids:
            return 0
        ts = now if now is not None else now_utc_naive()
        return (
            self.session.query(MonitorIncident)
            .filter(MonitorIncident.id.in_(ids))
            .update({"status": "closed", "closed_at": ts},
                    synchronize_session="evaluate")
        )

    def close_recovered_connectivity(
        self, alert_type: str, limit: int = 500, now: Optional[datetime] = None,
    ) -> int:
        """自愈：关闭「设备当前被监控且可达」的连通性问题事件，返回关闭条数。

        为什么需要（2026-10-08 现场实例）：恢复通知只在**探测到恢复的那一刻**
        发出并关闭事件；若那一刻进程正在重启/维护静默，这条转移就永久丢了 ——
        实测设备 107 在 02:45:45 恢复、而新代码 02:48 才生效，事件从此挂在
        active。仅靠"停滞清扫"要等满 24h 才收敛，期间"未关闭事件"数字是假的。

        判据刻意收紧到"**在监控**（monitor_enabled=1）**且可达**"：
        - 暂停探测的设备快照可能是陈旧的 reachable=True（设备实际已宕），
          不能据此断言恢复 —— 它们由停滞清扫兜底；
        - 无状态行的设备无从判断，跳过。
        仅针对连通性问题键（``{alert_type}:`` 前缀）：指标类事件的可达性
        与"指标是否恢复"无关，不能顺手关掉。

        Args:
            alert_type: 连通性问题侧告警类型（如 ``device_unreachable``）。
            limit: 单次最多关闭条数。
            now: 关闭时间（测试注入）；None 取当前 UTC。

        Returns:
            关闭条数（0 = 没有需要自愈的事件）。
        """
        from app.models.device_monitor_status import DeviceMonitorStatus

        ids = [
            row[0]
            for row in (
                self.session.query(MonitorIncident.id)
                .join(
                    DeviceMonitorStatus,
                    DeviceMonitorStatus.device_id == MonitorIncident.root_device_id,
                )
                .filter(
                    MonitorIncident.status != "closed",
                    MonitorIncident.incident_key.startswith(
                        f"{alert_type}:", autoescape=True,
                    ),
                    DeviceMonitorStatus.monitor_enabled.is_(True),
                    DeviceMonitorStatus.reachable.is_(True),
                )
                .order_by(MonitorIncident.id.asc())
                .limit(limit)
                .all()
            )
        ]
        if not ids:
            return 0
        ts = now if now is not None else now_utc_naive()
        return (
            self.session.query(MonitorIncident)
            .filter(MonitorIncident.id.in_(ids))
            .update({"status": "closed", "closed_at": ts},
                    synchronize_session="evaluate")
        )

    def set_diagnosis_backfill(
        self, incident_id: int, session_id: int, summary: Optional[str],
    ) -> int:
        """把诊断结论回填到事件行（B-44 收敛；诊断会话完成时调用）。

        [WARN] 刻意用 **Core UPDATE 而非改 ORM 对象**：事件行的 ``last_alert_at``
        等字段被聚合器高频写入，把行加载进会话后回写会与聚合器的并发更新
        互相覆盖（原实现即如此，注释保留）。`synchronize_session=False`：
        本会话不需要这些行的最新内存态。

        Returns:
            int: 更新行数（0 = 事件已被删/不存在）
        """
        return (
            self.session.query(MonitorIncident)
            .filter(MonitorIncident.id == incident_id)
            .update(
                {
                    "ai_diagnosis_session_id": session_id,
                    "ai_diagnosis_summary": summary,
                },
                synchronize_session=False,
            )
        )

    def snapshot_root_trace(self, device_id: int, device_name) -> int:
        """把根因设备引用置空并写设备名快照（B-44 收敛：设备彻底删的留痕处置）。

        [WARN] **Core UPDATE 而非改 ORM 对象**，且快照与置空**必须同一语句**：
        只置空不写快照 = "行还在、却不知是哪台设备"的孤儿留痕（迁移 0015
        的 ``*_device_name`` 列就是为这个自证而生）。
        ``synchronize_session=False``：本会话不需要这些行的内存态。
        """
        return (
            self.session.query(MonitorIncident)
            .filter(MonitorIncident.root_device_id == device_id)
            .update(
                {
                    MonitorIncident.root_device_name: device_name,
                    MonitorIncident.root_device_id: None,
                },
                synchronize_session=False,
            )
        )

    def snapshot_root_trace_batch(self, rows) -> None:
        """批量把根因设备引用置空并写快照（B-46 批 5：批量处置入口）。

        [WARN] 必须用 **Core 表更新**（``update(model.__table__)``）而非 ORM 实体：
        ``update(Model)`` 的 executemany 走"ORM 按**主键**批量 UPDATE"路径，要求
        每行参数携带主键值；我们的 WHERE 条件是 device_id（非主键），会直接抛
        ``InvalidRequestError: No primary key value supplied``（2026-09-18 实测：
        机房强删 500、整条链路回滚）。Core 表更新无此限制。
        ``rows`` 每项形如 ``{"_device_id": int, "_device_name": str|None}``。
        """
        from sqlalchemy import bindparam, update

        table = MonitorIncident.__table__
        self.session.execute(
            update(table)
            .where(table.c["root_device_id"] == bindparam("_device_id"))
            .values(root_device_name=bindparam("_device_name"), root_device_id=None),
            rows,
        )

    def list_by_root_device(
        self, root_device_id: int, since, limit: Optional[int] = None,
        newest_first: bool = False,
    ) -> List[MonitorIncident]:
        """取该设备作为**根因**的事件（B-44 收敛；时间窗 + 可选限条）

        两个调用点的排序方向与限条不同（AI 时间线**时间升序、不限条**；
        事件上下文**最近优先 + limit**），故分别用 ``newest_first`` / ``limit``
        显式表达（``limit=None`` = 不限，保持原语义）。
        """
        order = (
            MonitorIncident.first_alert_at.desc() if newest_first
            else MonitorIncident.first_alert_at.asc()
        )
        query = (
            self.session.query(MonitorIncident)
            .filter(
                MonitorIncident.root_device_id == root_device_id,
                MonitorIncident.first_alert_at >= since,
            )
            .order_by(order)
        )
        if limit is not None:
            query = query.limit(limit)
        return query.all()


    def _device_name_predicate(self, device_name: str):
        """构造"设备名快照命中"的 SQL 条件（三个快照列的并集）。"""
        pattern = f"%{_escape_like(device_name)}%"
        suppressed_hit = (
            self.session.query(MonitorSuppressedAlertLog.incident_id)
            .filter(
                or_(
                    MonitorSuppressedAlertLog.device_name.ilike(
                        pattern, escape=_LIKE_ESCAPE),
                    MonitorSuppressedAlertLog.upstream_device_name.ilike(
                        pattern, escape=_LIKE_ESCAPE),
                ),
                MonitorSuppressedAlertLog.incident_id.isnot(None),
            )
        )
        return or_(
            MonitorIncident.root_device_name.ilike(pattern, escape=_LIKE_ESCAPE),
            MonitorIncident.id.in_(suppressed_hit),
        )

    def _filtered_query(
        self,
        status: Optional[str] = None,
        device_name: Optional[str] = None,
    ):
        """列表与计数的**共用**查询骨架（保证两者口径恒等）。

        ``status=None`` ⇒ 非 closed（默认列表语义）；显式给值 ⇒ 等值过滤。
        """
        query = self.session.query(MonitorIncident)
        if status:
            query = query.filter(MonitorIncident.status == status)
        else:
            query = query.filter(MonitorIncident.status != "closed")
        if device_name:
            query = query.filter(self._device_name_predicate(device_name))
        return query

    def list_incidents(
        self,
        status: Optional[str] = None,
        device_name: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list:
        """列出事件（按末次告警时间倒序），支持状态 + 设备名快照过滤。"""
        ensure_offset_within_limit(offset)
        return (
            self._filtered_query(status, device_name)
            .order_by(MonitorIncident.last_alert_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def count_incidents(
        self,
        status: Optional[str] = None,
        device_name: Optional[str] = None,
    ) -> int:
        """与 :meth:`list_incidents` **同口径**的总数（供分页 total）。"""
        return self._filtered_query(status, device_name).count()

    def list_active(self, limit: int = 50, offset: int = 0) -> list:
        """列出活跃事件，按末次告警时间倒序。"""
        return self.list_incidents(status=None, device_name=None,
                                   limit=limit, offset=offset)

    def list_by_status(self, status: str, limit: int = 50, offset: int = 0) -> list:
        """按状态列事件（支持显式查 closed）。"""
        return self.list_incidents(status=status, device_name=None,
                                   limit=limit, offset=offset)

    def count_active(self) -> int:
        """活跃事件总数（用于分页 total）。"""
        return self.count_incidents(status=None, device_name=None)

    def count_by_status(self, status: str) -> int:
        """指定状态事件总数（用于分页 total）。"""
        return self.count_incidents(status=status, device_name=None)

    def list_alerts_by_incident(self, incident_id: int, limit: int = 200) -> list:
        """事件关联的入箱告警（按时间倒序，最多 limit 条）。

        Service/Route 层禁止裸查 outbox，统一走此方法。
        """
        return (
            self.session.query(MonitorAlertOutbox)
            .filter(MonitorAlertOutbox.incident_id == incident_id)
            .order_by(MonitorAlertOutbox.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_suppressed_by_incident(self, incident_id: int, limit: int = 200) -> list:
        """事件关联的被抑制下游设备留痕（按时间倒序，最多 limit 条）。"""
        return (
            self.session.query(MonitorSuppressedAlertLog)
            .filter(MonitorSuppressedAlertLog.incident_id == incident_id)
            .order_by(MonitorSuppressedAlertLog.created_at.desc())
            .limit(limit)
            .all()
        )
