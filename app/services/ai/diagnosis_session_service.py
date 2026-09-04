# -*- coding: utf-8 -*-
"""诊断会话持久化服务。

设计文档第九节：ai_diagnosis_session 表支撑历史回溯、准确率统计。
runner.py 在 run() 开始时创建会话（status=running），结束时更新 final_answer_json/status。
rounds_json 由 runner 每轮追加（或结束时一次性写入，简化实现）。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.models.ai_diagnosis_session import AIDiagnosisSession
from app.utils.logging import get_logger
from extensions import db

logger = get_logger(__name__)


class DiagnosisSessionService:
    """诊断会话 CRUD。"""

    def create_session(
        self,
        device_id: Optional[int],
        user_id: int,
        skill_name: str,
        question: str,
    ) -> int:
        """创建诊断会话（status=running），返回 session_id。"""
        session = AIDiagnosisSession(
            device_id=device_id,
            user_id=user_id,
            skill_name=skill_name,
            question=question,
            status="running",
        )
        db.session.add(session)
        db.session.flush()
        return session.id

    def complete_session(
        self,
        session_id: int,
        rounds: List[Dict[str, Any]],
        final_answer: Any,
        status: str = "completed",
        token_cost: Optional[int] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        """结束诊断会话，写入 rounds_json/final_answer_json/status。

        I9 修复：rounds 入库前逐条脱敏（strip_sensitive_result），
        避免 SSH 回显/设备配置/IP/MAC 等敏感信息落库。
        """
        session = db.session.get(AIDiagnosisSession, session_id)
        if session is None:
            logger.warning("diagnosis session %s not found, skip complete", session_id)
            return
        sanitized_rounds = self._sanitize_rounds(rounds) if rounds else None
        session.rounds_json = json.dumps(sanitized_rounds, ensure_ascii=False) if sanitized_rounds else None
        if isinstance(final_answer, (dict, list)):
            session.final_answer_json = json.dumps(final_answer, ensure_ascii=False)
        elif isinstance(final_answer, str):
            try:
                json.loads(final_answer)
                session.final_answer_json = final_answer
            except (json.JSONDecodeError, ValueError):
                session.final_answer_json = json.dumps(
                    {"diagnosis": final_answer}, ensure_ascii=False
                )
        session.status = status
        if token_cost is not None:
            session.token_cost = token_cost
        if duration_ms is not None:
            session.duration_ms = duration_ms
        db.session.flush()

    @staticmethod
    def _sanitize_rounds(rounds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """I9 修复：对 rounds 逐条脱敏，重点处理 result 字段（工具回显）。"""
        try:
            from app.services.ai.prompt_guard import strip_sensitive_result
        except Exception:  # noqa: BLE001
            return rounds  # 脱敏模块不可用，降级为原样入库
        sanitized = []
        for r in rounds:
            if isinstance(r, dict) and "result" in r:
                r_copy = dict(r)
                r_copy["result"] = strip_sensitive_result(r_copy["result"])
                sanitized.append(r_copy)
            else:
                sanitized.append(r)
        return sanitized

    def set_device_id(self, session_id: int, device_id: int) -> None:
        """回填诊断目标设备 ID。

        runner 创建会话时还不知道 LLM 会诊断哪台设备（device_id 由工具调用
        参数决定），故结束阶段从 rounds 中提取后回填，支撑"这台设备上次
        同样故障怎么修的"这类按设备回溯的查询。
        """
        session = db.session.get(AIDiagnosisSession, session_id)
        if session is None:
            return
        session.device_id = device_id
        db.session.flush()

    def mark_rollback_failed(self, session_id: int) -> None:
        """标记回滚失败（Phase 4.4：设备滞留已变更未回滚的中间态）。"""
        session = db.session.get(AIDiagnosisSession, session_id)
        if session is None:
            return
        session.rollback_failed = True
        db.session.flush()

    def mark_remedial_executed(self, session_id: int) -> None:
        """标记有 remedial 命令被实际执行。"""
        session = db.session.get(AIDiagnosisSession, session_id)
        if session is None:
            return
        session.remedial_executed = True
        db.session.flush()

    def list_sessions(
        self,
        user_id: Optional[int],
        device_id: Optional[int] = None,
        limit: int = 20,
    ) -> Optional[List[Dict[str, Any]]]:
        """查诊断会话历史（叠加当前用户数据域过滤）。

        数据域过滤下沉到 service，路由层不再直接拼 SQLAlchemy 查询。
        visible=None 表示无限制（data_scope=all 或角色豁免）。

        Args:
            user_id: 当前用户 ID；None 表示未取到（此时不做数据域过滤）
            device_id: 可选，按设备过滤
            limit: 返回条数上限

        Returns:
            会话字典列表；**None 表示指定了无权访问的设备**（路由应转 403），
            与"查得到但为空"（返回 []）语义不同，不可混淆。
        """
        visible = None
        if user_id:
            try:
                from app.services.monitoring.data_scope_service import get_visible_device_ids
                visible = get_visible_device_ids(user_id)
            except Exception:  # noqa: BLE001
                logger.warning("数据域解析失败，按无限制处理 user_id=%s", user_id)
                visible = None

        query = db.session.query(AIDiagnosisSession)
        if visible is not None:
            query = query.filter(AIDiagnosisSession.device_id.in_(list(visible)))
        if device_id:
            if visible is not None and device_id not in visible:
                return None
            query = query.filter_by(device_id=device_id)

        rows = query.order_by(AIDiagnosisSession.created_at.desc()).limit(limit).all()
        return [r.to_dict() for r in rows]

    def list_rollback_failures(self, limit: int = 50) -> List[Dict[str, Any]]:
        """查回滚失败会话。

        Phase 4.4：设备滞留"已变更未回滚"的中间态是最危险的状态，
        不能让运维误以为已恢复，故需持续告警（路由层原为直接拼查询）。
        """
        rows = (
            db.session.query(AIDiagnosisSession)
            .filter_by(rollback_failed=True)
            .order_by(AIDiagnosisSession.created_at.desc())
            .limit(limit)
            .all()
        )
        return [r.to_dict() for r in rows]

    def get_history_by_device(
        self, device_id: int, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """查某设备的历史诊断会话（"这台设备上次同样故障怎么修的"）。"""
        rows = (
            db.session.query(AIDiagnosisSession)
            .filter_by(device_id=device_id)
            .order_by(AIDiagnosisSession.created_at.desc())
            .limit(limit)
            .all()
        )
        return [r.to_dict() for r in rows]
