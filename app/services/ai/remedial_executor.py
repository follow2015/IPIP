# -*- coding: utf-8 -*-
"""remedial 命令执行服务：复用 SwitchConfigService + DeviceOpLock。

设计文档第七节四层校验 + 执行前置：
1. 命令安全校验层（command_safety.render_remedial_command）已校验白名单/模板/回滚。
2. 下发前自动备份 running-config（复用 DeviceConfigBackupRepository）。
3. 高风险命令强制要求 rollback_command_key（render_remedial_command 已校验）。
4. 走写锁（mode="write"），与诊断只读锁隔离。

回滚链路：执行失败或运维触发回滚时，用 rollback_command_key 渲染并下发回滚命令。
回滚失败标记 rollback_failed=True（Phase 4.4 持续告警）。
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from app.services.ai.command_safety import (
    get_backup_command,
    render_remedial_command,
    CommandSafetyError,
    enforce_confirmation,
)
from app.services.device_op_lock import device_op_lock, DeviceOperationConflict
from app.services.ai.diagnosis_session_service import DiagnosisSessionService
from app.utils.logging import get_logger
from extensions import db

logger = get_logger(__name__)


class RemedialExecutionError(Exception):
    """remedial 命令执行失败。"""


class RemedialExecutor:
    """remedial 命令执行器。"""

    def __init__(self, session_service: Optional[DiagnosisSessionService] = None):
        self.sessions = session_service or DiagnosisSessionService()

    def execute(
        self,
        device_id: int,
        command_key: str,
        params: Dict[str, Any],
        brand: str,
        session_id: Optional[int] = None,
        confirmed: bool = False,
    ) -> Dict[str, Any]:
        """执行 remedial 命令（经四层校验 + 备份 + 写锁）。

        Args:
            device_id: 设备 ID。
            command_key: 修复命令键（白名单内）。
            params: 模板参数。
            brand: 设备厂商。
            session_id: 诊断会话 ID（用于标记 remedial_executed/rollback_failed）。
            confirmed: 用户是否已确认（前端"执行"按钮触发）。

        Returns:
            {"success", "output", "backup_id", "rollback_command_key"}

        Raises:
            RemedialExecutionError: 校验失败/执行失败/回滚失败。
        """
        if not confirmed:
            raise RemedialExecutionError("remedial 命令必须经用户确认后执行（confirmed=true）")

        try:
            rendered = render_remedial_command(command_key, brand, params)
        except CommandSafetyError as e:
            raise RemedialExecutionError(f"命令安全校验失败：{e}") from e

        command = rendered["command"]
        rollback_key = rendered["rollback_command_key"]

        from app.persistence.switch_repo import SwitchRepository
        from app.services.switch_config_service import SwitchConfigService

        switch = SwitchRepository().find_by_device_id(device_id)
        if not switch:
            raise RemedialExecutionError(f"设备 {device_id} 无 SSH 凭据")

        config_service = SwitchConfigService()

        try:
            with device_op_lock.acquire(device_id, timeout=60, mode="write"):
                backup_id = self._backup_running_config(
                    device_id, switch, config_service, brand)
                if backup_id is None:
                    raise RemedialExecutionError(
                        f"执行前备份 running-config 失败，已中止下发（设备 {device_id}）"
                    )

                try:
                    commands = command.split("\n")
                    result = config_service._send_config(switch, commands, err_label="remedial")
                except Exception as e:  # noqa: BLE001 - 统一转入下方失败处理
                    logger.error("remedial execute raised device=%s cmd=%s: %s",
                                 device_id, command_key, e, exc_info=True)
                    result = {"success": False, "error": str(e)}

                if not isinstance(result, dict) or not result.get("success"):
                    error = (result or {}).get("error") or "未知错误"
                    logger.error("remedial execute failed device=%s cmd=%s: %s",
                                 device_id, command_key, error)
                    if rollback_key:
                        self._try_rollback(device_id, rollback_key, params, brand,
                                          config_service, switch, session_id)
                    raise RemedialExecutionError(f"命令执行失败：{error}")

                if session_id:
                    self.sessions.mark_remedial_executed(session_id)

                return {
                    "success": True,
                    "output": result.get("output", ""),
                    "backup_id": backup_id,
                    "rollback_command_key": rollback_key,
                }
        except DeviceOperationConflict as e:
            raise RemedialExecutionError(f"设备繁忙：{e}") from e

    def _backup_running_config(
        self, device_id: int, switch, config_service, brand: str,
    ) -> Optional[int]:
        """下发前备份 running-config（真实备份）。

        备份命令按厂商命令族选取（H3C/Huawei 为 display current-configuration，
        Cisco 为 show running-config）。此前硬编码 H3C 命令，在 Cisco 设备上
        执行会失败 —— 叠加「备份失败即中止」策略后，等于 Cisco 设备无法执行
        任何 remedial 命令。

        SHA-256 去重后存入 DeviceConfigBackup，回滚失败时可据此恢复完整配置。
        """
        import hashlib
        from app.models.device_config_backup import DeviceConfigBackup
        from app.infra import SSHManager

        backup_command = get_backup_command(brand)
        if not backup_command:
            logger.warning("backup: no backup command for brand=%s device=%s",
                           brand, device_id)
            return None

        try:
            from app.services.ai.circuit_breaker import get_circuit_breaker, AICircuitOpenError
            try:
                raw_config = get_circuit_breaker("ssh").call(
                    lambda: SSHManager().send_show_command(
                        switch, backup_command, timeout=30
                    )
                )
            except AICircuitOpenError:
                logger.warning("backup: SSH circuit open device=%s", device_id)
                return None

            if not raw_config or not isinstance(raw_config, str):
                logger.warning("backup: empty running-config device=%s", device_id)
                return None

            config_hash = hashlib.sha256(raw_config.encode("utf-8")).hexdigest()

            existing = (
                db.session.query(DeviceConfigBackup)
                .filter_by(device_id=device_id, config_hash=config_hash)
                .first()
            )
            if existing:
                return existing.id

            backup = DeviceConfigBackup(
                device_id=device_id,
                config_content=raw_config,
                config_hash=config_hash,
                backup_type="pre_remedial",
                file_size=len(raw_config.encode("utf-8")),
            )
            db.session.add(backup)
            db.session.flush()
            logger.info("remedial backup running-config device=%s backup_id=%s",
                        device_id, backup.id)
            return backup.id
        except Exception as e:
            logger.warning("backup running-config failed device=%s: %s", device_id, e)
            return None

    def _try_rollback(
        self, device_id: int, rollback_key: str, params: Dict[str, Any],
        brand: str, config_service, switch, session_id: Optional[int],
    ) -> None:
        """执行失败时尝试回滚。回滚失败标记 rollback_failed=True。

        判据与 execute 一致：_send_config 失败返回 {success:False} 不抛异常，
        只看异常会把「回滚没生效」误报成成功，导致设备滞留中间态却无告警。
        """
        try:
            rollback_rendered = render_remedial_command(rollback_key, brand, params)
            rollback_commands = rollback_rendered["command"].split("\n")
            result = config_service._send_config(switch, rollback_commands, err_label="rollback")
            if not isinstance(result, dict) or not result.get("success"):
                error = (result or {}).get("error") or "未知错误"
                raise RuntimeError(f"回滚命令未生效：{error}")
            logger.info("remedial rollback success device=%s key=%s", device_id, rollback_key)
        except Exception as e:
            logger.error("remedial rollback FAILED device=%s key=%s: %s",
                         device_id, rollback_key, e, exc_info=True)
            if session_id:
                self.sessions.mark_rollback_failed(session_id)

    def execute_rollback(
        self, device_id: int, rollback_key: str, params: Dict[str, Any],
        brand: str, session_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """运维手动触发回滚。"""
        from app.persistence.switch_repo import SwitchRepository
        from app.services.switch_config_service import SwitchConfigService

        switch = SwitchRepository().find_by_device_id(device_id)
        if not switch:
            raise RemedialExecutionError(f"设备 {device_id} 无 SSH 凭据")

        config_service = SwitchConfigService()
        try:
            with device_op_lock.acquire(device_id, timeout=60, mode="write"):
                try:
                    rollback_rendered = render_remedial_command(rollback_key, brand, params)
                    commands = rollback_rendered["command"].split("\n")
                    result = config_service._send_config(switch, commands, err_label="rollback")
                    if not isinstance(result, dict) or not result.get("success"):
                        error = (result or {}).get("error") or "未知错误"
                        raise RemedialExecutionError(f"回滚失败：{error}")
                    return {"success": True, "output": result.get("output", "")}
                except RemedialExecutionError:
                    raise
                except Exception as e:
                    logger.error("manual rollback FAILED device=%s: %s", device_id, e, exc_info=True)
                    if session_id:
                        self.sessions.mark_rollback_failed(session_id)
                    raise RemedialExecutionError(f"回滚失败：{e}") from e
        except DeviceOperationConflict as e:
            raise RemedialExecutionError(f"设备繁忙：{e}") from e
