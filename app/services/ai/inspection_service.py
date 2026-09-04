# -*- coding: utf-8 -*-
"""设备 AI 巡查：生成巡查清单 + 汇总发现。

generate_checklist 必须先查设备信息（类型/型号/状态），
经 prompt_guard 过滤凭据字段后拼入 prompt，而非只传孤立 device_id。
"""
import json
from typing import List

from app.services.ai.llm_factory import create_llm_client
from app.services.ai.llm_base import LLMClient
from app.services.ai.prompt_guard import strip_sensitive_fields
from app.services.ai._runtime import observe_call, CallTimer
from app.utils.logging import get_logger

logger = get_logger(__name__)

SYSTEM = (
    "你是现场巡检助手，针对一台网络设备输出 3-5 条中文巡检要点，每行一条，不要编号外的解释。"
    "请根据设备类型、型号、当前状态针对性给出要点。"
)


class InspectionService:
    def __init__(self, client: LLMClient = None, device_service=None, monitor_service=None):
        self.client = client or create_llm_client()
        self._device_svc = device_service
        self._monitor_svc = monitor_service

    def _get_device_service(self):
        if self._device_svc is not None:
            return self._device_svc
        from app.services.ai.service_factory import get_device_service
        return get_device_service()

    def _get_monitor_service(self):
        if self._monitor_svc is not None:
            return self._monitor_svc
        from app.services.ai.service_factory import get_monitor_service
        return get_monitor_service()

    def generate_checklist(self, device_id: int, user_id: int = 0) -> List[str]:
        if not isinstance(device_id, int) or device_id <= 0:
            return ["（device_id 无效，请传入正整数）"]
        if not self.client.is_configured():
            return ["（AI 未配置，使用默认清单）检查电源/端口/温度"]
        device = self._get_device_service().get_device_by_id(device_id) or {}
        monitor = self._get_monitor_service().get_device_status(device_id) or {}
        safe_device = strip_sensitive_fields(device)
        safe_monitor = strip_sensitive_fields(monitor)
        user_prompt = (
            f"设备ID={device_id}\n"
            f"设备信息：{json.dumps(safe_device, ensure_ascii=False)}\n"
            f"监控状态：{json.dumps(safe_monitor, ensure_ascii=False)}"
        )
        status = "ok"
        lines: List[str] = []
        with CallTimer() as t:
            try:
                raw = self.client.chat(SYSTEM, user_prompt)
                lines = [line.strip("0123456789.、 ") for line in raw.splitlines() if line.strip()]
            except Exception as e:  # noqa: BLE001
                status = "error"
                lines = [f"（AI 巡查失败：{e}）"]
                raise
            finally:
                observe_call(scenario="inspection", user_id=user_id,
                             request={"device_id": device_id}, response=lines,
                             status=status, duration_ms=t.duration_ms,
                             model=getattr(self.client, "model", None),
                             base_url=getattr(self.client, "base_url", None))
        return lines

    def summarize(self, findings: List[str], user_id: int = 0) -> str:
        if not self.client.is_configured():
            return "（AI 未配置）"
        status = "ok"
        summary = ""
        with CallTimer() as t:
            try:
                summary = self.client.chat("你是巡检报告助手，汇总以下发现为一段结论。", "\n".join(findings))
            except Exception as e:  # noqa: BLE001
                status = "error"
                summary = f"（AI 汇总失败：{e}）"
                raise
            finally:
                observe_call(scenario="inspection_summarize", user_id=user_id,
                             request=findings, response=summary,
                             status=status, duration_ms=t.duration_ms,
                             model=getattr(self.client, "model", None),
                             base_url=getattr(self.client, "base_url", None))
        return summary
