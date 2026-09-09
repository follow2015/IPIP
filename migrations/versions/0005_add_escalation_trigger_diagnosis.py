# -*- coding: utf-8 -*-
"""monitor_escalation_step 加「触发 AI 诊断」动作（AI 诊断 × 告警集成 ③）。

背景：升级链路已有三种动作（升级别 / 通知角色 / webhook），但「持续未恢复 →
自动做一次深度诊断」这条最能省人力的一环缺失：运维半夜被叫醒后，还得自己把
现场重新摸一遍，而 AI 完全可以在第 N 分钟未确认时就先把根因分析跑完。

采用独立 Boolean + 技能名字段而非 action_type 枚举：现有三种动作本就是三个
独立 nullable 列（可组合、非互斥），引入枚举会牵动既有判空逻辑并需要数据
迁移；新字段 nullable / 默认 0，旧 step 行为完全不变。

幂等：列存在即跳过。
"""
import logging

logger = logging.getLogger(__name__)

TABLE = "monitor_escalation_step"


def _column_exists(conn, column: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = %s "
            "AND column_name = %s",
            (TABLE, column),
        )
        row = cur.fetchone()
        return bool(row and row[0])
    finally:
        cur.close()


def apply(conn) -> None:
    cur = conn.cursor()
    try:
        if not _column_exists(conn, "trigger_ai_diagnosis"):
            cur.execute(
                f"ALTER TABLE `{TABLE}` "
                f"ADD COLUMN `trigger_ai_diagnosis` tinyint(1) NOT NULL DEFAULT 0 "
                f"COMMENT '本步骤是否触发 AI 深度诊断（incident 级，按事件去重）' "
                f"AFTER `escalate_webhook_url`"
            )
            logger.info("已补列 %s.trigger_ai_diagnosis", TABLE)
        else:
            logger.info("跳过：%s.trigger_ai_diagnosis 已存在", TABLE)

        if not _column_exists(conn, "ai_skill_name"):
            cur.execute(
                f"ALTER TABLE `{TABLE}` "
                f"ADD COLUMN `ai_skill_name` varchar(64) NULL "
                f"COMMENT '触发诊断使用的 agentic 技能名（空=用默认 network_troubleshoot）' "
                f"AFTER `trigger_ai_diagnosis`"
            )
            logger.info("已补列 %s.ai_skill_name", TABLE)
        else:
            logger.info("跳过：%s.ai_skill_name 已存在", TABLE)
    finally:
        cur.close()
    conn.commit()
