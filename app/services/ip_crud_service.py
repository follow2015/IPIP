# -*- coding: utf-8 -*-
"""IP CRUD 服务"""
import asyncio
from app.utils.logging import get_logger
from typing import List, Optional

from app.core.enums import IPStatus
from config import Config
from app.persistence.ip_repositories import IPManagerRepository
from app.services.switch_events import emit_resource_change_global
from app.services.ip_status_service import detect_ip_status, _async_ping, _async_tcp_probe

logger = get_logger(__name__)


class IPCrudService:
    """IP地址CRUD服务"""

    def __init__(self, repo: IPManagerRepository):
        self.repo = repo

    def _assert_unambiguous_scope(self, ip_list: List[str], room_id: Optional[int]) -> None:
        """跨机房歧义守卫：room_id 未限定且目标 IP 存在于多个机房时拒绝执行。

        同一私网 IP 在多个机房各有一条记录（(ip_address, room_id) 唯一约束）。
        room_id=None 时 UPDATE 会波及全部匹配行——曾导致"释放一个机房的 IP，
        另一个机房的同名 IP 被连带释放"（2026-09-08 rooms 16/17 事故）。
        涉及多机房归属变更必须显式指定机房。
        """
        if room_id is not None:
            return
        rows = self.repo.get_by_ips(ip_list)
        rooms_by_ip: dict = {}
        for r in rows:
            rooms_by_ip.setdefault(r.ip_address, set()).add(r.room_id)
        ambiguous = {ip: rooms for ip, rooms in rooms_by_ip.items() if len(rooms) > 1}
        if ambiguous:
            detail = ", ".join(
                f"{ip}（机房 {sorted(r for r in rooms if r is not None)}）"
                for ip, rooms in sorted(ambiguous.items())
            )
            from app.exceptions.validation import ValidationError
            raise ValidationError(
                f"以下 IP 存在于多个机房，归属变更必须指定机房：{detail}"
            )

    def update_ip_customer(self, ip_address: str, customer_id: int, room_id: Optional[int] = None) -> int:
        """更新IP客户关联，并留痕到 IP 审计日志"""
        self._assert_unambiguous_scope([ip_address], room_id)

        if customer_id is not None:
            from app.services.customer_service import CustomerService
            from app.persistence.customer_repository import CustomerRepository
            CustomerService(CustomerRepository()).assert_allocatable(customer_id)

        before = [
            (r.ip_address, r.room_id, r.customer_id)
            for r in self.repo.get_by_ips([ip_address], room_id)
        ]
        result = self.repo.update_customer_by_ip(ip_address, customer_id, room_id)
        if result:
            emit_resource_change_global("ip", "update", ids=[ip_address])
            self._audit_customer_change(before, customer_id)
        return result

    def batch_update_customer(self, ip_list: List[str], customer_id: Optional[int],
                              room_id: Optional[int] = None) -> int:
        """批量更新IP客户关联，并留痕到 IP 审计日志

        收敛原先 API 层直调 Repository 的写法：审计挂钩只应存在于 Service 层，
        否则留痕逻辑散落在 API 层，后续新增入口极易漏挂。
        """
        if customer_id is not None:
            from app.services.customer_service import CustomerService
            from app.persistence.customer_repository import CustomerRepository
            CustomerService(CustomerRepository()).assert_allocatable(customer_id)

        self._assert_unambiguous_scope(ip_list, room_id)

        before = [
            (r.ip_address, r.room_id, r.customer_id)
            for r in self.repo.get_by_ips(ip_list, room_id)
        ]
        count = self.repo.batch_update_customer_by_ips(customer_id, ip_list, room_id)
        if count:
            self._audit_customer_change(before, customer_id)
        return count

    def _audit_customer_change(
        self, before: List[tuple], customer_id: Optional[int],
    ) -> None:
        """IP 归属变更留痕（提交后执行，best-effort）

        Args:
            before: UPDATE 前的归属快照 [(ip_address, room_id, prev_customer_id), ...]，
                调用方必须在 UPDATE 前提取（原因见 update_ip_customer 注释）
            customer_id: 新归属（None 表示 release）

        只记录真正发生变更的行（重复保存同值不留痕，与批量/网段路径口径一致）；
        只记录人工操作：无请求上下文时（定时任务/系统扫描）取不到操作人，直接
        跳过。这是「系统驱动动作不记录」的结构性保证——将来任何系统调用复用
        本 Service，都不会把系统动作静默记成人工分配。
        """
        from app.utils.auth import get_current_user_id
        from app.utils.transactional import on_commit
        from app.persistence.ip_audit_repository import IPAuditRepository
        from app.services.ip_audit_service import IPAuditService

        try:
            operator_id = get_current_user_id()
        except Exception:  # noqa: BLE001 - 无 app context 时访问 flask.g 会抛异常
            operator_id = None
        if operator_id is None:
            logger.debug("无操作人上下文，跳过IP归属审计留痕: %d 条", len(before))
            return

        changed = [(ip, rid, prev) for ip, rid, prev in before if prev != customer_id]
        if not changed:
            return

        action = "allocate" if customer_id is not None else "release"
        names = IPAuditService.load_customer_names(
            {customer_id, *(prev for _, _, prev in changed)}
        )

        entries = []
        for ip, rid, prev_id in changed:
            detail = {
                "customer_id": customer_id,
                "customer_name": names.get(customer_id),
            }
            if prev_id is not None:
                detail["prev_customer_id"] = prev_id
                detail["prev_customer_name"] = names.get(prev_id)
            entries.append({
                "ip_address": ip,
                "room_id": rid,
                "action": action,
                "detail": detail,
            })

        on_commit(
            lambda: IPAuditService(IPAuditRepository()).record_allocation_batch(
                entries, operator_id=operator_id,
            )
        )

    def get_ip_notes(self, ip_address: str, room_id: Optional[int] = None) -> list:
        """获取IP备注"""
        return self.repo.find_notes_by_ip(ip_address, room_id)

    def update_ip_notes(self, ip_address: str, notes: str, room_id: Optional[int] = None) -> int:
        """更新IP备注"""
        result = self.repo.update_notes_by_ip(ip_address, notes, room_id)
        if result:
            emit_resource_change_global("ip", "update", ids=[ip_address])
        return result

    def get_ip_detail(self, ip_address: str, room_id: Optional[int] = None) -> Optional[dict]:
        """获取IP详细信息"""
        record = self.repo.find_by_ip_address(ip_address)
        return record.to_dict() if record else None

    def get_ip_addresses_paginated(self, keyword: str = None, customer_id: int = None, room_id: int = None, status: int = None, page: int = 1, page_size: int = 20) -> dict:
        """分页查询IP列表"""
        return self.repo.search_ips(keyword, customer_id, room_id, status, page, page_size)

    def ping_ip(self, ip_address: str) -> bool:
        """Ping检测"""
        status = detect_ip_status(ip_address)
        return status == IPStatus.ACTIVE

    def scan_ports(self, ip_address: str, ports: list = None) -> dict:
        """端口扫描，返回开放端口列表

        用 _async_tcp_probe 异步探测指定端口，默认扫 Config.COMMON_PORTS。
        """
        port_list = ports if ports else list(Config.COMMON_PORTS)
        loop = asyncio.new_event_loop()
        try:
            open_ports = loop.run_until_complete(self._scan_ports_async(ip_address, port_list))
        finally:
            loop.close()
        return {"ip_address": ip_address, "open_ports": open_ports}

    async def _scan_ports_async(self, ip_address: str, ports: list) -> list:
        """异步并发探测多个端口，返回开放端口列表"""
        tasks = [_async_tcp_probe(ip_address, int(p), timeout=1.5) for p in ports]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        open_ports = []
        for port, ok in zip(ports, results):
            if ok is True:
                open_ports.append(int(port))
        return open_ports


IPRudService = IPCrudService
