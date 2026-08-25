# -*- coding: utf-8 -*-
"""
IP 封禁 / 解封服务

支持两种封禁方式：
  - 三层封禁（黑洞路由）：在核心交换机添加 /32 黑洞路由，适用于三层网络
  - 二层封禁（静态ARP）：在网关交换机配置静态ARP绑定无效MAC，适用于二层网络

自动判断逻辑（基于 switch_routes 表）：
  - IP 属于直连子网路由（route_type=SUBNET, nexthop 为空或出接口为本机）→ 静态ARP封禁
  - IP 属于非直连路由（需经静态/动态路由到达）→ 黑洞路由封禁
  - 无法判断 → 降级到黑洞路由封禁
"""
import ipaddress
from app.utils.logging import get_logger
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text

from app.adapters.adapter_factory import get_adapter
from app.core.enums import IPStatus, RouteNotes
from app.exceptions.business import (
    IPAlreadyBannedException, IPNotBannedException,
    NoCoreSwitch, BanCommandFailed, BanConfigNotFoundError,
)
from app.infra import SSHManager
from app.models.ip_model import IPBanRecord, ip_to_int
from app.models.switch_route import SwitchRoute
from app.persistence.ip_repositories import IPManagerRepository, IPNetworkRepository, IPBanRecordRepository, IPSwitchInfoRepository
from app.persistence.switch_repo import SwitchRepository
from app.services.ip_status_service import detect_ip_status

logger = get_logger(__name__)

BAN_MODE_ROUTE = "route"
BAN_MODE_ARP = "arp"


@dataclass
class BanResult:
    ip_address: str
    success: bool
    switch_id: int
    switch_ip: str
    ban_mode: str = BAN_MODE_ROUTE
    message: str = ""


class IPBanService:

    def __init__(self, ssh_manager: SSHManager, session=None):
        self.ssh_mgr = ssh_manager
        self.ip_mgr_repo = IPManagerRepository(session)
        self.ip_net_repo = IPNetworkRepository(session)
        self.ip_ban_repo = IPBanRecordRepository(session)
        self.ip_sw_repo = IPSwitchInfoRepository(session)
        self.sw_repo = SwitchRepository(session)
        self.session = self.ip_mgr_repo.session


    def ban_ip(
        self,
        ip_address: str,
        room_id: Optional[int] = None,
        operator_id: Optional[int] = None,
        ban_mode: Optional[str] = None,
    ) -> BanResult:
        if room_id is not None:
            ip_record = self.ip_mgr_repo.get_by_ip_room(ip_address, room_id)
        else:
            ip_record = self.ip_mgr_repo.find_by_ip_address(ip_address)

        if ip_record is None:
            if room_id is not None:
                raise ValueError(f"IP {ip_address} 不存在于机房 {room_id}")
            else:
                raise ValueError(f"IP {ip_address} 不存在于任何机房")

        actual_room_id = ip_record.room_id

        if ip_record.status == IPStatus.BANNED:
            raise IPAlreadyBannedException(f"{ip_address} 已处于封禁状态")
        if ip_record.status == IPStatus.PENDING_BAN:
            raise IPAlreadyBannedException(f"{ip_address} 正在封禁中，请勿重复操作")

        if ban_mode is None:
            ban_mode = self._determine_ban_mode(ip_address, actual_room_id)

        if ban_mode == BAN_MODE_ARP:
            return self._ban_via_arp(ip_address, actual_room_id, operator_id)
        else:
            return self._ban_via_route(ip_address, actual_room_id, operator_id)

    def _ban_via_route(
        self, ip_address: str, room_id: int, operator_id: Optional[int],
    ) -> BanResult:
        switch = self._pick_core_switch(ip_address, room_id)
        adapter = get_adapter(switch.device_type)
        device_model = switch.device.device_model if switch.device else ""
        ban_cmds_obj = adapter.get_ban_commands(ip_address, device_model)

        ip_record = self.ip_mgr_repo.get_by_ip_room(ip_address, room_id)
        original_status = ip_record.status if ip_record else IPStatus.INACTIVE

        _mark_ban_pending(ip_address, room_id, switch.device_id, BAN_MODE_ROUTE)
        self.ip_mgr_repo.update_status(ip_address, room_id, IPStatus.PENDING_BAN)
        self._upsert_ban_record(
            ip_address, switch.device_id, room_id,
            ban_mode=BAN_MODE_ROUTE, operator_id=operator_id,
        )
        self.session.commit()

        logger.info("三层封禁 IP %s → switch %s (黑洞路由)", ip_address, switch.ip)
        ssh_failed = False
        try:
            output = self.ssh_mgr.send_config_commands(
                switch=switch,
                commands=ban_cmds_obj.ban_cmds,
                save_cmd=ban_cmds_obj.save_cmd,
            )
            _verify_ban_output(output, ip_address, action="ban")
        except BanCommandFailed:
            ssh_failed = True
        except Exception as exc:
            ssh_failed = True
            logger.warning("三层封禁 SSH 异常: %s", exc)

        if ssh_failed:
            self.ip_mgr_repo.update_status(ip_address, room_id, original_status)
            self._deactivate_ban_record(ip_address, room_id)
            self.session.commit()
            _clear_ban_pending(ip_address, room_id)
            raise BanCommandFailed(f"IP {ip_address} 三层封禁 SSH 执行失败")

        self.ip_mgr_repo.update_status(ip_address, room_id, IPStatus.BANNED)
        self.session.commit()
        _clear_ban_pending(ip_address, room_id)

        logger.info("三层封禁成功: IP=%s switch=%d", ip_address, switch.device_id)
        return BanResult(
            ip_address=ip_address, success=True,
            switch_id=switch.device_id, switch_ip=switch.ip,
            ban_mode=BAN_MODE_ROUTE,
            message=f"IP {ip_address} 已封禁（黑洞路由 → {switch.ip}）",
        )

    def _ban_via_arp(
        self, ip_address: str, room_id: int, operator_id: Optional[int],
    ) -> BanResult:
        switch, mac_address, vlan_id = self._find_gateway_info(ip_address, room_id)
        adapter = get_adapter(switch.device_type)
        device_model = switch.device.device_model if switch.device else ""
        arp_ban_cmds = adapter.get_arp_ban_commands(ip_address, mac_address, vlan_id, device_model)

        ip_record = self.ip_mgr_repo.get_by_ip_room(ip_address, room_id)
        original_status = ip_record.status if ip_record else IPStatus.INACTIVE

        _mark_ban_pending(ip_address, room_id, switch.device_id, BAN_MODE_ARP)
        self.ip_mgr_repo.update_status(ip_address, room_id, IPStatus.PENDING_BAN)
        self._upsert_ban_record(
            ip_address, switch.device_id, room_id,
            ban_mode=BAN_MODE_ARP, mac_address=mac_address, vlan_id=vlan_id,
            operator_id=operator_id,
        )
        self.session.commit()

        logger.info("二层封禁 IP %s → switch %s (静态ARP, vlan=%d)", ip_address, switch.ip, vlan_id)
        ssh_failed = False
        try:
            output = self.ssh_mgr.send_config_commands(
                switch=switch,
                commands=arp_ban_cmds.ban_cmds,
                save_cmd=arp_ban_cmds.save_cmd,
            )
            _verify_ban_output(output, ip_address, action="ban")
        except BanCommandFailed:
            ssh_failed = True
        except Exception as exc:
            ssh_failed = True
            logger.warning("二层封禁 SSH 异常: %s", exc)

        if ssh_failed:
            self.ip_mgr_repo.update_status(ip_address, room_id, original_status)
            self._deactivate_ban_record(ip_address, room_id)
            self.session.commit()
            _clear_ban_pending(ip_address, room_id)
            raise BanCommandFailed(f"IP {ip_address} 二层封禁 SSH 执行失败")

        self.ip_mgr_repo.update_status(ip_address, room_id, IPStatus.BANNED)
        self.session.commit()
        _clear_ban_pending(ip_address, room_id)

        logger.info("二层封禁成功: IP=%s switch=%d vlan=%d", ip_address, switch.device_id, vlan_id)
        return BanResult(
            ip_address=ip_address, success=True,
            switch_id=switch.device_id, switch_ip=switch.ip,
            ban_mode=BAN_MODE_ARP,
            message=f"IP {ip_address} 已封禁（静态ARP → {switch.ip}, VLAN {vlan_id}）",
        )


    def unban_ip(
        self,
        ip_address: str,
        room_id: Optional[int] = None,
        operator_id: Optional[int] = None,
    ) -> BanResult:
        if room_id is not None:
            ip_record = self.ip_mgr_repo.get_by_ip_room(ip_address, room_id)
        else:
            ip_record = self._find_banned_ip_record(ip_address)

        if ip_record is None:
            if room_id is not None:
                raise ValueError(f"IP {ip_address} 不存在于机房 {room_id}")
            else:
                raise ValueError(f"IP {ip_address} 不存在或未处于封禁状态")

        if ip_record.status != IPStatus.BANNED:
            raise IPNotBannedException(f"{ip_address} 当前并非封禁状态")
        if ip_record.status == IPStatus.PENDING_UNBAN:
            raise IPNotBannedException(f"{ip_address} 正在解封中，请勿重复操作")

        actual_room_id = ip_record.room_id

        ban_mode = self._detect_ban_mode_from_record(ip_address, actual_room_id)

        if ban_mode == BAN_MODE_ARP:
            return self._unban_via_arp(ip_address, actual_room_id, operator_id)
        else:
            return self._unban_via_route(ip_address, actual_room_id, operator_id)

    def _unban_via_route(
        self, ip_address: str, room_id: int, operator_id: Optional[int],
    ) -> BanResult:
        switch = self._find_ban_switch(ip_address, room_id)
        adapter = get_adapter(switch.device_type)
        device_model = switch.device.device_model if switch.device else ""
        ban_cmds_obj = adapter.get_ban_commands(ip_address, device_model)

        _mark_ban_pending(ip_address, room_id, switch.device_id, BAN_MODE_ROUTE)
        self.ip_mgr_repo.update_status(ip_address, room_id, IPStatus.PENDING_UNBAN)
        self.session.commit()

        logger.info("三层解封 IP %s → switch %s", ip_address, switch.ip)
        ssh_failed = False
        config_not_found = False
        try:
            output = self.ssh_mgr.send_config_commands(
                switch=switch,
                commands=ban_cmds_obj.unban_cmds,
                save_cmd=ban_cmds_obj.save_cmd,
            )
            _verify_ban_output(output, ip_address, action="unban")
        except BanConfigNotFoundError as exc:
            config_not_found = True
            logger.info("三层解封 IP %s: 交换机配置不存在，视为已解封 (%s)", ip_address, exc)
        except BanCommandFailed:
            ssh_failed = True
        except Exception as exc:
            ssh_failed = True
            logger.warning("三层解封 SSH 异常: %s", exc)

        if ssh_failed:
            self.ip_mgr_repo.update_status(ip_address, room_id, IPStatus.BANNED)
            self.session.commit()
            _clear_ban_pending(ip_address, room_id)
            raise BanCommandFailed(f"IP {ip_address} 三层解封 SSH 执行失败")

        return self._finalise_unban(
            ip_address, room_id, switch, BAN_MODE_ROUTE, operator_id,
            already_unbanned=config_not_found,
        )

    def _unban_via_arp(
        self, ip_address: str, room_id: int, operator_id: Optional[int],
    ) -> BanResult:
        switch, mac_address, vlan_id = self._find_arp_ban_info(ip_address, room_id)
        adapter = get_adapter(switch.device_type)
        device_model = switch.device.device_model if switch.device else ""
        arp_ban_cmds = adapter.get_arp_ban_commands(ip_address, mac_address, vlan_id, device_model)

        _mark_ban_pending(ip_address, room_id, switch.device_id, BAN_MODE_ARP)
        self.ip_mgr_repo.update_status(ip_address, room_id, IPStatus.PENDING_UNBAN)
        self.session.commit()

        logger.info("二层解封 IP %s → switch %s", ip_address, switch.ip)
        ssh_failed = False
        config_not_found = False
        try:
            output = self.ssh_mgr.send_config_commands(
                switch=switch,
                commands=arp_ban_cmds.unban_cmds,
                save_cmd=arp_ban_cmds.save_cmd,
            )
            _verify_ban_output(output, ip_address, action="unban")
        except BanConfigNotFoundError as exc:
            config_not_found = True
            logger.info("二层解封 IP %s: 交换机配置不存在，视为已解封 (%s)", ip_address, exc)
        except BanCommandFailed:
            ssh_failed = True
        except Exception as exc:
            ssh_failed = True
            logger.warning("二层解封 SSH 异常: %s", exc)

        if ssh_failed:
            self.ip_mgr_repo.update_status(ip_address, room_id, IPStatus.BANNED)
            self.session.commit()
            _clear_ban_pending(ip_address, room_id)
            raise BanCommandFailed(f"IP {ip_address} 二层解封 SSH 执行失败")

        return self._finalise_unban(
            ip_address, room_id, switch, BAN_MODE_ARP, operator_id,
            already_unbanned=config_not_found,
        )

    def _finalise_unban(
        self, ip_address: str, room_id: int,
        switch, ban_mode: str, operator_id: Optional[int],
        already_unbanned: bool = False,
    ) -> BanResult:
        active_ban = self.ip_ban_repo.find_active_ban(ip_address, room_id)
        if active_ban:
            active_ban.is_active = False
            self.session.add(IPBanRecord(
                ip_address=ip_address,
                ip_int=ip_to_int(ip_address),
                switch_id=active_ban.switch_id,
                room_id=room_id,
                action="unban",
                is_active=False,
                operator_id=operator_id,
            ))

        if ban_mode == BAN_MODE_ROUTE:
            self.ip_net_repo.delete_blackhole_for_ip(ip_address, switch.device_id)

        self.ip_mgr_repo.update_status(ip_address, room_id, IPStatus.INACTIVE)
        self.session.commit()
        _clear_ban_pending(ip_address, room_id)

        new_status = IPStatus.INACTIVE
        try:
            new_status = detect_ip_status(ip_address)
            if new_status != IPStatus.INACTIVE:
                self.ip_mgr_repo.update_status(ip_address, room_id, new_status)
                self.session.commit()
        except Exception as exc:
            logger.warning("解封后探测 IP %s 状态失败（不影响解封结果）: %s", ip_address, exc)

        if already_unbanned:
            message = f"IP {ip_address} 已通过其他方式解封，当前状态: {new_status.name}"
        else:
            message = f"IP {ip_address} 已解封，当前状态: {new_status.name}"

        return BanResult(
            ip_address=ip_address, success=True,
            switch_id=switch.device_id, switch_ip=switch.ip,
            ban_mode=ban_mode,
            message=message,
        )


    def _determine_ban_mode(self, ip_address: str, room_id: int) -> str:
        route = self._find_ip_route(ip_address, room_id)
        if route is None:
            logger.debug("IP %s 无路由记录，降级到黑洞路由封禁", ip_address)
            return BAN_MODE_ROUTE

        is_direct = (
            route.route_type == int(RouteNotes.SUBNET) and
            bool(route.port) and
            bool(re.search(r'(?i)(?:vlanif|vlan-interface|svi)', route.port or ""))
        )

        if is_direct:
            logger.debug("IP %s 属于二层网段(直连路由 %s)，选择静态ARP封禁",
                        ip_address, route.destination)
            return BAN_MODE_ARP
        else:
            logger.debug("IP %s 属于三层网段(非直连路由 %s, nexthop=%s)，选择黑洞路由封禁",
                        ip_address, route.destination, route.nexthop)
            return BAN_MODE_ROUTE

    def _find_ip_route(
        self, ip_address: str, room_id: int,
    ) -> Optional[SwitchRoute]:
        try:
            ipaddress.ip_address(ip_address)
        except ValueError:
            return None

        ip_int_val = ip_to_int(ip_address)
        if ip_int_val is None:
            return None

        row = self.session.execute(text("""
            SELECT id FROM switch_routes
            WHERE room_id = :room_id
              AND route_type != :blackhole_type
              AND destination_int <= :ip_int
              AND :ip_int <= destination_int + POW(2, 32 - destination_prefix) - 1
            ORDER BY destination_prefix DESC
            LIMIT 1
        """), {
            "ip_int": ip_int_val, "room_id": room_id,
            "blackhole_type": int(RouteNotes.BLACKHOLE),
        }).first()

        if row is None:
            return None

        return self.session.query(SwitchRoute).get(row[0])

    def _detect_ban_mode_from_record(
        self, ip_address: str, room_id: int,
    ) -> str:
        record = self.ip_ban_repo.find_active_ban(ip_address, room_id)
        if record:
            return record.ban_mode

        return self._determine_ban_mode(ip_address, room_id)


    def _find_gateway_info(
        self, ip_address: str, room_id: int,
    ) -> tuple:
        from app.models.switch_credentials import IPSwitchInfo

        isi = self.ip_sw_repo.get_by_ip_room(ip_address, room_id)
        mac_address = ""
        vlan_id = 1

        if isi:
            mac_address = isi.mac_address or ""
            if isi.port:
                extracted_vlan = self._extract_vlan_from_interface(isi.port)
                if extracted_vlan > 0:
                    vlan_id = extracted_vlan
            if vlan_id <= 1 and isi.vlan_id:
                vlan_id = isi.vlan_id

        switch = self._pick_core_switch(ip_address, room_id)
        return switch, mac_address, vlan_id

    def _find_arp_ban_info(
        self, ip_address: str, room_id: int,
    ) -> tuple:
        record = self.ip_ban_repo.find_active_ban(ip_address, room_id)

        if record:
            switch = self.sw_repo.find_by_device_id(record.switch_id)
            ban_meta = record.ban_meta or {}
            mac_address = ban_meta.get("mac_address", "")
            vlan_id = ban_meta.get("vlan_id", 1)
            if switch:
                return switch, mac_address, vlan_id

        from app.models.switch_credentials import IPSwitchInfo
        switch = self._pick_core_switch(ip_address, room_id)
        isi = self.ip_sw_repo.get_by_ip_room(ip_address, room_id)
        mac = isi.mac_address if isi else ""
        vlan = 1
        if isi:
            extracted_vlan = self._extract_vlan_from_interface(isi.port) if isi.port else 0
            if extracted_vlan > 0:
                vlan = extracted_vlan
            elif isi.vlan_id:
                vlan = isi.vlan_id
        return switch, mac, vlan

    @staticmethod
    def _extract_vlan_from_interface(interface: str) -> int:
        m = re.search(r'(?i)(?:vlanif|vlan-interface|svi)(\d+)', interface)
        return int(m.group(1)) if m else 0

    def _pick_core_switch(self, ip_address: str, room_id: int):
        try:
            ip_obj = ipaddress.ip_address(ip_address)
        except ValueError:
            ip_obj = None

        if ip_obj:
            ip_int_val = int(ip_obj)

            best_switch_id = self._find_best_switch_by_prefix(ip_int_val, room_id)
            if best_switch_id:
                sw = self.sw_repo.find_by_device_id(best_switch_id)
                if sw:
                    return sw

            best_switch_id = self._find_best_switch_by_prefix(ip_int_val, room_id=None)
            if best_switch_id:
                sw = self.sw_repo.find_by_device_id(best_switch_id)
                if sw:
                    logger.info(
                        "IP %s 网关交换机不在机房 %d，跨机房选中 switch_id=%d",
                        ip_address, room_id, best_switch_id,
                    )
                    return sw

        core_switches = self.sw_repo.get_core_switches(room_id)
        if core_switches:
            return core_switches[0]

        raise NoCoreSwitch(
            f"机房 {room_id} 没有可用的核心交换机，无法执行封禁。"
            f"请选择该 IP 网关（核心）所在机房，或使用对应的虚拟机房。"
        )

    def _find_best_switch_by_prefix(self, ip_int_val: int, room_id: Optional[int] = None) -> Optional[int]:
        if room_id is not None:
            all_networks = self.ip_net_repo.find_by_room_id(room_id)
        else:
            all_networks = self.ip_net_repo.find_all({})

        best_switch_id = None
        best_prefixlen = -1
        for r in all_networks:
            if r.network_int is not None and r.prefix is not None:
                if r.prefix >= 32:
                    continue
                broadcast_int = r.network_int + (1 << (32 - r.prefix)) - 1
                if r.network_int <= ip_int_val <= broadcast_int and r.prefix > best_prefixlen:
                    best_prefixlen = r.prefix
                    best_switch_id = r.switch_id
        return best_switch_id

    def _find_banned_ip_record(self, ip_address: str):
        from app.models.ip_model import IPManager
        return self.ip_mgr_repo.find_one({"ip_address": ip_address, "status": IPStatus.BANNED})

    def _find_ban_switch(self, ip_address: str, room_id: int):
        record = self.ip_ban_repo.find_active_ban(ip_address, room_id)
        if record:
            sw = self.sw_repo.find_by_device_id(record.switch_id)
            if sw:
                return sw
        return self._pick_core_switch(ip_address, room_id)

    def _upsert_ban_record(
        self, ip_address: str, switch_id: int, room_id: int,
        ban_mode: str = BAN_MODE_ROUTE,
        mac_address: str = None, vlan_id: int = None,
        operator_id: Optional[int] = None,
    ) -> None:
        exists = self.ip_ban_repo.exists_active_ban(ip_address, room_id)
        if exists:
            return

        ban_meta = None
        if ban_mode == BAN_MODE_ARP and (mac_address or vlan_id):
            ban_meta = {}
            if mac_address:
                ban_meta["mac_address"] = mac_address
            if vlan_id:
                ban_meta["vlan_id"] = vlan_id

        self.session.add(IPBanRecord(
            ip_address=ip_address,
            ip_int=ip_to_int(ip_address),
            switch_id=switch_id,
            room_id=room_id,
            ban_mode=ban_mode,
            ban_meta=ban_meta,
            operator_id=operator_id,
        ))

    def _deactivate_ban_record(self, ip_address: str, room_id: int) -> None:
        record = self.ip_ban_repo.find_active_ban(ip_address, room_id)
        if record:
            record.is_active = False


def ban_ip_list(
    service: IPBanService,
    ip_list: list,
    room_id: Optional[int] = None,
    operator_id: Optional[int] = None,
    ban_mode: Optional[str] = None,
) -> dict:
    result = {"success": [], "failed": [], "skipped": []}

    groups = defaultdict(list)

    ip_records = {}
    if room_id is not None:
        ip_records = service.ip_mgr_repo.get_by_ips_room(ip_list, room_id)

    for ip in ip_list:
        try:
            if room_id is not None:
                ip_record = ip_records.get(ip)
            else:
                ip_record = service.ip_mgr_repo.find_by_ip_address(ip)

            if ip_record is None:
                if room_id is not None:
                    result["failed"].append({"ip": ip, "error": f"IP {ip} 不存在于机房 {room_id}"})
                else:
                    result["failed"].append({"ip": ip, "error": f"IP {ip} 不存在于任何机房"})
                continue
            if ip_record.status in (IPStatus.BANNED, IPStatus.PENDING_BAN):
                result["skipped"].append({"ip": ip, "reason": "已是封禁/封禁中状态"})
                continue

            actual_room_id = ip_record.room_id
            original_status = ip_record.status

            actual_mode = ban_mode or service._determine_ban_mode(ip, actual_room_id)

            if actual_mode == BAN_MODE_ARP:
                switch, mac_address, vlan_id = service._find_gateway_info(ip, actual_room_id)
                adapter = get_adapter(switch.device_type)
                device_model = switch.device.device_model if switch.device else ""
                cmds_obj = adapter.get_arp_ban_commands(ip, mac_address, vlan_id, device_model)
            else:
                switch = service._pick_core_switch(ip, actual_room_id)
                adapter = get_adapter(switch.device_type)
                device_model = switch.device.device_model if switch.device else ""
                cmds_obj = adapter.get_ban_commands(ip, device_model)

            _mark_ban_pending(ip, actual_room_id, switch.device_id, actual_mode)
            service.ip_mgr_repo.update_status(ip, actual_room_id, IPStatus.PENDING_BAN)
            service._upsert_ban_record(
                ip, switch.device_id, actual_room_id,
                ban_mode=actual_mode, operator_id=operator_id,
            )
            groups[(switch.device_id, actual_mode)].append((ip, adapter, cmds_obj, switch, original_status, actual_room_id))

        except Exception as exc:
            logger.error("批量封禁预检 %s 失败: %s", ip, exc)
            result["failed"].append({"ip": ip, "error": str(exc)})

    try:
        service.session.commit()
    except Exception as exc:
        logger.error("批量封禁阶段1 commit 失败: %s", exc)
        service.session.rollback()
        return result

    for (switch_id, mode), items in groups.items():
        ip, adapter, _, switch, _, _ = items[0]
        device_model = switch.device.device_model if switch.device else ""
        is_ce = adapter.is_ce_model(device_model) if hasattr(adapter, 'is_ce_model') else False

        merged_cmds = []
        for ip_addr, _, cmds_obj, _, _, _ in items:
            merged_cmds.extend(cmds_obj.ban_cmds)

        if is_ce:
            merged_cmds = [c for c in merged_cmds if c != "commit"]
            merged_cmds.append("commit")

        logger.info("批量封禁: switch=%s mode=%s 合并 %d 个IP的命令",
                     switch.ip, mode, len(items))

        ssh_ok = True
        try:
            output = service.ssh_mgr.send_config_commands(
                switch=switch,
                commands=merged_cmds,
                save_cmd="",
            )
            save_cmd = adapter.get_save_command(device_model)
            if save_cmd:
                service.ssh_mgr.send_config_commands(
                    switch=switch, commands=[], save_cmd=save_cmd,
                )
        except Exception as exc:
            logger.error("批量封禁 switch=%s 命令下发失败: %s", switch.ip, exc)
            ssh_ok = False

        for ip_addr, _, _, _, orig_status, actual_room_id in items:
            try:
                if ssh_ok:
                    service.ip_mgr_repo.update_status(ip_addr, actual_room_id, IPStatus.BANNED)
                    _clear_ban_pending(ip_addr, actual_room_id)
                    result["success"].append({
                        "ip": ip_addr, "ban_mode": mode,
                        "message": f"IP {ip_addr} 已封禁（{mode} → {switch.ip}）",
                    })
                else:
                    service.ip_mgr_repo.update_status(ip_addr, actual_room_id, orig_status)
                    service._deactivate_ban_record(ip_addr, actual_room_id)
                    _clear_ban_pending(ip_addr, actual_room_id)
                    result["failed"].append({"ip": ip_addr, "error": "SSH 命令下发失败"})
            except Exception as exc:
                logger.error("批量封禁 %s 数据库同步失败: %s", ip_addr, exc)
                result["failed"].append({"ip": ip_addr, "error": str(exc)})

        try:
            service.session.commit()
        except Exception as exc:
            logger.error("批量封禁阶段3 commit 失败: %s", exc)
            service.session.rollback()

    return result


def unban_ip_list(
    service: IPBanService,
    ip_list: list,
    room_id: Optional[int] = None,
    operator_id: Optional[int] = None,
) -> dict:
    result = {"success": [], "failed": [], "skipped": []}

    groups = defaultdict(list)

    for ip in ip_list:
        try:
            if room_id is not None:
                ip_record = service.ip_mgr_repo.get_by_ip_room(ip, room_id)
            else:
                ip_record = service._find_banned_ip_record(ip)

            if ip_record is None:
                result["failed"].append({"ip": ip, "error": "IP不存在或未处于封禁状态"})
                continue
            if ip_record.status not in (IPStatus.BANNED,):
                if ip_record.status == IPStatus.PENDING_UNBAN:
                    result["skipped"].append({"ip": ip, "reason": "正在解封中"})
                else:
                    result["skipped"].append({"ip": ip, "reason": "未处于封禁状态"})
                continue

            actual_room_id = ip_record.room_id
            ban_mode = service._detect_ban_mode_from_record(ip, actual_room_id)

            if ban_mode == BAN_MODE_ARP:
                switch, mac_address, vlan_id = service._find_arp_ban_info(ip, actual_room_id)
                adapter = get_adapter(switch.device_type)
                device_model = switch.device.device_model if switch.device else ""
                cmds_obj = adapter.get_arp_ban_commands(ip, mac_address, vlan_id, device_model)
            else:
                switch = service._find_ban_switch(ip, actual_room_id)
                adapter = get_adapter(switch.device_type)
                device_model = switch.device.device_model if switch.device else ""
                cmds_obj = adapter.get_ban_commands(ip, device_model)

            _mark_ban_pending(ip, actual_room_id, switch.device_id, ban_mode)
            service.ip_mgr_repo.update_status(ip, actual_room_id, IPStatus.PENDING_UNBAN)
            groups[(switch.device_id, ban_mode)].append((ip, adapter, cmds_obj, switch, actual_room_id))

        except Exception as exc:
            logger.error("批量解封预检 %s 失败: %s", ip, exc)
            result["failed"].append({"ip": ip, "error": str(exc)})

    try:
        service.session.commit()
    except Exception as exc:
        logger.error("批量解封阶段1 commit 失败: %s", exc)
        service.session.rollback()
        return result

    for (switch_id, mode), items in groups.items():
        ip, adapter, _, switch, _ = items[0]
        device_model = switch.device.device_model if switch.device else ""
        is_ce = adapter.is_ce_model(device_model) if hasattr(adapter, 'is_ce_model') else False

        merged_cmds = []
        for ip_addr, _, cmds_obj, _, _ in items:
            merged_cmds.extend(cmds_obj.unban_cmds)

        if is_ce:
            merged_cmds = [c for c in merged_cmds if c != "commit"]
            merged_cmds.append("commit")

        logger.info("批量解封: switch=%s mode=%s 合并 %d 个IP的命令",
                     switch.ip, mode, len(items))

        ssh_ok = True
        try:
            output = service.ssh_mgr.send_config_commands(
                switch=switch,
                commands=merged_cmds,
                save_cmd="",
            )
            save_cmd = adapter.get_save_command(device_model)
            if save_cmd:
                service.ssh_mgr.send_config_commands(
                    switch=switch, commands=[], save_cmd=save_cmd,
                )
        except Exception as exc:
            logger.error("批量解封 switch=%s 命令下发失败: %s", switch.ip, exc)
            ssh_ok = False

        for ip_addr, _, _, sw, actual_room_id in items:
            try:
                if ssh_ok:
                    active_ban = service.ip_ban_repo.find_active_ban(ip_addr, actual_room_id)
                    if active_ban:
                        active_ban.is_active = False
                        service.session.add(IPBanRecord(
                            ip_address=ip_addr,
                            ip_int=ip_to_int(ip_addr),
                            switch_id=active_ban.switch_id,
                            room_id=actual_room_id,
                            action="unban",
                            is_active=False,
                            operator_id=operator_id,
                        ))

                    service.ip_mgr_repo.update_status(ip_addr, actual_room_id, IPStatus.INACTIVE)

                    if mode == BAN_MODE_ROUTE:
                        service.ip_net_repo.delete_blackhole_for_ip(ip_addr, sw.id)

                    _clear_ban_pending(ip_addr, actual_room_id)
                    result["success"].append({
                        "ip": ip_addr, "ban_mode": mode,
                        "message": f"IP {ip_addr} 已解封",
                    })
                else:
                    service.ip_mgr_repo.update_status(ip_addr, actual_room_id, IPStatus.BANNED)
                    _clear_ban_pending(ip_addr, actual_room_id)
                    result["failed"].append({"ip": ip_addr, "error": "SSH 命令下发失败"})
            except Exception as exc:
                logger.error("批量解封 %s 数据库同步失败: %s", ip_addr, exc)
                result["failed"].append({"ip": ip_addr, "error": str(exc)})

        try:
            service.session.commit()
        except Exception as exc:
            logger.error("批量解封阶段3 commit 失败: %s", exc)
            service.session.rollback()

        for ip_addr, _, _, _, actual_room_id in items:
            try:
                new_status = detect_ip_status(ip_addr)
                if new_status != IPStatus.INACTIVE:
                    service.ip_mgr_repo.update_status(ip_addr, actual_room_id, new_status)
                    service.session.commit()
            except Exception as exc:
                logger.warning("批量解封后探测 IP %s 状态失败（不影响解封结果）: %s", ip_addr, exc)

    return result


BAN_PENDING_TTL = 300


def _mark_ban_pending(ip_address: str, room_id: int, switch_id: int, ban_mode: str) -> None:
    try:
        from app.utils.cache import cache_manager
        import json
        key = f"ipm:ban_pending:{room_id}:{ip_address}"
        cache_manager.set(key, json.dumps({
            "switch_id": switch_id, "ban_mode": ban_mode,
        }), ttl=BAN_PENDING_TTL)
    except Exception:
        logger.warning("标记封禁pending失败: ip=%s, room_id=%d", ip_address, room_id, exc_info=True)


def _clear_ban_pending(ip_address: str, room_id: int) -> None:
    try:
        from app.utils.cache import cache_manager
        key = f"ipm:ban_pending:{room_id}:{ip_address}"
        cache_manager.delete(key)
    except Exception:
        logger.warning("清除封禁pending失败: ip=%s, room_id=%d", ip_address, room_id, exc_info=True)


def _verify_ban_output(output: str, ip: str, action: str) -> None:
    if not output:
        return
    error_patterns = re.compile(
        r'^(Error|Invalid|Failed|Incomplete)\b', re.IGNORECASE | re.MULTILINE
    )
    match = error_patterns.search(output)
    if match:
        if action == "unban":
            not_found_patterns = re.compile(
                r'(?:does not exist|not exist|not found|no such|未找到|不存在)',
                re.IGNORECASE,
            )
            if not_found_patterns.search(output):
                raise BanConfigNotFoundError(
                    reason=f"交换机返回: {match.group()!r} — {output[:200]}"
                )
        raise BanCommandFailed(
            f"{action} 命令输出异常（关键词: {match.group()!r}）\n输出: {output[:500]}"
        )


def check_ban_consistency(room_id: int = None) -> dict:
    import json
    from app.utils.cache import cache_manager
    from app.models.ip_model import IPManager
    from app.persistence.ip_repositories import IPManagerRepository, IPBanRecordRepository

    result = {"inconsistent": [], "pending_timeout": [], "pending_stuck": []}

    repo = IPManagerRepository()
    ban_repo = IPBanRecordRepository()
    session = repo.session

    query = ban_repo.find_all_active()
    if room_id is not None:
        query = [r for r in query if r.room_id == room_id]

    batch_size = 500
    offset = 0
    while True:
        batch = query[offset:offset + batch_size]
        if not batch:
            break
        ip_room_pairs = [(rec.ip_address, rec.room_id) for rec in batch]
        ip_addrs = [p[0] for p in ip_room_pairs]
        room_ids = list({p[1] for p in ip_room_pairs})
        ip_records_map = {}
        for rec in repo.session.query(IPManager).filter(
            IPManager.ip_address.in_(ip_addrs),
            IPManager.room_id.in_(room_ids),
        ).all():
            ip_records_map[(rec.ip_address, rec.room_id)] = rec

        for rec in batch:
            ip_record = ip_records_map.get((rec.ip_address, rec.room_id))
            if ip_record and ip_record.status not in (IPStatus.BANNED, IPStatus.PENDING_BAN):
                result["inconsistent"].append({
                    "ip": rec.ip_address, "room_id": rec.room_id,
                    "ban_mode": rec.ban_mode, "switch_id": rec.switch_id,
                    "actual_status": ip_record.status.name,
                })
        offset += batch_size

    try:
        redis_client = cache_manager.primary_storage.redis_client
        if redis_client:
            pattern = f"ipm:ban_pending:{room_id if room_id else '*'}:*"
            for key in redis_client.scan_iter(match=pattern):
                data = cache_manager.get(key)
                if data:
                    parts = key.split(":")
                    r_id = int(parts[-2])
                    ip = parts[-1]
                    result["pending_timeout"].append({
                        "ip": ip, "room_id": r_id,
                        "detail": json.loads(data) if isinstance(data, str) else data,
                    })
    except Exception:
        logger.warning("检查封禁pending超时失败", exc_info=True)

    pending_query = repo.session.query(IPManager).filter(
        IPManager.status.in_((IPStatus.PENDING_BAN, IPStatus.PENDING_UNBAN))
    )
    if room_id is not None:
        pending_query = pending_query.filter(IPManager.room_id == room_id)

    for ip_record in pending_query.all():
        redis_key = f"ipm:ban_pending:{ip_record.room_id}:{ip_record.ip_address}"
        redis_pending = False
        try:
            redis_pending = cache_manager.get(redis_key) is not None
        except Exception:
            pass

        if not redis_pending:
            result["pending_stuck"].append({
                "ip": ip_record.ip_address,
                "room_id": ip_record.room_id,
                "status": ip_record.status.name,
                "suggestion": (
                    "重试封禁" if ip_record.status == IPStatus.PENDING_BAN else "重试解封"
                ),
            })

    if result["inconsistent"] or result["pending_timeout"] or result["pending_stuck"]:
        logger.warning(
            "封禁一致性检查: inconsistent=%d, pending_timeout=%d, pending_stuck=%d",
            len(result["inconsistent"]), len(result["pending_timeout"]),
            len(result["pending_stuck"]),
        )

    return result
