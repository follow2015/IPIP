# -*- coding: utf-8 -*-
"""AI 诊断会话仓库（AIDiagnosisSessionRepository）

B-44 收敛：诊断会话的取数原先散在 `diagnosis_session_service` 与
`incident_context` 里直用 `db.session.query(...)`（5 处），现统一收进本仓储。

口径说明（无软删除）：`AIDiagnosisSession` 继承 `BaseModel` 但未开启
``__soft_delete__``，故不走 `_base_query()`；**留痕保留语义**由"行留存 +
`device_id` 置空"表达（迁移 0015），不是软删除列。
"""
from typing import List, Optional

from sqlalchemy import or_

from extensions import db
from app.models.ai_diagnosis_session import AIDiagnosisSession

FINISHED_STATUSES = ("completed", "incomplete")


class AIDiagnosisSessionRepository:
    """AI 诊断会话仓库"""

    def __init__(self, session=None):
        self.session = session or db.session

    def snapshot_device_trace(self, device_id: int, device_name) -> int:
        """把诊断会话的设备引用置空并写设备名快照（B-44 收敛：留痕处置）。

        诊断会话是 token 换来的知识资产，**保留不删** —— 设备行被物理删除后
        靠快照列自证（迁移 0015 语义）。
        """
        return (
            self.session.query(AIDiagnosisSession)
            .filter(AIDiagnosisSession.device_id == device_id)
            .update(
                {
                    AIDiagnosisSession.device_name: device_name,
                    AIDiagnosisSession.device_id: None,
                },
                synchronize_session=False,
            )
        )

    def snapshot_device_trace_batch(self, rows) -> None:
        """批量处置诊断会话的设备引用（Core 表更新 + executemany）。

        理由同 ``IncidentRepository.snapshot_root_trace_batch``；会话保留（知识资产）。
        """
        from sqlalchemy import bindparam, update

        table = AIDiagnosisSession.__table__
        self.session.execute(
            update(table)
            .where(table.c["device_id"] == bindparam("_device_id"))
            .values(device_name=bindparam("_device_name"), device_id=None),
            rows,
        )

    def count_running(self, incident_id: int) -> int:
        """统计该事件名下**进行中**的诊断会话数。

        只取 ``id`` 列计数（与原实现同形）：本方法只要计数，不必拉整行。
        """
        return (
            self.session.query(AIDiagnosisSession.id)
            .filter(
                AIDiagnosisSession.incident_id == incident_id,
                AIDiagnosisSession.status == "running",
            )
            .count()
        )

    def latest_finished(self, incident_id: int) -> Optional[AIDiagnosisSession]:
        """取该事件**最近一次已完成**的诊断会话（无则 None）。"""
        return (
            self.session.query(AIDiagnosisSession)
            .filter(
                AIDiagnosisSession.incident_id == incident_id,
                AIDiagnosisSession.status.in_(FINISHED_STATUSES),
            )
            .order_by(AIDiagnosisSession.id.desc())
            .first()
        )

    def list_for_user(
        self, visible: Optional[list], device_id: Optional[int], limit: int,
    ) -> List[AIDiagnosisSession]:
        """按数据域取诊断会话（时间倒序 + 限条）。

        ``visible`` 为 ``None`` 表示**不限**（数据域服务异常时的 fail-open 口径，
        由调用方决定）；为列表时按设备域过滤。``device_id`` 为调用方的显式过滤
        （是否在其可见范围内由调用方前置判断，本方法只负责查询）。

        ⚠️ **NULL 行放行**（2026-09-20 实测修复的口径，勿"顺手收紧"）：
        数据域是**设备级**过滤器，而 `device_id IS NULL` 的行**没有设备可过滤**。
        它有两种来源：① 设备已彻底删除（迁移 0015 的保留语义：行留下、
        `device_id` 置空、`device_name` 自证）；② 事件级诊断尚未回填出目标设备
        （`set_device_id` 未命中）。若写成"仅 `device_id IN (visible)`"，
        `NULL NOT IN (...)` 会把这两类行整体吞掉 —— 那正是「留痕留下却在界面上
        看不见」的成因（当时三表 349 行全部读取面为零消费）。任何有 `ai:use`
        的用户都能看到它们，与同级的事件中心（`/api/monitor/incidents` 无数据域
        过滤）口径一致。
        """
        query = self.session.query(AIDiagnosisSession)
        if visible is not None:
            query = query.filter(
                or_(
                    AIDiagnosisSession.device_id.in_(list(visible)),
                    AIDiagnosisSession.device_id.is_(None),
                )
            )
        if device_id:
            query = query.filter_by(device_id=device_id)
        return (
            query.order_by(AIDiagnosisSession.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_rollback_failed(self, limit: int) -> List[AIDiagnosisSession]:
        """取回滚失败的会话（时间倒序 + 限条）。

        Phase 4.4：设备滞留"已变更未回滚"的中间态是最危险的状态，不能让运维
        误以为已恢复，故需持续告警。
        """
        return (
            self.session.query(AIDiagnosisSession)
            .filter_by(rollback_failed=True)
            .order_by(AIDiagnosisSession.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_by_device(self, device_id: int, limit: int) -> List[AIDiagnosisSession]:
        """取某设备的历史诊断会话（时间倒序 + 限条）——"上次同样故障怎么修的"。"""
        return (
            self.session.query(AIDiagnosisSession)
            .filter_by(device_id=device_id)
            .order_by(AIDiagnosisSession.created_at.desc())
            .limit(limit)
            .all()
        )
