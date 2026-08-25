# -*- coding: utf-8 -*-
"""
同步协调器

从 SwitchConfigService 中提取的同步与事务相关方法，
子服务注入此对象替代 parent 反向引用，消除循环依赖。

职责：
- _db_transaction：统一事务上下文管理器
- _sync_port_from_device：从设备同步端口信息
- fetch_port_config：获取端口配置

P8: _sync_port_from_device 异常分层处理
- SSHConnectionError：可重试的连接异常（warning）
- OperationalError：DB 连接失败（error + rollback）
- 其他 Exception：编程错误（error + rollback + exc_info）
"""
import json
from app.utils.logging import get_logger
from contextlib import contextmanager
from typing import Optional

import sqlalchemy.exc

from app.adapters.adapter_factory import get_adapter
from app.exceptions.system import SSHConnectionError
from app.services.switch_events import emit_resource_change
from app.services.switch_event_schema import OpType
from app.utils.port_name_utils import is_trunk_interface, is_vlan_interface, normalize_port
from app.utils.network_utils import validate_port_name

logger = get_logger(__name__)


class SyncCoordinator:

    def __init__(self, ssh_mgr, switch_repo, device_op_lock):
        self.ssh_mgr = ssh_mgr
        self.switch_repo = switch_repo
        self.device_op_lock = device_op_lock


    @contextmanager
    def _db_transaction(
        self,
        switch_id:            int,
        op_type:              str,
        *,
        affected_ports:       list[str] = None,
        affected_vlans:       list[int] = None,
        affected_lags:        list[int] = None,
        affected_connections: list[int] = None,
        extra:                dict      = None,
    ):
        try:
            yield
            emit_resource_change(
                device_id=switch_id,
                op_type=op_type,
                affected_ports=affected_ports       or [],
                affected_vlans=affected_vlans       or [],
                affected_lags=affected_lags         or [],
                affected_connections=affected_connections or [],
                extra=extra or {},
            )
        except Exception:
            raise


    def _sync_port_from_device(self, switch_id: int, port: str,
                               op_type: str = OpType.PORT_UPDATE,
                               *,
                               affected_ports:  list[str] = None,
                               affected_vlans:  list[int] = None,
                               affected_lags:   list[int] = None,
                               affected_connections: list[int] = None) -> None:
        try:
            with self._db_transaction(
                switch_id, op_type,
                affected_ports=affected_ports or [port],
                affected_vlans=affected_vlans or [],
                affected_lags=affected_lags or [],
                affected_connections=affected_connections or [],
            ):
                if op_type in (OpType.PORT_DISABLE, OpType.PORT_ENABLE):
                    actual_status = self._read_port_link_status(switch_id, port)
                    if actual_status is None:
                        actual_status = (
                            "admin_down" if op_type == OpType.PORT_DISABLE else "up"
                        )
                    self.switch_repo.update_port_status(
                        switch_id, port, actual_status)

                self.fetch_port_config(switch_id, port, force_refresh=True)
            logger.info("端口 %s 配置后缓存刷新成功", port)
        except SSHConnectionError as e:
            logger.warning("SSH 同步失败（可重试）: %s", e)
        except sqlalchemy.exc.OperationalError as e:
            logger.error("DB 连接失败，同步中止: %s", e, exc_info=True)
        except Exception as e:
            logger.error("同步意外异常（编程错误）: %s", e, exc_info=True)

    def _read_port_link_status(self, switch_id: int, port: str) -> Optional[str]:
        switch = self.switch_repo.find_by_device_id(switch_id)
        if not switch:
            logger.warning("读取端口链路状态失败：交换机不存在 device_id=%s", switch_id)
            return None
        adapter = get_adapter(switch.device_type)
        try:
            raw = self.ssh_mgr.send_show_command(
                switch, adapter.get_interface_status_command(port), timeout=60,
            )
        except SSHConnectionError as e:
            logger.warning("读取端口 %s 实际链路状态失败（连接异常）: %s", port, e)
            return None
        except Exception as e:
            logger.warning("读取端口 %s 实际链路状态失败: %s", port, e)
            return None
        if not raw or not raw.strip():
            logger.warning("读取端口 %s 实际链路状态：无输出", port)
            return None
        try:
            target = normalize_port(port).lower()
            for p in adapter.parse_ports(raw):
                if p.port and normalize_port(p.port).lower() == target:
                    return p.status
            logger.warning("读取端口 %s 实际链路状态：输出中未匹配到该端口", port)
        except Exception as e:
            logger.warning("读取端口 %s 实际链路状态解析失败: %s", port, e)
        return None

    def sync_single_port_on_conn(self, conn, switch, port: str, op_type: str) -> Optional[str]:
        adapter = get_adapter(switch.device_type)
        actual_status: Optional[str] = None
        try:
            raw = self.ssh_mgr.execute_show_on_conn(
                conn, adapter.get_interface_status_command(port), timeout=60,
            )
            if raw and raw.strip():
                target = normalize_port(port).lower()
                for p in adapter.parse_ports(raw):
                    if p.port and normalize_port(p.port).lower() == target:
                        actual_status = p.status
                        break
                if actual_status is None:
                    logger.warning("端口 %s 实际链路状态：输出中未匹配到该端口", port)
        except Exception as e:
            logger.warning("端口 %s 读取实际链路状态失败（连接复用路径）: %s", port, e)

        with self._db_transaction(switch.device_id, op_type, affected_ports=[port]):
            self.switch_repo.update_port_status(
                switch.device_id, port,
                actual_status or ("admin_down" if op_type == OpType.PORT_DISABLE else "up"),
            )
            try:
                config_output = self.ssh_mgr.execute_show_on_conn(
                    conn, f"display current-configuration interface {port}", timeout=60,
                )
                if config_output and config_output.strip():
                    self._apply_port_config_text(
                        switch.device_id, port, config_output, switch, adapter,
                    )
            except Exception as e:
                logger.warning("端口 %s 配置缓存同步失败（状态已更新）: %s", port, e)
        return actual_status

    def bulk_sync_ports_from_device(
        self, switch_id: int, ports: list, op_type: str, *, timeout: int = 120,
    ) -> dict:
        switch = self.switch_repo.find_by_device_id(switch_id)
        if not switch:
            logger.warning("批量同步失败：交换机不存在 device_id=%s", switch_id)
            return {"succeeded": [], "failed": [(p, "交换机不存在") for p in ports]}

        adapter = get_adapter(switch.device_type)
        succeeded: list = []
        failed: list = []

        try:
            with self.ssh_mgr.get_connection(switch) as conn:
                for port in ports:
                    try:
                        if not validate_port_name(port):
                            logger.warning("批量同步跳过非法端口名: %s", port)
                            failed.append((port, "端口名格式无效"))
                            continue
                        config_output = self.ssh_mgr.execute_show_on_conn(
                            conn, f"display current-configuration interface {port}", timeout)
                        if not config_output or not config_output.strip():
                            logger.warning("批量同步端口 %s 无配置输出，跳过", port)
                            failed.append((port, "未获取到配置文本"))
                            continue
                        self._apply_port_config_text(switch_id, port, config_output, switch, adapter)
                        succeeded.append(port)
                    except Exception as e:
                        logger.warning("批量同步端口 %s 失败(跳过): %s", port, e)
                        failed.append((port, str(e)))
        except Exception as e:
            logger.error("批量同步建立 SSH 连接失败: %s", e)
            failed = [(p, f"SSH 连接失败: {e}") for p in ports]


        try:
            with self._db_transaction(switch_id, op_type, affected_ports=list(ports)):
                pass
        except Exception as e:
            logger.error("批量同步广播 SSE 事件失败: %s", e)

        return {"succeeded": succeeded, "failed": failed}

    def fetch_port_config(
        self, device_id: int, port: str, force_refresh: bool = False,
    ) -> dict:
        if not force_refresh:
            cached_result = self._get_cached_config(device_id, port)
            if cached_result:
                return cached_result

        switch = self.switch_repo.find_by_device_id(device_id)
        if not switch:
            return {"success": False, "message": "交换机不存在"}

        if not validate_port_name(port):
            return {"success": False, "message": f"端口名称格式无效: {port}"}

        config_output = self.ssh_mgr.send_show_command(
            switch, f"display current-configuration interface {port}",
        )
        if not config_output or not config_output.strip():
            return {"success": False, "message": "未获取到配置文本"}

        adapter = get_adapter(switch.device_type)
        port_extra = self._apply_port_config_text(device_id, port, config_output, switch, adapter)

        cached = self.switch_repo.get_port_config_with_time(device_id, port)
        return {
            "port_config": config_output,
            "updated_at": cached["updated_at"] if cached else None,
            "from_cache": False,
            **port_extra,
        }

    def _apply_port_config_text(
        self, device_id: int, port: str, config_output: str, switch, adapter,
    ) -> dict:
        self.switch_repo.upsert_port_config(device_id, port, config_output)

        port_extra = {}
        if is_vlan_interface(port):
            members = self._get_port_members(switch, port, "vlan")
            port_extra["vlan_ports"] = members
            self._sync_vlan_members(device_id, port, members)
        elif is_trunk_interface(port):
            members = self._get_port_members(switch, port, "trunk")
            port_extra["trunk_members"] = members
            self._sync_trunk_members(device_id, port, members)

        if port_extra:
            self.switch_repo.upsert_port_info_cache(device_id, port, {
                "port_info": json.dumps(port_extra, ensure_ascii=False),
            })

        self._sync_port_vlan_from_config(device_id, port, config_output, adapter)
        self._sync_port_ips_from_config(device_id, port, config_output, adapter)
        self._sync_port_description_from_config(device_id, port, config_output, adapter)
        return port_extra


    def _get_cached_config(self, switch_id: int, port: str) -> Optional[dict]:
        cached = self.switch_repo.get_port_config_with_time(switch_id, port)
        if not cached:
            return None

        result = {
            "port_config": cached["port_config"],
            "updated_at": cached["updated_at"],
            "from_cache": True,
        }
        info = self.switch_repo.get_port_info_cache(switch_id, port)
        if info and info.get("port_info"):
            try:
                extra = json.loads(info["port_info"])
                for key in ("vlan_ports", "trunk_members"):
                    if key in extra:
                        result[key] = extra[key]
            except (json.JSONDecodeError, TypeError):
                pass
        return result

    def _get_port_members(self, switch, port: str, port_type: str) -> list:
        import re

        try:
            id_match = re.search(r"\d+", port)
            if not id_match:
                return []
            port_id = int(id_match.group())

            if port_type == "vlan" and not (1 <= port_id <= 4094):
                logger.warning("端口 %s 提取的 VLAN ID %d 超出合法范围 1-4094，跳过成员获取", port, port_id)
                return []
            if port_type == "trunk" and not (1 <= port_id <= 512):
                logger.warning("端口 %s 提取的 Trunk ID %d 超出合法范围 1-512，跳过成员获取", port, port_id)
                return []

            adapter = get_adapter(switch.device_type)

            if port_type == "vlan":
                cmd = adapter.get_check_vlan_command(port_id)
            else:
                cmd = adapter.get_check_trunk_command(port_id)

            output = self.ssh_mgr.send_show_command(switch, cmd)
            if not output:
                return []

            pattern = (
                r"\b(?:10GE|XGE|GE|GigabitEthernet|XGigabitEthernet|Eth|"
                r"Ten-GigabitEthernet|HundredGigE|40GE|25GE)\S*\d+"
            )
            members = re.findall(pattern, output, re.IGNORECASE)
            port_norm = re.sub(r"\s+", "", port).lower()
            return [m for m in members if re.sub(r"\s+", "", m).lower() != port_norm]
        except Exception as e:
            logger.warning("获取端口 %s 成员列表失败: %s", port, e)
            return []

    def _sync_trunk_members(self, device_id: int, port: str, members: list) -> None:
        self.switch_repo.sync_trunk_members(device_id, port, members)

    def _update_port_info_cache_if_exists(
        self, device_id: int, port: str, extra: dict,
    ) -> None:
        from app.persistence.switch_port_repository import NetworkPort
        row = self.switch_repo.session.query(NetworkPort).filter(
            NetworkPort.device_id == device_id,
            NetworkPort.port_name == port,
        ).first()
        if row:
            existing = {}
            if row.raw_info:
                try:
                    existing = json.loads(row.raw_info)
                except (json.JSONDecodeError, TypeError):
                    pass
            existing.update(extra)
            row.raw_info = json.dumps(existing, ensure_ascii=False)
            self.switch_repo.session.flush()

    def _sync_vlan_members(self, device_id: int, port: str, members: list) -> None:
        self.switch_repo.sync_vlan_members(device_id, port, members)


    def batch_sync_members(self, device_id: int) -> dict:
        results = {"vlan_synced": 0, "lag_synced": 0, "errors": []}

        switch = self.switch_repo.find_by_device_id(device_id)
        if not switch:
            results["errors"].append("交换机不存在")
            return results

        adapter = get_adapter(switch.device_type)

        try:
            vlan_cmd = adapter.get_list_all_vlans_command()
            vlan_output = self.ssh_mgr.send_show_command(switch, vlan_cmd)
            if vlan_output:
                vlan_members_map = self._parse_all_vlan_members(vlan_output)
                for vlan_id, members in vlan_members_map.items():
                    port_name = f"Vlanif{vlan_id}"
                    try:
                        self._sync_vlan_members(device_id, port_name, members)
                        self._update_port_info_cache_if_exists(
                            device_id, port_name, {"vlan_ports": members},
                        )
                        results["vlan_synced"] += 1
                    except Exception as e:
                        results["errors"].append(f"{port_name}: {e}")
            else:
                results["errors"].append("display vlan 无输出")
        except Exception as e:
            results["errors"].append(f"VLAN 批量同步失败: {e}")

        try:
            trunk_cmd = adapter.get_list_all_trunks_command()
            trunk_output = self.ssh_mgr.send_show_command(switch, trunk_cmd)
            if trunk_output:
                trunk_members_map = self._parse_all_trunk_members(trunk_output)
                for trunk_id, members in trunk_members_map.items():
                    from app.utils.port_name_utils import get_trunk_name
                    port_name = get_trunk_name(switch.device_type, trunk_id)
                    try:
                        self._sync_trunk_members(device_id, port_name, members)
                        self._update_port_info_cache_if_exists(
                            device_id, port_name, {"trunk_members": members},
                        )
                        results["lag_synced"] += 1
                    except Exception as e:
                        results["errors"].append(f"{port_name}: {e}")
            else:
                results["errors"].append("display eth-trunk 无输出")
        except Exception as e:
            results["errors"].append(f"链路聚合批量同步失败: {e}")

        return results

    @staticmethod
    def _parse_all_vlan_members(output: str) -> dict[int, list[str]]:
        import re
        from app.utils.port_name_utils import normalize_port

        port_pattern = re.compile(
            r"\b(?:10GE|XGE|GE|GigabitEthernet|XGigabitEthernet|Eth-Trunk|"
            r"Ten-GigabitEthernet|HundredGigE|40GE|25GE|100GE)\S*\d+",
            re.IGNORECASE,
        )
        vlan_s_type_pattern = re.compile(r"^(\d+)\s+common\s+")
        vlan_core_pattern = re.compile(r"^\s+(\d+)\s+")
        vlan_detail_id_pattern = re.compile(r"^\s*VLAN\s+ID\s*:\s*(\d+)", re.IGNORECASE)
        vlan_detail_ports_pattern = re.compile(
            r"^\s*(?:Tagged|Untagged)\s+Ports?\s*:\s*(.*)",
            re.IGNORECASE,
        )

        result = {}
        current_vlan_id = None

        for line in output.splitlines():
            m_detail = vlan_detail_id_pattern.match(line)
            if m_detail:
                current_vlan_id = int(m_detail.group(1))
                if current_vlan_id not in result:
                    result[current_vlan_id] = []
                continue

            m_ports = vlan_detail_ports_pattern.match(line)
            if m_ports and current_vlan_id is not None:
                ports_str = m_ports.group(1).strip()
                if ports_str and ports_str.lower() != "none":
                    ports = port_pattern.findall(ports_str)
                    for p in ports:
                        p_clean = normalize_port(p.strip())
                        if p_clean and p_clean not in result[current_vlan_id]:
                            result[current_vlan_id].append(p_clean)
                continue

            m_s = vlan_s_type_pattern.match(line)
            if m_s:
                current_vlan_id = int(m_s.group(1))
                if current_vlan_id not in result:
                    result[current_vlan_id] = []
                ports = port_pattern.findall(line)
                for p in ports:
                    p_clean = normalize_port(p.strip())
                    if p_clean and p_clean not in result[current_vlan_id]:
                        result[current_vlan_id].append(p_clean)
                continue

            m_core = vlan_core_pattern.match(line)
            if m_core:
                current_vlan_id = int(m_core.group(1))
                if current_vlan_id not in result:
                    result[current_vlan_id] = []
                ports = port_pattern.findall(line)
                for p in ports:
                    p_clean = normalize_port(p.strip())
                    if p_clean and p_clean not in result[current_vlan_id]:
                        result[current_vlan_id].append(p_clean)
                continue

            if current_vlan_id is not None:
                ports = port_pattern.findall(line)
                for p in ports:
                    p_clean = normalize_port(p.strip())
                    if p_clean and p_clean not in result[current_vlan_id]:
                        result[current_vlan_id].append(p_clean)

        return result

    @staticmethod
    def _parse_all_trunk_members(output: str) -> dict[int, list[str]]:
        import re

        trunk_header = re.compile(
            r"Eth-Trunk(\d+)'s\s+state\s+information\s+is\s*:",
            re.IGNORECASE,
        )
        port_pattern = re.compile(
            r"^\s*((?:10GE|XGE|GE|GigabitEthernet|XGigabitEthernet|"
            r"Ten-GigabitEthernet|HundredGigE|40GE|25GE|100GE)\S*\d+)\s+",
            re.IGNORECASE,
        )

        result = {}
        current_trunk_id = None
        past_header = False

        for line in output.splitlines():
            m = trunk_header.search(line)
            if m:
                current_trunk_id = int(m.group(1))
                result[current_trunk_id] = []
                past_header = False
                continue

            if current_trunk_id is not None:
                if "PortName" in line:
                    past_header = True
                    continue

                if past_header:
                    pm = port_pattern.match(line)
                    if pm:
                        port_name = pm.group(1).strip()
                        if port_name not in result[current_trunk_id]:
                            result[current_trunk_id].append(port_name)
                    elif not line.strip():
                        past_header = False

        return result

    def _sync_port_vlan_from_config(
        self, switch_id: int, port: str, config_text: str, adapter=None,
    ) -> None:
        if not adapter:
            switch = self.switch_repo.find_by_device_id(switch_id)
            if not switch:
                return
            adapter = get_adapter(switch.device_type)

        vlan_info = adapter.parse_vlan_info(config_text or "")
        vlan_id = vlan_info.get("pvid")
        try:
            self.switch_repo.update_port_status_vlan(switch_id, port, vlan_id)
        except Exception as e:
            logger.warning("同步端口 VLAN 失败（非致命）: %s", e)

    def _sync_port_ips_from_config(
        self, switch_id: int, port: str, config_text: str, adapter,
    ) -> None:
        try:
            parsed_ips = adapter.parse_existing_ips(config_text or "")
            ip_list = []
            for ip in parsed_ips:
                ip_data = {"ip_address": ip.ip_address, "subnet_mask": ip.subnet_mask, "is_primary": ip.is_primary}
                try:
                    import ipaddress as _ipa
                    ip_data["prefix"] = _ipa.IPv4Network(f"0.0.0.0/{ip.subnet_mask}", strict=False).prefixlen
                except (ValueError, TypeError):
                    ip_data["prefix"] = None
                ip_list.append(ip_data)
            self.switch_repo.sync_port_ips(switch_id, port, ip_list)
            primary_ip = next((ip.ip_address for ip in parsed_ips if ip.is_primary), None)
            self.switch_repo.upsert_port_info_cache(switch_id, port, {
                "ip_address": primary_ip or "",
            })
        except Exception as e:
            logger.warning("同步端口 IP 失败（非致命）: %s", e)

    def _sync_port_description_from_config(
        self, switch_id: int, port: str, config_text: str, adapter=None,
    ) -> None:
        if not adapter:
            switch = self.switch_repo.find_by_device_id(switch_id)
            if not switch:
                return
            adapter = get_adapter(switch.device_type)

        description = adapter.parse_port_description(config_text or "")
        try:
            self.switch_repo.update_port_description(switch_id, port, description)
        except Exception as e:
            logger.warning("同步端口描述失败（非致命）: %s", e)
