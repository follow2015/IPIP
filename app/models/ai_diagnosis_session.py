# -*- coding: utf-8 -*-
"""AI 诊断会话持久化模型。

设计文档第九节：支撑历史回溯、准确率统计、"这台设备上次同样故障怎么修的"这类查询。
rounds_json 存每轮 tool/args/result 摘要；final_answer_json 存结构化诊断结论。
SSH 原始输出快照走对象存储/文件（大文本不进数据库正文字段），此处只存摘要。
"""
from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT

from app.models.base import BaseModel
from extensions import db


class AIDiagnosisSession(BaseModel):
    """AI 诊断会话（一次 network_troubleshoot 执行的完整记录）。"""

    __tablename__ = "ai_diagnosis_sessions"
    __table_args__ = (
        Index("idx_ai_diag_device_user", "device_id", "user_id"),
        Index("idx_ai_diag_skill_status", "skill_name", "status"),
        {"comment": "AI 诊断会话持久化"},
    )

    device_id = db.Column(
        db.BigInteger,
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
        comment="设备ID（诊断目标设备，设备删除时保留会话供回溯）",
    )
    user_id = db.Column(
        db.BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="用户ID",
    )
    skill_name = db.Column(
        String(64),
        nullable=False,
        comment="agentic 技能名（如 network_troubleshoot）",
    )
    question = db.Column(
        Text,
        nullable=False,
        comment="用户原始问题",
    )
    rounds_json = db.Column(
        LONGTEXT,
        nullable=True,
        comment="每轮工具调用摘要 JSON：[{round, tool, args, result_summary, duration_ms}]",
    )
    final_answer_json = db.Column(
        LONGTEXT,
        nullable=True,
        comment="结构化诊断结论 JSON：{diagnosis, confidence, evidence, proposed_commands}",
    )
    status = db.Column(
        String(20),
        nullable=False,
        default="running",
        comment="running/completed/incomplete/failed",
    )
    token_cost = db.Column(
        Integer,
        nullable=True,
        comment="本次诊断总 token 消耗",
    )
    duration_ms = db.Column(
        Integer,
        nullable=True,
        comment="本次诊断总耗时毫秒",
    )
    remedial_executed = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        comment="是否有 remedial 命令被实际执行",
    )
    rollback_failed = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        comment="回滚是否失败（设备滞留已变更未回滚的中间态标记）",
    )
