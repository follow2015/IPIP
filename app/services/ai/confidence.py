# -*- coding: utf-8 -*-
"""诊断置信度混合公式计算。

设计文档第五节：confidence 非纯 LLM 自评，而是混合公式：
- evidence_completeness = 成功获取的 check 项数 / 诊断流程所需总 check 项数
- baseline_significance = 基线偏离命中 3-sigma 的指标数 / 总异常指标数
- rag_relevance = RAG 检索 Top-1 相似度分数

存在异常指标（常规场景）：
  confidence = 0.4×evidence_completeness + 0.3×baseline_significance + 0.3×rag_relevance

无异常指标（配置类故障，baseline_significance 恒为 0）：权重按比例重分配：
  confidence = 0.571×evidence_completeness + 0.429×rag_relevance
  （0.4/(0.4+0.3)=0.571, 0.3/(0.4+0.3)=0.429）

最终 confidence = min(混合计算值, LLM 自评值)——LLM 自评只作参考上限。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def compute_confidence(
    total_checks: int,
    successful_checks: int,
    anomalous_metrics: int,
    baseline_hit_3sigma: int,
    rag_top1_score: Optional[float],
    llm_self_eval: Optional[float] = None,
) -> float:
    """计算诊断置信度（混合公式）。

    Args:
        total_checks: 诊断流程所需总 check 项数。
        successful_checks: 成功获取的 check 项数（supported=true）。
        anomalous_metrics: 异常指标数（偏离基线或超阈值）。
        baseline_hit_3sigma: 基线偏离命中 3-sigma 的指标数。
        rag_top1_score: RAG 检索 Top-1 相似度分数（0-1，无检索结果为 None）。
        llm_self_eval: LLM 自评置信度（0-1，作为上限，None 则不约束）。

    Returns:
        置信度（0-1）。
    """
    evidence_completeness = (
        successful_checks / total_checks if total_checks > 0 else 0.0
    )

    rag_relevance = rag_top1_score if rag_top1_score is not None else 0.0

    if anomalous_metrics == 0:
        confidence = 0.571 * evidence_completeness + 0.429 * rag_relevance
    else:
        baseline_significance = (
            baseline_hit_3sigma / anomalous_metrics if anomalous_metrics > 0 else 0.0
        )
        confidence = (
            0.4 * evidence_completeness
            + 0.3 * baseline_significance
            + 0.3 * rag_relevance
        )

    if llm_self_eval is not None:
        confidence = min(confidence, llm_self_eval)

    return max(0.0, min(1.0, confidence))


def extract_confidence_inputs(
    rounds: List[Dict[str, Any]],
    final_answer: Dict[str, Any],
) -> Dict[str, Any]:
    """从诊断轮次和 final_answer 中提取 confidence 计算所需输入。

    供 runner.py 在生成 final_answer 时调用，把结构化事实喂给混合公式，
    而不是让 LLM 自己判断"这个值算不算高"。

    Args:
        rounds: 每轮工具调用记录 [{tool, args, result, ...}]。
        final_answer: LLM 输出的 final_answer dict。

    Returns:
        {"total_checks", "successful_checks", "anomalous_metrics",
         "baseline_hit_3sigma", "rag_top1_score", "llm_self_eval",
         "anomalous_metric_names", "pre_snapshot"}

        - anomalous_metric_names: 异常指标名列表，供处置后验证回路回读对比。
        - pre_snapshot: 所有成功采集指标的当前值快照（处置前基线）。
          这两项由代码从工具结果提取，不依赖 LLM 输出，避免前端拿不到验证输入。
    """
    total_checks = 0
    successful_checks = 0
    anomalous_metrics = 0
    baseline_hit_3sigma = 0
    rag_top1_score = None
    anomalous_metric_names: List[str] = []
    pre_snapshot: Dict[str, float] = {}

    for r in rounds:
        tool = r.get("tool")
        result = r.get("result")
        if tool == "device.live_inspection" and isinstance(result, dict):
            checks = result.get("checks", {})
            for check_name, check_result in checks.items():
                if not isinstance(check_result, dict):
                    continue
                total_checks += 1
                if check_result.get("supported", True) is False:
                    continue
                successful_checks += 1
                value = check_result.get("value")
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    pre_snapshot[check_name] = float(value)
                baseline_reason = check_result.get("baseline_reason")
                deviation = check_result.get("deviation_pct")
                if baseline_reason == "baseline_3sigma" or (
                    baseline_reason is None and deviation is not None and abs(deviation) > 300
                ):
                    anomalous_metrics += 1
                    anomalous_metric_names.append(check_name)
                    if check_result.get("baseline_status") in (None, "normal", "degraded"):
                        baseline_hit_3sigma += 1
        elif tool == "rag.retrieve" and isinstance(result, list) and result:
            top1 = result[0]
            if isinstance(top1, dict):
                score = top1.get("score")
                if score is not None:
                    rag_top1_score = float(score)

    llm_self_eval = final_answer.get("confidence") if isinstance(final_answer, dict) else None

    return {
        "total_checks": total_checks,
        "successful_checks": successful_checks,
        "anomalous_metrics": anomalous_metrics,
        "baseline_hit_3sigma": baseline_hit_3sigma,
        "rag_top1_score": rag_top1_score,
        "llm_self_eval": llm_self_eval,
        "anomalous_metric_names": anomalous_metric_names,
        "pre_snapshot": pre_snapshot,
    }
