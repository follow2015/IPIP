# -*- coding: utf-8 -*-
"""多通道采集 · CLI（SSH）通道 ``CliChannel``（T0.5）。

把既有 CLI 链路包进 :class:`BaseChannel`，**不改变任何既有采集行为**：

- 命令完全由 ``get_adapter()`` 提供（100% 委托，零重写），解析亦然；
- 转换规则复用 ``cli_translate`` / ``port_rows`` 的共享实现，保证与
  ``ScanOrchestrator._collect_single`` 逐字段一致。

两条施工要点（计划 T0.5 的验收口径）—— 会话层细节见
:mod:`app.services.collector._cli_session`：

1. **握手 N→1**：per-device 会话 + 互斥锁，把命令发送串行化（一条连接多次复用）；
2. **单命令粒度重试**：语义对齐 ``SSHManager._execute_with_retry``，不在连接粒度
   整体重试，但连接确实断掉时重建一次再重发。

能力矩阵（T0.7 定稿）：

- ``LLDP`` 已声明（``FULL``）：适配器契约（``get_lldp_neighbor_command()`` /
  ``parse_lldp_neighbors()``）现成且经拓扑模块（P2-1）验证，通道层把它**纳入
  统一采集契约**，解析零重复。现役 ``full_scan`` 不请求 LLDP，故声明不改变
  既有扫描行为；CDP 回退是拓扑服务的编排行为，通道层刻意不复刻（见
  ``_collect_lldp`` docstring）。
- ``OPTICS`` / ``COUNTERS`` 仍**不声明**：CLI 侧无现役实现，声明即
  "假 advertised"（F6 的成因）。这两个能力的现役原语在 CLI 侧不存在，
  归 G 阶段随真实需求落地。
"""
from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any

from app.adapters.adapter_factory import get_adapter
from app.core.enums import CollectCapability, QualityLevel
from app.exceptions.system import SSHConnectionError, SwitchConfigError
from app.infra import RETRY_BASE, MAX_RETRIES, SSHManager
from app.persistence.switch_repo import SwitchRepository
from app.services.collector._cli_session import (
    DEFAULT_IDLE_TTL,
    DEFAULT_READ_TIMEOUT,
    _CliSession,
    _DEAD_CONNECTION_EXC_NAMES,
    _SessionPool,
)
from app.services.collector.base_channel import BaseChannel, implements
from app.services.collector.cli_device_info import collect_full_device_info
from app.services.collector.cli_translate import (
    translate_arps,
    translate_device_info,
    translate_macs,
    translate_routes,
)
from app.services.port_rows import build_port_rows
from app.utils.logging import get_logger

logger = get_logger(__name__)

class CliChannel(BaseChannel):
    """CLI（SSH）采集通道。

    构造参数全部可注入：既有服务层（``SwitchInfoService``）的依赖注入风格在
    项目里已是常态，单测也因此不必连真机。
    """

    code = "cli"

    def __init__(
        self,
        ssh_manager: SSHManager | None = None,
        switch_repo: Any | None = None,
        idle_ttl: float = DEFAULT_IDLE_TTL,
    ) -> None:
        self._ssh = ssh_manager or SSHManager()
        self._repo = switch_repo
        self._pool = _SessionPool(self._ssh, idle_ttl=idle_ttl)

    @property
    def repo(self) -> Any:
        if self._repo is None:
            self._repo = SwitchRepository()
        return self._repo

    def _switch(self, device_id: int) -> Any:
        """取 ``SwitchCredentials``（按 device_id，而非 switch_credentials.id）。"""
        switch = self.repo.find_by_device_id(device_id)
        if switch is None:
            raise ValueError(f"交换机 device_id={device_id} 不存在或未配置 SSH 凭据")
        return switch

    @staticmethod
    def _layer_of(switch: Any) -> int:
        """设备层级（2/3），口径与 ``_load_switch_metas`` 一致：``device.layer or 3``。

        注意此处**不使用** ``scan_switch`` 的 ``ext.layer or 2`` 口径：两条路径的
        默认值不同是既有代码的分歧点（详见施工记要），包壳必须复刻 **被包的那一
        条**（``full_scan`` → ``_collect_single`` → SwitchMeta.layer）。
        """
        device = getattr(switch, "device", None)
        return (getattr(device, "layer", None) or 3)

    def is_available(self, device_id: int) -> bool:
        """凭据齐备 + ``has_ssh`` 为真即视为可用。

        不做网络探测（那是 ``health_probe`` 的事）：``is_available`` 会被选择器
        频繁调用，每次都握手会把"选择"变成"采集"。
        """
        try:
            switch = self.repo.find_by_device_id(device_id)
        except Exception as exc:
            logger.error("CliChannel.is_available 无法读取凭据 device_id=%s: %s",
                         device_id, exc)
            raise
        if switch is None:
            return False
        return bool(getattr(switch, "has_ssh", False))

    def health_probe(self, device_id: int) -> bool:
        """轻量健康检查：建连后立即断开（Selector 的熔断判据）。

        成本是一次完整握手 —— 这是当前基础设施能提供的最诚实信号
        （``SSHManager.test_connection`` 还要额外发一条 version 命令）。后续
        若接入在选择路径上被调用得太频繁，应改为带 TTL 的探测结果缓存。
        """
        switch = self._switch(device_id)
        probe_session = _CliSession(device_id, self._ssh)
        try:
            probe_session.connect(switch)
            return True
        except Exception as exc:  # noqa: BLE001 -- CLI 健康检查失败返回 False：采集通道探测不得抛错
            logger.warning("CLI 健康检查失败 device_id=%s: %s", device_id, exc)
            return False
        finally:
            probe_session.close()

    def _read_timeout(self, timeout: float | None) -> int:
        if timeout is None:
            return DEFAULT_READ_TIMEOUT
        return max(1, int(timeout))

    def _deadline(self, timeout: float | None) -> float:
        """把"剩余预算（秒）"折算成**绝对截止时刻**，供本批次内逐步收紧。

        [WARN] 评审 P0-4：模板层超时只是"放弃等待"，被杀不掉的工作线程若拿的是
        一个固定 read_timeout，会在每次重试/每条命令上**重新开满窗口**
        （3 条命令 × 3 次重试 = 最多 9 倍预算）。改为绝对时刻后，每个 I/O 前重算
        剩余量，越界就立刻收手 —— 线程自己看得见截止时间。
        """
        budget = DEFAULT_READ_TIMEOUT if timeout is None else max(0.1, float(timeout))
        return time.monotonic() + budget

    def _send(self, device_id: int, switch: Any, command: str, timeout: float | None) -> str:
        """在复用连接上发一条命令，**单命令粒度重试**。

        串行化在这里：同一设备的多个能力可能被并发调度（``collect`` 是并发模板），
        但同一条 netmiko 连接同时只接受一个命令。

        ``timeout`` 是本次可用时间（相对秒）；内部折算成截止时刻贯穿连接与重试。
        """
        session = self._pool.get(device_id)
        deadline = self._deadline(timeout)
        with session.in_use(), session.lock:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SSHConnectionError(
                    f"device_id={device_id} 预算已耗尽，未发起命令：{command}"
                )
            session.touch()
            if not session.connected:
                session.connect(switch)
                if deadline - time.monotonic() <= 0:
                    raise SSHConnectionError(
                        f"device_id={device_id} 握手已耗尽预算，未发起命令：{command}"
                    )
            return self._execute_with_retry_locked(
                session, switch, command, deadline, in_lock=True,
            )

    def _execute_with_retry_locked(
        self,
        session: _CliSession,
        switch: Any,
        command: str,
        deadline: float,
        *,
        in_lock: bool,
    ) -> str:
        """``SSHManager._execute_with_retry`` 的"复用连接版"。

        参数与退出行为严格对齐原实现（``MAX_RETRIES`` / ``RETRY_BASE`` /
        ``SwitchConfigError`` 不重试 / 耗尽抛 ``SSHConnectionError``），只在三点
        上不同，且都是为了让语义在"复用连接"下仍然成立：

        1. 重试不再重新握手（这正是握手 N→1 的收益）；
        2. 命中"连接已死"的异常时**重建一次连接**再重发 —— 否则同连接上的后
           两次尝试必然重蹈同一个失败，等于把 3 次容错退化成 1 次；
        3. **每次尝试按截止时刻重算窗口**（评审 P0-4）：不再每次重试都开满
           ``DEFAULT_READ_TIMEOUT``，剩余不足就立刻收手（返回超时错误），
           保证单能力的实际耗时收敛在预算内而不是 3~9 倍。

        ``in_lock`` 只是让重连路径确认自己确实持有锁（重构保护）：持有锁才能
        安全地调换 ``session.conn``。
        """
        if not in_lock:  # pragma: no cover - 守卫误用，正常调用路径不会走到
            raise AssertionError("_execute_with_retry_locked 必须在持有会话锁时调用")

        last_exc: BaseException | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SSHConnectionError(
                    f"device_id={session.device_id} 命令 {command} 超出预算，"
                    f"已放弃第 {attempt}/{MAX_RETRIES} 次尝试"
                ) from last_exc
            read_timeout = max(1, int(min(DEFAULT_READ_TIMEOUT, remaining)))
            try:
                return self._ssh.execute_show_on_conn(session.conn, command, read_timeout)
            except Exception as exc:
                last_exc = exc
                if isinstance(exc, SwitchConfigError):
                    raise
                if attempt >= MAX_RETRIES:
                    break
                logger.warning(
                    "CLI 命令失败 device_id=%s attempt=%d/%d: %s",
                    session.device_id, attempt, MAX_RETRIES, exc,
                )
                if self._looks_dead(exc):
                    try:
                        session.reconnect(switch)
                    except Exception as recon_exc:  # noqa: BLE001 -- SSH 重连失败容错：记录后由上层决定降级
                        logger.warning(
                            "重建 SSH 连接失败 device_id=%s: %s",
                            session.device_id, recon_exc,
                        )
                time.sleep(RETRY_BASE * (2 ** (attempt - 1)))

        raise SSHConnectionError(
            f"SSH 到 device_id={session.device_id} 执行命令连续 {MAX_RETRIES} 次失败"
        ) from last_exc

    @staticmethod
    def _looks_dead(exc: BaseException) -> bool:
        """异常是否表明连接已不可用（值得重连后再试）。"""
        if isinstance(exc, SSHConnectionError):
            return True
        if type(exc).__name__ in _DEAD_CONNECTION_EXC_NAMES:
            return True
        return isinstance(exc, (EOFError, OSError))

    @implements(CollectCapability.PORTS, QualityLevel.FULL)
    def _collect_ports(self, device_id: int, timeout: float | None = None) -> list[dict]:
        switch = self._switch(device_id)
        adapter = get_adapter(switch.device_type)
        output = self._send(device_id, switch, adapter.get_interface_command(), timeout)
        return build_port_rows(adapter.parse_ports(output))

    @implements(CollectCapability.ARP, QualityLevel.FULL)
    def _collect_arp(self, device_id: int, timeout: float | None = None) -> list[dict]:
        switch = self._switch(device_id)
        adapter = get_adapter(switch.device_type)
        output = self._send(device_id, switch, adapter.get_arp_command(), timeout)
        return translate_arps(adapter.parse_arp(output))

    @implements(CollectCapability.MAC, QualityLevel.FULL)
    def _collect_mac(self, device_id: int, timeout: float | None = None) -> list[dict]:
        switch = self._switch(device_id)
        adapter = get_adapter(switch.device_type)
        output = self._send(device_id, switch, adapter.get_mac_command(), timeout)
        return translate_macs(adapter.parse_mac_table(output))

    @implements(CollectCapability.ROUTES, QualityLevel.FULL)
    def _collect_routes(self, device_id: int, timeout: float | None = None) -> list[dict]:
        """路由表：**仅 L3 设备**，与 ``_collect_single`` 同口径。

        复刻的是"L2 设备不发这条命令"这个行为 —— 对二层/接入交换机发
        ``display ip routing-table`` 既拿不到有意义的结果，又把整设备时间预算
        花在一次注定为空的命令上。返回空列表落在 ``EMPTY``（确定答案，不补采）。
        """
        switch = self._switch(device_id)
        if self._layer_of(switch) != 3:
            return []
        adapter = get_adapter(switch.device_type)
        output = self._send(device_id, switch, adapter.get_route_command(), timeout)
        return translate_routes(adapter.parse_routes(output))

    @implements(CollectCapability.DEVICE_INFO, QualityLevel.FULL)
    def _collect_device_info(self, device_id: int, timeout: float | None = None) -> dict:
        switch = self._switch(device_id)
        adapter = get_adapter(switch.device_type)
        deadline = self._deadline(timeout)
        info = collect_full_device_info(
            switch, adapter,
            send_command=lambda sw, cmd: self._send(
                device_id, sw, cmd, deadline - time.monotonic()
            ),
        )
        return translate_device_info(info)

    @implements(CollectCapability.LLDP, QualityLevel.FULL)
    def _collect_lldp(self, device_id: int, timeout: float | None = None) -> list[dict]:
        """LLDP 邻居表（T0.7 纳入统一采集契约）。

        与 ``TopologyDiscoveryService.discover_switch`` 用**同一套适配器契约**
        （``get_lldp_neighbor_command()`` / ``parse_lldp_neighbors()``，P2-1 已
        在拓扑模块验证），解析逻辑零重复 —— 通道层只做"统一契约出口"。

        **刻意不做 CDP 回退**：LLDP 空结果时回退 CDP 是拓扑服务的**编排行为**
        （``source`` 从 lldp 切到 cdp），通道层复刻它会形成第二真源；
        ``base_adapter.get_cdp_neighbor_command`` 的契约本身也是"不支持的厂商
        返回 None、不做回退"。未来若需回退，``ParsedLldpNeighbor.protocol``
        字段已预留来源标注。

        产出经 ``asdict`` 转 JSON 可序列化 dict：``CollectedFacts`` 其余能力
        字段（ports/arps/...）均为 dict 形态，LLDP 保持同构；字段名与
        ``ParsedLldpNeighbor`` 一致（local_port / neighbor_sysname /
        neighbor_port / neighbor_mgmt_ip / chassis_id / protocol）。

        设备未启用 LLDP 时输出无邻居块 → 解析返回空列表 → ``EMPTY``
        （确定答案，不补采、不记 error）。
        """
        switch = self._switch(device_id)
        adapter = get_adapter(switch.device_type)
        output = self._send(device_id, switch, adapter.get_lldp_neighbor_command(), timeout)
        return [asdict(neighbor) for neighbor in adapter.parse_lldp_neighbors(output)]

    def release(self, device_id: int) -> None:
        """释放该设备的 SSH 连接（扫描结束后由上层调用）。"""
        self._pool.release(device_id)

    def release_all(self) -> None:
        """释放全部连接。进程退出前 / 一次扫描结束后调用。"""
        self._pool.release_all()


__all__ = ["CliChannel", "DEFAULT_READ_TIMEOUT"]
