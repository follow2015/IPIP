# -*- coding: utf-8 -*-
"""处置后验证回路 + 案例回流 RAG。

设计文档第二节末尾：
- 自动回读关键指标 → 对比处置前快照 → 输出"已恢复/部分恢复/未恢复"
- 未恢复 → 携带本次处置记录重入诊断循环
- 已恢复 → 案例沉淀入 RAG（domain=case）
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.services.ai.rag_store import get_rag_store
from app.utils.logging import get_logger

logger = get_logger(__name__)


class PostRemediationVerifier:
    """处置后验证回路。

    注意：本服务不在请求线程内 sleep 等待指标刷新（会阻塞 Flask worker）。
    延迟由前端控制（setTimeout 后再调 /diagnosis/verify）。
    """

    def verify(
        self,
        device_id: int,
        pre_snapshot: Dict[str, Any],
        anomalous_metrics: List[str],
    ) -> Dict[str, Any]:
        """处置后回读关键指标，对比处置前快照。

        Args:
            device_id: 设备 ID。
            pre_snapshot: 处置前指标快照（如 {"cpu": 86, "memory": 72}）。
            anomalous_metrics: 处置前异常的指标列表（如 ["cpu"]）。

        Returns:
            {"status": "recovered|partial|not_recovered",
             "post_snapshot": {...}, "comparison": [...]}
        """
        from app.services.ai.capabilities.diagnostic import live_inspection
        post_result = live_inspection({"device_id": device_id, "checks": anomalous_metrics})
        post_snapshot = self._extract_values(post_result)

        comparison = []
        recovered_count = 0
        for metric in anomalous_metrics:
            pre_val = pre_snapshot.get(metric)
            post_val = post_snapshot.get(metric)
            if pre_val is None or post_val is None:
                comparison.append({"metric": metric, "pre": pre_val, "post": post_val,
                                    "recovered": None, "note": "无法对比"})
                continue
            if pre_val > 0:
                recovered = post_val < pre_val * 0.8
            else:
                recovered = post_val <= 1.0  # 绝对阈值：≤1 视为恢复
            comparison.append({"metric": metric, "pre": pre_val, "post": post_val,
                                "recovered": recovered})
            if recovered:
                recovered_count += 1

        total = len(anomalous_metrics)
        if total == 0:
            status = "recovered"
        elif recovered_count == total:
            status = "recovered"
        elif recovered_count > 0:
            status = "partial"
        else:
            status = "not_recovered"

        return {
            "status": status,
            "post_snapshot": post_snapshot,
            "comparison": comparison,
        }

    def _extract_values(self, inspection_result: Dict[str, Any]) -> Dict[str, float]:
        """从 live_inspection 结果提取指标值。"""
        values = {}
        checks = inspection_result.get("checks", {}) if isinstance(inspection_result, dict) else {}
        for name, result in checks.items():
            if isinstance(result, dict) and result.get("supported") is not False:
                v = result.get("value")
                if v is not None:
                    values[name] = float(v)
        return values

    def case_to_rag(
        self,
        symptom: str,
        evidence: List[str],
        root_cause: str,
        remedial_commands: List[Dict[str, Any]],
        verified_status: str,
    ) -> bool:
        """案例回流 RAG（运维确认处置有效后调用）。

        设计文档第九节：(现象+证据+根因+处置命令) 自动入 RAG，domain=case。

        Args:
            symptom: 故障现象（用户原始问题）。
            evidence: 证据列表。
            root_cause: 根因说明。
            remedial_commands: 处置命令列表。
            verified_status: 验证状态（recovered/partial/not_recovered）。

        Returns:
            是否入库成功。
        """
        if verified_status == "not_recovered":
            logger.info("skip case to RAG: not_recovered (处置无效不入库)")
            return False

        case_text = (
            f"【故障现象】{symptom}\n"
            f"【证据】{'; '.join(evidence)}\n"
            f"【根因】{root_cause}\n"
            f"【处置命令】{json.dumps(remedial_commands, ensure_ascii=False)}\n"
            f"【验证结果】{verified_status}"
        )
        try:
            store = get_rag_store()
            store.ingest([case_text], domain="case", source="diagnosis_loop")
            logger.info("case ingested to RAG domain=case symptom=%s", symptom[:50])
            return True
        except Exception as e:
            logger.warning("case to RAG failed: %s", e)
            return False
