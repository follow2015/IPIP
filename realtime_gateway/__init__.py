# -*- coding: utf-8 -*-
"""
realtime_gateway — 独立 ASGI 推送网关

从 Flask 主应用中剥离 SSE 服务，作为独立 uvicorn 进程运行。
职责单一：订阅 Redis Pub/Sub，分配全局唯一 seq，维护环形缓冲区，
通过 SSE 推送给浏览器 EventSource 客户端。

架构：
    Flask (switch_events.py) ──publish──▶ Redis Pub/Sub ──▶ 本网关 ──▶ 浏览器

启动：
    uvicorn realtime_gateway.main:app
"""
