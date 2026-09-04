# -*- coding: utf-8 -*-
"""AI 对话历史仓储。

Task 0.4：复用 BaseService.session，提供 save_turn / list_recent。

⚠️ 当前状态：预留未接线。各 AI service 尚未调用 save_turn，表内无数据。

保留原因：对话历史是《智能运维诊断闭环 · 完整工程方案》中"多轮追问/上下文延续"
与诊断准确率复盘的基础设施。该方案另规划了 ai_diagnosis_session 表承载
诊断过程，本表承载通用对话轮次，两者定位不同、互为补充，故保留待接线。
"""
from typing import List

from app.models.ai_conversation import AIConversation
from app.services.base import BaseService

_MAX_CONTENT_LENGTH = 10000
_MAX_SCENARIO_LENGTH = 50
_MAX_ROLE_LENGTH = 20
_ALLOWED_ROLES = ("user", "assistant")


class AIConversationRepository(BaseService):
    """AI 对话历史仓储。"""

    def __init__(self):
        super().__init__(AIConversation)

    def save_turn(self, user_id: int, role: str, content: str, scenario: str) -> AIConversation:
        """保存一轮对话。

        M4 修复：补齐内容长度与取值校验，防止超长/非法数据落库。

        Raises:
            ValueError: content 为空或超长、role 取值非法、scenario 超长。
        """
        if not isinstance(content, str) or not content.strip():
            raise ValueError("content 必须为非空字符串")
        if len(content) > _MAX_CONTENT_LENGTH:
            raise ValueError(
                f"content 过长（{len(content)} > {_MAX_CONTENT_LENGTH}），已拒绝写入")
        if role not in _ALLOWED_ROLES:
            raise ValueError(f"非法 role={role!r}，允许取值：{_ALLOWED_ROLES}")
        if len(scenario) > _MAX_SCENARIO_LENGTH:
            raise ValueError(
                f"scenario 过长（{len(scenario)} > {_MAX_SCENARIO_LENGTH}）")

        row = AIConversation(user_id=user_id, role=role, content=content, scenario=scenario)
        self.session.add(row)
        self.session.commit()
        return row

    def list_recent(self, user_id: int, scenario: str, limit: int = 20) -> List[AIConversation]:
        """查询最近对话（按 id 倒序）。"""
        return (
            self.session.query(AIConversation)
            .filter_by(user_id=user_id, scenario=scenario)
            .order_by(AIConversation.id.desc())
            .limit(limit)
            .all()
        )
