# -*- coding: utf-8 -*-
"""
二维码服务

处理二维码生成、状态管理等业务逻辑。
"""
import base64
import io
from app.utils.logging import get_logger
import random
import string
import time
from typing import Dict, Optional

import qrcode
import requests

from app.utils.cache import cache_manager

logger = get_logger(__name__)

QR_CODE_EXPIRE_TIME = 300  # 5分钟


class QRCodeService:
    """二维码服务"""
    
    def __init__(self):
        self.expire_time = QR_CODE_EXPIRE_TIME
    
    def generate_qr_code(self) -> Dict:
        """生成登录二维码
        
        Returns:
            Dict: 包含二维码URL、场景ID和过期时间的字典
        """
        scene_id = self._generate_scene_id()
        
        qr_content = f"wx_login:{scene_id}"
        
        qr_code = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr_code.add_data(qr_content)
        qr_code.make(fit=True)
        
        img = qr_code.make_image(fill_color="black", back_color="white")
        img_io = io.BytesIO()
        img.save(img_io, "PNG")
        img_io.seek(0)
        img_base64 = base64.b64encode(img_io.getvalue()).decode("utf-8")
        qr_url = f"data:image/png;base64,{img_base64}"
        
        expires_at = int(time.time()) + self.expire_time
        
        cache_data = {
            "status": "waiting",
            "created_at": int(time.time()),
            "expires_at": expires_at,
        }
        cache_manager.cache_qr_login(scene_id, cache_data, ttl=self.expire_time)
        
        logger.info(f"生成二维码成功，场景ID: {scene_id}")
        
        return {
            "qr_url": qr_url,
            "scene_id": scene_id,
            "expires_at": expires_at,
        }
    
    def check_qr_status(self, scene_id: str) -> Dict:
        """检查二维码登录状态
        
        Args:
            scene_id: 二维码场景ID
            
        Returns:
            Dict: 包含状态信息的字典
        """
        cache_data = cache_manager.get_qr_login(scene_id)
        
        if not cache_data:
            return {
                "status": "expired",
                "message": "二维码已过期"
            }
        
        status = cache_data.get("status", "waiting")
        message = self._get_status_message(status)
        
        result = {
            "status": status,
            "message": message
        }
        
        if status == "confirmed":
            result.update({
                "token": cache_data.get("token"),
                "user": cache_data.get("user", {}),
            })
            
            cache_manager.delete_qr_login(scene_id)
        
        return result
    
    def exchange_code_for_openid(self, code: str) -> Optional[Dict]:
        """用微信授权码换取 openid（后端校验，不可伪造）

        通过微信 jscode2session 接口，使用 code 换取 openid。
        此方法确保 openid 由微信服务器返回，客户端无法伪造。

        Args:
            code: 微信小程序登录凭证（wx.login 获取）

        Returns:
            Optional[Dict]: 成功返回 {"openid": "...", "user_info": {}}，失败返回 None
        """
        from config import Config

        appid = getattr(Config, 'WX_APPID', '')
        secret = getattr(Config, 'WX_SECRET', '')

        if not appid or not secret:
            logger.error("微信小程序配置缺失：WX_APPID 或 WX_SECRET 未设置")
            return None

        url = "https://api.weixin.qq.com/sns/jscode2session"
        params = {
            "appid": appid,
            "secret": secret,
            "js_code": code,
            "grant_type": "authorization_code"
        }

        try:
            resp = requests.get(url, params=params, timeout=5)
            data = resp.json()

            if "errcode" in data and data["errcode"] != 0:
                logger.warning("微信 code2session 失败: errcode=%s, errmsg=%s",
                               data.get("errcode"), data.get("errmsg"))
                return None

            openid = data.get("openid")
            if not openid:
                logger.warning("微信 code2session 返回无 openid: %s", data)
                return None

            return {"openid": openid, "user_info": {}}

        except requests.RequestException as e:
            logger.error("微信授权请求异常: %s", e)
            return None
        except (ValueError, KeyError) as e:
            logger.error("微信授权响应解析失败: %s", e)
            return None

    def confirm_qr_scan(self, scene_id: str, openid: str, user_info: Dict = None) -> bool:
        """确认二维码扫描
        
        Args:
            scene_id: 场景ID
            openid: 微信openid
            user_info: 用户信息
            
        Returns:
            bool: 操作是否成功
        """
        cache_data = cache_manager.get_qr_login(scene_id)
        
        if not cache_data:
            return False
        
        if cache_data.get("status") != "waiting":
            return False
        
        cache_data["status"] = "scanned"
        cache_data["openid"] = openid
        if user_info:
            cache_data["user_info"] = user_info
            
        cache_manager.cache_qr_login(scene_id, cache_data, ttl=self.expire_time)
        
        logger.info(f"二维码已扫描，场景ID: {scene_id}, openid: {openid[:10]}...")
        
        return True
    
    def complete_qr_login(self, scene_id: str, token: str, user: Dict) -> bool:
        """完成二维码登录
        
        Args:
            scene_id: 场景ID
            token: 访问令牌
            user: 用户信息
            
        Returns:
            bool: 操作是否成功
        """
        cache_data = cache_manager.get_qr_login(scene_id)
        
        if not cache_data:
            return False
        
        if cache_data.get("status") != "scanned":
            return False
        
        cache_data["status"] = "confirmed"
        cache_data["token"] = token
        cache_data["user"] = user
        cache_manager.cache_qr_login(scene_id, cache_data, ttl=self.expire_time)
        
        logger.info(f"二维码登录成功，场景ID: {scene_id}, 用户ID: {user.get('id')}")
        
        return True
    
    def _generate_scene_id(self, length: int = 16) -> str:
        """生成随机场景ID
        
        Args:
            length: ID长度
            
        Returns:
            随机字符串
        """
        chars = string.ascii_letters + string.digits
        return "".join(random.choice(chars) for _ in range(length))
    
    def _get_status_message(self, status: str) -> str:
        """获取状态描述
        
        Args:
            status: 状态码
            
        Returns:
            状态描述
        """
        messages = {
            "waiting": "等待扫码...",
            "scanned": "已扫码，等待确认...",
            "confirmed": "登录成功！",
            "expired": "二维码已过期",
            "error": "系统错误",
        }
        return messages.get(status, "未知状态")