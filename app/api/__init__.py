# -*- coding: utf-8 -*-
"""
API蓝图包

包含所有API端点的蓝图。
"""
from app.api.auth import auth_bp
from app.api.cabinet import cabinet_bp
from app.api.customer import customer_bp
from app.api.device import device_bp
from app.api.device_storage import device_storage_bp
from app.api.health import health_bp
from app.api.room import room_bp
from app.api.user import user_bp

from app.api.ip_routes import router as ip_bp
from app.api.network_routes import router as network_bp
from app.api.switch_routes import router as switch_bp

from app.api.dashboard import dashboard_bp
from app.api.component_template import component_template_bp

__all__ = [
    "health_bp",
    "auth_bp",
    "user_bp",
    "room_bp",
    "cabinet_bp",
    "device_bp",
    "device_storage_bp",
    "customer_bp",
    "dashboard_bp",
    "network_bp",
    "ip_bp",
    "switch_bp",
    "component_template_bp",
]
