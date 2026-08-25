from __future__ import annotations
# -*- coding: utf-8 -*-
"""扫描流程 Redis 操作统一封装

所有 Phase 通过此类读写 Redis，禁止各 Phase 直接操作 Redis。
封装 MAC 倒排索引、端口反向索引、直连网段索引、
无权限降级映射、扫描进度等操作。
"""
import ipaddress
from app.utils.logging import get_logger

logger = get_logger(__name__)


def get_scan_redis_client():
    """获取扫描流程可用的 Redis 客户端

    优先使用 ScanOrchestrator 的连接，回退到 cache_manager。
    供 API 层统一调用，避免重复的 fallback 逻辑。
    """
    from app.services.network_scanner_service import ScanOrchestrator
    redis_client = ScanOrchestrator._get_redis_client()
    if not redis_client:
        from app.utils.cache import cache_manager
        if cache_manager.primary_storage and cache_manager.primary_storage.redis_client:
            redis_client = cache_manager.primary_storage.redis_client
    return redis_client


class ScanRedis:
    """统一封装扫描流程的 Redis 操作

    提供以下功能模块：
    - MAC 倒排索引：MAC → 端口候选（写入，供拓扑图遍历读取）
    - 端口反向索引：端口 → MAC 集合
    - 端口 IP 索引：端口配置的 IP → 端口（Phase 0c 写入，Phase 1 路由同步查询）
    - 无权限降级映射：无权限交换机IP → 上联交换机+端口
    - 扫描进度：机房扫描阶段跟踪
    """

    TTL_SCAN = 3600   # mac_index / port_mac / port_ip 的 TTL（秒）

    def __init__(self, redis_client):
        """初始化 ScanRedis

        Args:
            redis_client: 原生 Redis 客户端实例
        """
        self.r = redis_client


    def mac_index_set(self, scope: str, mac: str, sw_id: int,
                      port: str):
        """写入 MAC 倒排索引

        Args:
            scope: 扫描范围标识，"r:{room_id}" 或 "vr:{virtual_room_id}"
            mac: 归一化 MAC 地址
            sw_id: 交换机 devices.id
            port: 归一化端口名
        """
        key = f"mac_index:{scope}:{mac}"
        field = f"{sw_id}:{port}"
        self.r.hset(key, field, 1)
        self.r.expire(key, self.TTL_SCAN)


    def port_mac_add(self, scope: str, sw_id: int,
                     port: str, mac: str):
        """添加端口→MAC 反向索引（用于 Phase 5 L2 降级）

        Args:
            scope: 扫描范围标识
            sw_id: 交换机 devices.id
            port: 归一化端口名
            mac: 归一化 MAC 地址
        """
        key = f"port_mac:{scope}:{sw_id}:{port}"
        self.r.sadd(key, mac)
        self.r.expire(key, self.TTL_SCAN)

    def port_mac_get(self, scope: str, sw_id: int,
                     port: str) -> set[str]:
        """获取端口上的所有 MAC

        Args:
            scope: 扫描范围标识
            sw_id: 交换机 devices.id
            port: 归一化端口名

        Returns:
            set[str]: 该端口上的 MAC 地址集合
        """
        key = f"port_mac:{scope}:{sw_id}:{port}"
        result = self.r.smembers(key)
        return result if result else set()


    def port_ip_set(self, scope: str, sw_id: int, port: str,
                    ip_address: str, prefix: int):
        """写入端口 IP 索引（Phase 0 采集后写入，Phase 1 路由同步时查询）

        Args:
            scope: 扫描范围标识
            sw_id: 交换机 devices.id
            port: 归一化端口名
            ip_address: 端口 IP 地址
            prefix: 子网前缀长度
        """
        key = f"port_ip:{scope}"
        field = f"{sw_id}|{port}|{ip_address}/{prefix}"
        self.r.hset(key, field, 1)
        self.r.expire(key, self.TTL_SCAN)

    def port_ip_find_by_ip(self, scope: str, ip: str
                           ) -> tuple[int, str] | None:
        """在端口 IP 索引中查找 IP 所属网段（最长前缀匹配）

        供 _resolve_unknown_ports 推断 port="Unknown" 的路由端口。

        Args:
            scope: 扫描范围标识
            ip: 待查找的 IP 地址

        Returns:
            tuple[int, str] | None: (sw_id, port) 或 None
        """
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
        """查询指定交换机端口上配置的所有 IP 地址

        供 RouteSync 获取 Vlanif 端口的真实 IP 地址（替代 _infer_gateway 猜测）。

        Args:
            scope: 扫描范围标识
            sw_id: 交换机 devices.id
            port: 归一化端口名

        Returns:
            list[str]: 该端口上配置的 IP 地址列表（不含前缀），无结果时返回空列表
        """
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
        """清除端口 IP 索引（扫描结束后调用）"""
        key = f"port_ip:{scope}"
        self.r.delete(key)


    def fallback_set(self, scope: str, no_auth_sw_ip: str,
                     upstream_sw_id: int, upstream_port: str):
        """写入降级映射

        Args:
            scope: 扫描范围标识
            no_auth_sw_ip: 无权限交换机的管理IP
            upstream_sw_id: 上联交换机 devices.id
            upstream_port: 上联交换机上的端口（已归一化）
        """
        key = f"no_auth_fallback:{scope}"
        self.r.hset(key, no_auth_sw_ip,
                    f"{upstream_sw_id}:{upstream_port}")

    def fallback_get(self, scope: str, no_auth_sw_ip: str
                     ) -> tuple[int, str] | None:
        """查询降级映射

        Args:
            scope: 扫描范围标识
            no_auth_sw_ip: 无权限交换机的管理IP

        Returns:
            tuple[int, str] | None: (upstream_sw_id, upstream_port) 或 None
        """
        key = f"no_auth_fallback:{scope}"
        val = self.r.hget(key, no_auth_sw_ip)
        if not val:
            return None
        sw_id_str, port = val.split(":", 1)
        return int(sw_id_str), port

    def fallback_rebuild_from_db(self, scope: str, sw_ext_repo,
                                  sw_repo):
        """从 switch_credentials 数据库表重建 no_auth_fallback Redis 映射

        Args:
            scope: 扫描范围标识
            sw_ext_repo: SwitchExtRepository 实例
            sw_repo: SwitchRepository 实例
        """
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
        """设置扫描进度（对齐 ScanProgress.to_dict() 格式）

        Args:
            scope: 扫描范围标识
            progress_data: ScanProgress.to_dict() 格式的进度数据
        """
        key = f"ipm:scan_progress:{scope}"
        mapping = {k: str(v) for k, v in progress_data.items()}
        self.r.hset(key, mapping=mapping)
        self.r.expire(key, 3600)

    def progress_get(self, scope: str) -> dict | None:
        """获取扫描进度

        Args:
            scope: 扫描范围标识

        Returns:
            dict | None: 包含 total, completed, failed, phase 等字段的字典，或 None
        """
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
