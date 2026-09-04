# -*- coding: utf-8 -*-
"""AI Prompt 模板包。import 本包即触发所有模板注册。"""
from app.services.ai.prompts import alert_interpret_prompt  # noqa: F401
from app.services.ai.prompts import device_inspect_prompt   # noqa: F401
from app.services.ai.prompts import rag_answer_prompt       # noqa: F401
