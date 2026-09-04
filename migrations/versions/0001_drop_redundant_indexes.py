# -*- coding: utf-8 -*-
"""清理 12+2 个冗余索引（docs/2026-09-04-Schema差异评估与修改计划.md §3.2）。

冗余判定：索引 B 的列集是索引 A 的左前缀 → B 可被 A 服务，删除仅减少写放大。
每个 DROP 前执行两道防御检查（幂等 + 防误删）：
  1. 待删索引仍存在（不存在则跳过，重跑安全）；
  2. 替代索引（以被删索引最左列为前缀）仍存在（不存在则抛错中止，
     避免删掉某 FK 的唯一支撑索引导致 error 1553）。

上线纪律：flask db-upgrade --dry-run 预检 → 低峰执行 → SHOW INDEX 复核。

注意：评估文档摘要写"12 个"，但 §3.2 表格实列 13 行（virtual_rooms 一行
含 2 个 DROP，合计 14 条 DROP 语句），以表格为准实现。
"""
import logging

logger = logging.getLogger(__name__)

DROPS = [
    ("audit_logs", "idx_audit_resource_id",
     ["idx_audit_resource_time"]),
    ("customer_termination_archive", "ix_cta_customer_id",
     ["ix_cta_customer_created"]),
    ("device_metric_baseline", "ix_dmb_device_metric",
     ["uq_dmb_device_metric_hour_dow"]),
    ("device_metric_latest", "ix_dml_device_id",
     ["uq_dml_device_metric_index"]),
    ("device_metric_override", "ix_dmo_device",
     ["uq_dmo_device_metric"]),
    ("ip_addresses", "ip_addresses_ibfk_1",
     ["idx_ip_deleted_room_status"]),
    ("ip_allocation_logs", "idx_alloc_ip",
     ["idx_alloc_ip_time"]),
    ("monitor_alert_outbox", "ix_mao_incident",
     ["idx_mao_incident"]),
    ("monitor_credentials", "ix_mc_protocol",
     ["uk_mc_protocol_name", "uk_mc_protocol_hash"]),
    ("monitor_escalation_step", "ix_mes_policy",
     ["ix_mes_policy_step"]),
    ("monitor_metric_template_group_items", "ix_mmtgi_group_id",
     ["uq_mmtgi_group_template"]),
    ("virtual_room_members", "uq_vr_member",
     ["PRIMARY"]),
    ("virtual_rooms", "name",
     ["uq_virtual_room_name"]),
    ("virtual_rooms", "idx_virtual_room_name",
     ["uq_virtual_room_name"]),
]


def _index_exists(conn, table: str, index: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() AND table_name = %s "
            "AND index_name = %s",
            (table, index),
        )
        row = cur.fetchone()
        return bool(row and row[0])
    finally:
        cur.close()


def apply(conn) -> None:
    for table, index, replacements in DROPS:
        if not _index_exists(conn, table, index):
            logger.info("跳过 %s.%s（不存在，幂等）", table, index)
            continue
        ok = any(_index_exists(conn, table, r) for r in replacements)
        if not ok:
            raise RuntimeError(
                f"替代索引 {replacements} 均不存在于 {table}，"
                f"中止 DROP {index}（防删除 FK 唯一支撑/破坏查询覆盖）"
            )
        cur = conn.cursor()
        try:
            cur.execute(f"DROP INDEX `{index}` ON `{table}`")
        finally:
            cur.close()
        logger.info("已删除冗余索引 %s.%s（替代: %s）", table, index, replacements)
    conn.commit()
