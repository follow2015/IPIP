# -*- coding: utf-8 -*-
"""Celery 任务包（AI 长任务异步化）。

仅本包与 `app/celery_app.py` 依赖 celery，API / 服务层不直接依赖，保持分层
（方案 §8「Celery 依赖污染」约束）。
"""
