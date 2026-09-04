# -*- coding: utf-8 -*-
"""RAG 问答 Prompt 模板。"""
from app.services.ai.prompts.registry import register_prompt

register_prompt(
    name="rag_answer",
    system="你是文档问答助手。只根据提供的检索片段回答，片段中没有的信息不要编造，找不到答案时明确说不知道。",
    user_tpl="检索片段：{chunks}\n用户问题：{question}",
)
