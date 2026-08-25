from __future__ import annotations

"""
设备连接服务

重构说明（v5 → v6）
──────────────────────────────────────────────────────────────
① 消除所有 db.session 直接调用，全部通过 Repository 路由数据访问。
   - db.session.query() → repo 查询方法
   - db.session.get()   → repo.find_by_id() / find_by_id_orm()
   - db.session.delete()→ repo.delete_connection_orm()
   - db.session.flush() → repo 内部 flush
   - db.session.commit()/rollback() → 移除（API 层 @transactional 统一处理）

② 构造函数参数改为必传，消除隐式依赖，便于测试和依赖注入。

③ 导入路径从 app.models.repositories 迁移至 app.persistence。
"""
from app.utils.logging import get_logger
from typing import Dict, List, Optional

from app.persistence.device_connection_repository import DeviceConnectionRepository
from app.persistence.network_connection_repository import NetworkConnectionRepository
from app.persistence.switch_port_repository import NetworkPortRepository
from app.persistence.device_nics_port_repository import DeviceNicsPortRepository
from app.persistence.device_repository import DeviceRepository
from app.services.port_matching_engine import PortMatchingEngine
from app.exceptions.validation import ValidationError
from app.utils.cache import cache_manager

logger = get_logger(__name__)

_NETWORK_DEVICE_TYPES = PortMatchingEngine.NETWORK_DEVICE_TYPES


class DeviceConnectionService:

    def __init__(
        self,
        connection_repo: DeviceConnectionRepository,
        port_repo: NetworkPortRepository,
        n2n_repo: NetworkConnectionRepository,
        nics_port_repo: DeviceNicsPortRepository,
        device_repo: DeviceRepository,
    ):
        self.connection_repo = connection_repo
        self.port_repo       = port_repo
        self.n2n_repo        = n2n_repo
        self.nics_port_repo  = nics_port_repo
        self.device_repo     = device_repo


    @staticmethod
    def derive_connection_status(local_link_status: str | None, peer_link_status: str | None,
                                  local_port_name: str | None = None, peer_port_name: str | None = None) -> str:
        from app.models.network_port import NetworkPort
        return NetworkPort.derive_connection_status(
            local_link_status, peer_link_status, local_port_name, peer_port_name,
        )

    @staticmethod
    def _set_physical_port_up(port_id: int) -> None:
        pass

    @staticmethod
    def _set_physical_port_down(port_id: int) -> None:
        pass


    def get_connection(self, connection_id: int) -> Optional[Dict]:
        return self.connection_repo.find_by_id(connection_id)

    def get_device_connections(self, device_id: int) -> List[Dict]:
        return self.connection_repo.find_by_device(device_id)

    def get_switch_connections(self, switch_device_id: int) -> List[Dict]:
        return self.connection_repo.find_by_switch_device(switch_device_id)

    def get_network_connections(self, device_id: int) -> List[Dict]:
        return self.n2n_repo.find_by_device(device_id)


    def create_connection(self, data: Dict) -> int:
        device_id        = data.get("device_id")
        switch_device_id = data.get("switch_device_id")
        switch_port_id   = data.get("switch_port_id")
        nics_port_id     = data.get("device_nics_port_id")
        link_type        = data.get("link_type", "device_to_network")
        peer_port_id     = data.get("peer_port_id")

        self._validate_device_type_for_link(device_id, switch_device_id, link_type)

        if link_type == "network_to_network":
            validation = self._validate_network_to_network_ports(
                switch_port_id, peer_port_id, device_id, switch_device_id,
                for_update=True,
            )
            derived_status = validation.get("derived_status", "active")

            old_conn = self.n2n_repo.find_existing_by_ports_orm(switch_port_id, peer_port_id)
            if old_conn:
                old_local = old_conn.local_port_id
                old_peer  = old_conn.peer_port_id
                for old_pid in (old_local, old_peer):
                    if old_pid not in (switch_port_id, peer_port_id):
                        self._release_network_port(old_pid)
                        self._set_physical_port_down(old_pid)
                        logger.info("UPSERT: 旧端口 %d 已释放", old_pid)

            n2n_id = self.n2n_repo.create_connection({
                "local_port_id": switch_port_id,
                "peer_port_id": peer_port_id,
                "local_device_id": device_id,
                "peer_device_id": switch_device_id,
                "connection_type": data.get("connection_type"),
                "vlan_id": data.get("vlan_id"),
                "status": derived_status,
                "notes": data.get("notes"),
            })
            self._occupy_network_port(switch_port_id)
            self._occupy_network_port(peer_port_id)
            self._set_physical_port_up(switch_port_id)
            self._set_physical_port_up(peer_port_id)
            connection_id = n2n_id
        else:
            if switch_port_id:
                self._validate_port_for_connect(switch_port_id, switch_device_id, for_update=True)
                self._validate_switch_port_limit(switch_device_id)

            if nics_port_id:
                self._validate_nics_port(nics_port_id, device_id)

            if nics_port_id and switch_port_id:
                self._validate_nics_speed_limit(nics_port_id, switch_port_id)

            if device_id and switch_device_id and switch_port_id:
                if self.connection_repo.exists_connection_for_update(device_id, switch_device_id, switch_port_id):
                    raise ValidationError(
                        f"该设备连接已存在 (设备: {device_id}, 交换机: {switch_device_id}, 端口: {switch_port_id})"
                    )

            connection_id = self.connection_repo.create_connection(data)

            if connection_id:
                if switch_port_id:
                    self._occupy_network_port(switch_port_id)
                    self._set_physical_port_up(switch_port_id)
                    logger.info("NetworkPort %d 已占用，设备: %d", switch_port_id, device_id)

                if nics_port_id:
                    self._occupy_nics_port(nics_port_id)
                    logger.info("NicsPort %d 已占用，设备: %d", nics_port_id, device_id)

        self._invalidate_caches(
            device_ids=[device_id, switch_device_id],
            switch_port_ids=[switch_port_id, peer_port_id] if peer_port_id else ([switch_port_id] if switch_port_id else []),
        )
        logger.info("创建设备连接成功: connection_id=%d", connection_id)
        return connection_id


    def update_connection(self, connection_id: int, data: Dict) -> bool:
        old = self.connection_repo.find_by_id(connection_id)
        if not old:
            raise ValidationError(f"连接不存在 (ID: {connection_id})")

        device_id        = data["device_id"]        if "device_id"        in data else old.get("device_id")
        switch_device_id = data["switch_device_id"] if "switch_device_id" in data else old.get("switch_device_id")
        link_type        = data["link_type"]        if "link_type"        in data else old.get("link_type", "device_to_network")
        new_port_id      = data.get("switch_port_id")
        old_port_id      = old.get("switch_port_id")
        new_nics_port_id = data.get("device_nics_port_id")
        old_nics_port_id = old.get("device_nics_port_id")

        if link_type != "network_to_network":
            if new_port_id and new_port_id != old_port_id:
                self._validate_port_for_connect(new_port_id, switch_device_id, for_update=True)
                self._validate_switch_port_limit(switch_device_id, exclude_port_id=old_port_id)

            if new_nics_port_id and new_nics_port_id != old_nics_port_id:
                self._validate_nics_port(new_nics_port_id, device_id)

        result = self.connection_repo.update_connection(connection_id, data)

        if result and link_type != "network_to_network":
            if old_port_id and old_port_id != new_port_id:
                self._release_network_port(old_port_id)
                self._set_physical_port_down(old_port_id)
                logger.info("旧 NetworkPort %d 已释放", old_port_id)
            if new_port_id:
                self._occupy_network_port(new_port_id)
                self._set_physical_port_up(new_port_id)
                logger.info("新 NetworkPort %d 已占用，设备: %d", new_port_id, device_id)

            if old_nics_port_id and old_nics_port_id != new_nics_port_id:
                self._release_nics_port(old_nics_port_id)
                logger.info("旧 NicsPort %d 已释放", old_nics_port_id)
            if new_nics_port_id:
                self._occupy_nics_port(new_nics_port_id)
                logger.info("新 NicsPort %d 已占用，设备: %d", new_nics_port_id, device_id)

        self._invalidate_caches(
            device_ids=[device_id, switch_device_id],
            switch_port_ids=list(filter(None, [old_port_id, new_port_id])),
        )
        logger.info("更新设备连接成功: connection_id=%d", connection_id)
        return result


    def delete_connection(self, connection_id: int) -> bool:
        conn = self.connection_repo.find_by_id(connection_id)
        if not conn:
            logger.warning("连接不存在: connection_id=%d", connection_id)
            return False

        switch_port_id   = conn.get("switch_port_id")
        nics_port_id     = conn.get("device_nics_port_id")
        device_id        = conn.get("device_id")
        switch_device_id = conn.get("switch_device_id")

        result = self.connection_repo.delete_connection(connection_id)

        if result:
            if switch_port_id:
                self._release_network_port(switch_port_id)
                self._set_physical_port_down(switch_port_id)
                logger.info("NetworkPort %d 已释放", switch_port_id)
            if nics_port_id:
                self._release_nics_port(nics_port_id)
                logger.info("NicsPort %d 已释放", nics_port_id)

        self._invalidate_caches(
            device_ids=[device_id, switch_device_id],
            switch_port_ids=[switch_port_id] if switch_port_id else [],
        )
        logger.info("删除设备连接成功: connection_id=%d", connection_id)
        return result

    def delete_network_connection(self, port_id: int) -> bool:
        conn = self.n2n_repo.find_by_port_for_update_orm(port_id)
        if not conn:
            logger.warning("端口 %d 无 N2N 连接", port_id)
            return False

        local_port_id = conn.local_port_id
        peer_port_id  = conn.peer_port_id

        self.n2n_repo.delete_connection_orm(conn)

        self.port_repo.release_port_and_set_link_down(local_port_id)
        self.port_repo.release_port_and_set_link_down(peer_port_id)

        logger.info("N2N 连接已删除: 端口 %d ↔ %d", local_port_id, peer_port_id)
        return True

    def delete_network_connection_by_id(self, connection_id: int) -> bool:
        conn = self.n2n_repo.find_by_id_for_update_orm(connection_id)
        if not conn:
            logger.warning("连接 %d 不存在", connection_id)
            return False

        local_port_id = conn.local_port_id
        peer_port_id  = conn.peer_port_id

        self.n2n_repo.delete_connection_orm(conn)

        self.port_repo.release_port_and_set_link_down(local_port_id)
        self.port_repo.release_port_and_set_link_down(peer_port_id)

        logger.info("N2N 连接已删除: 端口 %d ↔ %d", local_port_id, peer_port_id)
        return True

    def delete_device_connections(self, device_id: int) -> int:
        connections = self.connection_repo.find_by_device(device_id)
        port_ids_to_invalidate = []
        count = self.connection_repo.delete_device_connections(device_id)

        for conn in connections:
            port_id      = conn.get("switch_port_id")
            nics_port_id = conn.get("device_nics_port_id")
            if port_id:
                self.port_repo.release_port(port_id)
                self._set_physical_port_down(port_id)
                port_ids_to_invalidate.append(port_id)
                logger.info("NetworkPort %d 已释放", port_id)
            if nics_port_id:
                self._release_nics_port(nics_port_id)
                logger.info("NicsPort %d 已释放", nics_port_id)

        n2n_count = self.n2n_repo.delete_by_device(device_id)
        if n2n_count:
            ports = self.port_repo.find_occupied_ports_by_device_orm(device_id)
            for port in ports:
                self.port_repo.release_port_and_set_link_down(port.id)
                port_ids_to_invalidate.append(port.id)

        self._invalidate_caches(
            device_ids=[device_id],
            switch_port_ids=port_ids_to_invalidate,
        )
        total = count + n2n_count
        logger.info("删除设备 %d 的全部连接，D2N %d 条 + N2N %d 条", device_id, count, n2n_count)
        return total


    def _occupy_network_port(self, port_id: int) -> None:
        self.port_repo.occupy_port(port_id)

    def _release_network_port(self, port_id: int) -> None:
        self.port_repo.release_port(port_id)


    def _validate_nics_port(self, nics_port_id: int, device_id: int) -> None:
        port = self.nics_port_repo.find_by_id_orm(nics_port_id)
        if not port:
            raise ValidationError(f"NIC 端口不存在 (ID: {nics_port_id})")
        if port.device_id != device_id:
            raise ValidationError(
                f"端口不属于该设备 (端口ID: {nics_port_id}, 设备ID: {device_id})"
            )
        if not port.is_available():
            raise ValidationError(
                f"NIC 端口不可用: {port.display_name} (状态: {port.port_status})"
            )

    def _validate_nics_speed_limit(self, nics_port_id: int, switch_port_id: int) -> None:
        nics_port = self.nics_port_repo.find_by_id_orm(nics_port_id)
        switch_port_data = self.port_repo.find_by_id(switch_port_id)
        if not nics_port or not switch_port_data:
            return

        nics_speed_mbps = self._parse_speed_to_mbps(nics_port.port_speed)
        switch_speed_mbps = self._parse_speed_to_mbps(switch_port_data.get("speed"))

        if nics_speed_mbps is None or switch_speed_mbps is None:
            return

        if nics_speed_mbps > switch_speed_mbps:
            raise ValidationError(
                f"设备网卡速率超出限制: 网卡 {nics_port.port_speed} ({nics_speed_mbps}Mbps) "
                f"> 对端端口 {switch_port_data.get('speed')} ({switch_speed_mbps}Mbps)，"
                f"网卡速率不能超过对端端口速率"
            )

    @staticmethod
    def _parse_speed_to_mbps(speed_str: str) -> Optional[int]:
        if not speed_str:
            return None
        s = speed_str.strip().upper().replace(" ", "")
        import re
        m = re.match(r'(\d+)', s)
        if not m:
            return None
        value = int(m.group(1))
        if 'T' in s:
            return value * 1_000_000
        if 'G' in s:
            return value * 1_000
        return value

    def _occupy_nics_port(self, nics_port_id: int) -> None:
        self.nics_port_repo.occupy_port(nics_port_id)

    def _release_nics_port(self, nics_port_id: int) -> None:
        self.nics_port_repo.release_port(nics_port_id)


    def _validate_network_to_network_ports(
        self,
        local_port_id: int,
        peer_port_id: int,
        device_id: int,
        switch_device_id: int,
        for_update: bool = False,
    ) -> dict:
        if not local_port_id:
            raise ValidationError("network_to_network 必须指定本机端口")
        if not peer_port_id:
            raise ValidationError("network_to_network 必须指定对端端口")
        if local_port_id == peer_port_id:
            raise ValidationError("本机端口和对端端口不能相同")

        find_fn = self.port_repo.find_by_id_for_update if for_update else self.port_repo.find_by_id
        local_port = find_fn(local_port_id)
        if not local_port:
            raise ValidationError(f"本机端口不存在 (ID: {local_port_id})")
        if local_port.get("device_id") != device_id:
            raise ValidationError(
                f"本机端口不属于当前设备 (端口ID: {local_port_id}, 设备ID: {device_id})"
            )

        peer_port = find_fn(peer_port_id)
        if not peer_port:
            raise ValidationError(f"对端端口不存在 (ID: {peer_port_id})")
        if peer_port.get("device_id") != switch_device_id:
            raise ValidationError(
                f"对端端口不属于指定设备 (端口ID: {peer_port_id}, 设备ID: {switch_device_id})"
            )

        local_status = local_port.get("usage_status")
        peer_status = peer_port.get("usage_status")
        local_link = local_port.get("link_status")
        peer_link = peer_port.get("link_status")
        derived_status = "active"
        if local_status not in ("free", "occupied") or peer_status not in ("free", "occupied"):
            derived_status = "inactive"
        elif local_link not in ("up", None) or peer_link not in ("up", None):
            derived_status = "inactive"

        local_name = (local_port.get("port_name") or "").lower()
        peer_name = (peer_port.get("port_name") or "").lower()
        local_is_trunk = "trunk" in local_name or "eth-trunk" in local_name
        peer_is_trunk = "trunk" in peer_name or "eth-trunk" in peer_name
        if local_is_trunk != peer_is_trunk:
            if local_is_trunk:
                raise ValidationError(
                    f"Eth-Trunk 端口只能对接 Eth-Trunk 端口，"
                    f"对端端口 {peer_port.get('port_name')} 不是 Eth-Trunk"
                )
            else:
                raise ValidationError(
                    f"Eth-Trunk 端口只能对接 Eth-Trunk 端口，"
                    f"本机端口 {local_port.get('port_name')} 不是 Eth-Trunk"
                )

        return {"derived_status": derived_status}


    def _validate_device_type_for_link(
        self, device_id: int, switch_device_id: int, link_type: str
    ) -> None:
        device = self.device_repo.find_by_id(device_id)
        target = self.device_repo.find_by_id(switch_device_id)
        if not device or not target:
            raise ValidationError("设备不存在")

        is_valid, msg = PortMatchingEngine.validate_device_type_for_connection(
            device.device_type, target.device_type, link_type
        )
        if not is_valid:
            raise ValidationError(msg)

    def _validate_port_for_connect(
        self, switch_port_id: int, switch_device_id: int, for_update: bool = False
    ) -> None:
        find_fn = self.port_repo.find_by_id_for_update if for_update else self.port_repo.find_by_id
        port = find_fn(switch_port_id)
        if not port:
            raise ValidationError(f"端口不存在 (ID: {switch_port_id})")
        if port.get("device_id") != switch_device_id:
            raise ValidationError(
                f"端口不属于指定交换机 (端口ID: {switch_port_id}, 交换机ID: {switch_device_id})"
            )
        status = port.get("usage_status")
        if status != "free":
            port_name = port.get("port_name")
            raise ValidationError(f"端口状态为 '{status}'，无法连接 (端口: {port_name})")

    def _validate_switch_port_limit(
        self, switch_device_id: int, exclude_port_id: int = None
    ) -> None:
        active_ports = self.port_repo.find_active_ports(switch_device_id)
        total_active = len(active_ports)
        used_count   = sum(1 for p in active_ports if p.get("usage_status") == "occupied")
        if exclude_port_id:
            used_count = max(0, used_count - 1)
        if used_count >= total_active:
            raise ValidationError(
                f"交换机端口已满，无法创建新连接 (已用: {used_count}/{total_active})"
            )


    def _invalidate_caches(
        self,
        device_ids: List[Optional[int]] = None,
        switch_port_ids: List[Optional[int]] = None,
    ) -> None:
        seen_devices = set()
        for did in (device_ids or []):
            if did is not None and did not in seen_devices:
                seen_devices.add(did)
                cache_manager.invalidate_pattern(f"device:{did}:*")

        seen_ports = set()
        for pid in (switch_port_ids or []):
            if pid is not None and pid not in seen_ports:
                seen_ports.add(pid)
                cache_manager.invalidate_pattern(f"switch_port:{pid}:*")


device_connection_service = DeviceConnectionService(
    connection_repo=DeviceConnectionRepository(),
    port_repo=NetworkPortRepository(),
    n2n_repo=NetworkConnectionRepository(),
    nics_port_repo=DeviceNicsPortRepository(),
    device_repo=DeviceRepository(),
)
