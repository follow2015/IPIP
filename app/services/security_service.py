# -*- coding: utf-8 -*-
"""
安全服务

提供密码验证、格式检查等安全相关功能。
"""
import re
from typing import Tuple

from app.utils.security.password import password_manager


class SecurityService:
    
    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        return password_manager.verify_password(password, hashed_password)
    
    @staticmethod
    def validate_password(password: str) -> Tuple[bool, str]:
        if not password:
            return False, "密码不能为空"
        
        strength_info = password_manager.check_strength(password)
        
        if strength_info['level'] == 'weak':
            suggestions = strength_info.get('suggestions', [])
            if suggestions:
                return False, f"密码强度不足：{'; '.join(suggestions[:3])}"
            else:
                return False, "密码强度不足"
        
        return True, ""
    
    @staticmethod
    def validate_username(username: str) -> bool:
        if not username:
            return False
        
        if len(username) < 3 or len(username) > 50:
            return False
        
        if not re.match(r'^[a-zA-Z0-9_-]+$', username):
            return False
        
        if username[0].isdigit():
            return False
        
        return True
