# -*- coding: utf-8 -*-
"""
安全服务

提供密码验证、格式检查等安全相关功能。
"""
import re
from typing import Tuple

from app.utils.security.password import password_manager


class SecurityService:
    """安全服务"""
    
    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        """验证密码
        
        Args:
            password: 明文密码
            hashed_password: 加密后的密码
            
        Returns:
            bool: 密码正确返回True
        """
        return password_manager.verify_password(password, hashed_password)
    
    @staticmethod
    def validate_password(password: str) -> Tuple[bool, str]:
        """验证密码格式
        
        Args:
            password: 明文密码
            
        Returns:
            Tuple[bool, str]: (是否有效, 错误信息)
        """
        if not password:
            return False, "密码不能为空"
        
        strength_info = password_manager.check_strength(password)
        
        if strength_info['level'] == 'weak':
            suggestions = strength_info.get('suggestions', [])
            if suggestions:
                return False, f"密码强度不足：{'; '.join(suggestions[:3])}"  # 只显示前3个建议
            else:
                return False, "密码强度不足"
        
        return True, ""
    
    @staticmethod
    def validate_username(username: str) -> bool:
        """验证用户名格式
        
        Args:
            username: 用户名
            
        Returns:
            bool: 格式正确返回True
        """
        if not username:
            return False
        
        if len(username) < 3 or len(username) > 50:
            return False
        
        if not re.match(r'^[a-zA-Z0-9_-]+$', username):
            return False
        
        if username[0].isdigit():
            return False
        
        return True