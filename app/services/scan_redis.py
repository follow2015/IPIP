from __future__ import annotations

"""扫描流程 Redis 操作统一封装

所有 Phase 通过此类读写 Redis，禁止各 Phase 直接操作 Redis。
封装 MAC 倒排索引、端口反向索引、直连网段索引、
无权限降级映射、扫描进度等操作。
"""
import ipaddress
from app.utils.logging import get_logger

logger = get_logger(__name__)


def get_scan_redis_client():
    from app.services.network_scanner_service import ScanOrchestrator
    redis_client = ScanOrchestrator._get_redis_client()
    if not redis_client:
        from app.utils.cache import cache_manager
        if cache_manager.primary_storage and cache_manager.primary_storage.redis_client:
            redis_client = cache_manager.primary_storage.redis_client
    return redis_client


class ScanRedis:

    TTL_SCAN = 3600

    def __init__(self, redis_client):
        self.r = redis_client


    def mac_index_set(self, scope: str, mac: str, sw_id: int,
                      port: str):
        key = f"mac_index:{scope}:{mac}"
        field = f"{sw_id}:{port}"
        self.r.hset(key, field, 1)
        self.r.expire(key, self.TTL_SCAN)


    def port_mac_add(self, scope: str, sw_id: int,
                     port: str, mac: str):
        key = f"port_mac:{scope}:{sw_id}:{port}"
        self.r.sadd(key, mac)
        self.r.expire(key, self.TTL_SCAN)

    def port_mac_get(self, scope: str, sw_id: int,
                     port: str) -> set[str]:
        key = f"port_mac:{scope}:{sw_id}:{port}"
        result = self.r.smembers(key)
        return result if result else set()


    def port_ip_set(self, scope: str, sw_id: int, port: str,
                    ip_address: str, prefix: int):
        key = f"port_ip:{scope}"
        field = f"{sw_id}|{port}|{ip_address}/{prefix}"
        self.r.hset(key, field, 1)
        self.r.expire(key, self.TTL_SCAN)

    def port_ip_find_by_ip(self, scope: str, ip: str
                           ) -> tuple[int, str] | None:
        key = f"port_ip:{scope}"
        all_entries = self.r.hgetall(key)
        if not all_entries:
            return None
        try:
            ip_obj = ipaddress.ip_address(ip)
        except ValueError:
            return None

        best_prefix = -1
        best_sw_id = None
        best_port = None
        for field in all_entries:
            try:
                first_pipe = field.index("|")
                second_pipe = field.index("|", first_pipe + 1)
                sw_id_str = field[:first_pipe]
                port = field[first_pipe + 1:second_pipe]
                ip_prefix = field[second_pipe + 1:]
                net = ipaddress.ip_network(ip_prefix, strict=False)
                if ip_obj in net and net.prefixlen > best_prefix:
                    best_prefix = net.prefixlen
                    best_sw_id = int(sw_id_str)
                    best_port = port
            except (ValueError, IndexError):
                continue

        if best_sw_id is not None and best_port is not None:
            return best_sw_id, best_port
        return None

    def port_ip_get_ips_by_switch_port(self, scope: str, sw_id: int,
                                        port: str) -> list[str]:
        key = f"port_ip:{scope}"
        all_entries = self.r.hgetall(key)
        if not all_entries:
            return []
        prefix_pattern = f"{sw_id}|{port}|"
        result = []
        for field in all_entries:
            if field.startswith(prefix_pattern):
                ip_prefix = field[len(prefix_pattern):]
                slash_idx = ip_prefix.find("/")
                ip_addr = ip_prefix[:slash_idx] if slash_idx != -1 else ip_prefix
                if ip_addr:
                    result.append(ip_addr)
        return result

    def port_ip_clear(self, scope: str):
        key = f"port_ip:{scope}"
        self.r.delete(key)


    def fallback_set(self, scope: str, no_auth_sw_ip: str,
                     upstream_sw_id: int, upstream_port: str):
        key = f"no_auth_fallback:{scope}"
        self.r.hset(key, no_auth_sw_ip,
                    f"{upstream_sw_id}:{upstream_port}")

    def fallback_get(self, scope: str, no_auth_sw_ip: str
                     ) -> tuple[int, str] | None:
        key = f"no_auth_fallback:{scope}"
        val = self.r.hget(key, no_auth_sw_ip)
        if not val:
            return None
        sw_id_str, port = val.split(":", 1)
        return int(sw_id_str), port

    def fallback_rebuild_from_db(self, scope: str, sw_ext_repo,
                                  sw_repo):
        key = f"no_auth_fallback:{scope}"
        self.r.delete(key)
        if scope.startswith("r:"):
            room_id = int(scope[2:])
            no_auth_list = sw_ext_repo.get_no_auth_switches(room_id)
        elif scope.startswith("vr:"):
            virtual_room_id = int(scope[3:])
            from app.services.virtual_room_service import VirtualRoomService
            from app.persistence.virtual_room_repository import VirtualRoomRepository
            device_ids = VirtualRoomService(VirtualRoomRepository()).get_member_device_ids(virtual_room_id)
            no_auth_list = sw_ext_repo.get_no_auth_switches_by_device_ids(device_ids) if device_ids else []
        else:
            no_auth_list = []

        all_port_ids = []
        for ext in no_auth_list:
            if ext.device and ext.device.switch_ext:
                port_ids = ext.device.switch_ext.uplink_port_ids
                if port_ids and isinstance(port_ids, list) and ext.device.switch_ext.uplink_device_id:
                    all_port_ids.extend(port_ids)

        conn_map: dict = {}
        if all_port_ids:
            from app.models.network_connection import NetworkConnection
            from sqlalchemy import or_
            from sqlalchemy.orm import joinedload
            port_id_set = set(all_port_ids)
            conns = NetworkConnection.query.filter(
                or_(
                    NetworkConnection.local_port_id.in_(port_id_set),
                    NetworkConnection.peer_port_id.in_(port_id_set),
                )
            ).options(
                joinedload(NetworkConnection.local_port),
                joinedload(NetworkConnection.peer_port),
            ).all()
            for conn in conns:
                if conn.local_port_id in port_id_set:
                    conn_map[conn.local_port_id] = conn.peer_port.port_name if conn.peer_port else None
                if conn.peer_port_id in port_id_set:
                    conn_map[conn.peer_port_id] = conn.local_port.port_name if conn.local_port else None

        for ext in no_auth_list:
            uplink_device_id = None
            uplink_port = None
            if ext.device and ext.device.switch_ext:
                uplink_device_id = ext.device.switch_ext.uplink_device_id
                port_ids = ext.device.switch_ext.uplink_port_ids
                if port_ids and isinstance(port_ids, list) and uplink_device_id:
                    uplink_port = conn_map.get(port_ids[0])
            if uplink_device_id and uplink_port:
                sw = sw_repo.find_by_device_id(ext.device_id)
                if sw and sw.ip:
                    self.fallback_set(scope, sw.ip,
                                      uplink_device_id, uplink_port)


    def progress_set(self, scope: str, progress_data: dict):
        key = f"ipm:scan_progress:{scope}"
        mapping = {k: str(v) for k, v in progress_data.items()}
        self.r.hset(key, mapping=mapping)
        self.r.expire(key, 3600)

    def progress_get(self, scope: str) -> dict | None:
        key = f"ipm:scan_progress:{scope}"
        result = self.r.hgetall(key)
        if not result:
            return None
        for k in ("room_id", "total", "completed", "failed"):
            if k in result:
                try:
                    result[k] = int(result[k])
                except (ValueError, TypeError):
                    pass
        for k in ("elapsed_seconds", "eta_seconds"):
            if k in result:
                try:
                    result[k] = float(result[k])
                except (ValueError, TypeError):
                    pass
        return result
