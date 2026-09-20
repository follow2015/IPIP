# -*- coding: utf-8 -*-
"""机房平面图增强：rooms.building + room_channels + room_layout_markers（路线 A §2.1/§2.2/§2.4）

三项均为纯增量、可空/可选改动，无存量数据回填，失败重跑安全。

DDL 与 app/models/room.py、room_channel.py、room_layout_marker.py 的声明严格对齐
（列顺序为「子类字段在前、基类时间戳在后」，与 SQLAlchemy 生成结果一致，
手写易错，故此处按模型编译结果落笔）。

新装的 0000_baseline 不含这三项，故不做 baseline 特判，全部走幂等分支。
"""
import logging

logger = logging.getLogger(__name__)

ROOM_CHANNELS_DDL = """
CREATE TABLE IF NOT EXISTS `room_channels` (
  `room_id` int NOT NULL COMMENT '所属机房ID',
  `col_number` int NOT NULL COMMENT '通道位于第 col_number 列与第 col_number+1 列之间；0 表示第 1 列外侧',
  `channel_type` varchar(20) NOT NULL COMMENT 'cold 冷 / hot 热 / mixed 混合(不规范布置)',
  `enclosed` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否封闭(端门/顶板)；新式模块机房的封闭冷通道为 True，封闭热通道(HAC)亦为 True',
  `supply` varchar(20) DEFAULT NULL COMMENT '送风方式：floor(地板下,推荐) / direct(上送风直吹通道,易掺混,非推荐) / none(无)',
  `label` varchar(100) DEFAULT NULL COMMENT '展示文本,如''A-B 冷通道''',
  `notes` varchar(500) DEFAULT NULL COMMENT '备注',
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_room_col_channel` (`room_id`,`col_number`),
  KEY `ix_room_channels_room` (`room_id`),
  CONSTRAINT `fk_room_channels_room` FOREIGN KEY (`room_id`) REFERENCES `rooms` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='机房通道配置表'
"""

ROOM_LAYOUT_MARKERS_DDL = """
CREATE TABLE IF NOT EXISTS `room_layout_markers` (
  `room_id` int NOT NULL COMMENT '所属机房ID',
  `row_number` int NOT NULL COMMENT '行号（允许 0，用于机柜网格外侧）',
  `col_number` int NOT NULL COMMENT '列号（允许 0，用于机柜网格外侧）',
  `marker_type` varchar(20) NOT NULL COMMENT 'ac(空调) / pdu / pillar(立柱) / door / other',
  `label` varchar(100) DEFAULT NULL COMMENT '展示文本,如''空调-01''',
  `notes` varchar(500) DEFAULT NULL COMMENT '备注',
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_marker_position` (`room_id`,`row_number`,`col_number`),
  KEY `ix_room_layout_markers_room` (`room_id`),
  CONSTRAINT `fk_room_layout_markers_room` FOREIGN KEY (`room_id`) REFERENCES `rooms` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='机房平面图占位标记表'
"""


def _column_exists(conn, table: str, column: str) -> bool:
    """列是否已存在（幂等判断）"""
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
            (table, column),
        )
        row = cur.fetchone()
        return bool(row and row[0])
    finally:
        cur.close()


def _table_exists(conn, table: str) -> bool:
    """表是否已存在（幂等判断）"""
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = %s",
            (table,),
        )
        row = cur.fetchone()
        return bool(row and row[0])
    finally:
        cur.close()


def apply(conn) -> None:
    """应用三条 DDL（各自幂等）"""
    cur = conn.cursor()
    try:
        if _column_exists(conn, "rooms", "building"):
            logger.info("跳过：rooms.building 已存在")
        else:
            cur.execute(
                "ALTER TABLE `rooms` ADD COLUMN `building` VARCHAR(100) NULL "
                "COMMENT '所属建筑/园区(用于跨机房总览分组展示,自由文本)' "
                "AFTER `contact_phone`"
            )
            logger.info("已加列 rooms.building")

        if _table_exists(conn, "room_channels"):
            logger.info("跳过：room_channels 已存在")
        else:
            cur.execute(ROOM_CHANNELS_DDL)
            logger.info("已建表 room_channels")

        if _table_exists(conn, "room_layout_markers"):
            logger.info("跳过：room_layout_markers 已存在")
        else:
            cur.execute(ROOM_LAYOUT_MARKERS_DDL)
            logger.info("已建表 room_layout_markers")
    finally:
        cur.close()
    conn.commit()
