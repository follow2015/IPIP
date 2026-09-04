# -*- coding: utf-8 -*-
"""AI 对话历史持久化模型。

Task 0.4：记录用户与 AI 的对话轮次，供前端展示历史问答。
当前各 AI service 暂未接线 save_turn（待后续接入），模型与仓储已就位。
"""
from sqlalchemy import ForeignKey, Index, Integer, String, Text

from app.models.base import BaseModel
from extensions import db


class AIConversation(BaseModel):
    """AI 对话历史。

    M4 修复：user_id 补外键约束（原为无约束 Integer，用户删除后会残留孤儿
    对话记录，且无法利用外键索引做联表查询）。
    """

    __tablename__ = "ai_conversations"
    __table_args__ = (
        Index("idx_ai_conv_user_scenario", "user_id", "scenario"),
        {"comment": "AI 对话历史"},
    )

    user_id = db.Column(
        db.BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="用户ID（FK→users.id，用户删除时级联清理其对话历史）",
    )
    scenario = db.Column(String(50), nullable=False, comment="场景: chat/alert/nlq/rag/inspection")
    role = db.Column(String(20), nullable=False, comment="user/assistant")
    content = db.Column(Text, nullable=False, comment="消息内容")
