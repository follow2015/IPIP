#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配件模板种子数据导入脚本

将常见 CPU / 内存 / 硬盘 / 网卡 / GPU 型号写入 component_templates 表。
幂等执行：全局模板（customer_id 为 NULL）采用"逐行查重 upsert"，
规避 ON DUPLICATE KEY UPDATE 在 customer_id=NULL 下失效的问题（MySQL 唯一索引将 NULL 视为互异）。
- 磁盘（disk）类按 (category, model, capacity_gb) 维度查重，支持同型号多容量共存；
- 其余类按 (category, model) 维度查重。
重复运行不会重复插入，只会更新已有记录。运行前会先清理历史版本残留的重复全局行
（去重维度与 upsert 一致，避免误删同型号不同容量的磁盘模板）。

用法:
    python3 migrations/seed_component_templates.py

环境变量（可选，默认读取 .env 或 config.py 中的值）:
    MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
"""
import json
import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root / ".env")

DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "ip_management"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}


SEED_DATA = {
    "cpu": [
        {"brand": "Intel", "model": "Xeon Platinum 8490H", "spec": {"cores_per_cpu": 60, "architecture": "x86_64", "base_freq_ghz": 1.9, "boost_freq_ghz": 3.5, "tdp_w": 350}, "sort_order": 10, "remark": "Sapphire Rapids，最高端"},
        {"brand": "Intel", "model": "Xeon Platinum 8480+", "spec": {"cores_per_cpu": 56, "architecture": "x86_64", "base_freq_ghz": 2.0, "boost_freq_ghz": 3.4, "tdp_w": 350}, "sort_order": 11, "remark": "Sapphire Rapids"},
        {"brand": "Intel", "model": "Xeon Gold 6458Q", "spec": {"cores_per_cpu": 32, "architecture": "x86_64", "base_freq_ghz": 3.0, "boost_freq_ghz": 3.8, "tdp_w": 250}, "sort_order": 20, "remark": "Sapphire Rapids，高频"},
        {"brand": "Intel", "model": "Xeon Gold 6448Y", "spec": {"cores_per_cpu": 32, "architecture": "x86_64", "base_freq_ghz": 2.1, "boost_freq_ghz": 4.1, "tdp_w": 225}, "sort_order": 21, "remark": "Sapphire Rapids"},
        {"brand": "Intel", "model": "Xeon Gold 6430", "spec": {"cores_per_cpu": 32, "architecture": "x86_64", "base_freq_ghz": 2.1, "boost_freq_ghz": 3.4, "tdp_w": 270}, "sort_order": 22, "remark": "Sapphire Rapids"},
        {"brand": "Intel", "model": "Xeon Gold 5418N", "spec": {"cores_per_cpu": 24, "architecture": "x86_64", "base_freq_ghz": 2.1, "boost_freq_ghz": 3.4, "tdp_w": 150}, "sort_order": 30, "remark": "Sapphire Rapids"},
        {"brand": "Intel", "model": "Xeon Silver 4416+", "spec": {"cores_per_cpu": 20, "architecture": "x86_64", "base_freq_ghz": 2.1, "boost_freq_ghz": 3.6, "tdp_w": 165}, "sort_order": 40, "remark": "Sapphire Rapids"},
        {"brand": "Intel", "model": "Xeon Silver 4410Y", "spec": {"cores_per_cpu": 12, "architecture": "x86_64", "base_freq_ghz": 2.0, "boost_freq_ghz": 3.9, "tdp_w": 150}, "sort_order": 41, "remark": "Sapphire Rapids"},
        {"brand": "Intel", "model": "Xeon Bronze 3408U", "spec": {"cores_per_cpu": 8, "architecture": "x86_64", "base_freq_ghz": 1.8, "boost_freq_ghz": 2.3, "tdp_w": 125}, "sort_order": 50, "remark": "Sapphire Rapids，入门"},
        {"brand": "Intel", "model": "Xeon Platinum 8380", "spec": {"cores_per_cpu": 40, "architecture": "x86_64", "base_freq_ghz": 2.3, "boost_freq_ghz": 3.4, "tdp_w": 270}, "sort_order": 60, "remark": "Ice Lake"},
        {"brand": "Intel", "model": "Xeon Gold 6354", "spec": {"cores_per_cpu": 18, "architecture": "x86_64", "base_freq_ghz": 3.0, "boost_freq_ghz": 3.6, "tdp_w": 205}, "sort_order": 70, "remark": "Ice Lake"},
        {"brand": "Intel", "model": "Xeon Silver 4314", "spec": {"cores_per_cpu": 16, "architecture": "x86_64", "base_freq_ghz": 2.4, "boost_freq_ghz": 3.4, "tdp_w": 135}, "sort_order": 80, "remark": "Ice Lake"},
        {"brand": "AMD", "model": "EPYC 9654", "spec": {"cores_per_cpu": 96, "architecture": "x86_64", "base_freq_ghz": 2.4, "boost_freq_ghz": 3.7, "tdp_w": 360}, "sort_order": 100, "remark": "Genoa，96核旗舰"},
        {"brand": "AMD", "model": "EPYC 9554", "spec": {"cores_per_cpu": 64, "architecture": "x86_64", "base_freq_ghz": 3.1, "boost_freq_ghz": 3.75, "tdp_w": 360}, "sort_order": 101, "remark": "Genoa"},
        {"brand": "AMD", "model": "EPYC 9454", "spec": {"cores_per_cpu": 48, "architecture": "x86_64", "base_freq_ghz": 2.75, "boost_freq_ghz": 3.65, "tdp_w": 290}, "sort_order": 102, "remark": "Genoa"},
        {"brand": "AMD", "model": "EPYC 9354", "spec": {"cores_per_cpu": 32, "architecture": "x86_64", "base_freq_ghz": 3.25, "boost_freq_ghz": 3.8, "tdp_w": 280}, "sort_order": 103, "remark": "Genoa"},
        {"brand": "AMD", "model": "EPYC 9254", "spec": {"cores_per_cpu": 24, "architecture": "x86_64", "base_freq_ghz": 2.9, "boost_freq_ghz": 4.15, "tdp_w": 200}, "sort_order": 104, "remark": "Genoa"},
        {"brand": "AMD", "model": "EPYC 9124", "spec": {"cores_per_cpu": 16, "architecture": "x86_64", "base_freq_ghz": 3.0, "boost_freq_ghz": 3.7, "tdp_w": 200}, "sort_order": 105, "remark": "Genoa"},
        {"brand": "AMD", "model": "EPYC 7763", "spec": {"cores_per_cpu": 64, "architecture": "x86_64", "base_freq_ghz": 2.45, "boost_freq_ghz": 3.5, "tdp_w": 280}, "sort_order": 110, "remark": "Milan"},
        {"brand": "AMD", "model": "EPYC 7713", "spec": {"cores_per_cpu": 64, "architecture": "x86_64", "base_freq_ghz": 2.0, "boost_freq_ghz": 3.675, "tdp_w": 225}, "sort_order": 111, "remark": "Milan"},
        {"brand": "AMD", "model": "EPYC 7543", "spec": {"cores_per_cpu": 32, "architecture": "x86_64", "base_freq_ghz": 2.8, "boost_freq_ghz": 3.7, "tdp_w": 225}, "sort_order": 112, "remark": "Milan"},
        {"brand": "Intel", "model": "Xeon Platinum 8280", "spec": {"cores_per_cpu": 28, "architecture": "x86_64", "base_freq_ghz": 2.7, "boost_freq_ghz": 4.0, "tdp_w": 205}, "sort_order": 55, "remark": "Cascade Lake，旗舰"},
        {"brand": "Intel", "model": "Xeon Gold 6248", "spec": {"cores_per_cpu": 20, "architecture": "x86_64", "base_freq_ghz": 2.5, "boost_freq_ghz": 3.9, "tdp_w": 150}, "sort_order": 56, "remark": "Cascade Lake"},
        {"brand": "Intel", "model": "Xeon Gold 6230", "spec": {"cores_per_cpu": 20, "architecture": "x86_64", "base_freq_ghz": 2.1, "boost_freq_ghz": 3.9, "tdp_w": 125}, "sort_order": 57, "remark": "Cascade Lake"},
        {"brand": "Intel", "model": "Xeon Silver 4210", "spec": {"cores_per_cpu": 10, "architecture": "x86_64", "base_freq_ghz": 2.2, "boost_freq_ghz": 3.2, "tdp_w": 85}, "sort_order": 58, "remark": "Cascade Lake"},
        {"brand": "Intel", "model": "Xeon Bronze 3204", "spec": {"cores_per_cpu": 6, "architecture": "x86_64", "base_freq_ghz": 1.9, "boost_freq_ghz": 2.0, "tdp_w": 85}, "sort_order": 59, "remark": "Cascade Lake，入门"},
        {"brand": "AMD", "model": "EPYC 9575F", "spec": {"cores_per_cpu": 64, "architecture": "x86_64", "base_freq_ghz": 3.3, "boost_freq_ghz": 5.0, "tdp_w": 400}, "sort_order": 106, "remark": "Turin，高主频"},
        {"brand": "AMD", "model": "EPYC 9455", "spec": {"cores_per_cpu": 48, "architecture": "x86_64", "base_freq_ghz": 3.15, "boost_freq_ghz": 4.8, "tdp_w": 300}, "sort_order": 107, "remark": "Turin"},
        {"brand": "AMD", "model": "EPYC 9255", "spec": {"cores_per_cpu": 24, "architecture": "x86_64", "base_freq_ghz": 3.25, "boost_freq_ghz": 4.8, "tdp_w": 200}, "sort_order": 108, "remark": "Turin"},
        {"brand": "AMD", "model": "EPYC 9754", "spec": {"cores_per_cpu": 128, "architecture": "x86_64", "base_freq_ghz": 2.25, "boost_freq_ghz": 3.1, "tdp_w": 360}, "sort_order": 113, "remark": "Bergamo，128核"},
        {"brand": "海光", "model": "C86-3185", "spec": {"cores_per_cpu": 8, "architecture": "x86_64", "base_freq_ghz": 2.0, "boost_freq_ghz": 2.5, "tdp_w": 95}, "sort_order": 200, "remark": "海光 C86 系列"},
        {"brand": "海光", "model": "C86-3280", "spec": {"cores_per_cpu": 16, "architecture": "x86_64", "base_freq_ghz": 2.1, "boost_freq_ghz": 2.8, "tdp_w": 150}, "sort_order": 201, "remark": "海光 C86 系列"},
        {"brand": "海光", "model": "C86-5380", "spec": {"cores_per_cpu": 32, "architecture": "x86_64", "base_freq_ghz": 2.5, "boost_freq_ghz": 3.0, "tdp_w": 200}, "sort_order": 202, "remark": "海光 C86 系列"},
        {"brand": "华为", "model": "鲲鹏 920-7260", "spec": {"cores_per_cpu": 64, "architecture": "ARM64", "base_freq_ghz": 2.6, "boost_freq_ghz": 3.0, "tdp_w": 180}, "sort_order": 210, "remark": "鲲鹏 920"},
        {"brand": "华为", "model": "鲲鹏 920-5250", "spec": {"cores_per_cpu": 48, "architecture": "ARM64", "base_freq_ghz": 2.6, "boost_freq_ghz": 3.0, "tdp_w": 150}, "sort_order": 211, "remark": "鲲鹏 920"},
        {"brand": "华为", "model": "鲲鹏 920-3210", "spec": {"cores_per_cpu": 24, "architecture": "ARM64", "base_freq_ghz": 2.6, "boost_freq_ghz": 3.0, "tdp_w": 90}, "sort_order": 212, "remark": "鲲鹏 920，低功耗"},
        {"brand": "华为", "model": "鲲鹏 920-3226", "spec": {"cores_per_cpu": 48, "architecture": "ARM64", "base_freq_ghz": 2.6, "boost_freq_ghz": 3.0, "tdp_w": 120}, "sort_order": 213, "remark": "鲲鹏 920"},
        {"brand": "飞腾", "model": "FT-2000+", "spec": {"cores_per_cpu": 64, "architecture": "ARM64", "base_freq_ghz": 2.0, "boost_freq_ghz": 2.4, "tdp_w": 110}, "sort_order": 250, "remark": "国产 ARM，服务器"},
        {"brand": "飞腾", "model": "S2500", "spec": {"cores_per_cpu": 64, "architecture": "ARM64", "base_freq_ghz": 2.1, "boost_freq_ghz": 2.2, "tdp_w": 150}, "sort_order": 251, "remark": "国产 ARM，多路"},
    ],
    "memory": [
        {"brand": "Samsung", "model": "M321R4GA3BB6-CQK", "spec": {"capacity_gb": 32, "type": "DDR5", "speed_mhz": 4800, "form_factor": "RDIMM", "ecc": True}, "sort_order": 10, "remark": "DDR5-4800 32GB"},
        {"brand": "Samsung", "model": "M321R8GA3BB6-CQK", "spec": {"capacity_gb": 64, "type": "DDR5", "speed_mhz": 4800, "form_factor": "RDIMM", "ecc": True}, "sort_order": 11, "remark": "DDR5-4800 64GB"},
        {"brand": "Samsung", "model": "M321RAGA3BB6-CQK", "spec": {"capacity_gb": 128, "type": "DDR5", "speed_mhz": 4800, "form_factor": "RDIMM", "ecc": True}, "sort_order": 12, "remark": "DDR5-4800 128GB"},
        {"brand": "SK Hynix", "model": "HMCG88AEBRA115N", "spec": {"capacity_gb": 64, "type": "DDR5", "speed_mhz": 4800, "form_factor": "RDIMM", "ecc": True}, "sort_order": 20, "remark": "DDR5-4800 64GB"},
        {"brand": "SK Hynix", "model": "HMCG78AEBRA109N", "spec": {"capacity_gb": 32, "type": "DDR5", "speed_mhz": 4800, "form_factor": "RDIMM", "ecc": True}, "sort_order": 21, "remark": "DDR5-4800 32GB"},
        {"brand": "Micron", "model": "MTC20F2085S1RC48BA1", "spec": {"capacity_gb": 32, "type": "DDR5", "speed_mhz": 4800, "form_factor": "RDIMM", "ecc": True}, "sort_order": 30, "remark": "DDR5-4800 32GB"},
        {"brand": "Micron", "model": "MTC40F2046S1RC48BA1", "spec": {"capacity_gb": 64, "type": "DDR5", "speed_mhz": 4800, "form_factor": "RDIMM", "ecc": True}, "sort_order": 31, "remark": "DDR5-4800 64GB"},
        {"brand": "Samsung", "model": "M393A4K40DB3-CWE", "spec": {"capacity_gb": 32, "type": "DDR4", "speed_mhz": 3200, "form_factor": "RDIMM", "ecc": True}, "sort_order": 100, "remark": "DDR4-3200 32GB"},
        {"brand": "Samsung", "model": "M393A8K40DB3-CWE", "spec": {"capacity_gb": 64, "type": "DDR4", "speed_mhz": 3200, "form_factor": "RDIMM", "ecc": True}, "sort_order": 101, "remark": "DDR4-3200 64GB"},
        {"brand": "Samsung", "model": "M393A2K40CB3-CWE", "spec": {"capacity_gb": 16, "type": "DDR4", "speed_mhz": 3200, "form_factor": "RDIMM", "ecc": True}, "sort_order": 102, "remark": "DDR4-3200 16GB"},
        {"brand": "SK Hynix", "model": "HMAA4GR7AJR8N-XN", "spec": {"capacity_gb": 32, "type": "DDR4", "speed_mhz": 3200, "form_factor": "RDIMM", "ecc": True}, "sort_order": 110, "remark": "DDR4-3200 32GB"},
        {"brand": "SK Hynix", "model": "HMAA8GR7AJR8N-XN", "spec": {"capacity_gb": 64, "type": "DDR4", "speed_mhz": 3200, "form_factor": "RDIMM", "ecc": True}, "sort_order": 111, "remark": "DDR4-3200 64GB"},
        {"brand": "Micron", "model": "MTA36ASF4G72PZ-2G6E1", "spec": {"capacity_gb": 32, "type": "DDR4", "speed_mhz": 2666, "form_factor": "RDIMM", "ecc": True}, "sort_order": 120, "remark": "DDR4-2666 32GB"},
        {"brand": "Micron", "model": "MTA36ASF8G72PZ-2G6E1", "spec": {"capacity_gb": 64, "type": "DDR4", "speed_mhz": 2666, "form_factor": "RDIMM", "ecc": True}, "sort_order": 121, "remark": "DDR4-2666 64GB"},
        {"brand": "长鑫存储", "model": "CXDQ5A8AM-CG", "spec": {"capacity_gb": 16, "type": "DDR4", "speed_mhz": 3200, "form_factor": "UDIMM", "ecc": False}, "sort_order": 200, "remark": "DDR4-3200 16GB 消费级"},
        {"brand": "记忆科技", "model": "RAMAXEL DDR4-3200 32GB", "spec": {"capacity_gb": 32, "type": "DDR4", "speed_mhz": 3200, "form_factor": "RDIMM", "ecc": True}, "sort_order": 210, "remark": "DDR4-3200 32GB 国产"},
        {"brand": "记忆科技", "model": "RAMAXEL DDR5-4800 64GB", "spec": {"capacity_gb": 64, "type": "DDR5", "speed_mhz": 4800, "form_factor": "RDIMM", "ecc": True}, "sort_order": 211, "remark": "DDR5-4800 64GB 国产"},
        {"brand": "Samsung", "model": "M321R8GA0PB2-CCP", "spec": {"capacity_gb": 64, "type": "DDR5", "speed_mhz": 5600, "form_factor": "RDIMM", "ecc": True}, "sort_order": 13, "remark": "DDR5-5600 64GB"},
        {"brand": "Samsung", "model": "M321R4GA0PB2-CCP", "spec": {"capacity_gb": 32, "type": "DDR5", "speed_mhz": 5600, "form_factor": "RDIMM", "ecc": True}, "sort_order": 14, "remark": "DDR5-5600 32GB"},
        {"brand": "SK Hynix", "model": "HMCG88AEBRA168N", "spec": {"capacity_gb": 64, "type": "DDR5", "speed_mhz": 5600, "form_factor": "RDIMM", "ecc": True}, "sort_order": 22, "remark": "DDR5-5600 64GB"},
        {"brand": "Micron", "model": "MTC40F2046S1RC56BD1", "spec": {"capacity_gb": 64, "type": "DDR5", "speed_mhz": 5600, "form_factor": "RDIMM", "ecc": True}, "sort_order": 32, "remark": "DDR5-5600 64GB"},
        {"brand": "Samsung", "model": "M393A4K40CB3-CVF", "spec": {"capacity_gb": 32, "type": "DDR4", "speed_mhz": 2933, "form_factor": "RDIMM", "ecc": True}, "sort_order": 130, "remark": "DDR4-2933 32GB"},
        {"brand": "SK Hynix", "model": "HMA84GR7DJR4N-XN", "spec": {"capacity_gb": 32, "type": "DDR4", "speed_mhz": 2933, "form_factor": "RDIMM", "ecc": True}, "sort_order": 131, "remark": "DDR4-2933 32GB"},
    ],
    "disk": [
        {"brand": "Samsung", "model": "PM1733a", "spec": {"storage_type": "NVMe", "capacity_gb": 7680, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 14000}, "sort_order": 10, "remark": "U.2 NVMe 7.68TB"},
        {"brand": "Samsung", "model": "PM1733a", "spec": {"storage_type": "NVMe", "capacity_gb": 15360, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 28000}, "sort_order": 11, "remark": "U.2 NVMe 15.36TB"},
        {"brand": "Samsung", "model": "PM893", "spec": {"storage_type": "SSD", "capacity_gb": 3840, "interface_type": "SATA", "form_factor": "2.5\"", "endurance_tbw": 7000}, "sort_order": 20, "remark": "SATA SSD 3.84TB"},
        {"brand": "Samsung", "model": "PM893", "spec": {"storage_type": "SSD", "capacity_gb": 7680, "interface_type": "SATA", "form_factor": "2.5\"", "endurance_tbw": 14000}, "sort_order": 21, "remark": "SATA SSD 7.68TB"},
        {"brand": "Intel", "model": "D7-P5520", "spec": {"storage_type": "NVMe", "capacity_gb": 3840, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 7000}, "sort_order": 30, "remark": "U.2 NVMe 3.84TB"},
        {"brand": "Intel", "model": "D7-P5520", "spec": {"storage_type": "NVMe", "capacity_gb": 7680, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 14000}, "sort_order": 31, "remark": "U.2 NVMe 7.68TB"},
        {"brand": "Intel", "model": "D3-S4520", "spec": {"storage_type": "SSD", "capacity_gb": 1920, "interface_type": "SATA", "form_factor": "2.5\"", "endurance_tbw": 3500}, "sort_order": 40, "remark": "SATA SSD 1.92TB"},
        {"brand": "Intel", "model": "D3-S4520", "spec": {"storage_type": "SSD", "capacity_gb": 3840, "interface_type": "SATA", "form_factor": "2.5\"", "endurance_tbw": 7000}, "sort_order": 41, "remark": "SATA SSD 3.84TB"},
        {"brand": "Micron", "model": "7450 PRO", "spec": {"storage_type": "NVMe", "capacity_gb": 3840, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 7000}, "sort_order": 50, "remark": "U.2 NVMe 3.84TB"},
        {"brand": "Micron", "model": "7450 PRO", "spec": {"storage_type": "NVMe", "capacity_gb": 7680, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 14000}, "sort_order": 51, "remark": "U.2 NVMe 7.68TB"},
        {"brand": "Micron", "model": "5400 PRO", "spec": {"storage_type": "SSD", "capacity_gb": 1920, "interface_type": "SATA", "form_factor": "2.5\"", "endurance_tbw": 3500}, "sort_order": 60, "remark": "SATA SSD 1.92TB"},
        {"brand": "Micron", "model": "5400 PRO", "spec": {"storage_type": "SSD", "capacity_gb": 7680, "interface_type": "SATA", "form_factor": "2.5\"", "endurance_tbw": 14000}, "sort_order": 61, "remark": "SATA SSD 7.68TB"},
        {"brand": "Kioxia", "model": "CM7-R", "spec": {"storage_type": "NVMe", "capacity_gb": 3840, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 7000}, "sort_order": 70, "remark": "U.2 NVMe 3.84TB"},
        {"brand": "Kioxia", "model": "CM7-R", "spec": {"storage_type": "NVMe", "capacity_gb": 7680, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 14000}, "sort_order": 71, "remark": "U.2 NVMe 7.68TB"},
        {"brand": "WD", "model": "SN640", "spec": {"storage_type": "NVMe", "capacity_gb": 7680, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 14000}, "sort_order": 80, "remark": "U.2 NVMe 7.68TB"},
        {"brand": "WD", "model": "SN640", "spec": {"storage_type": "NVMe", "capacity_gb": 15360, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 28000}, "sort_order": 81, "remark": "U.2 NVMe 15.36TB"},
        {"brand": "Seagate", "model": "Exos X18", "spec": {"storage_type": "HDD", "capacity_gb": 18000, "interface_type": "SATA", "form_factor": "3.5\"", "endurance_tbw": 0}, "sort_order": 100, "remark": '3.5" SATA 18TB'},
        {"brand": "Seagate", "model": "Exos X20", "spec": {"storage_type": "HDD", "capacity_gb": 20000, "interface_type": "SATA", "form_factor": "3.5\"", "endurance_tbw": 0}, "sort_order": 101, "remark": '3.5" SATA 20TB'},
        {"brand": "Seagate", "model": "Exos X22", "spec": {"storage_type": "HDD", "capacity_gb": 22000, "interface_type": "SATA", "form_factor": "3.5\"", "endurance_tbw": 0}, "sort_order": 102, "remark": '3.5" SATA 22TB'},
        {"brand": "WD", "model": "Ultrastar DC HC560", "spec": {"storage_type": "HDD", "capacity_gb": 20000, "interface_type": "SATA", "form_factor": "3.5\"", "endurance_tbw": 0}, "sort_order": 110, "remark": '3.5" SATA 20TB'},
        {"brand": "WD", "model": "Ultrastar DC HC580", "spec": {"storage_type": "HDD", "capacity_gb": 24000, "interface_type": "SATA", "form_factor": "3.5\"", "endurance_tbw": 0}, "sort_order": 111, "remark": '3.5" SATA 24TB'},
        {"brand": "Toshiba", "model": "MG10ACA", "spec": {"storage_type": "HDD", "capacity_gb": 20000, "interface_type": "SATA", "form_factor": "3.5\"", "endurance_tbw": 0}, "sort_order": 120, "remark": '3.5" SATA 20TB'},
        {"brand": "长江存储", "model": "PE310", "spec": {"storage_type": "NVMe", "capacity_gb": 3840, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 7000}, "sort_order": 200, "remark": "U.2 NVMe 3.84TB 国产"},
        {"brand": "长江存储", "model": "PE310", "spec": {"storage_type": "NVMe", "capacity_gb": 7680, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 14000}, "sort_order": 201, "remark": "U.2 NVMe 7.68TB 国产"},
        {"brand": "忆恒创源", "model": "PBlaze6 6530", "spec": {"storage_type": "NVMe", "capacity_gb": 3840, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 7000}, "sort_order": 210, "remark": "U.2 NVMe 3.84TB 国产"},
        {"brand": "忆恒创源", "model": "PBlaze6 6530", "spec": {"storage_type": "NVMe", "capacity_gb": 7680, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 14000}, "sort_order": 211, "remark": "U.2 NVMe 7.68TB 国产"},
        {"brand": "Samsung", "model": "PM9A3", "spec": {"storage_type": "NVMe", "capacity_gb": 1920, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 3500}, "sort_order": 12, "remark": "U.2 NVMe 1.92TB 主流"},
        {"brand": "Samsung", "model": "PM9A3", "spec": {"storage_type": "NVMe", "capacity_gb": 3840, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 7000}, "sort_order": 13, "remark": "U.2 NVMe 3.84TB 主流"},
        {"brand": "Samsung", "model": "PM9A3", "spec": {"storage_type": "NVMe", "capacity_gb": 7680, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 14000}, "sort_order": 14, "remark": "U.2 NVMe 7.68TB 主流"},
        {"brand": "Kioxia", "model": "CM6-R", "spec": {"storage_type": "NVMe", "capacity_gb": 3840, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 7000}, "sort_order": 72, "remark": "U.2 NVMe 3.84TB PCIe4.0"},
        {"brand": "Kioxia", "model": "CM6-R", "spec": {"storage_type": "NVMe", "capacity_gb": 7680, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 14000}, "sort_order": 73, "remark": "U.2 NVMe 7.68TB PCIe4.0"},
        {"brand": "Solidigm", "model": "D5-P5316", "spec": {"storage_type": "NVMe", "capacity_gb": 15360, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 22000}, "sort_order": 90, "remark": "U.2 QLC 15.36TB 大容量"},
        {"brand": "Solidigm", "model": "D5-P5316", "spec": {"storage_type": "NVMe", "capacity_gb": 30720, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 45000}, "sort_order": 91, "remark": "U.2 QLC 30.72TB 大容量"},
        {"brand": "Micron", "model": "6500 ION", "spec": {"storage_type": "NVMe", "capacity_gb": 7680, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 10000}, "sort_order": 60, "remark": "U.2 7.68TB 大容量"},
        {"brand": "Micron", "model": "6500 ION", "spec": {"storage_type": "NVMe", "capacity_gb": 15360, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 20000}, "sort_order": 61, "remark": "U.2 15.36TB 大容量"},
        {"brand": "Micron", "model": "6500 ION", "spec": {"storage_type": "NVMe", "capacity_gb": 30720, "interface_type": "NVMe", "form_factor": "2.5\"", "endurance_tbw": 40000}, "sort_order": 62, "remark": "U.2 30.72TB 大容量"},
    ],
    "nic": [
        {"brand": "Intel", "model": "X710-DA2", "spec": {"port_count": 2, "port_type": "SFP+", "port_speed": "10G", "form_factor": "PCIe"}, "sort_order": 10, "remark": "双口 10G SFP+"},
        {"brand": "Intel", "model": "X710-DA4", "spec": {"port_count": 4, "port_type": "SFP+", "port_speed": "10G", "form_factor": "PCIe"}, "sort_order": 11, "remark": "四口 10G SFP+"},
        {"brand": "Intel", "model": "X550-T2", "spec": {"port_count": 2, "port_type": "RJ45", "port_speed": "10G", "form_factor": "PCIe"}, "sort_order": 20, "remark": "双口 10G 电口"},
        {"brand": "Intel", "model": "E810-CQDA2", "spec": {"port_count": 2, "port_type": "QSFP28", "port_speed": "100G", "form_factor": "PCIe"}, "sort_order": 30, "remark": "双口 100G QSFP28"},
        {"brand": "Intel", "model": "E810-XXVDA2", "spec": {"port_count": 2, "port_type": "SFP28", "port_speed": "25G", "form_factor": "PCIe"}, "sort_order": 31, "remark": "双口 25G SFP28"},
        {"brand": "Intel", "model": "E810-XXVDA4", "spec": {"port_count": 4, "port_type": "SFP28", "port_speed": "25G", "form_factor": "PCIe"}, "sort_order": 32, "remark": "四口 25G SFP28"},
        {"brand": "NVIDIA", "model": "ConnectX-6 Dx", "spec": {"port_count": 2, "port_type": "QSFP28", "port_speed": "100G", "form_factor": "PCIe"}, "sort_order": 50, "remark": "双口 100G，智能卸载"},
        {"brand": "NVIDIA", "model": "ConnectX-6 Lx", "spec": {"port_count": 2, "port_type": "SFP28", "port_speed": "25G", "form_factor": "PCIe"}, "sort_order": 51, "remark": "双口 25G"},
        {"brand": "NVIDIA", "model": "ConnectX-7", "spec": {"port_count": 1, "port_type": "QSFP-DD", "port_speed": "400G", "form_factor": "PCIe"}, "sort_order": 52, "remark": "单口 400G"},
        {"brand": "NVIDIA", "model": "BlueField-3", "spec": {"port_count": 2, "port_type": "QSFP112", "port_speed": "100G", "form_factor": "PCIe"}, "sort_order": 60, "remark": "DPU 智能网卡 100G"},
        {"brand": "Broadcom", "model": "BCM57414", "spec": {"port_count": 2, "port_type": "SFP28", "port_speed": "25G", "form_factor": "PCIe"}, "sort_order": 70, "remark": "双口 25G"},
        {"brand": "Broadcom", "model": "BCM57508", "spec": {"port_count": 2, "port_type": "QSFP28", "port_speed": "100G", "form_factor": "PCIe"}, "sort_order": 71, "remark": "双口 100G"},
        {"brand": "Marvell", "model": "QLogic QL41112", "spec": {"port_count": 2, "port_type": "RJ45", "port_speed": "10G", "form_factor": "PCIe"}, "sort_order": 80, "remark": "双口 10G 电口"},
        {"brand": "Marvell", "model": "QLogic QL41212", "spec": {"port_count": 2, "port_type": "SFP+", "port_speed": "10G", "form_factor": "PCIe"}, "sort_order": 81, "remark": "双口 10G SFP+"},
        {"brand": "华为", "model": "SP570", "spec": {"port_count": 2, "port_type": "SFP28", "port_speed": "25G", "form_factor": "PCIe"}, "sort_order": 200, "remark": "双口 25G"},
        {"brand": "华为", "model": "SP580", "spec": {"port_count": 2, "port_type": "QSFP28", "port_speed": "100G", "form_factor": "PCIe"}, "sort_order": 201, "remark": "双口 100G"},
        {"brand": "新华三", "model": "NIC-10GE-2P-520F-B2", "spec": {"port_count": 2, "port_type": "SFP+", "port_speed": "10G", "form_factor": "PCIe"}, "sort_order": 210, "remark": "双口 10G SFP+"},
        {"brand": "新华三", "model": "NIC-25GE-2P-620F-B2", "spec": {"port_count": 2, "port_type": "SFP28", "port_speed": "25G", "form_factor": "PCIe"}, "sort_order": 211, "remark": "双口 25G SFP28"},
        {"brand": "浪潮", "model": "INSPUR 10G 双口", "spec": {"port_count": 2, "port_type": "SFP+", "port_speed": "10G", "form_factor": "PCIe"}, "sort_order": 220, "remark": "双口 10G SFP+"},
        {"brand": "浪潮", "model": "INSPUR 25G 双口", "spec": {"port_count": 2, "port_type": "SFP28", "port_speed": "25G", "form_factor": "PCIe"}, "sort_order": 221, "remark": "双口 25G SFP28"},
        {"brand": "Intel", "model": "X710-T2L (OCP)", "spec": {"port_count": 2, "port_type": "RJ45", "port_speed": "10G", "form_factor": "OCP"}, "sort_order": 300, "remark": "OCP 3.0 双口 10G 电口"},
        {"brand": "NVIDIA", "model": "ConnectX-6 Lx (OCP)", "spec": {"port_count": 2, "port_type": "SFP28", "port_speed": "25G", "form_factor": "OCP"}, "sort_order": 301, "remark": "OCP 3.0 双口 25G"},
        {"brand": "NVIDIA", "model": "ConnectX-5 Ex", "spec": {"port_count": 2, "port_type": "SFP28", "port_speed": "25G", "form_factor": "PCIe"}, "sort_order": 53, "remark": "双口 25G SFP28"},
        {"brand": "NVIDIA", "model": "ConnectX-5 Ex", "spec": {"port_count": 2, "port_type": "QSFP28", "port_speed": "100G", "form_factor": "PCIe"}, "sort_order": 54, "remark": "双口 100G QSFP28"},
        {"brand": "Intel", "model": "XXV710-DA2", "spec": {"port_count": 2, "port_type": "SFP28", "port_speed": "25G", "form_factor": "PCIe"}, "sort_order": 33, "remark": "双口 25G SFP28"},
        {"brand": "NVIDIA", "model": "ConnectX-6 (200G)", "spec": {"port_count": 2, "port_type": "QSFP56", "port_speed": "200G", "form_factor": "PCIe"}, "sort_order": 56, "remark": "双口 200G QSFP56"},
        {"brand": "华为", "model": "SP310", "spec": {"port_count": 2, "port_type": "SFP+", "port_speed": "10G", "form_factor": "PCIe"}, "sort_order": 202, "remark": "双口 10G SFP+"},
        {"brand": "华为", "model": "SP680", "spec": {"port_count": 4, "port_type": "QSFP28", "port_speed": "100G", "form_factor": "PCIe"}, "sort_order": 203, "remark": "四口 100G QSFP28"},
        {"brand": "Broadcom", "model": "BCM57412", "spec": {"port_count": 2, "port_type": "RJ45", "port_speed": "10G", "form_factor": "PCIe"}, "sort_order": 72, "remark": "双口 10G 电口"},
    ],
    "gpu": [
        {"brand": "NVIDIA", "model": "H100 SXM5 80GB", "spec": {"vram_gb": 80, "gpu_memory_type": "HBM3", "cuda_cores": 16896, "tdp_w": 700, "interface": "SXM5", "fp32_tflops": 67}, "sort_order": 10, "remark": "Hopper 架构，旗舰训练卡"},
        {"brand": "NVIDIA", "model": "H100 PCIe 80GB", "spec": {"vram_gb": 80, "gpu_memory_type": "HBM3", "cuda_cores": 14592, "tdp_w": 350, "interface": "PCIe 5.0", "fp32_tflops": 51}, "sort_order": 11, "remark": "Hopper 架构，PCIe 版"},
        {"brand": "NVIDIA", "model": "H200 SXM5 141GB", "spec": {"vram_gb": 141, "gpu_memory_type": "HBM3e", "cuda_cores": 16896, "tdp_w": 700, "interface": "SXM5", "fp32_tflops": 67}, "sort_order": 12, "remark": "Hopper 升级版，大显存"},
        {"brand": "NVIDIA", "model": "B200 SXM5 192GB", "spec": {"vram_gb": 192, "gpu_memory_type": "HBM3e", "cuda_cores": 18432, "tdp_w": 1000, "interface": "SXM5", "fp32_tflops": 90}, "sort_order": 13, "remark": "Blackwell 架构，次世代"},
        {"brand": "NVIDIA", "model": "A100 SXM4 80GB", "spec": {"vram_gb": 80, "gpu_memory_type": "HBM2e", "cuda_cores": 6912, "tdp_w": 400, "interface": "SXM4", "fp32_tflops": 19.5}, "sort_order": 20, "remark": "Ampere 架构，主流训练卡"},
        {"brand": "NVIDIA", "model": "A100 PCIe 80GB", "spec": {"vram_gb": 80, "gpu_memory_type": "HBM2e", "cuda_cores": 6912, "tdp_w": 300, "interface": "PCIe 4.0", "fp32_tflops": 19.5}, "sort_order": 21, "remark": "Ampere 架构，PCIe 版"},
        {"brand": "NVIDIA", "model": "A100 SXM4 40GB", "spec": {"vram_gb": 40, "gpu_memory_type": "HBM2e", "cuda_cores": 6912, "tdp_w": 400, "interface": "SXM4", "fp32_tflops": 19.5}, "sort_order": 22, "remark": "Ampere 架构，40GB 版"},
        {"brand": "NVIDIA", "model": "L40S 48GB", "spec": {"vram_gb": 48, "gpu_memory_type": "GDDR6X", "cuda_cores": 18176, "tdp_w": 350, "interface": "PCIe 4.0", "fp32_tflops": 91.6}, "sort_order": 30, "remark": "Ada Lovelace 架构，推理+图形"},
        {"brand": "NVIDIA", "model": "L40 48GB", "spec": {"vram_gb": 48, "gpu_memory_type": "GDDR6X", "cuda_cores": 18176, "tdp_w": 300, "interface": "PCIe 4.0", "fp32_tflops": 90.5}, "sort_order": 31, "remark": "Ada Lovelace 架构，图形渲染"},
        {"brand": "NVIDIA", "model": "A30 24GB", "spec": {"vram_gb": 24, "gpu_memory_type": "HBM2e", "cuda_cores": 3584, "tdp_w": 165, "interface": "PCIe 4.0", "fp32_tflops": 10.3}, "sort_order": 40, "remark": "Ampere 架构，推理入门"},
        {"brand": "NVIDIA", "model": "A10 24GB", "spec": {"vram_gb": 24, "gpu_memory_type": "GDDR6", "cuda_cores": 9216, "tdp_w": 150, "interface": "PCIe 4.0", "fp32_tflops": 31.2}, "sort_order": 41, "remark": "Ampere 架构，推理+图形"},
        {"brand": "NVIDIA", "model": "T4 16GB", "spec": {"vram_gb": 16, "gpu_memory_type": "GDDR6", "cuda_cores": 2560, "tdp_w": 70, "interface": "PCIe 3.0", "fp32_tflops": 8.1}, "sort_order": 50, "remark": "Turing 架构，低功耗推理"},
        {"brand": "AMD", "model": "Instinct MI300X 192GB", "spec": {"vram_gb": 192, "gpu_memory_type": "HBM3", "compute_units": 304, "tdp_w": 750, "interface": "OAM", "fp32_tflops": 81.7}, "sort_order": 100, "remark": "CDNA 3 架构，大显存"},
        {"brand": "AMD", "model": "Instinct MI250X 128GB", "spec": {"vram_gb": 128, "gpu_memory_type": "HBM2e", "compute_units": 232, "tdp_w": 560, "interface": "OAM", "fp32_tflops": 47.9}, "sort_order": 110, "remark": "CDNA 2 架构"},
        {"brand": "AMD", "model": "Instinct MI210 64GB", "spec": {"vram_gb": 64, "gpu_memory_type": "HBM2e", "compute_units": 104, "tdp_w": 300, "interface": "PCIe 4.0", "fp32_tflops": 22.6}, "sort_order": 120, "remark": "CDNA 2 架构，PCIe 版"},
        {"brand": "Intel", "model": "Data Center GPU Max 1550", "spec": {"vram_gb": 128, "gpu_memory_type": "HBM2e", "execution_units": 128, "tdp_w": 600, "interface": "PCIe 5.0", "fp32_tflops": 52.4}, "sort_order": 150, "remark": "Ponte Vecchio 架构"},
        {"brand": "Intel", "model": "Data Center GPU Max 1100", "spec": {"vram_gb": 48, "gpu_memory_type": "HBM2e", "execution_units": 56, "tdp_w": 300, "interface": "PCIe 5.0", "fp32_tflops": 22.3}, "sort_order": 151, "remark": "Ponte Vecchio 架构，入门"},
        {"brand": "华为", "model": "昇腾 910B 64GB", "spec": {"vram_gb": 64, "gpu_memory_type": "HBM2e", "ai_cores": 80, "tdp_w": 310, "interface": "PCIe 4.0", "fp32_tflops": 32}, "sort_order": 200, "remark": "达芬奇架构，训练卡"},
        {"brand": "华为", "model": "昇腾 310P 24GB", "spec": {"vram_gb": 24, "gpu_memory_type": "LPDDR4X", "ai_cores": 8, "tdp_w": 75, "interface": "PCIe 4.0", "fp32_tflops": 7.2}, "sort_order": 210, "remark": "达芬奇架构，推理卡"},
        {"brand": "寒武纪", "model": "思元 370-S4 32GB", "spec": {"vram_gb": 32, "gpu_memory_type": "LPDDR5", "ai_cores": 32, "tdp_w": 150, "interface": "PCIe 4.0", "fp32_tflops": 12}, "sort_order": 220, "remark": "推理卡"},
        {"brand": "寒武纪", "model": "思元 590 64GB", "spec": {"vram_gb": 64, "gpu_memory_type": "HBM2e", "ai_cores": 64, "tdp_w": 350, "interface": "PCIe 4.0", "fp32_tflops": 28}, "sort_order": 221, "remark": "训练卡"},
        {"brand": "壁仞", "model": "BR100 64GB", "spec": {"vram_gb": 64, "gpu_memory_type": "HBM2e", "compute_units": 128, "tdp_w": 550, "interface": "OAM", "fp32_tflops": 40}, "sort_order": 230, "remark": "训练卡"},
        {"brand": "摩尔线程", "model": "MTT S4000 32GB", "spec": {"vram_gb": 32, "gpu_memory_type": "GDDR6", "compute_units": 64, "tdp_w": 200, "interface": "PCIe 4.0", "fp32_tflops": 15}, "sort_order": 240, "remark": "推理+图形"},
        {"brand": "NVIDIA", "model": "A800 SXM4 80GB", "spec": {"vram_gb": 80, "gpu_memory_type": "HBM2e", "cuda_cores": 6912, "tdp_w": 400, "interface": "SXM4", "fp32_tflops": 19.5}, "sort_order": 23, "remark": "Ampere，中国特供版"},
        {"brand": "NVIDIA", "model": "H800 SXM5 80GB", "spec": {"vram_gb": 80, "gpu_memory_type": "HBM3", "cuda_cores": 16896, "tdp_w": 700, "interface": "SXM5", "fp32_tflops": 67}, "sort_order": 14, "remark": "Hopper，中国特供版"},
        {"brand": "NVIDIA", "model": "L20 48GB", "spec": {"vram_gb": 48, "gpu_memory_type": "GDDR6", "cuda_cores": 11776, "tdp_w": 350, "interface": "PCIe 4.0", "fp32_tflops": 59.8}, "sort_order": 32, "remark": "Ada Lovelace，推理主流"},
        {"brand": "NVIDIA", "model": "L4 24GB", "spec": {"vram_gb": 24, "gpu_memory_type": "GDDR6", "cuda_cores": 7424, "tdp_w": 72, "interface": "PCIe 4.0", "fp32_tflops": 30.3}, "sort_order": 42, "remark": "Ada Lovelace，低功耗推理"},
        {"brand": "NVIDIA", "model": "RTX 6000 Ada 48GB", "spec": {"vram_gb": 48, "gpu_memory_type": "GDDR6", "cuda_cores": 18176, "tdp_w": 300, "interface": "PCIe 4.0", "fp32_tflops": 91.1}, "sort_order": 52, "remark": "Ada Lovelace，图形/推理"},
        {"brand": "NVIDIA", "model": "RTX PRO 6000 Blackwell 96GB", "spec": {"vram_gb": 96, "gpu_memory_type": "GDDR7", "cuda_cores": 24064, "tdp_w": 600, "interface": "PCIe 5.0", "fp32_tflops": 125}, "sort_order": 53, "remark": "Blackwell 架构，工作站旗舰 96GB"},
        {"brand": "NVIDIA", "model": "RTX PRO 6000D Blackwell 84GB", "spec": {"vram_gb": 84, "gpu_memory_type": "GDDR7", "cuda_cores": 19968, "tdp_w": 600, "interface": "PCIe 5.0", "fp32_tflops": 97}, "sort_order": 54, "remark": "Blackwell 架构，6000D 服务器版 84GB"},
        {"brand": "NVIDIA", "model": "RTX 5090 32GB", "spec": {"vram_gb": 32, "gpu_memory_type": "GDDR7", "cuda_cores": 21760, "tdp_w": 575, "interface": "PCIe 5.0", "fp32_tflops": 165}, "sort_order": 55, "remark": "Blackwell 架构，消费级旗舰"},
        {"brand": "NVIDIA", "model": "RTX 4090 24GB", "spec": {"vram_gb": 24, "gpu_memory_type": "GDDR6X", "cuda_cores": 16384, "tdp_w": 450, "interface": "PCIe 4.0", "fp32_tflops": 82.6}, "sort_order": 56, "remark": "Ada Lovelace 架构，消费级旗舰"},
        {"brand": "沐曦", "model": "C500 64GB", "spec": {"vram_gb": 64, "gpu_memory_type": "HBM2e", "compute_units": 128, "tdp_w": 350, "interface": "PCIe 4.0", "fp32_tflops": 26}, "sort_order": 250, "remark": "训练卡"},
        {"brand": "天数智芯", "model": "天垓 100 32GB", "spec": {"vram_gb": 32, "gpu_memory_type": "HBM2", "compute_units": 64, "tdp_w": 250, "interface": "PCIe 4.0", "fp32_tflops": 18}, "sort_order": 260, "remark": "训练卡"},
        {"brand": "摩尔线程", "model": "MTT S3000 32GB", "spec": {"vram_gb": 32, "gpu_memory_type": "GDDR6", "compute_units": 64, "tdp_w": 250, "interface": "PCIe 4.0", "fp32_tflops": 15.2}, "sort_order": 241, "remark": "推理+图形"},
    ],
}


def _dedupe_key(category: str, model: str, spec: dict) -> tuple:
    if category == "disk":
        return (category, model, spec.get("capacity_gb"))
    return (category, model)


def seed():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) as cnt FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = 'component_templates'"
            )
            if cur.fetchone()["cnt"] == 0:
                print("ERROR: component_templates 表不存在，请先执行 component_templates_integration.sql")
                sys.exit(1)

            cur.execute(
                "SELECT id, category, model, spec FROM component_templates "
                "WHERE customer_id IS NULL"
            )
            global_rows = cur.fetchall()
            seen_keys = {}
            to_delete_ids = []
            for row in global_rows:
                try:
                    row_spec = json.loads(row["spec"]) if row["spec"] else {}
                except (ValueError, TypeError):
                    row_spec = {}
                key = _dedupe_key(row["category"], row["model"], row_spec)
                if key in seen_keys:
                    if row["id"] < seen_keys[key]:
                        to_delete_ids.append(seen_keys[key])
                        seen_keys[key] = row["id"]
                    else:
                        to_delete_ids.append(row["id"])
                else:
                    seen_keys[key] = row["id"]
            if to_delete_ids:
                placeholders = ",".join(["%s"] * len(to_delete_ids))
                cur.execute(
                    f"DELETE FROM component_templates WHERE id IN ({placeholders})",
                    to_delete_ids,
                )
            dedupe_deleted = len(to_delete_ids)

            total_inserted = 0
            total_updated = 0

            for category, items in SEED_DATA.items():
                for item in items:
                    spec_json = json.dumps(item["spec"], ensure_ascii=False)
                    cur.execute(
                        "SELECT id, spec FROM component_templates "
                        "WHERE category = %s AND model = %s AND customer_id IS NULL",
                        (category, item["model"]),
                    )
                    candidates = cur.fetchall()
                    existing = None
                    if category == "disk":
                        target_cap = item["spec"].get("capacity_gb")
                        for cand in candidates:
                            try:
                                cand_spec = json.loads(cand["spec"]) if cand["spec"] else {}
                            except (ValueError, TypeError):
                                cand_spec = {}
                            if cand_spec.get("capacity_gb") == target_cap:
                                existing = cand
                                break
                    else:
                        existing = candidates[0] if candidates else None
                    if existing:
                        cur.execute(
                            """
                            UPDATE component_templates
                            SET brand = %s, spec = %s, is_active = 1,
                                sort_order = %s, remark = %s
                            WHERE id = %s
                            """,
                            (item["brand"], spec_json, item["sort_order"], item["remark"], existing["id"]),
                        )
                        total_updated += 1
                    else:
                        cur.execute(
                            """
                            INSERT INTO component_templates
                              (category, customer_id, brand, model, spec, is_active, sort_order, remark)
                            VALUES (%s, NULL, %s, %s, %s, 1, %s, %s)
                            """,
                            (category, item["brand"], item["model"], spec_json, item["sort_order"], item["remark"]),
                        )
                        total_inserted += 1

            conn.commit()
            suffix = f"（清理历史重复 {dedupe_deleted} 条）" if dedupe_deleted else ""
            print(f"种子数据导入完成: 新增 {total_inserted} 条, 更新 {total_updated} 条{suffix}")

            cur.execute(
                "SELECT category, COUNT(*) as cnt FROM component_templates GROUP BY category ORDER BY category"
            )
            print("\n当前各类别数量:")
            for row in cur.fetchall():
                print(f"  {row['category']:8s}: {row['cnt']} 条")
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
