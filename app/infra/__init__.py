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
RETRY_BASE = 0.5  # 秒，指数退避基数


_NETMIKO_LOG_REPORTED = False


def _netmiko_log_state():
    """返回 (是否开启, 环境变量值, 配置值)，供开关判定与自报共用"""
    env_val = os.environ.get("NETMIKO_SESSION_LOG")
    cfg_val = getattr(Config, "NETMIKO_SESSION_LOG", False)
    enabled = bool(env_val) or bool(cfg_val)
    return enabled, env_val, cfg_val


def report_netmiko_log_switch():
    """进程内一次性自报 netmiko 会话日志开关状态

    放在 Flask 启动期调用，这样**无需真正连接设备**即可在启动日志里确认开关
    是否生效（例如：env=None config=False → 关闭）。连接设备时也会再调用一次，
    但受 _NETMIKO_LOG_REPORTED 保护只打一次。
    """
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
    """根据环境变量 NETMIKO_SESSION_LOG 或 Config.NETMIKO_SESSION_LOG 决定是否记录 netmiko 完整会话日志

    返回会话日志文件路径；返回 None 表示禁用（默认）。

    开启后 netmiko 会把与设备的完整交互（发送的命令 + 设备回显，含登录密码
    明文）写入 logs/netmiko_{ip}_{时间戳}.log，并把标准库 ``netmiko`` logger
    设为 DEBUG。仅用于临时调试 **range 失败 / 逐端口降级** 等疑难问题，
    调试结束后务必删除 logs/netmiko_*.log 文件，避免敏感凭证泄露。

    Returns:
        Optional[str]: 会话日志绝对路径，或 None（未开启）
    """
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
    """SSH 连接管理器

    封装 netmiko 的连接管理，提供命令下发、自动重试等功能。
    """

    def send_show_command(
        self,
        switch,
        command: str,
        timeout: int = 120,
    ) -> str:
        """下发 show 命令并返回输出

        Args:
            switch: 交换机对象
            command: 查询命令
            timeout: 超时时间（秒）

        Returns:
            str: 命令输出

        Raises:
            SSHConnectionError: 连接失败
        """
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
        """下发配置命令序列（自动重试）

        对 CE 型号使用 config set 模式，其他使用 send_config_set。

        Args:
            switch: 交换机对象
            commands: 配置命令列表
            save_cmd: 保存配置命令

        Returns:
            str: 命令输出

        Raises:
            SSHConnectionError: 连续 3 次失败
        """
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
        """下发交互式命令序列

        每个步骤为 (command, expect_pattern) 元组。
        适用于 clear configuration this 等需要交互式确认的命令。

        Args:
            switch: 交换机对象
            steps: 命令步骤列表，每项为 (command_str, expect_regex)
            save_cmd: 保存配置命令

        Returns:
            str: 命令输出
        """
        return self._execute_with_retry(
            lambda: self._send_interactive_sync(switch, steps, save_cmd),
            switch.ip,
        )

    @staticmethod
    def _normalize_switch_info(switch_info) -> dict:
        """将交换机凭证 ORM 对象或原始 dict 统一为连接参数字典。"""
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
        """上下文管理器：创建并自动释放 SSH/Telnet 连接

        Args:
            switch_info: 交换机信息（dict 或 SwitchCredentials ORM 对象）

        Yields:
            netmiko 连接对象
        """
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
        """测试 SSH 连接

        Args:
            switch_info: 交换机信息字典

        Returns:
            dict: {success: bool, message: str, details: dict}
        """
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
        """执行单条命令。

        执行失败（异常）时抛出 SSHConnectionError，交由调用方决定重试/降级，
        避免把失败静默转为空串、被上层误判为"设备无输出/资源不存在"（fail-open 掩码）。
        仅当设备确实返回空输出时返回空串——此时与异常有本质区别。
        """
        try:
            return connection.send_command(command, delay_factor=2) or ""
        except Exception as e:
            raise SSHConnectionError(f"命令执行失败 [{command}]: {e}") from e

    def execute_config_commands(self, connection, commands: list) -> str:
        """执行配置模式命令序列。

        执行失败（异常）时抛出 SwitchConfigError，避免静默返回空串掩盖配置错误。
        """
        try:
            return connection.send_config_set(commands) or ""
        except Exception as e:
            raise SwitchConfigError(reason=f"配置命令执行失败 {commands}: {e}") from e

    def execute_show_on_conn(self, connection, command: str, timeout: int = 120) -> str:
        """在已有连接上执行 show 命令

        Args:
            connection: 已建立的 netmiko 连接
            command: 查询命令
            timeout: 超时时间（秒）

        Returns:
            str: 命令输出
        """
        return connection.send_command(command, read_timeout=timeout)

    def execute_config_on_conn(self, connection, commands: list) -> str:
        """在已有连接上执行配置命令序列

        执行后检测设备返回中的 Error 信息，发现错误时抛出异常。

        Args:
            connection: 已建立的 netmiko 连接
            commands: 配置命令列表

        Returns:
            str: 命令输出

        Raises:
            SSHConnectionError: 设备返回配置错误
        """
        output = connection.send_config_set(commands)
        error_lines = self._detect_config_errors(output)
        if error_lines:
            error_msg = "; ".join(error_lines)
            raise SwitchConfigError(reason=error_msg)
        return output

    def execute_interactive_on_conn(self, connection, steps: list) -> str:
        """在已有连接上执行交互式命令序列

        Args:
            connection: 已建立的 netmiko 连接
            steps: 命令步骤列表，每项为 (command_str, expect_regex)

        Returns:
            str: 命令输出
        """
        output = ""
        for cmd, expect in steps:
            output += connection.send_command(cmd, expect_string=expect, read_timeout=60)
        return output


    def _execute_with_retry(self, func, switch_ip: str) -> str:
        """带指数退避重试的执行器

        Args:
            func: 待执行的同步函数
            switch_ip: 交换机 IP（用于日志）

        Returns:
            str: 命令输出

        Raises:
            SSHConnectionError: 重试耗尽
        """
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
        """同步执行 show 命令"""
        from netmiko import ConnectHandler

        conn_params = self._build_conn_params(switch, timeout)
        with ConnectHandler(**conn_params) as conn:
            output = conn.send_command(command, read_timeout=timeout)
        return output

    def _send_config_sync(self, switch, commands: list, save_cmd: str, read_timeout: int = 120) -> str:
        """同步执行配置命令

        执行后检测设备返回中的 Error 信息，发现错误时抛出异常。
        """
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
        """检测设备配置输出中的 Error 行

        匹配华为/H3C/Cisco 常见的配置错误模式（以 "Error:" 开头的行）。
        空输出或无匹配时返回空列表。

        Args:
            output: 设备命令输出

        Returns:
            list[str]: 错误信息列表，空列表表示无错误
        """
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
        """同步执行交互式命令序列

        每个步骤使用 send_command + expect_string 逐条发送。
        """
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
        """构建 netmiko 连接参数字典

        Args:
            switch: 交换机对象
            timeout: 读取超时时间（秒）

        Returns:
            dict: netmiko ConnectHandler 参数
        """
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
        """旧版华为固件（< 200519）禁用 rsa-sha2-512/256 算法

        Args:
            version: 固件版本号字符串

        Returns:
            dict: 额外的 SSH 参数，或空字典
        """
        DISABLED = {"pubkeys": ["rsa-sha2-512", "rsa-sha2-256"]}
        try:
            ver_num = int("".join(filter(str.isdigit, version))[:6])
            if ver_num < 200519:
                return {"disabled_algorithms": DISABLED}
        except (ValueError, TypeError):
            return {"disabled_algorithms": DISABLED}
        return {}
