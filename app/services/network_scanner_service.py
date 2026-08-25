from __future__ import annotations

"""全量扫描编排服务

ScanOrchestrator 替换原 NetworkScannerService，
严格按 Phase 1→2→3→4→5 顺序执行。
"""
from app.utils.logging import get_logger
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, Optional

from app.adapters.adapter_factory import get_adapter
from app.core.enums import SwitchDeviceTypeCode
from app.infra import SSHManager
from app.persistence.switch_repo import SwitchRepository
from app.persistence.switch_ext_repository import SwitchExtRepository
from app.persistence.ip_repositories import IPManagerRepository
from app.persistence.virtual_room_repository import VirtualRoomRepository
from app.services.scan_context import (
    SwitchContext, ParsedRoute, ParsedArpEntry, ParsedMacEntry,
)
from app.services.scan_redis import ScanRedis
from app.services.ip_route_service import RouteSync, NexthopResolver
from app.services.ip_mac_service import MacIndexBuilder, detect_uplink_ports
from app.services.ip_arp_service import ArpSync
from app.services.scan_degrader import NoAuthL3Degrader, NoAuthL2Degrader
from app.utils.port_name_utils import normalize_port
from app.utils.network_utils import normalize_mac_address
from app.utils.transactional import transaction_checkpoint

logger = get_logger(__name__)


@dataclass
class ScanProgress:
    scope: str = ""
    room_id: int = 0
    total_switches: int = 0
    completed: int = 0
    failed: int = 0
    current_phase: str = ""
    reason: str = ""
    start_time: float = 0
    switch_timings: Dict[int, float] = field(default_factory=dict)

    def start(self) -> None:
        self.start_time = time.time()

    def to_dict(self) -> dict:
        elapsed = time.time() - self.start_time if self.start_time else 0
        remaining = self.total_switches - self.completed - self.failed
        eta = (elapsed / max(self.completed, 1) * remaining) if remaining > 0 and self.completed > 0 else 0
        return {
            "scope": self.scope,
            "room_id": self.room_id,
            "total": self.total_switches,
            "completed": self.completed,
            "failed": self.failed,
            "phase": self.current_phase,
            "reason": self.reason,
            "elapsed_seconds": round(elapsed, 1),
            "eta_seconds": round(eta, 1),
        }

    def save_to_redis(self) -> None:
        try:
            from app.services.scan_redis import ScanRedis
            from app.utils.cache import cache_manager
            redis_client = (
                cache_manager.primary_storage.redis_client
                if cache_manager.primary_storage else None
            )
            if redis_client:
                sr = ScanRedis(redis_client)
                sr.progress_set(self.scope or str(self.room_id), self.to_dict())
        except Exception:
            logger.warning("推送扫描进度到Redis失败: scope=%s", self.scope or self.room_id, exc_info=True)


def get_scan_progress(scope: str) -> Optional[dict]:
    try:
        from app.utils.cache import cache_manager
        key = f"ipm:scan_progress:{scope}"
        redis_client = (
            cache_manager.primary_storage.redis_client
            if cache_manager.primary_storage else None
        )
        if redis_client:
            result = redis_client.hgetall(key)
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
    except Exception:
        logger.warning("获取扫描进度失败: scope=%s", scope, exc_info=True)
    return None


def _resolve_uplink_port_name(uplink_port_ids, uplink_device_id=None) -> str | None:
    if not uplink_port_ids or not isinstance(uplink_port_ids, list):
        return None
    from app.models.network_connection import NetworkConnection
    from app.models.network_port import NetworkPort
    from sqlalchemy import or_

    first_port_id = uplink_port_ids[0]

    conn = NetworkConnection.query.filter(
        or_(
            NetworkConnection.local_port_id == first_port_id,
            NetworkConnection.peer_port_id == first_port_id,
        )
    ).first()
    if conn:
        if conn.local_port_id == first_port_id:
            return conn.peer_port.port_name if conn.peer_port else None
        else:
            return conn.local_port.port_name if conn.local_port else None

    port = NetworkPort.query.get(first_port_id)
    return port.port_name if port else None


@dataclass
class SwitchMeta:
    id: int
    cred_id: int
    ip: str
    device_type: str
    has_ssh: bool
    layer: int
    is_core: bool
    uplink_sw_id: int | None
    uplink_port: str | None
    room_id: int
    scope: str = ""


class ScanOrchestrator:

    def __init__(self, ssh_manager=None, redis_client=None):
        self.ssh_mgr = ssh_manager or SSHManager()
        self.sw_repo = SwitchRepository()
        self.sw_ext_repo = SwitchExtRepository()
        self.ip_repo = IPManagerRepository(self.sw_repo.session)
        self.vr_repo = VirtualRoomRepository(self.sw_repo.session)

        self._redis_client = redis_client or self._get_redis_client()
        self.scan_redis = ScanRedis(self._redis_client) if self._redis_client else None

        self.route_sync = RouteSync()
        self.mac_builder = MacIndexBuilder()
        self.arp_sync = ArpSync(self.ip_repo)
        self.nexthop = NexthopResolver()

    @staticmethod
    def _get_redis_client():
        try:
            from app.utils.cache import cache_manager
            if cache_manager.primary_storage and cache_manager.primary_storage.redis_client:
                return cache_manager.primary_storage.redis_client
        except Exception:
            logger.debug("获取Redis客户端失败", exc_info=True)
        return None

    def full_scan(self, room_id: int = None, virtual_room_id: int = None) -> dict:
        if virtual_room_id:
            scope = f"vr:{virtual_room_id}"
            all_sw = self._load_switch_metas_by_virtual_room(virtual_room_id)
        else:
            scope = f"r:{room_id}"
            all_sw = self._load_switch_metas(room_id)

        if not all_sw:
            logger.warning("full_scan: 无可用交换机，scope=%s", scope)
            return {"scope": scope, "status": "skipped", "reason": "no_switches"}

        scan_start = time.time()
        sr = self.scan_redis

        def _emit_progress():
            progress_dict = progress.to_dict()
            if sr:
                sr.progress_set(scope, progress_dict)
            try:
                from app.services.switch_events import emit_global_event
                emit_global_event("scan_progress", progress_dict)
            except Exception as e:
                logger.warning("推送扫描进度 SSE 事件失败: %s", e)

        if sr:
            try:
                progress_key = f"ipm:scan_progress:{scope}"
                key_type = sr.r.type(progress_key)
                if key_type and key_type != b'hash' and key_type != 'hash':
                    sr.r.delete(progress_key)
            except Exception:
                logger.debug("清理旧进度key失败: key=%s", progress_key, exc_info=True)

        SCAN_LOCK_TTL = 7200
        acquired_locks = []
        if sr:
            for sw in all_sw:
                lock_key = f"scan_lock:{sw.id}"
                existing = sr.r.get(lock_key)
                if existing:
                    existing_str = existing if isinstance(existing, str) else existing.decode()
                    if existing_str == scope:
                        sr.r.expire(lock_key, SCAN_LOCK_TTL)
                        acquired_locks.append(lock_key)
                        continue
                    logger.error("scan_lock 获取失败: device_id=%d, scope=%s", sw.id, scope)
                    for lk in acquired_locks:
                        sr.r.delete(lk)
                    return {"scope": scope, "status": "failed", "reason": f"scan_lock_conflict:{sw.id}"}
                if sr.r.set(lock_key, scope, nx=True, ex=SCAN_LOCK_TTL):
                    acquired_locks.append(lock_key)
                else:
                    for lk in acquired_locks:
                        sr.r.delete(lk)
                    logger.error("scan_lock 获取失败: device_id=%d, scope=%s", sw.id, scope)
                    return {"scope": scope, "status": "failed", "reason": f"scan_lock_conflict:{sw.id}"}

        import threading
        heartbeat_stop = threading.Event()

        def _heartbeat():
            while not heartbeat_stop.wait(1800):
                if sr:
                    for lk in acquired_locks:
                        sr.r.expire(lk, SCAN_LOCK_TTL)

        heartbeat_thread = threading.Thread(target=_heartbeat, daemon=True)
        heartbeat_thread.start()

        try:
            if sr:
                sr.progress_set(scope, {"scope": scope, "room_id": room_id or 0,
                                         "total": len(all_sw), "completed": 0, "failed": 0,
                                         "phase": "准备中", "elapsed_seconds": 0, "eta_seconds": 0})

            authorized = [s for s in all_sw if s.has_ssh]

            progress = ScanProgress(scope=scope, room_id=room_id or 0)
            progress.total_switches = len(all_sw)
            progress.start()

            if sr:
                sr.fallback_rebuild_from_db(scope, self.sw_ext_repo, self.sw_repo)
            progress.current_phase = "准备中"
            _emit_progress()

            progress.current_phase = "collecting"
            _emit_progress()
            valid_ctxs, failed = self._collect_all(authorized)
            progress.failed = len(failed)
            progress.completed = len(valid_ctxs)
            if failed:
                logger.warning("[Scan] %d 台采集失败: %s", len(failed), failed)

            progress.current_phase = "phase0_port_info"
            _emit_progress()
            from app.services.switch_info_service import SwitchInfoService
            from flask import current_app

            app_ref = current_app._get_current_object()

            def collect_port_one(device_id: int):
                with app_ref.app_context():
                    from app.services.switch_info_service import SwitchInfoService
                    from extensions import db
                    svc = SwitchInfoService()
                    try:
                        with transaction_checkpoint(svc.sw_repo.session, f"phase0:port:{device_id}"):
                            return svc.collect_port_info(device_id)
                    finally:
                        db.session.remove()

            with ThreadPoolExecutor(max_workers=min(10, len(authorized))) as pool:
                futures = {pool.submit(collect_port_one, sw.id): sw
                           for sw in authorized}
                for f in as_completed(futures):
                    sw = futures[f]
                    try:
                        f.result(timeout=60)
                    except Exception as e:
                        logger.error("[Phase0] %s 端口采集失败: %s", sw.ip, e)

            progress.current_phase = "phase0b_device_info"
            _emit_progress()

            def collect_info_one(device_id: int):
                with app_ref.app_context():
                    from app.services.switch_info_service import SwitchInfoService
                    from extensions import db
                    svc = SwitchInfoService()
                    try:
                        with transaction_checkpoint(svc.sw_repo.session, f"phase0b:info:{device_id}"):
                            return svc.collect_device_info(device_id)
                    finally:
                        db.session.remove()

            with ThreadPoolExecutor(max_workers=min(5, len(authorized))) as pool:
                futures = {pool.submit(collect_info_one, sw.id): sw
                           for sw in authorized}
                for f in as_completed(futures):
                    sw = futures[f]
                    try:
                        f.result(timeout=90)
                    except Exception as e:
                        logger.error("[Phase0b] %s 设备信息采集失败: %s", sw.ip, e)

            try:
                device_ids = [sw.id for sw in authorized]
                if device_ids:
                    port_ip_rows = self.sw_repo.get_port_ips_by_device_ids(device_ids)
                    for row in port_ip_rows:
                        sr.port_ip_set(scope, row[0], row[1], row[2], row[3] or 24)
                    logger.info("[Phase0c] 端口IP索引已加载到Redis: %d 条", len(port_ip_rows))
            except Exception as e:
                logger.warning("[Phase0c] 端口IP索引加载失败（不影响后续流程）: %s", e)

            progress.current_phase = "phase0d_sync_members"
            _emit_progress()
            from app.services.sync_coordinator import SyncCoordinator
            from app.services.device_op_lock import DeviceOpLock

            coordinator = SyncCoordinator(
                SSHManager(), SwitchRepository(), DeviceOpLock()
            )
            for sw in authorized:
                try:
                    with transaction_checkpoint(self.sw_repo.session, f"phase0d:sync:{sw.id}"):
                        result = coordinator.batch_sync_members(sw.id)
                    if result.get("lag_synced") or result.get("vlan_synced"):
                        logger.info(
                            f"[Phase0d] {sw.ip} 成员同步: "
                            f"VLAN={result.get('vlan_synced', 0)}, "
                            f"LAG={result.get('lag_synced', 0)}"
                        )
                    if result.get("errors"):
                        logger.warning(
                            f"[Phase0d] {sw.ip} 同步错误: {result['errors']}"
                        )
                except Exception as e:
                    logger.error("[Phase0d] %s 成员同步失败: %s", sw.ip, e)

            progress.current_phase = "phase1b_topology_build"
            _emit_progress()
            from app.services.topology_graph import build_topology_graph
            topology_graph = build_topology_graph(scope, all_sw, self.sw_repo.session)

            if len(all_sw) > 1 and len(topology_graph.links) == 0:
                logger.error("N2N连接缺失：交换机数=%d 但无连接记录，扫描中止",
                             len(all_sw),
                             extra={"phase": "topology_build", "scope": scope})
                heartbeat_stop.set()
                for lk in acquired_locks:
                    sr.r.delete(lk)
                progress.current_phase = "failed"
                progress.reason = "missing_n2n_connections"
                progress.failed = 1
                _emit_progress()
                return {
                    "scope": scope,
                    "status": "failed",
                    "reason": "missing_n2n_connections",
                    "message": f"当前范围有 {len(all_sw)} 台交换机但无 N2N 端口连接记录，请先在「网络连接」中创建交换机间的端口连接，再重新扫描。",
                }

            topology_warnings = _validate_topology_coverage(all_sw, topology_graph)
            for w in topology_warnings:
                logger.warning(w, extra={"phase": "topology_build", "scope": scope})

            progress.current_phase = "phase1_route_sync"
            _emit_progress()
            for ctx in valid_ctxs:
                if ctx.layer == 3:
                    try:
                        with transaction_checkpoint(self.sw_repo.session, f"phase1:route:{ctx.sw_id}"):
                            self.route_sync.sync(ctx, self.sw_repo.session, sr, topology_graph=topology_graph)
                    except Exception as e:
                        logger.error("[Phase1] 交换机 %s 路由同步失败: %s", ctx.ip, e)

            progress.current_phase = "phase2_mac_index"
            _emit_progress()
            for ctx in valid_ctxs:
                self.mac_builder.build(ctx, sr)

            progress.current_phase = "phase3_arp_sync"
            _emit_progress()
            try:
                with transaction_checkpoint(self.sw_repo.session, "phase3:arp_sync"):
                    self.arp_sync.sync_all(valid_ctxs, self.sw_repo.session, sr, topology_graph=topology_graph)
            except Exception as e:
                logger.error("[Phase3] ARP 同步失败: %s", e)

            progress.current_phase = "phase4_nexthop"
            _emit_progress()
            try:
                with transaction_checkpoint(self.sw_repo.session, "phase4:nexthop"):
                    self.nexthop.resolve(scope, self.sw_repo.session)
            except Exception as e:
                logger.error("[Phase4] Nexthop 推断失败: %s", e)

            progress.current_phase = "phase5_degrade"
            _emit_progress()
            no_auth_sws = [s for s in all_sw if not s.has_ssh]
            for sw in no_auth_sws:
                try:
                    with transaction_checkpoint(self.sw_repo.session, f"phase5:degrade:{sw.id}"):
                        if sw.layer == 3:
                            NoAuthL3Degrader().degrade(
                                sw.ip, scope, self.sw_repo.session, sr
                            )
                        elif sw.layer == 2:
                            NoAuthL2Degrader().degrade(
                                sw.ip, scope, valid_ctxs, self.sw_repo.session, sr
                            )
                except Exception as e:
                    logger.error("[Phase5] 降级处理 %s 失败: %s", sw.ip, e)

            progress.current_phase = "phase6_ip_reconcile"
            _emit_progress()

            from app.services.ip_reconcile_service import IPReconcileService

            _BANNED_MACS = {"0000-0000-0001", "0000-0000-0000", "0000.0000.0001", "0000.0000.0000"}
            _INVALID_MACS = {"n/a", ""}
            active_ips = set()
            arp_banned_ips = set()
            for ctx in valid_ctxs:
                for arp in ctx.arps:
                    mac = (arp.mac or "").lower().replace(":", "-")
                    if mac in _BANNED_MACS:
                        arp_banned_ips.add(arp.ip)
                    elif mac in _INVALID_MACS:
                        continue
                    else:
                        active_ips.add(arp.ip)

            try:
                with transaction_checkpoint(self.sw_repo.session, "phase6:ip_reconcile"):
                    IPReconcileService(IPManagerRepository(self.sw_repo.session)).reconcile(scope, active_ips, self.sw_repo.session, arp_banned_ips=arp_banned_ips)
            except Exception as e:
                logger.error("[Phase6] IP对账失败: %s", e)

            progress.current_phase = "phase6a_route_ip_info"
            _emit_progress()
            try:
                with transaction_checkpoint(self.sw_repo.session, "phase6a:route_ip_info"):
                    from app.services.ip_route_info_service import RouteIPInfoService
                    RouteIPInfoService().fill_from_routes(scope, self.sw_repo.session)
            except Exception as e:
                logger.error("[Phase6a] 路由驱动IP信息补填失败: %s", e)

            probe_ips_for_phase7: list[str] = []
            try:
                import ipaddress as _ipa
                from app.core.enums import IPStatus

                if scope.startswith("r:"):
                    _phase6b_room_ids = [int(scope[2:])]
                elif scope.startswith("vr:"):
                    from app.services.virtual_room_service import VirtualRoomService
                    _phase6b_room_ids = list(VirtualRoomService(VirtualRoomRepository(self.sw_repo.session)).get_covered_room_ids(int(scope[3:])))
                else:
                    _phase6b_room_ids = []

                if _phase6b_room_ids:
                    ip_rows = self.ip_repo.find_unused_inactive_ips_by_rooms(
                        _phase6b_room_ids,
                        [int(IPStatus.UNUSED), int(IPStatus.INACTIVE)],
                    )
                    for ip_str in ip_rows:
                        try:
                            if not _ipa.ip_address(ip_str).is_private:
                                probe_ips_for_phase7.append(ip_str)
                        except ValueError:
                            continue
                logger.info("[Phase6b] ARP 未覆盖 IP: %d 个（待 Phase7 探测）",
                            len(probe_ips_for_phase7))
            except Exception as e:
                logger.error("[Phase6b] 查询待探测 IP 失败: %s", e)

            progress.current_phase = "phase7_supplement_detect"
            _emit_progress()
            try:
                with transaction_checkpoint(self.sw_repo.session, "phase7:supplement_detect"):
                    from app.services.ip_status_service import fast_supplement_detect, SAFE_MAX_CONCURRENT

                    def _phase7_progress(probed: int, total: int):
                        progress.current_phase = f"phase7_supplement_detect:{probed}/{total}"
                        _emit_progress()

                    supplement_result = fast_supplement_detect(
                        scope, probe_ips_for_phase7, self.sw_repo.session,
                        timeout=0.1, max_concurrent=SAFE_MAX_CONCURRENT,
                        progress_callback=_phase7_progress,
                    )
                    if supplement_result.get("active_found", 0) > 0:
                        logger.info(
                            f"[Phase7] 补充探测发现 {supplement_result['active_found']} 个新在线IP"
                        )
            except Exception as e:
                logger.error("[Phase7] 补充探测失败: %s", e)

            progress.current_phase = "完成"
            _emit_progress()

            if virtual_room_id:
                try:
                    self.vr_repo.update_last_scan(virtual_room_id, scope)
                except Exception as e:
                    logger.warning("写回 last_scan_at 失败: %s", e)

            elapsed = time.time() - scan_start
            logger.info("[Scan] 全量扫描完成 scope=%s, "
                        "耗时=%.1fs, "
                        "采集=%d, 失败=%d", scope, elapsed, len(valid_ctxs), len(failed))
            return self._summary(scope, progress)
        finally:
            ScanOrchestrator.release_scan_locks(scope, acquired_locks, heartbeat_stop, sr)

    @staticmethod
    def release_scan_locks(scope: str, acquired_locks: list[str],
                           heartbeat_stop: threading.Event = None,
                           sr: 'ScanRedis' = None):
        if heartbeat_stop:
            heartbeat_stop.set()
        if sr:
            for lk in acquired_locks:
                try:
                    sr.r.delete(lk)
                except Exception:
                    logger.debug("释放扫描锁失败: lock_key=%s", lk, exc_info=True)

    def _load_switch_metas(self, room_id: int) -> list[SwitchMeta]:
        scope = f"r:{room_id}"
        switches = self.sw_repo.get_by_room(room_id)
        metas = []
        for sw in switches:
            sw_room_id = None
            if sw.device and sw.device.cabinet:
                sw_room_id = sw.device.cabinet.room_id
            device = sw.device
            ext = device.switch_ext if device else None
            metas.append(SwitchMeta(
                id=sw.device_id,
                cred_id=sw.id,
                ip=sw.ip,
                device_type=sw.device_type or SwitchDeviceTypeCode.HUAWEI,
                has_ssh=sw.has_ssh,
                layer=device.layer or 3,
                is_core=(device.switch_role == 0) if device.switch_role is not None else False,
                uplink_sw_id=ext.uplink_device_id if ext else None,
                uplink_port=_resolve_uplink_port_name(ext.uplink_port_ids) if ext else None,
                room_id=sw_room_id,
                scope=scope,
            ))
        return metas

    def _load_switch_metas_by_virtual_room(self, virtual_room_id: int) -> list[SwitchMeta]:
        scope = f"vr:{virtual_room_id}"
        from app.services.virtual_room_service import VirtualRoomService
        from app.persistence.virtual_room_repository import VirtualRoomRepository
        device_ids = VirtualRoomService(VirtualRoomRepository(self.sw_repo.session)).get_member_device_ids(virtual_room_id)
        if not device_ids:
            return []
        switches = self.sw_repo.get_by_device_ids(device_ids)
        metas = []
        for sw in switches:
            sw_room_id = None
            if sw.device and sw.device.cabinet:
                sw_room_id = sw.device.cabinet.room_id
            device = sw.device
            ext = device.switch_ext if device else None
            metas.append(SwitchMeta(
                id=sw.device_id,
                cred_id=sw.id,
                ip=sw.ip,
                device_type=sw.device_type or SwitchDeviceTypeCode.HUAWEI,
                has_ssh=sw.has_ssh,
                layer=device.layer or 3,
                is_core=(device.switch_role == 0) if device.switch_role is not None else False,
                uplink_sw_id=ext.uplink_device_id if ext else None,
                uplink_port=_resolve_uplink_port_name(ext.uplink_port_ids) if ext else None,
                room_id=sw_room_id,
                scope=scope,
            ))
        return metas

    def _collect_all(self, authorized: list[SwitchMeta]
                     ) -> tuple[list[SwitchContext], list[str]]:
        from flask import current_app

        valid, failed = [], []
        app_ref = current_app._get_current_object()

        def collect_one(sw: SwitchMeta) -> SwitchContext:
            with app_ref.app_context():
                return self._collect_single(sw)

        with ThreadPoolExecutor(max_workers=min(10, len(authorized))) as pool:
            futures = {pool.submit(collect_one, sw): sw for sw in authorized}
            for future in as_completed(futures):
                sw = futures[future]
                try:
                    valid.append(future.result(timeout=60))
                except Exception as e:
                    logger.error("采集 %s 失败: %s", sw.ip, e)
                    failed.append(f"{sw.ip}: {e}")
        return valid, failed

    def _collect_single(self, sw: SwitchMeta) -> SwitchContext:
        MAX_RETRY = 2
        for attempt in range(MAX_RETRY + 1):
            try:
                switch_obj = self.sw_repo.find_by_id(sw.cred_id)
                adapter = get_adapter(sw.device_type)

                routes = []
                if sw.layer == 3:
                    try:
                        route_out = self.ssh_mgr.send_show_command(
                            switch_obj, adapter.get_route_command()
                        )
                        parsed = adapter.parse_routes(route_out)
                        routes = [
                            ParsedRoute(
                                network=r.network,
                                nexthop=r.nexthop or "0.0.0.0",
                                flags=r.protocol or "C",
                                interface=r.interface or "",
                                port=normalize_port(r.interface or ""),
                            )
                            for r in parsed
                        ]
                    except Exception as e:
                        logger.warning("交换机 %s 路由采集失败: %s", sw.ip, e)

                arps = []
                try:
                    arp_out = self.ssh_mgr.send_show_command(
                        switch_obj, adapter.get_arp_command()
                    )
                    parsed_arps = adapter.parse_arp(arp_out)
                    arps = [
                        ParsedArpEntry(
                            ip=a.ip_address,
                            mac=normalize_mac_address(a.mac_address),
                            interface=a.interface or "",
                            vlan=a.vlan if hasattr(a, 'vlan') else None,
                        )
                        for a in parsed_arps
                        if a.mac_address and a.mac_address.strip().upper() != "INCOMPLETE"
                    ]
                except Exception as e:
                    logger.warning("交换机 %s ARP采集失败: %s", sw.ip, e)

                macs = []
                try:
                    mac_out = self.ssh_mgr.send_show_command(
                        switch_obj, adapter.get_mac_command()
                    )
                    parsed_macs = adapter.parse_mac_table(mac_out)
                    macs = [
                        ParsedMacEntry(
                            mac=normalize_mac_address(m.mac_address),
                            port=normalize_port(m.port),
                            vlan=m.vlan if hasattr(m, 'vlan') else None,
                        )
                        for m in parsed_macs
                    ]
                except Exception as e:
                    logger.warning("交换机 %s MAC采集失败: %s", sw.ip, e)

                return SwitchContext(
                    sw_id=sw.id, ip=sw.ip, has_ssh=True,
                    layer=sw.layer, is_core=sw.is_core,
                    routes=routes, arps=arps, macs=macs,
                    uplink_sw_id=sw.uplink_sw_id,
                    uplink_port=sw.uplink_port,
                    room_id=sw.room_id,
                    scope=sw.scope,
                )
            except Exception as e:
                if attempt < MAX_RETRY:
                    time.sleep(2 ** attempt)
                else:
                    raise RuntimeError(f"采集 {sw.ip} 失败: {e}") from e

    @staticmethod
    def _summary(scope: str, progress: ScanProgress) -> dict:
        return {
            "scope": scope,
            "room_id": progress.room_id,
            "total_switches": progress.total_switches,
            "completed": progress.completed,
            "failed": progress.failed,
            "elapsed_seconds": round(time.time() - progress.start_time, 1),
        }


    def scan_room(self, room_id: int) -> dict:
        return self.full_scan(room_id)

    def scan_switch(self, device_id: int) -> dict:
        sw = self.sw_repo.find_by_device_id(device_id)
        if not sw:
            raise ValueError(f"交换机 {device_id} 不存在")
        room_id = None
        if sw.device and sw.device.cabinet:
            room_id = sw.device.cabinet.room_id
        device = sw.device
        ext = device.switch_ext if device else None
        meta = SwitchMeta(
            id=sw.device_id, cred_id=sw.id, ip=sw.ip, device_type=sw.device_type or SwitchDeviceTypeCode.HUAWEI,
            has_ssh=ext.has_ssh if ext else True,
            layer=ext.layer if ext and ext.layer else 2,
            is_core=(ext.switch_role == 0) if ext and ext.switch_role is not None else False,
            uplink_sw_id=ext.uplink_device_id if ext else None,
            uplink_port=_resolve_uplink_port_name(ext.uplink_port_ids) if ext else None,
            room_id=room_id,
        )

        if not meta.has_ssh:
            return {"device_id": device_id, "ip": sw.ip, "skipped": "无SSH权限"}

        sr = self.scan_redis

        ctx = self._collect_single(meta)

        try:
            with transaction_checkpoint(self.sw_repo.session, f"scan_switch:phase0:{device_id}"):
                from app.services.switch_info_service import SwitchInfoService
                port_svc = SwitchInfoService()
                port_svc.collect_port_info(sw.device_id)
        except Exception as e:
            logger.error("[scan_switch] 交换机 %s 端口采集失败: %s", sw.ip, e)

        try:
            with transaction_checkpoint(self.sw_repo.session, f"scan_switch:phase0b:{device_id}"):
                from app.services.switch_info_service import SwitchInfoService
                port_svc = SwitchInfoService()
                port_svc.collect_device_info(sw.device_id)
        except Exception as e:
            logger.error("[scan_switch] 交换机 %s 设备信息采集失败: %s", sw.ip, e)

        try:
            scope = f"r:{room_id}"
            port_ip_rows = self.sw_repo.get_port_ips_by_device_id(sw.device_id)
            for row in port_ip_rows:
                sr.port_ip_set(scope, row[0], row[1], row[2], row[3] or 24)
            if port_ip_rows:
                logger.debug("[scan_switch] 端口IP索引已加载: %d 条", len(port_ip_rows))
        except Exception as e:
            logger.warning("[scan_switch] 端口IP索引加载失败: %s", e)

        from app.services.topology_graph import build_topology_graph
        topology_graph = build_topology_graph(f"r:{room_id}", [meta], self.sw_repo.session)

        if ctx.layer == 3:
            try:
                with transaction_checkpoint(self.sw_repo.session, f"scan_switch:phase1:{device_id}"):
                    self.route_sync.sync(ctx, self.sw_repo.session, sr, topology_graph=topology_graph)
            except Exception as e:
                logger.error("[scan_switch] 交换机 %s 路由同步失败: %s", sw.ip, e)

        detect_uplink_ports(ctx)
        self.mac_builder.build(ctx, sr)

        try:
            with transaction_checkpoint(self.sw_repo.session, f"scan_switch:phase3:{device_id}"):
                self.arp_sync.sync_all([ctx], self.sw_repo.session, sr, topology_graph=topology_graph)
        except Exception as e:
            logger.error("[scan_switch] 交换机 %s ARP同步失败: %s", sw.ip, e)

        try:
            _BANNED_MACS = {"0000-0000-0001", "0000-0000-0000", "0000.0000.0001", "0000.0000.0000"}
            active_ips = set()
            arp_banned_ips = set()
            for a in ctx.arps:
                mac = (a.mac or "").lower().replace(":", "-")
                if mac in _BANNED_MACS:
                    arp_banned_ips.add(a.ip)
                else:
                    active_ips.add(a.ip)
            with transaction_checkpoint(self.sw_repo.session, f"scan_switch:phase6:{device_id}"):
                from app.services.ip_reconcile_service import IPReconcileService
                IPReconcileService(IPManagerRepository(self.sw_repo.session)).reconcile(f"r:{room_id}", active_ips, self.sw_repo.session, arp_banned_ips=arp_banned_ips)
        except Exception as e:
            logger.error("[scan_switch Phase6] IP对账失败: %s", e)

        try:
            with transaction_checkpoint(self.sw_repo.session, f"scan_switch:phase7:{device_id}"):
                from app.services.ip_status_service import supplement_detect_room_ips
                supplement_detect_room_ips(room_id, self.sw_repo.session)
        except Exception as e:
            logger.error("[scan_switch Phase7] 补充探测失败: %s", e)

        return {"device_id": device_id, "ip": sw.ip, "context": ctx}


class NetworkScannerService:

    def __init__(self, ssh_manager=None):
        self._orchestrator = ScanOrchestrator(ssh_manager=ssh_manager)
        self.ssh_mgr = self._orchestrator.ssh_mgr
        self.sw_repo = self._orchestrator.sw_repo

    def scan_switch(self, device_id: int) -> dict:
        return self._orchestrator.scan_switch(device_id)

    def scan_room(self, room_id: int) -> dict:
        return self._orchestrator.scan_room(room_id)

    def get_scan_status(self) -> dict:
        return {"is_scanning": False}


def _validate_topology_coverage(all_sw: list, topology_graph) -> list[str]:
    warnings = []
    core_ids = {n.sw_id for n in topology_graph.nodes.values() if n.is_core}
    for sw in all_sw:
        if sw.id in core_ids:
            continue
        if sw.id not in topology_graph._adjacency or not topology_graph._adjacency[sw.id]:
            warnings.append(
                f"交换机 {sw.ip}（device_id={sw.id}）在拓扑图中是孤立节点，"
                f"缺少与其他交换机的 NetworkConnection 记录，"
                f"其下终端IP将无法通过图遍历精确定位"
            )
    return warnings
