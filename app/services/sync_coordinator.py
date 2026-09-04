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
    """同步协调器：封装事务管理与设备同步逻辑"""

    def __init__(self, ssh_mgr, switch_repo, device_op_lock):
        """
        Args:
            ssh_mgr: SSHManager 实例
            switch_repo: SwitchRepository 实例
            device_op_lock: DeviceOpLock 实例（设备级操作锁）
        """
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
        """统一事务上下文：yield 后广播结构化 SSE 事件。

        用法：
            with sync._db_transaction(switch.device_id, OpType.VLAN_CREATE,
                                      affected_ports=[port]):
                switch_repo.update_port_status_vlan(switch.device_id, port, vlan_id)

        事务提交由 API 层 @transactional 统一管理，此处仅负责广播事件。
        异常时事件不广播，异常继续向上传播。

        Args:
            switch_id:            交换机 device_id（devices.id，用于 SSE 路由和日志）
            op_type:              操作类型（OpType 常量）
            affected_ports:       变更的端口名列表
            affected_vlans:       变更的 VLAN 数据库 ID 列表
            affected_lags:        变更的 LAG 数据库 ID 列表
            affected_connections: 变更的连接 ID 列表
            extra:                额外上下文
        """
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
        """SSH 配置成功后，从设备实时同步三表，commit 并广播结构化 SSE 事件。

        所有 SSH 配置操作统一调用本方法作为唯一的 DB 更新入口，
        消除中间 DB 写入（会被本方法全量覆盖）。
        fetch_port_config 仅做 flush，commit 在此处统一执行。
        刷新失败时 rollback，主操作结果不受影响（仅记录警告日志）。

        P8: 异常分层处理
        - SSHConnectionError：可重试的连接异常（warning）
        - OperationalError：DB 连接失败（error + rollback）
        - 其他 Exception：编程错误（error + rollback + exc_info）

        Args:
            switch_id: 交换机 device_id（devices.id）
            port:      端口名称
            op_type:   SSE 事件操作类型（OpType 常量）
            affected_ports:  变更的端口名列表
            affected_vlans:  变更的 VLAN 数据库 ID 列表
            affected_lags:   变更的 LAG 数据库 ID 列表
            affected_connections: 变更的连接 ID 列表
        """
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
        """从设备读取单个端口的实际链路状态

        用于启用/禁用单端口后获取真实链路状态（替代硬编码 up/admin_down）。
        通过 `display/show interface <port>` 精准查询，经 parse_ports 解析出该端口 status。

        Args:
            switch_id: 交换机 device_id
            port:      端口名称

        Returns:
            Optional[str]: 实际链路状态（up/down/admin_down），查询或解析失败时返回 None
        """
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
        """在已建立的 SSH 连接上同步单端口：实际链路状态 + 配置缓存（连接复用）

        供单端口 enable/disable 合并路径使用，将「读取实际链路状态 + 配置缓存同步」
        合并到配置下发的同一连接，避免额外 SSH 握手，减少等待时间。

        流程：
        1. 读取该端口实际链路状态（display/show interface <port>）→ update_port_status
        2. 读取配置缓存（display current-configuration interface <port>）→ _apply_port_config_text
        3. 广播 SSE（_db_transaction）

        Args:
            conn: 已建立的 SSH 连接（来自 ssh_mgr.get_connection）
            switch: 交换机对象
            port:  端口名称
            op_type: OpType.PORT_ENABLE / OpType.PORT_DISABLE

        Returns:
            Optional[str]: 实际链路状态；读取/解析失败时返回 None（由调用方兜底）
        """
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
        """批量同步多个端口缓存：仅建立 1 个 SSH 连接（连接复用），并合并广播 1 个 SSE 事件。

        用于替代批量操作中的逐端口 _sync_port_from_device，将 O(N) 次 SSH 握手降为 O(1)，
        O(N) 个 SSE 事件降为 1 个。

        - 调用方须已持有设备锁（batch_port_action 已在 device_op_lock 内调用本方法）。
        - 单端口同步失败不影响其他端口（尽力同步），失败端口进入返回值的 failed 列表。
        - 仅物理口（GE/10GE/...）真正复用连接；Vlanif/Eth-Trunk 的成员查询(_get_port_members)
          会额外建连，但批量操作几乎不涉及此类端口，影响可忽略。
        - 合并后的 SSE 事件 affected_ports 为全部端口（含失败端口），由前端一次性刷新。

        Returns:
            {"succeeded": [port, ...], "failed": [(port, reason), ...]}
        """
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
        """获取端口配置（三类处理：普通口 / VLANIF / Eth-Trunk）

        流程：
        1. 查 network_ports.raw_info 缓存（非强制刷新时）
        2. 未命中或强制刷新 → SSH 获取
        3. 写入 network_ports.raw_info，解析成员列表，同步 network_ports / switch_port_ips

        Args:
            device_id: 交换机 device_id（devices.id，统一交换机标识）
        """
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
        """给定端口配置文本，回写 DB 缓存（VLAN/IP/描述/成员）。

        供单端口 fetch_port_config 与批量 bulk_sync_ports_from_device 共用，
        避免解析回写逻辑重复。返回 port_extra（vlan_ports/trunk_members），
        供上层合并进返回结构。
        """
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
            self._update_port_info_cache_if_exists(device_id, port, port_extra)

        self._sync_port_vlan_from_config(device_id, port, config_output, adapter)
        self._sync_port_ips_from_config(device_id, port, config_output, adapter)
        self._sync_port_description_from_config(device_id, port, config_output, adapter)
        return port_extra


    def _get_cached_config(self, switch_id: int, port: str) -> Optional[dict]:
        """从缓存中提取端口配置，若命中返回完整结构，否则返回 None

        Args:
            switch_id: 交换机 ID
            port:      端口名称

        Returns:
            缓存命中时返回 {port_config, updated_at, from_cache, ...}，否则 None
        """
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
        """获取 VLANIF 或 Eth-Trunk 的成员端口列表

        Args:
            switch: 交换机对象
            port: 端口名称（如 Vlanif100 或 Eth-Trunk1）
            port_type: "vlan" 或 "trunk"
        """
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
        """将Eth-Trunk成员端口列表写入link_aggregation_groups表"""
        self.switch_repo.sync_trunk_members(device_id, port, members)

    def _update_port_info_cache_if_exists(
        self, device_id: int, port: str, extra: dict,
    ) -> None:
        """仅当端口已存在于 network_ports 表时，更新其 port_info 缓存"""
        from app.persistence.switch_port_repository import NetworkPort
        row = self.switch_repo.session.query(NetworkPort).filter(
            NetworkPort.device_id == device_id,
            NetworkPort.port_name == port,
        ).first()
        if row:
            existing = row.raw_info
            if isinstance(existing, str):
                try:
                    existing = json.loads(existing)
                except (json.JSONDecodeError, TypeError):
                    existing = {}
            if not isinstance(existing, dict):
                existing = {}
            existing.update(extra)
            row.raw_info = existing
            self.switch_repo.session.flush()

    def _sync_vlan_members(self, device_id: int, port: str, members: list) -> None:
        """将VLAN成员端口列表写入vlans表"""
        self.switch_repo.sync_vlan_members(device_id, port, members)


    def batch_sync_members(self, device_id: int) -> dict:
        """批量同步 VLAN 和链路聚合的成员端口

        使用 display vlan / display eth-trunk（不带 ID）一次性获取所有成员，
        替代逐个端口 SSH 查询，大幅减少 SSH 连接次数。

        Args:
            device_id: 交换机 device_id（devices.id）

        Returns:
            {"vlan_synced": int, "lag_synced": int, "errors": list}
        """
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
        """解析 display vlan 输出，提取每个 VLAN 的成员端口列表

        支持三种输出格式：

        1. S 型表格格式（华为 S 系列交换机，VID 从行首开始）：
            VID  Type    Ports
            --------------------------------------------------------------------------------
            1    common  UT:Eth-Trunk1(D)
            3    common  UT:GE0/0/1(D)      GE0/0/2(D)      GE0/0/3(D)
                            GE0/0/5(U)      GE0/0/6(U)

        2. 核心交换机表格格式（VID 前有缩进）：
            VID          Ports
            --------------------------------------------------------------------------------
               1         UT:Eth-Trunk10(D)  100GE1/0/3(D)   10GE1/0/48(U)
                         TG:10GE1/0/47(D)   10GE1/0/48(U)
               3         UT:Eth-Trunk1(U)   10GE1/0/2(U)

        3. 详细格式（华为 VRP 特有）：
            VLAN ID: 1
            VLAN Type: Common
            ...
            Tagged   Ports: none
            Untagged Ports: 10GE1/0/1  10GE1/0/2

        底部统计行格式为 "VID  Status  Property  MAC-LRN  Statistics  Description"，
        不含端口信息，需排除。

        Returns:
            {vlan_id: [port_name, ...]}
        """
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
        """解析 display eth-trunk 输出，提取每个 Eth-Trunk 的成员端口列表

        输出格式示例：
            Eth-Trunk1's state information is:
            ...
            PortName                      Status      Weight
            10GE1/0/5                     Up          1
            10GE1/0/6                     Down        1

            Eth-Trunk2's state information is:
            ...
            PortName                      Status      Weight
            10GE1/0/8                     Down        1

        Returns:
            {trunk_id: [port_name, ...]}
        """
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
        past_header = False  # 是否已过 PortName 表头行

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
        """从端口配置文本提取 VLAN ID，同步回 network_ports.vlan"""
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
        """从端口配置文本提取 IP，全量同步到 switch_port_ips，并更新 network_ports.ip_address"""
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
        """从端口配置文本提取描述，同步回 network_ports.description"""
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