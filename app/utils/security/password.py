# -*- coding: utf-8 -*-
"""
密码管理器实现

提供统一的密码加密、验证、强度检查等功能。
"""
from app.utils.logging import get_logger
import re
import secrets
import string
from datetime import datetime, timedelta
from typing import Any, Dict

import bcrypt

from abc import ABC, abstractmethod
from config import get_config

logger = get_logger(__name__)
config = get_config()


class PasswordManager(ABC):

    @abstractmethod
    def hash_password(self, password: str) -> str:
        pass

    @abstractmethod
    def verify_password(self, password: str, hashed_password: str) -> bool:
        pass

    @abstractmethod
    def check_strength(self, password: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def generate_password(self, length: int = 12,
                         include_symbols: bool = True) -> str:
        pass

    @abstractmethod
    def is_password_expired(self, last_changed: datetime,
                           max_age_days: int = 90) -> bool:
        pass


class BCryptPasswordManager(PasswordManager):
    
    DUMMY_HASH = "$2b$12$q2MUtXQE7jJmEVbk0AaJteVRD61g4DOk41kXptczzsdfk1b7tn6ze"
    
    def __init__(self, rounds: int = None):
        self.rounds = rounds or getattr(config, 'BCRYPT_LOG_ROUNDS', 12)
        
        self.strength_rules = {
            'min_length': 8,
            'max_length': 128,
            'require_uppercase': True,
            'require_lowercase': True,
            'require_digits': True,
            'require_symbols': True,
            'min_unique_chars': 4,
        }
        
        self.weak_patterns = [
            r'(.)\1{2,}',
            r'(012|123|234|345|456|567|678|789|890)',
            r'(abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)',
            r'(qwe|asd|zxc)',
        ]
        
        self.common_passwords = {
            'password', '123456', '123456789', 'qwerty', 'abc123',
            'password123', 'admin', 'root', '12345678', '1234567890',
            'welcome', 'login', 'guest', 'test', 'user'
        }
    
    def hash_password(self, password: str) -> str:
        if not password:
            raise ValueError("密码不能为空")
        
        if not isinstance(password, str):
            raise ValueError("密码必须是字符串类型")
        
        try:
            salt = bcrypt.gensalt(rounds=self.rounds)
            hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
            return hashed.decode('utf-8')
        except Exception as e:
            logger.error(f"密码加密失败: {e}", exc_info=True)
            raise ValueError(f"密码加密失败: {e}")
    
    def verify_password(self, password: str, hashed_password: str) -> bool:
        if not password or not hashed_password:
            return False
        
        try:
            if isinstance(hashed_password, str):
                hashed_password = hashed_password.encode('utf-8')
            
            return bcrypt.checkpw(password.encode('utf-8'), hashed_password)
        except Exception as e:
            logger.error(f"密码验证失败: {e}", exc_info=True)
            return False
    
    def check_strength(self, password: str) -> Dict[str, Any]:
        if not password:
            return {
                'score': 0,
                'level': 'weak',
                'suggestions': ['密码不能为空'],
                'checks': {}
            }
        
        checks = {}
        suggestions = []
        score = 0
        
        length = len(password)
        checks['length'] = {
            'passed': length >= self.strength_rules['min_length'],
            'value': length,
            'requirement': f"至少{self.strength_rules['min_length']}个字符"
        }
        if checks['length']['passed']:
            score += 20
        else:
            suggestions.append(f"密码长度至少需要{self.strength_rules['min_length']}个字符")
        
        has_uppercase = bool(re.search(r'[A-Z]', password))
        checks['uppercase'] = {
            'passed': has_uppercase or not self.strength_rules['require_uppercase'],
            'value': has_uppercase,
            'requirement': '包含大写字母'
        }
        if checks['uppercase']['passed'] and has_uppercase:
            score += 15
        elif self.strength_rules['require_uppercase'] and not has_uppercase:
            suggestions.append('添加大写字母')
        
        has_lowercase = bool(re.search(r'[a-z]', password))
        checks['lowercase'] = {
            'passed': has_lowercase or not self.strength_rules['require_lowercase'],
            'value': has_lowercase,
            'requirement': '包含小写字母'
        }
        if checks['lowercase']['passed'] and has_lowercase:
            score += 15
        elif self.strength_rules['require_lowercase'] and not has_lowercase:
            suggestions.append('添加小写字母')
        
        has_digits = bool(re.search(r'\d', password))
        checks['digits'] = {
            'passed': has_digits or not self.strength_rules['require_digits'],
            'value': has_digits,
            'requirement': '包含数字'
        }
        if checks['digits']['passed'] and has_digits:
            score += 15
        elif self.strength_rules['require_digits'] and not has_digits:
            suggestions.append('添加数字')
        
        has_symbols = bool(re.search(r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]', password))
        checks['symbols'] = {
            'passed': has_symbols or not self.strength_rules['require_symbols'],
            'value': has_symbols,
            'requirement': '包含特殊符号'
        }
        if checks['symbols']['passed'] and has_symbols:
            score += 15
        elif self.strength_rules['require_symbols'] and not has_symbols:
            suggestions.append('添加特殊符号 (!@#$%^&* 等)')
        
        unique_chars = len(set(password.lower()))
        checks['unique_chars'] = {
            'passed': unique_chars >= self.strength_rules['min_unique_chars'],
            'value': unique_chars,
            'requirement': f"至少{self.strength_rules['min_unique_chars']}个不同字符"
        }
        if checks['unique_chars']['passed']:
            score += 10
        else:
            suggestions.append(f'使用至少{self.strength_rules["min_unique_chars"]}个不同的字符')
        
        is_common = password.lower() in self.common_passwords
        checks['not_common'] = {
            'passed': not is_common,
            'value': not is_common,
            'requirement': '不是常见密码'
        }
        if not is_common:
            score += 10
        else:
            suggestions.append('避免使用常见密码')
            score = max(0, score - 20)
        
        weak_pattern_found = any(re.search(pattern, password.lower()) for pattern in self.weak_patterns)
        checks['no_weak_patterns'] = {
            'passed': not weak_pattern_found,
            'value': not weak_pattern_found,
            'requirement': '避免重复字符和简单模式'
        }
        if not weak_pattern_found:
            score += 10
        else:
            suggestions.append('避免使用重复字符或简单的字符序列')
            score = max(0, score - 15)
        
        if score >= 80:
            level = 'strong'
        elif score >= 60:
            level = 'medium'
        else:
            level = 'weak'
        
        return {
            'score': min(100, score),
            'level': level,
            'suggestions': suggestions,
            'checks': checks
        }
    
    def generate_password(self, length: int = 12, include_symbols: bool = True) -> str:
        if length < 4:
            raise ValueError("密码长度至少为4个字符")
        if length > 128:
            raise ValueError("密码长度不能超过128个字符")
        
        lowercase = string.ascii_lowercase
        uppercase = string.ascii_uppercase
        digits = string.digits
        symbols = '!@#$%^&*()_+-=[]{}|;:,.<>?' if include_symbols else ''
        
        password_chars = []
        all_chars = lowercase + uppercase + digits + symbols
        
        password_chars.append(secrets.choice(lowercase))
        
        password_chars.append(secrets.choice(uppercase))
        
        password_chars.append(secrets.choice(digits))
        
        if include_symbols:
            password_chars.append(secrets.choice(symbols))
        
        remaining_length = length - len(password_chars)
        for _ in range(remaining_length):
            password_chars.append(secrets.choice(all_chars))
        
        secrets.SystemRandom().shuffle(password_chars)
        
        return ''.join(password_chars)
    
    def is_password_expired(self, last_changed: datetime, max_age_days: int = 90) -> bool:
        if not last_changed:
            return True
        
        if max_age_days <= 0:
            return False
        
        expiry_date = last_changed + timedelta(days=max_age_days)
        return datetime.now() > expiry_date


password_manager = BCryptPasswordManager()
