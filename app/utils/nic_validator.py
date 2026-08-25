# -*- coding: utf-8 -*-
"""
网卡配置校验器

提供网卡配置数据的校验功能,确保配置的合法性和完整性。
适配新的device_nics_port表结构。

变更记录:
  - [Fix #2] prepare_ports_for_db: port_status 由 '空闲' 改为 'free'，
             避免写入非法 Enum 值导致 DB 约束违反
  - [Fix #10] VALID_PORT_SPEEDS 补充 '25G'/'40G'/'400G'/'100M'
"""
from typing import Dict, List, Tuple


class NicValidator:
    """网卡配置校验器"""

    MIN_NIC_COUNT = 1
    MAX_NIC_COUNT = 8

    MIN_PORT_COUNT = 1
    MAX_PORT_COUNT = 16

    VALID_PORT_TYPES = [
        'RJ45',        # 电口（铜缆双绞线）
        'SFP',         # 光口（1G SFP）
        'SFP+',        # 光口（10G SFP+）
        'SFP28',       # 光口（25G SFP28）
        'QSFP+',       # 光口（40G QSFP+）
        'QSFP28',      # 光口（100G QSFP28）
        'QSFP56',      # 光口（200G QSFP56）
        'QSFP-DD',     # 光口（400G QSFP-DD）
    ]

    VALID_PORT_SPEEDS = ['100M', '1G', '10G', '25G', '40G', '100G', '400G']

    @staticmethod
    def validate_nic_config(nics: List[Dict]) -> Tuple[bool, str]:
        """校验网卡配置的合法性

        Args:
            nics: 网卡配置列表

        Returns:
            (is_valid, error_message)
        """
        if not nics:
            return (False, "至少需要配置一个网卡")

        if len(nics) > NicValidator.MAX_NIC_COUNT:
            return (False, f"网卡数量不能超过{NicValidator.MAX_NIC_COUNT}个")

        nic_numbers = set()
        for nic in nics:
            nic_number = nic.get('nic_number')

            if nic_number is None:
                return (False, "网卡编号不能为空")

            if nic_number in nic_numbers:
                return (False, f"网卡编号重复: {nic_number}")
            nic_numbers.add(nic_number)

            is_valid, error_msg = NicValidator.validate_single_nic(nic)
            if not is_valid:
                return (False, error_msg)

        return (True, "")

    @staticmethod
    def validate_single_nic(nic: Dict) -> Tuple[bool, str]:
        """校验单个网卡的配置"""
        nic_number = nic.get('nic_number', '未知')
        ports = nic.get('ports', [])

        if not ports:
            return (False, f"网卡{nic_number}至少需要一个端口")

        if len(ports) > NicValidator.MAX_PORT_COUNT:
            return (False, f"网卡{nic_number}的端口数量不能超过{NicValidator.MAX_PORT_COUNT}个")

        port_numbers = set()
        for port in ports:
            port_number = port.get('port_number')

            if port_number is None:
                return (False, f"网卡{nic_number}的端口编号不能为空")

            if port_number in port_numbers:
                return (False, f"网卡{nic_number}的端口编号重复: {port_number}")
            port_numbers.add(port_number)

            port_type = port.get('port_type')
            if not port_type:
                return (False, f"网卡{nic_number}端口{port_number}的类型不能为空")
            if port_type not in NicValidator.VALID_PORT_TYPES:
                return (
                    False,
                    f"网卡{nic_number}端口{port_number}的类型非法: {port_type}，"
                    f"有效值为: {', '.join(NicValidator.VALID_PORT_TYPES)}"
                )

            speed = port.get('speed')
            if not speed:
                return (False, f"网卡{nic_number}端口{port_number}的速率不能为空")
            if speed not in NicValidator.VALID_PORT_SPEEDS:
                return (
                    False,
                    f"网卡{nic_number}端口{port_number}的速率非法: {speed}，"
                    f"有效值为: {', '.join(NicValidator.VALID_PORT_SPEEDS)}"
                )

        return (True, "")

    @staticmethod
    def validate_port_info(port_type: str, port_speed: str) -> Tuple[bool, str]:
        """校验端口类型和速率的合法性"""
        if port_type not in NicValidator.VALID_PORT_TYPES:
            return (False, f"非法的端口类型: {port_type}")
        if port_speed not in NicValidator.VALID_PORT_SPEEDS:
            return (False, f"非法的端口速率: {port_speed}")
        return (True, "")

    @staticmethod
    def prepare_ports_for_db(device_id: int, nics: List[Dict]) -> List[Dict]:
        """将网卡配置转换为数据库记录格式

        Args:
            device_id: 设备ID
            nics: 网卡配置列表

        Returns:
            可直接插入 device_nics_port 表的记录列表
        """
        ports_data = []

        for nic in nics:
            nic_number = nic.get('nic_number')
            nic_name   = nic.get('nic_name', f'网卡{nic_number}')
            ports      = nic.get('ports', [])

            for port in ports:
                port_number = port.get('port_number')
                port_name   = port.get('port_name', f'{nic_name}-端口{port_number}')
                port_type   = port.get('port_type')
                speed       = port.get('speed')
                description = port.get('description', f'{nic_name} 端口{port_number}')

                ports_data.append({
                    'device_id':   device_id,
                    'nic_number':  nic_number,
                    'port_number': port_number,
                    'port_name':   port_name,
                    'port_type':   port_type,
                    'port_speed':  speed,
                    'port_status': 'free',
                    'description': description,
                })

        return ports_data
