# -*- coding: utf-8 -*-
"""
SSH 连接管理器

基于 netmiko 实现 SSH 命令下发，支持：
- 自动重试（指数退避，最多 3 次）
- CE 型号 config set 模式
- 华为旧版固件 rsa-sha2 兼容
- netmiko 会话日志：默认关闭，设环境变量 NETMIKO_SESSION_LOG=1 后开启，
  写入 logs/netmiko_{ip}_{时间戳}.log（含设备交互完整 I/O，仅供临时调试）
"""
from app.utils.logging import get_logger
import logging
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from app.core.enums import SwitchDeviceTypeCode
from app.exceptions.system import SSHConnectionError, SwitchConfigError
from config import Config
from types import SimpleNamespace

logger = get_logger(__name__)

MAX_RETRIES = 3
RETRY_BASE = 0.5


_NETMIKO_LOG_REPORTED = False


def _netmiko_log_state():
    env_val = os.environ.get("NETMIKO_SESSION_LOG")
    cfg_val = getattr(Config, "NETMIKO_SESSION_LOG", False)
    enabled = bool(env_val) or bool(cfg_val)
    return enabled, env_val, cfg_val


def report_netmiko_log_switch():
    global _NETMIKO_LOG_REPORTED
    if _NETMIKO_LOG_REPORTED:
        return
    _NETMIKO_LOG_REPORTED = True
    enabled, env_val, cfg_val = _netmiko_log_state()
    if enabled:
        logger.warning(
            "✅ [netmiko会话日志] 已开启(调试用) env=%r config=%r → "
            "下次设备连接将写入 logs/netmiko_{ip}_{ts}.log"
            "（含登录密码明文，调试后务必关闭并删除日志）",
            env_val, cfg_val,
        )
    else:
        logger.warning(
            "⭕ [netmiko会话日志] 未开启(默认关闭)。需调试时：config.py 设 NETMIKO_SESSION_LOG=True "
            "或 环境变量 NETMIKO_SESSION_LOG=1；开启后日志含敏感凭证",
            env_val, cfg_val,
        )


def _enable_netmiko_session_log(switch) -> Optional[str]:
    enabled, _, _ = _netmiko_log_state()
    report_netmiko_log_switch()
    if not enabled:
        return None
    log_dir = Path(__file__).resolve().parents[2] / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = str(log_dir / f"netmiko_{switch.ip}_{ts}.log")
    logging.getLogger("netmiko").setLevel(logging.DEBUG)
    logger.warning("✅ [netmiko会话日志] 本次连接写入: %s", path)
    return path


class SSHManager:

    def send_show_command(
        self,
        switch,
        command: str,
        timeout: int = 120,
    ) -> str:
        return self._execute_with_retry(
            lambda: self._send_show_sync(switch, command, timeout),
            switch.ip,
        )

    def send_config_commands(
        self,
        switch,
        commands: list,
        save_cmd: str = "",
        read_timeout: int = 120,
    ) -> str:
        return self._execute_with_retry(
            lambda: self._send_config_sync(switch, commands, save_cmd, read_timeout),
            switch.ip,
        )

    def send_interactive_command(
        self,
        switch,
        steps: list,
        save_cmd: str = "",
    ) -> str:
        return self._execute_with_retry(
            lambda: self._send_interactive_sync(switch, steps, save_cmd),
            switch.ip,
        )

    @staticmethod
    def _normalize_switch_info(switch_info) -> dict:
        if isinstance(switch_info, dict):
            return switch_info
        return {
            "ip": switch_info.ip,
            "username": switch_info.username,
            "password": getattr(switch_info, "password", ""),
            "port": switch_info.port,
            "protocol": getattr(switch_info, "protocol", "ssh"),
            "device_type": getattr(switch_info, "device_type", SwitchDeviceTypeCode.HUAWEI),
            "authentication_method": getattr(switch_info, "authentication_method", "password"),
        }

    @contextmanager
    def get_connection(self, switch_info):
        from netmiko import ConnectHandler

        info = self._normalize_switch_info(switch_info)

        conn = None
        try:
            device_type = info.get("device_type", SwitchDeviceTypeCode.HUAWEI)
            protocol = (info.get("protocol") or "ssh").lower()
            if protocol == "telnet" and not device_type.endswith("_telnet"):
                device_type = f"{device_type}_telnet"

            default_port = 23 if protocol == "telnet" else 22

            params = {
                "device_type": device_type,
                "host": info["ip"],
                "username": info["username"],
                "port": info.get("port") or default_port,
                "timeout": 120,
                "conn_timeout": 10,
                "banner_timeout": 15,
                "auth_timeout": 30,
                "fast_cli": False,
                "session_log": _enable_netmiko_session_log(SimpleNamespace(ip=info["ip"])),
            }
            if info.get("authentication_method") == "Certificate":
                params["use_keys"] = True
                if Config.SSH_CERTIFICATE:
                    params["key_file"] = Config.SSH_CERTIFICATE
                if Config.SSH_PASSPHRASE:
                    params["passphrase"] = Config.SSH_PASSPHRASE
            else:
                params["password"] = info.get("password", "")

            if device_type == SwitchDeviceTypeCode.HUAWEI:
                params.update(self._huawei_ssh_options(info.get("device_version", "")))

            conn = ConnectHandler(**params)
            yield conn
        finally:
            if conn:
                try:
                    conn.disconnect()
                except Exception:
                    pass

    def test_connection(self, switch_info: dict) -> dict:
        try:
            with self.get_connection(switch_info) as conn:
                if conn:
                    output = conn.send_command(
                        "display version | include uptime",
                        delay_factor=2,
                        read_timeout=120,
                    )
                    return {
                        "success": True,
                        "message": "SSH连接成功",
                        "details": {"output": output[:200] if output else ""},
                    }
                return {"success": False, "message": "连接创建失败", "details": {}}
        except Exception as e:
            return {"success": False, "message": str(e), "details": {}}

    def execute_command(self, connection, command: str) -> str:
        try:
            return connection.send_command(command, delay_factor=2) or ""
        except Exception as e:
            raise SSHConnectionError(f"命令执行失败 [{command}]: {e}") from e

    def execute_config_commands(self, connection, commands: list) -> str:
        try:
            return connection.send_config_set(commands) or ""
        except Exception as e:
            raise SwitchConfigError(reason=f"配置命令执行失败 {commands}: {e}") from e

    def execute_show_on_conn(self, connection, command: str, timeout: int = 120) -> str:
        return connection.send_command(command, read_timeout=timeout)

    def execute_config_on_conn(self, connection, commands: list) -> str:
        output = connection.send_config_set(commands)
        error_lines = self._detect_config_errors(output)
        if error_lines:
            error_msg = "; ".join(error_lines)
            raise SwitchConfigError(reason=error_msg)
        return output

    def execute_interactive_on_conn(self, connection, steps: list) -> str:
        output = ""
        for cmd, expect in steps:
            output += connection.send_command(cmd, expect_string=expect, read_timeout=60)
        return output


    def _execute_with_retry(self, func, switch_ip: str) -> str:
        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return func()
            except Exception as exc:
                last_exc = exc
                if isinstance(exc, SwitchConfigError):
                    raise
                if attempt < MAX_RETRIES:
                    wait = RETRY_BASE * (2 ** (attempt - 1))
                    logger.warning(
                        "SSH 命令失败 switch=%s attempt=%d, %.1fs 后重试: %s",
                        switch_ip, attempt, wait, exc,
                    )
                    time.sleep(wait)

        raise SSHConnectionError(
            f"SSH 到 {switch_ip} 连续 {MAX_RETRIES} 次失败"
        ) from last_exc

    def _send_show_sync(self, switch, command: str, timeout: int) -> str:
        from netmiko import ConnectHandler

        conn_params = self._build_conn_params(switch, timeout)
        with ConnectHandler(**conn_params) as conn:
            output = conn.send_command(command, read_timeout=timeout)
        return output

    def _send_config_sync(self, switch, commands: list, save_cmd: str, read_timeout: int = 120) -> str:
        from netmiko import ConnectHandler

        conn_params = self._build_conn_params(switch)
        with ConnectHandler(**conn_params) as conn:
            output = conn.send_config_set(commands, read_timeout=read_timeout)

            error_lines = self._detect_config_errors(output)
            if error_lines:
                error_msg = "; ".join(error_lines)
                logger.error("设备配置返回错误 switch=%s: %s", switch.ip, error_msg)
                raise SwitchConfigError(reason=error_msg)

            if save_cmd:
                conn.send_command_timing("return")
                conn.send_command_timing(save_cmd)
                conn.send_command_timing("Y")

        return output

    @staticmethod
    def _detect_config_errors(output: str) -> list:
        if not output:
            return []

        error_pattern = re.compile(r'Error:\s*(.+?)(?:\n|$)', re.IGNORECASE)
        return [
            f"Error: {m.group(1).strip()}"
            for m in error_pattern.finditer(output)
            if m.group(1).strip()
        ]

    def _send_interactive_sync(
        self, switch, steps: list, save_cmd: str,
    ) -> str:
        from netmiko import ConnectHandler

        conn_params = self._build_conn_params(switch)
        output = ""

        with ConnectHandler(**conn_params) as conn:
            for cmd, expect in steps:
                output += conn.send_command(cmd, expect_string=expect, read_timeout=60)
            output += conn.send_command_timing("return")
            if save_cmd:
                conn.send_command_timing(save_cmd)
                conn.send_command_timing("Y")

        return output

    def _build_conn_params(self, switch, timeout: int = 120) -> dict:
        protocol = (switch.protocol or "ssh").lower()
        default_port = 23 if protocol == "telnet" else 22

        session_log = _enable_netmiko_session_log(switch)
        params = {
            "device_type": switch.get_netmiko_device_type(),
            "host": switch.ip,
            "username": switch.username,
            "port": switch.port or default_port,
            "timeout": timeout,
            "conn_timeout": 10,
            "banner_timeout": 15,
            "auth_timeout": 30,
            "fast_cli": False,
            "session_log": session_log,
        }
        if session_log:
            params["session_log_file_mode"] = "write"

        if switch.authentication_method == "Certificate":
            params["use_keys"] = True
            if Config.SSH_CERTIFICATE:
                params["key_file"] = Config.SSH_CERTIFICATE
            if Config.SSH_PASSPHRASE:
                params["passphrase"] = Config.SSH_PASSPHRASE
        else:
            params["password"] = switch.password

        if switch.device_type == SwitchDeviceTypeCode.HUAWEI:
            version = ""
            if switch.device and switch.device.status_cache:
                version = switch.device.status_cache.device_version or ""
            params.update(self._huawei_ssh_options(version))

        return params

    @staticmethod
    def _huawei_ssh_options(version: str) -> dict:
        DISABLED = {"pubkeys": ["rsa-sha2-512", "rsa-sha2-256"]}
        try:
            ver_num = int("".join(filter(str.isdigit, version))[:6])
            if ver_num < 200519:
                return {"disabled_algorithms": DISABLED}
        except (ValueError, TypeError):
            return {"disabled_algorithms": DISABLED}
        return {}
