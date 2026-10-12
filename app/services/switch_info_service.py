# -*- coding: utf-8 -*-
"""
交换机信息采集服务

从交换机采集版本、端口等信息并更新数据库。
采集端口信息写入 network_ports（统一端口表）。
"""
from types import SimpleNamespace

from app.utils.logging import get_logger
import re
from app.adapters.adapter_factory import get_adapter
from app.adapters.base_adapter import ParsedDeviceInfo
from app.infra import SSHManager
from app.persistence.switch_port_repository import NetworkPortRepository
from app.persistence.switch_repo import SwitchRepository
from app.services.collector.cli_device_info import (
    collect_hostname_if_missing,
    collect_serial_if_missing,
)
from app.services.collector.facts_adapter import legacy_trace
from app.services.port_rows import build_port_rows
from app.utils.port_name_utils import LAG_PORT_NAME_RE, VLAN_PORT_NAME_RE

logger = get_logger(__name__)

__all__ = [
    "LAG_PORT_NAME_RE",
    "ChannelSyncError",
    "SwitchInfoService",
    "VLAN_PORT_NAME_RE",
]


class ChannelSyncError(RuntimeError):
    """通道层 SNMP 同步**采集失败**（评审 N13）。

    为什么需要它：``sync_*_via_channel`` 系列有三种"没同步"的情形，原先一律
    ``return 0``：

    1. 设备不在台账 / 通道未放行该设备（``selector is None``）—— **不适用**，正常；
    2. 设备没开放该 MIB 子树、本次确实没采到（``rows`` 为空）—— **空结果**，正常；
    3. 采集过程抛错（超时 / 认证 / 解析）—— **失败**，本应可见。

    前两种是确定性结论，第三种是故障，但三者返回值一模一样 ⇒ 调用方（扫描器）无法
    区分，"SNMP 子阶段整体失败"在界面上完全不可见（``progress`` 里一个信号都没有）。
    这个异常把第 3 种单独标记出来，由调用方**按能力分别计入进度**并记 error 日志。

    语义边界：本异常只表示"这次没采到" —— 它**不**使整轮扫描失败（调用方必须
    逐能力捕获，见 ``network_scanner_service`` 的 Phase 0d-snmp），这是既有
    "Phase 隔离"纪律的一部分。
    """

    def __init__(self, capability: str, device_id: int, cause: object) -> None:
        super().__init__(f"通道层 {capability} 采集失败 device_id={device_id}: {cause}")
        self.capability = capability
        self.device_id = device_id


class SwitchInfoService:
    """交换机信息采集服务"""

    def __init__(self, ssh_manager: SSHManager = None):
        self.ssh_mgr = ssh_manager or SSHManager()
        self.sw_repo = SwitchRepository()
        self.port_repo = NetworkPortRepository()

    def collect_device_info(self, device_id: int) -> dict:
        """采集交换机设备信息并更新数据库

        采集步骤：
        1. 执行 display version，由适配器解析 model / version / uptime
        2. 若适配器未能解析出序列号，则发送设备特定命令补充采集（支持多槽位框架交换机）
        3. 执行 display sysname / show hostname，解析主机名
        4. 将采集结果写回：model/serial/hostname → Device，version/uptime → SwitchCredentials

        Args:
            device_id: 交换机 device_id（devices.id，统一交换机标识）

        Returns:
            dict: {success, switch_id, info} 或 {success, switch_id, error}
        """
        switch = self.sw_repo.find_by_device_id(device_id)
        if not switch:
            raise ValueError(f"交换机 device_id={device_id} 不存在")

        adapter = get_adapter(switch.device_type)

        try:
            version_output = self.ssh_mgr.send_show_command(
                switch, adapter.get_version_command(),
            )
            info = adapter.parse_device_info(version_output)

            if not info.serial:
                info = self._collect_serial(switch, info)

            if not info.hostname:
                info = self._collect_hostname(switch, adapter, info)

            if info.model:
                switch.device.device_model = info.model
            if info.serial:
                switch.device.serial_number = info.serial
            if info.hostname:
                switch.device.hostname = info.hostname
            if info.brand:
                switch.device.brand = info.brand

            from app.models.switch_credentials import SwitchStatusCache
            from app.persistence.switch_status_cache_repository import (
                SwitchStatusCacheRepository,
            )

            cache = SwitchStatusCacheRepository(
                session=self.sw_repo.session
            ).find_by_device(device_id)
            if not cache:
                cache = SwitchStatusCache(device_id=device_id)
                self.sw_repo.session.add(cache)
            if info.version:
                cache.device_version = info.version
            if info.uptime:
                cache.device_uptime = info.uptime

            self.sw_repo.session.flush()
            return {"success": True, "switch_id": device_id, "info": info}

        except Exception as e:  # noqa: BLE001 -- 设备信息采集失败转结构化返回：SSH/解析异常不可枚举
            logger.error("采集交换机 device_id=%d 设备信息失败: %s", device_id, e)
            return {"success": False, "switch_id": device_id, "error": str(e)}

    def _collect_serial(
        self, switch, info: ParsedDeviceInfo,
    ) -> ParsedDeviceInfo:
        """补充采集序列号（当适配器版本解析未能获取 serial 时调用）

        华为设备：display esn（收集所有槽位 ESN）
        H3C 设备：display device manuinfo

        多槽位框架交换机的序列号以逗号拼接存储。

        实现委托给 ``collector.cli_device_info.collect_serial_if_missing``
        （T0.5）：补采规则现在被 ``CliChannel`` 的 DEVICE_INFO 能力复用，
        抽走后本方法保留为**薄转发**，命令串/正则/异常降级语义都不变。

        Args:
            switch: 交换机对象
            info: 已解析的设备信息（serial 为空）

        Returns:
            ParsedDeviceInfo: 填充了 serial 字段的新实例（其余字段不变）
        """
        return collect_serial_if_missing(switch, info, self.ssh_mgr.send_show_command)

    def _collect_hostname(
        self, switch, adapter, info: ParsedDeviceInfo,
    ) -> ParsedDeviceInfo:
        """采集交换机主机名

        通过 display sysname（华为/H3C）或 show hostname（Cisco）获取主机名。
        部分设备可能不支持该命令，此时静默跳过。

        同样委托给 ``collector.cli_device_info.collect_hostname_if_missing``
        （T0.5），本方法保留为薄转发。

        Args:
            switch: 交换机对象（SwitchCredentials）
            adapter: 设备适配器实例
            info: 已解析的设备信息

        Returns:
            ParsedDeviceInfo: 填充了 hostname 字段的新实例
        """
        return collect_hostname_if_missing(
            switch, adapter, info, self.ssh_mgr.send_show_command,
        )

    def collect_port_info(self, device_id: int, *, triggered_by_auto: bool = False,
                          virtual_room_id: int | None = None) -> dict:
        """采集交换机端口信息并增量更新

        **G1.5 接管分流**（2026-10-05，设计文档《接管落库与无SSH设备主路径设计》R1 版）：
        先问通道层"这台设备该不该由我采"，再决定走哪条路 ——

        - **无 SSH 且 SNMP 被白名单放行** ⇒ 通道层（SNMP）为**主路径**，产出直接落库；
          这是"仅开放只读 SNMP 的接入交换机"首次能采到真实端口的路径（此前扫不到）。
        - 其余设备（含所有有 SSH 设备）⇒ 既有 CLI 直采路径，**行为零变更**。

        :param triggered_by_auto: 本次来自**自动扫描**（调度）时为真。除总开关外，
            通道层还要求 `SCAN_CHANNEL_AUTO_ENABLED`（G3 才放开）；同时它决定
            **影子对照不参与**（R9：SNMP 不得进入自动扫描关键路径）。

        Args:
            device_id: 交换机 device_id（devices.id，统一交换机标识）

        Returns:
            dict: {success, switch_id, port_count, channel?} 或 {success, switch_id, error}
        """
        switch = self.sw_repo.find_by_device_id(device_id)
        if not switch:
            raise ValueError(f"交换机 device_id={device_id} 不存在")

        taken = self._try_channel_takeover(switch, triggered_by_auto=triggered_by_auto,
                                           virtual_room_id=virtual_room_id)
        if taken is not None:
            return taken

        return self._legacy_collect_port_info(device_id, switch,
                                              triggered_by_auto=triggered_by_auto,
                                              virtual_room_id=virtual_room_id)

    def _apply_device_identity(self, switch, di: dict | None) -> None:
        """把通道层采到的设备身份写回（对齐 CLI ``collect_device_info`` 的语义）。

        原则：**真实设备采到的数据是最高优先级数据源** —— 有值即写回，``None``
        不清空（避免"这轮没采到"把上轮的正确值抹掉）。
        ``device_type``（驱动）由 brand 推导：sysObjectID 企业号是权威来源。

        抽成方法而不是内联在接管里：扫描路径（``scan_switch``）也要用它 —— 两处
        各写一份必然漂移，而漂移的表现是"某条路径上型号/序列号永远为空"。
        """
        if not di:
            return
        device = switch.device
        if device is not None:
            if di.get("model"):
                device.device_model = di["model"]
            if di.get("serial"):
                device.serial_number = di["serial"]
            if di.get("hostname"):
                device.hostname = di["hostname"]
            if di.get("brand"):
                device.brand = di["brand"]
                if not switch.device_type:
                    switch.device_type = str(di["brand"]).lower()
        from app.models.switch_credentials import SwitchStatusCache
        from app.persistence.switch_status_cache_repository import (
            SwitchStatusCacheRepository,
        )

        cache = SwitchStatusCacheRepository(
            session=self.sw_repo.session
        ).find_by_device(switch.device_id)
        if not cache:
            cache = SwitchStatusCache(device_id=switch.device_id)
            self.sw_repo.session.add(cache)
        if di.get("version"):
            cache.device_version = di["version"]
        if di.get("uptime"):
            cache.device_uptime = di["uptime"]
        self.sw_repo.session.flush()
        logger.info(
            "通道层设备身份回填 device_id=%s brand=%s model=%s serial=%s "
            "hostname=%s version=%s 驱动=%s",
            switch.device_id, di.get("brand"), di.get("model"), di.get("serial"),
            di.get("hostname"), di.get("version"), switch.device_type,
        )

    def collect_device_identity_via_channel(self, device_id: int) -> bool:
        """扫描路径专用：无 SSH 设备经通道层采设备信息并回填（型号/序列号/版本…）。

        为什么单开这个入口（2026-10-07 实测暴露）：``selector_for_snmp_takeover``
        在 ``triggered_by_auto=True`` 时还会要求 ``SCAN_CHANNEL_AUTO_ENABLED``（G3
        才开），而 ``scan_switch`` 正是按 auto 调 ``collect_port_info`` 的 —— 于是
        **扫描这条路径上设备身份从未被回填**：设备 178 的 SNMP 明明采得到序列号，
        ``devices.serial_number`` 却长期为 NULL，只有手动调一次非 auto 的采集才会填。

        设备身份是**主数据源**（不是影子对照），不该被 auto 这一层挡住；但仍受总
        开关与 SNMP 白名单约束 —— 走同一个 ``selector_for_snmp_takeover``，只是不
        声明 auto（等同"用户主动触发"的语义）。

        Returns:
            是否完成回填（``False`` 表示通道未放行/没采到，调用方保持原行为）。
        """
        switch = self.sw_repo.find_by_device_id(device_id)
        if switch is None:
            return False
        try:
            from app.core.enums import CollectCapability
            from app.services.collector import runtime

            selector = runtime.selector_for_snmp_takeover(
                switch, ssh_manager=self.ssh_mgr, switch_repo=self.sw_repo,
            )
            if selector is None:
                return False
            facts = selector.collect(device_id, [CollectCapability.DEVICE_INFO])
        except Exception as exc:  # noqa: BLE001 —— 身份采集失败不得中断整轮扫描
            logger.warning(
                "通道层设备信息采集失败 device_id=%s: %s", device_id, exc,
            )
            return False

        di = facts.device
        if not di:
            logger.info(
                "通道层未产出设备信息（outcomes=%s）device_id=%s",
                {k: str(v) for k, v in (facts.outcomes or {}).items()}, device_id,
            )
            return False
        self._apply_device_identity(switch, di)
        return True

    def sync_vlan_members_via_channel(self, device_id: int) -> int:
        """无 SSH 设备：用通道层采到的 VLAN 成员补上 Phase 0d（CLI 路径走不到）。

        Phase 0d 的 ``batch_sync_members`` 走 SSH（``display vlan`` /
        ``display eth-trunk``），对 ``has_ssh=False`` 的设备整段跳过 —— 这类设备
        因此永远建立不起 VLAN 成员关系。SNMP 侧 Q-BRIDGE-MIB 拿得到，这里按
        **同一个落库函数**（``sync_vlan_members``）写入，规则不与 CLI 侧漂移。

        **本方法同时补齐清理**（评审 N14）：写完成员后按"在册集合"清掉设备上已
        消失的 VLAN 残留，与 CLI 侧 ``_sync_vlan_trunk_bases`` 同口径。理由与两道
        保险见 :meth:`_prune_stale_vlans` 的 docstring。

        Returns:
            写入的 VLAN 数（0 = 通道未放行 / 设备没开放 VLAN 表 / 没采到成员）。
            **不含清理条数** —— 清理是副作用，不计入"写入"口径。

        Raises:
            ChannelSyncError: **采集失败**（区别于上面三种"确定性 0"）。由调用方
                按能力捕获并计入进度 —— 见 :class:`ChannelSyncError` 的说明。
                注意：**清理阶段不抛** —— 它在一个已成功采集的回合末尾执行，
                清理失败只是"库里留了旧记录"，不该让整个能力被记成采集失败。
        """
        switch = self.sw_repo.find_by_device_id(device_id)
        if switch is None:
            return 0
        try:
            from app.core.enums import CollectCapability
            from app.services.collector import runtime

            selector = runtime.selector_for_snmp_takeover(
                switch, ssh_manager=self.ssh_mgr, switch_repo=self.sw_repo,
            )
            if selector is None:
                return 0
            facts = selector.collect(device_id, [CollectCapability.VLANS])
        except Exception as exc:
            logger.warning("通道层 VLAN 采集失败 device_id=%s: %s", device_id, exc)
            raise ChannelSyncError("VLAN", device_id, exc) from exc

        rows = facts.vlans or []
        if not rows:
            logger.info(
                "通道层未产出 VLAN（outcomes=%s）device_id=%s",
                {k: str(v) for k, v in (facts.outcomes or {}).items()}, device_id,
            )
            return 0

        from app.utils.port_name_utils import get_vlanif_name

        synced = 0
        present_vlan_ids: set[int] = set()
        for row in rows:
            vlan_id_raw = row.get("vlan_id")
            if vlan_id_raw is None:
                continue
            try:
                vlan_id = int(vlan_id_raw)
            except (TypeError, ValueError):
                logger.warning(
                    "通道层 VLAN 行 vlan_id 不可解析，跳过 device_id=%s: %r",
                    device_id, vlan_id_raw,
                )
                continue
            present_vlan_ids.add(vlan_id)
            members = row.get("members") or []
            if not members:
                continue
            try:
                self.sw_repo.sync_vlan_members(
                    device_id, get_vlanif_name(switch.device_type, vlan_id), members,
                )
                synced += 1
            except Exception as exc:  # noqa: BLE001 —— 单个 VLAN 失败不影响其余
                logger.warning(
                    "VLAN %s 成员写入失败 device_id=%s: %s", vlan_id, device_id, exc,
                )
        self._prune_stale_vlans(device_id, present_vlan_ids, facts)
        if synced:
            logger.info(
                "通道层 VLAN 成员同步 device_id=%s 写入 %d 个 VLAN", device_id, synced,
            )
        return synced

    def _prune_stale_vlans(self, device_id: int, present_vlan_ids: set[int],
                           facts) -> int:
        """清掉设备上已消失的 VLAN 残留（与 CLI 侧 ``_sync_vlan_trunk_bases`` 同口径）。


        ``_sync_vlan_trunk_bases`` 里有一段"清理设备上已不存在的 Vlanif/Eth-Trunk 残留"，
        但它只挂在 **CLI / 接管路径** 上；而 ``sync_vlan_members_via_channel`` 恰恰是在
        接管路径没跑、或没产出逻辑端口名（``logical_names`` 为空 → 上面 else 分支明确
        跳过）时被调用的**补位入口** ⇒ 该入口建的 VLAN 记录**永不清理**。


        1. **在册集合非空**：空集等价于"设备确实没有 VLAN"**或**"采集没产出/未解析"，
           两者无法区分，而 ``NOT IN ()`` 的语义是"全部命中" ⇒ 会把该设备所有 VLAN
           删光。所以空集一律跳过（CLI 侧同一设计，见仓储 docstring 的调用方约定）。
        2. **VLANS 能力 outcome 不是 FAILED**：``FAILED`` 意味着本次是**部分/失败**的
           walk，在册集合因此是**残缺**的 —— 用它做差集删的是"没采到"而不是"已消失"。
           判据用 ``facts.needs_fallback``（公共语义 = outcome 为 FAILED），
           不直读 ``outcomes`` 里的字符串值（那是契约内部形态）。


        CLI 侧的在册集合来自 ``display interface`` 里的 **Vlanif 逻辑端口名**；本侧的
        来自 Q-BRIDGE 的 **VLAN 表**。后者是前者的**超集**（存在 VLAN 不代表配了 Vlanif，
        而配了 Vlanif 必然存在 VLAN）⇒ 本侧的集合更大、差集更小 ⇒ 删得更少。
        方向是安全的：不会删掉 CLI 侧会保留的记录。

        Args:
            present_vlan_ids: 在册集合（调用方须在"无成员则跳过"之前登记全部 id）。
            facts: 本轮 ``CollectedFacts``，只用其 outcome 做保险 2。

        Returns:
            删除的残留 VLAN 条数（级联删除其成员关系）；清理失败返回 0。

        [WARN] **清理是 best-effort，且用 savepoint 隔离**：本方法在成员写入**之后**
        执行，此时本轮的主数据已落库。若清理抛错（DB 异常 / 唯一约束 / 会话态问题），
        让它冒泡会连累同一个 ``transaction_checkpoint`` 里**已经成功的成员写入**
        （以及随后的 LAG / COUNTERS 两个能力）被整体回滚 —— 用一个"补充清理"的失败
        换掉"主体成功"，方向是错的。`begin_nested()` 把影响面收在 savepoint 内，
        失败只留 warning；残留记录下一轮再清（本方法幂等）。
        """
        if not present_vlan_ids:
            logger.info(
                "通道层 VLAN 在册集合为空，跳过残留清理（避免 NOT IN 空集全删）device_id=%s",
                device_id,
            )
            return 0

        from app.core.enums import CollectCapability

        if facts.needs_fallback(CollectCapability.VLANS):
            logger.warning(
                "VLANS 采集 FAILED，在册集合不完整，跳过残留清理（防误删）device_id=%s"
                " 在册=%d 个", device_id, len(present_vlan_ids),
            )
            return 0

        from app.persistence.vlan_repository import VLANRepository

        try:
            with self.sw_repo.session.begin_nested():
                stale = VLANRepository(
                    self.sw_repo.session
                ).list_by_device_excluding_vlan_ids(device_id, present_vlan_ids)
                for vlan in stale:
                    logger.debug(
                        "通道层 VLAN %s 已从设备消失，清理记录 device_id=%s",
                        vlan.vlan_id, device_id,
                    )
                    self.sw_repo.session.delete(vlan)
        except Exception as exc:  # noqa: BLE001 —— 补充清理失败不得回滚主体写入
            logger.warning(
                "残留 VLAN 清理失败（不影响本轮成员写入，下一轮重试）device_id=%s: %s",
                device_id, exc,
            )
            return 0
        if stale:
            logger.info(
                "通道层清理残留 VLAN 记录 device_id=%s count=%d", device_id, len(stale),
            )
        return len(stale)

    def sync_lag_members_via_channel(self, device_id: int) -> int:
        """无 SSH 设备：用通道层采到的链路聚合成员补上 Phase 0d（CLI 走不到）。

        与 VLAN 同一处境：``batch_sync_members`` 的 LAG 部分走 SSH
        （``display eth-trunk``），``has_ssh=False`` 的设备整段跳过。

        落库走 CLI 同一个 ``sync_trunk_members``；端口名用**设备自报的 ifName**
        （Eth-Trunk1 等），不按编号反推 —— 反推会与厂商命名漂移。

        Returns:
            写入的聚合组数（0 = 通道未放行 / 设备没启用 LACP 或没开放 1.2.840 子树）。

        Raises:
            ChannelSyncError: **采集失败**（与 VLAN 同口径）。
        """
        switch = self.sw_repo.find_by_device_id(device_id)
        if switch is None:
            return 0
        try:
            from app.core.enums import CollectCapability
            from app.services.collector import runtime

            selector = runtime.selector_for_snmp_takeover(
                switch, ssh_manager=self.ssh_mgr, switch_repo=self.sw_repo,
            )
            if selector is None:
                return 0
            facts = selector.collect(device_id, [CollectCapability.LAGS])
        except Exception as exc:
            logger.warning("通道层 LAG 采集失败 device_id=%s: %s", device_id, exc)
            raise ChannelSyncError("LAG", device_id, exc) from exc

        rows = facts.lags or []
        if not rows:
            logger.info(
                "通道层未产出 LAG（outcomes=%s）device_id=%s",
                {k: str(v) for k, v in (facts.outcomes or {}).items()}, device_id,
            )
            return 0

        synced = 0
        for row in rows:
            lag_name = (row.get("lag_name") or "").strip()
            members = row.get("members") or []
            if not lag_name or not members:
                continue
            try:
                self.sw_repo.sync_trunk_members(device_id, lag_name, members)
                synced += 1
            except Exception as exc:  # noqa: BLE001 —— 单个聚合组失败不影响其余
                logger.warning(
                    "聚合组 %s 成员写入失败 device_id=%s: %s", lag_name, device_id, exc,
                )
        if synced:
            logger.info(
                "通道层 LAG 成员同步 device_id=%s 写入 %d 个聚合组", device_id, synced,
            )
        return synced

    def sync_port_error_counters_via_channel(self, device_id: int) -> int:
        """无 SSH 设备：把通道层采到的错包/丢弃计数写进 ``network_ports``。

        范围与采集层一致：**只有 errors 与 discards 四项**，速率不在这里落库
        （监控侧 ``if_utilization`` 模板已经负责，避免两套口径）。

        写入纪律与设备身份同源：**有值才写，``None`` 不清空** —— 采集层用
        ``None`` 表示"设备没上报这一列"，把它当 0 写下去会掩盖真实状态。

        Returns:
            更新的端口数。

        Raises:
            ChannelSyncError: **采集失败**（与 VLAN / LAG 同口径）。
        """
        switch = self.sw_repo.find_by_device_id(device_id)
        if switch is None:
            return 0
        try:
            from app.core.enums import CollectCapability
            from app.services.collector import runtime

            selector = runtime.selector_for_snmp_takeover(
                switch, ssh_manager=self.ssh_mgr, switch_repo=self.sw_repo,
            )
            if selector is None:
                return 0
            facts = selector.collect(device_id, [CollectCapability.COUNTERS])
        except Exception as exc:
            logger.warning("通道层端口计数采集失败 device_id=%s: %s", device_id, exc)
            raise ChannelSyncError("COUNTERS", device_id, exc) from exc

        return self._apply_port_error_counters(device_id, facts.counters or [])

    def _apply_port_error_counters(self, device_id: int, rows: list[dict]) -> int:
        """按端口名把计数写回（纯落库，便于单测直测）。

        **一次批量委托**（评审 N6）：此前逐端口调仓储 ⇒ 48 口设备 48 次 SELECT。
        逐端口的写入纪律（有值才写 / ``None`` 不清空 / 白名单四列）已收在仓储的
        ``bulk_update_error_counters`` 里，服务层只负责把 ``port`` 归一成
        ``port_name`` 并剔掉空名行。
        """
        if not rows:
            return 0
        payload: list[dict] = []
        for row in rows:
            port_name = (row.get("port") or "").strip()
            if not port_name:
                continue
            payload.append({**row, "port_name": port_name})
        if not payload:
            return 0
        updated = self.port_repo.bulk_update_error_counters(device_id, payload)
        if updated:
            logger.info("端口错包/丢弃计数已写入 device_id=%s 端口 %d 个", device_id, updated)
        return updated

    def _try_channel_takeover(self, switch, *, triggered_by_auto: bool,
                              virtual_room_id: int | None = None) -> dict | None:
        """通道层接管（G1.5）：能接则接并落库，不能接返回 ``None`` 交回老路径。

        **回退是硬要求**：通道层没产出（全 FAILED / 无可用通道）时返回 ``None``，
        由老路径继续 —— 接管只允许"更早采到数据"，不允许"把本来能采的采丢"。
        """
        try:
            from app.services.collector import runtime

            selector = runtime.selector_for_snmp_takeover(
                switch, ssh_manager=self.ssh_mgr, switch_repo=self.sw_repo,
                triggered_by_auto=triggered_by_auto, virtual_room_id=virtual_room_id,
            )
        except Exception as exc:  # noqa: BLE001 —— 接管入口异常不得让采集终局失败
            logger.warning(
                "通道层接管入口异常，本轮回退 CLI 直采 device_id=%s: %s",
                getattr(switch, "device_id", None), exc,
            )
            return None
        if selector is None:
            return None

        from app.core.enums import CollectCapability
        from app.services.collector.facts_adapter import attach_trace

        try:
            facts = selector.collect(
                switch.device_id,
                [CollectCapability.PORTS, CollectCapability.DEVICE_INFO,
                 CollectCapability.COUNTERS]
            )
        except Exception as exc:  # noqa: BLE001 —— 采集异常同样回退（老路径仍可能成功）
            logger.warning(
                "通道层采集异常，回退 CLI 直采 device_id=%s: %s", switch.device_id, exc,
            )
            return None

        port_rows = facts.ports
        if not port_rows:
            logger.info(
                "通道层未产出端口（outcome=%s），回退 CLI 直采 device_id=%s",
                facts.outcomes.get("ports"), switch.device_id,
            )
            return None

        rows = attach_trace(port_rows, facts, cap=CollectCapability.PORTS)

        ip_source = [
            {"port_name": r.get("port_name"), "ip_address": r.get("ip_address")}
            for r in rows
        ]
        rows = [
            {**r, "ip_address": (r["ip_address"].split(",")[0].strip()
                                 if r.get("ip_address") else None)}
            for r in rows
        ]

        self.port_repo.incremental_update(switch.device_id, rows, reconcile_manual=True)

        if any(r.get("ip_address") for r in ip_source):
            self._sync_port_ips(switch.device_id, ip_source)
        else:
            logger.info(
                "通道层接管：本轮未采到任何 IP，跳过 sw_info_ip 同步"
                "（全量替换语义下传空会清空既有记录）device_id=%s", switch.device_id,
            )

        self._apply_device_identity(switch, facts.device)
        try:
            self._apply_port_error_counters(switch.device_id, facts.counters or [])
        except Exception as exc:  # noqa: BLE001 —— 附属同步失败不得回滚端口落库
            logger.warning(
                "端口错包/丢弃计数写入失败 device_id=%s: %s", switch.device_id, exc,
            )

        snmp_channel = next(
            (ch for ch in getattr(selector, "channels", [])
             if getattr(ch, "code", "") == "snmp"), None
        )
        logical: dict = {"vlan_names": [], "lag_names": []}
        if snmp_channel is not None:
            try:
                logical = snmp_channel.collect_logical_port_names(switch.device_id)
            except Exception as exc:  # noqa: BLE001 —— 附属同步失败不影响端口落库
                logger.warning(
                    "逻辑端口名采集失败，跳过 VLAN/LAG 基础记录同步 device_id=%s: %s",
                    switch.device_id, exc,
                )
        logical_names = logical["vlan_names"] + logical["lag_names"]
        if logical_names:
            self._sync_vlan_trunk_bases(
                switch.device_id,
                [SimpleNamespace(port=name) for name in logical_names],
                room_id=switch.device.cabinet.room_id
                if switch.device and switch.device.cabinet else None,
            )
        else:
            logger.info(
                "通道层接管：本轮未发现 Vlanif/Eth-Trunk 逻辑端口，跳过 VLAN/LAG 基础记录同步"
                "（空集合会触发残留清理，清空既有记录）device_id=%s", switch.device_id,
            )

        self.sw_repo.session.flush()

        logger.info(
            "通道层接管落库完成 device_id=%s 端口 %d 个（trace.channel=%s；"
            "IP 同步 %s；VLAN/LAG 基础记录按 R2 跳过）",
            switch.device_id, len(rows), rows[0]["collect_trace"]["channel"],
            "已执行" if any(r.get("ip_address") for r in ip_source) else "跳过（无 IP 数据）",
        )
        return {
            "success": True,
            "switch_id": switch.device_id,
            "port_count": len(rows),
            "channel": rows[0]["collect_trace"]["channel"],
            "via_channels": True,
        }

    def _legacy_collect_port_info(self, device_id: int, switch,
                                  *, triggered_by_auto: bool,
                                  virtual_room_id: int | None = None) -> dict:
        """既有 CLI 直采路径（行为零变更）。

        影子对照只在**非自动扫描**时执行（R9：G1/G2 期间 SNMP 不得进入自动扫描
        关键路径 —— 该约束按设备压力与耗时立，不按"是否落库"立）。
        """
        adapter = get_adapter(switch.device_type)

        try:
            interface_output = self.ssh_mgr.send_show_command(
                switch, adapter.get_interface_command(),
            )
            parsed_ports = adapter.parse_ports(interface_output)

            port_rows = build_port_rows(parsed_ports, device_id=switch.device_id)
            port_rows = [
                {**row, "collect_trace": legacy_trace()} for row in port_rows
            ]
            self.port_repo.incremental_update(switch.device_id, port_rows)
            self._sync_port_ips(switch.device_id, parsed_ports)
            self._sync_vlan_trunk_bases(switch.device_id, parsed_ports, room_id=switch.device.cabinet.room_id if switch.device and switch.device.cabinet else None)
            self.sw_repo.session.flush()

            if not triggered_by_auto:
                self._shadow_compare_channels(switch, port_rows)
            else:
                logger.debug("自动扫描路径跳过影子对照（R9）device_id=%s", device_id)

            return {
                "success": True,
                "switch_id": device_id,
                "port_count": len(parsed_ports),
            }

        except Exception as e:  # noqa: BLE001 -- 端口信息采集失败转结构化返回：同 97
            logger.error("采集交换机 device_id=%d 端口信息失败: %s", device_id, e)
            return {"success": False, "switch_id": device_id, "error": str(e)}

    def _shadow_compare_channels(self, switch, legacy_rows: list) -> None:
        """通道层影子对照（T-G1 接入点，2026-10-05 接入）。

        为什么是影子而不是接管：老路径的 ``parsed_ports`` 还承担
        ``_sync_port_ips`` 与 ``_sync_vlan_trunk_bases`` 两次附属同步，而 ``port_rows``
        **不含 trunk 信息** —— 直接让通道层接管落库会静默丢这两项功能。
        设计文档 §0.4 的路线也是 ``G1 旁路灰度 → 影子模式(A3) 跑全量 diff → G2 扩大灰度``。

        接管时的改动只有一处：把本方法采到的 ``facts.ports`` 作为落库入参，
        并补上 IP/VLAN 两次同步的等价实现（需先扩 `port_rows` 或让通道产出 trunk）。

        [WARN] **影子模式绝不影响主链路**：任何异常都吞掉并记日志（不静默），
        因为它的价值是"提供对照组数据"，不是"参与结果判定"。
        """
        try:
            from app.services.collector import runtime

            selector = runtime.selector_for(
                switch, ssh_manager=self.ssh_mgr, switch_repo=self.sw_repo,
            )
            if selector is None:
                return                      # 开关未开（默认）→ 零开销返回

            from app.core.enums import CollectCapability

            facts = selector.collect(switch.device_id, [CollectCapability.PORTS])
            outcome = facts.outcomes.get("ports")
            if facts.ports is None:
                logger.info(
                    "通道层影子对照：device_id=%s ports outcome=%s（未产出数据，跳过比对）",
                    switch.device_id, outcome,
                )
                return

            diff = runtime.diff_port_rows(legacy_rows, facts.ports)
            if diff["same"]:
                logger.info(
                    "通道层影子对照一致：device_id=%s %d 个端口",
                    switch.device_id, len(legacy_rows),
                )
            else:
                logger.warning(
                    "通道层影子对照存在差异：device_id=%s 仅老路径 %s 个 / 仅通道层 %s 个 / "
                    "字段不一致 %s 处（明细见 debug 日志）",
                    switch.device_id, len(diff["only_legacy"]),
                    len(diff["only_channel"]), len(diff["field_mismatches"]),
                )
                logger.debug("影子对照明细 device_id=%s: %s", switch.device_id, diff)
        except Exception as exc:  # noqa: BLE001 —— 影子模式不得反噬主链路
            logger.warning(
                "通道层影子对照失败（不影响本次采集结果）device_id=%s: %s",
                getattr(switch, "device_id", None), exc,
            )

    def _sync_port_ips(self, switch_id: int, parsed_ports) -> None:
        """将解析到的端口 IP 同步到 sw_info_ip 表（CIDR 或点分十进制均支持）

        修复：IP 为空的端口也调用 sync_port_ips（传空列表），利用其全量替换语义
        清理 sw_info_ip 中残留的旧 IP 记录，避免交换机删除端口 IP 后前端仍显示。

        入参兼容两种形态（CLI 的 ``ParsedPort`` 与通道层接管时的行 dict）：
        两者都提供 ``port``/``port_name`` 与 ``ip_address``，用取属性兜底而不是
        为接管路径再抄一份同步逻辑 —— 抄一份必然与这里漂移。
        多 IP 语义：``ip_address`` 是逗号分隔的**全部** IP（CLI 侧由 TextFSM List
        拼接、SNMP 侧由 IP-MIB 多值组装），逐个写入，第一个为主 IP。
        """
        import ipaddress
        for p in parsed_ports:
            port_name = p.get("port_name") if isinstance(p, dict) else p.port
            ip_raw = p.get("ip_address") if isinstance(p, dict) else p.ip_address
            ip_list = []
            if ip_raw:
                for ip_str in ip_raw.split(","):
                    ip_str = ip_str.strip()
                    if not ip_str:
                        continue
                    try:
                        if "/" in ip_str:
                            iface = ipaddress.ip_interface(ip_str)
                            ip_addr = str(iface.ip)
                            mask = str(iface.network.netmask)
                            prefix = iface.network.prefixlen  # CR-PREFIX-UNIFY: 同步计算prefix
                        else:
                            ip_addr = ip_str
                            mask = "255.255.255.0"
                            prefix = 24  # CR-PREFIX-UNIFY: 默认/24
                        ip_list.append({
                            "ip_address": ip_addr,
                            "subnet_mask": mask,
                            "prefix": prefix,  # CR-PREFIX-UNIFY
                            "is_primary": len(ip_list) == 0,
                        })
                    except (ValueError, TypeError):
                        continue
            self.sw_repo.sync_port_ips(switch_id, port_name, ip_list)

    def _sync_vlan_trunk_bases(self, device_id: int, parsed_ports,
                               room_id: int = None) -> None:
        """扫描时将 Vlanif/Eth-Trunk 端口同步写入 vlans/link_aggregation_groups 基础记录

        仅写入 device_id + vlan_id/lag_name 等基础字段，不获取成员列表（避免额外SSH开销）。
        成员列表在用户点击端口详情时按需 SSH 获取并缓存。
        若记录已存在则跳过，保留已有的 member_ports 缓存。
        同时清理设备上已不存在的 Vlanif/Eth-Trunk 对应的残留记录。
        """
        from app.models.link_aggregation import LinkAggregationGroup

        session = self.sw_repo.session
        scanned_vlan_ids = set()
        scanned_lag_names = set()

        for p in parsed_ports:
            port_name = p.port
            if not port_name:
                continue

            if VLAN_PORT_NAME_RE.match(port_name):
                vlan_id = int(re.search(r"\d+", port_name).group())
                scanned_vlan_ids.add(vlan_id)
                from app.services.vlan_service import VLANService
                from app.persistence.vlan_repository import VLANRepository
                VLANService(VLANRepository()).ensure_vlan(device_id, vlan_id, name=port_name, room_id=room_id)

            elif LAG_PORT_NAME_RE.match(port_name):
                scanned_lag_names.add(port_name)
                from app.persistence.link_aggregation_repository import (
                    LinkAggregationRepository,
                )

                existing = LinkAggregationRepository(
                    session=session
                ).find_by_device_and_name(device_id, port_name)
                if not existing:
                    session.add(LinkAggregationGroup(
                        device_id=device_id,
                        lag_name=port_name,
                        status=1,
                        purpose='',
                    ))
                    logger.debug("扫描同步: 新增 LAG 基础记录 device_id=%d lag_name=%s", device_id, port_name)

        if scanned_vlan_ids:
            from app.persistence.vlan_repository import VLANRepository

            stale_vlans = VLANRepository(
                session=session
            ).list_by_device_excluding_vlan_ids(device_id, scanned_vlan_ids)

            for vlan in stale_vlans:
                logger.debug(
                    "扫描同步: VLAN %d 已从设备消失，清理记录 device_id=%d",
                    vlan.vlan_id, device_id,
                )
                session.delete(vlan)

            del_count = len(stale_vlans)
            if del_count:
                logger.debug("扫描同步: 清理残留 VLAN 记录 device_id=%d count=%d", device_id, del_count)
        if scanned_lag_names:
            from app.persistence.link_aggregation_repository import (
                LinkAggregationRepository,
            )

            del_count = LinkAggregationRepository(
                session=session
            ).delete_by_device_excluding_names(device_id, scanned_lag_names)
            if del_count:
                logger.debug("扫描同步: 清理残留 LAG 记录 device_id=%d count=%d", device_id, del_count)

        session.flush()
