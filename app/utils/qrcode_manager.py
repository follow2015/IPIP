# -*- coding: utf-8 -*-
"""
二维码管理器模块

负责微信扫码登录的二维码生成和状态管理。
支持本地二维码生成和微信 API 生成（降级方案）。
"""
import io
import time
import secrets
from app.utils.logging import get_logger
import qrcode
import base64
from typing import Optional, Dict, Any
from flask import request

from app.utils.storage import StorageAdapter

logger = get_logger(__name__)


class QRCodeManager:
    """二维码管理器
    
    负责生成、存储和管理二维码状态。
    支持四种状态：waiting（等待扫码）、scanned（已扫码）、confirmed（已确认）、expired（已过期）
    """

    def __init__(self, redis_client=None):
        """初始化二维码管理器
        
        Args:
            redis_client: Redis 客户端实例，如果为 None 则使用内存存储
        """
        self.storage = StorageAdapter(redis_client)
        logger.info("二维码管理器初始化完成")

    def generate_scene_id(self) -> str:
        """生成唯一的场景 ID
        
        使用时间戳 + 随机数生成唯一标识符，确保并发请求的唯一性。
        
        Returns:
            str: 唯一的场景 ID（格式：时间戳 + 6位随机数）
        """
        timestamp = int(time.time())
        random_part = secrets.randbelow(999999)
        scene_id = f"{timestamp}{random_part:06d}"
        logger.info(f"生成场景 ID: {scene_id}")
        return scene_id

    def create_qr_session(self, scene_id: str, expire_minutes: int = 5) -> bool:
        """创建二维码会话
        
        初始化二维码会话数据，状态设置为 waiting，并设置过期时间。
        
        Args:
            scene_id: 场景 ID
            expire_minutes: 过期时间（分钟），默认 5 分钟
            
        Returns:
            bool: 创建是否成功
        """
        try:
            session_data = {
                'scene_id': scene_id,
                'status': 'waiting',  # waiting/scanned/confirmed/expired
                'created_at': int(time.time()),
                'expires_at': int(time.time()) + (expire_minutes * 60),
                'openid': None,
                'user_id': None
            }
            
            key = f"qr_session:{scene_id}"
            ttl = expire_minutes * 60
            
            success = self.storage.set(key, session_data, ttl)
            
            if success:
                logger.info(f"创建二维码会话成功: scene_id={scene_id}, expire_minutes={expire_minutes}")
            else:
                logger.error(f"创建二维码会话失败: scene_id={scene_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"创建二维码会话异常: scene_id={scene_id}, error={str(e)}", exc_info=True)
            return False

    def get_qr_session(self, scene_id: str) -> Optional[Dict[str, Any]]:
        """获取二维码会话数据
        
        查询指定场景 ID 的会话数据，如果已过期则返回 None。
        
        Args:
            scene_id: 场景 ID
            
        Returns:
            Optional[Dict]: 会话数据，如果不存在或已过期则返回 None
        """
        try:
            key = f"qr_session:{scene_id}"
            session_data = self.storage.get(key)
            
            if session_data is None:
                logger.info(f"二维码会话不存在或已过期: scene_id={scene_id}")
                return None
            
            current_time = int(time.time())
            if session_data.get('expires_at', 0) < current_time:
                logger.info(f"二维码会话已过期: scene_id={scene_id}")
                session_data['status'] = 'expired'
                self.storage.set(key, session_data, 60)  # 保留 1 分钟供查询
                return session_data
            
            logger.debug(f"获取二维码会话: scene_id={scene_id}, status={session_data.get('status')}")
            return session_data
            
        except Exception as e:
            logger.error(f"获取二维码会话异常: scene_id={scene_id}, error={str(e)}", exc_info=True)
            return None

    def update_qr_session(self, scene_id: str, status: str, 
                         openid: Optional[str] = None, 
                         user_id: Optional[int] = None,
                         error_message: Optional[str] = None) -> bool:
        """更新二维码会话状态
        
        更新会话的状态和相关信息。状态转换必须遵循状态机规则：
        waiting → scanned → confirmed 或 waiting → expired
        
        Args:
            scene_id: 场景 ID
            status: 新状态（waiting/scanned/confirmed/expired）
            openid: 微信 OpenID（可选）
            user_id: 用户 ID（可选）
            error_message: 错误消息（可选）
            
        Returns:
            bool: 更新是否成功
        """
        try:
            session_data = self.get_qr_session(scene_id)
            
            if session_data is None:
                logger.warning(f"更新二维码会话失败: 会话不存在, scene_id={scene_id}")
                return False
            
            current_status = session_data.get('status')
            valid_transitions = {
                'waiting': ['scanned', 'expired'],
                'scanned': ['confirmed', 'expired'],
                'confirmed': [],  # 已确认状态不能再转换
                'expired': []  # 已过期状态不能再转换
            }
            
            if status != current_status and status not in valid_transitions.get(current_status, []):
                logger.warning(
                    f"无效的状态转换: scene_id={scene_id}, "
                    f"from={current_status}, to={status}"
                )
                return False
            
            session_data['status'] = status
            
            if openid is not None:
                session_data['openid'] = openid
            
            if user_id is not None:
                session_data['user_id'] = user_id
            
            if error_message is not None:
                session_data['error_message'] = error_message
            
            session_data['updated_at'] = int(time.time())
            
            key = f"qr_session:{scene_id}"
            remaining_ttl = session_data.get('expires_at', 0) - int(time.time())
            if remaining_ttl < 0:
                remaining_ttl = 60  # 已过期的保留 1 分钟
            
            success = self.storage.set(key, session_data, remaining_ttl)
            
            if success:
                logger.info(
                    f"更新二维码会话成功: scene_id={scene_id}, status={status}, "
                    f"openid={openid}, user_id={user_id}"
                )
            else:
                logger.error(f"更新二维码会话失败: scene_id={scene_id}")
            
            return success
            
        except Exception as e:
            logger.error(
                f"更新二维码会话异常: scene_id={scene_id}, status={status}, "
                f"error={str(e)}", 
                exc_info=True
            )
            return False

    def generate_qr_code(self, scene_id: str) -> str:
        """生成二维码图片
        
        优先使用本地生成二维码，避免微信服务器的 CORS 问题。
        如果需要，可以降级到微信 API 生成。
        
        Args:
            scene_id: 场景 ID
            
        Returns:
            str: Base64 编码的二维码图片数据（data URL 格式）
            
        Raises:
            Exception: 当二维码生成失败时抛出异常，包含详细的错误信息
        """
        try:
            logger.info(f"生成二维码: scene_id={scene_id}, 使用本地生成")
            
            local_qr = self._generate_local_qr_code(scene_id)
            
            if local_qr is None:
                error_msg = f"本地生成二维码返回 None: scene_id={scene_id}"
                logger.error(error_msg)
                raise Exception(error_msg)
            
            return local_qr
            
        except Exception as e:
            logger.error(
                f"生成二维码失败: scene_id={scene_id}, "
                f"error_type={type(e).__name__}, "
                f"error_message={str(e)}", 
                exc_info=True
            )
            raise

    def _generate_local_qr_code(self, scene_id: str) -> str:
        """本地生成二维码（主要方案）
        
        使用 qrcode 库生成二维码图片，内容为包含 scene_id 的 URL。
        支持在测试环境中（request 对象不存在时）使用默认 URL。
        
        Args:
            scene_id: 场景 ID
            
        Returns:
            str: Base64 编码的二维码图片数据（data URL 格式）
            
        Raises:
            Exception: 当二维码生成失败时抛出异常
        """
        try:
            base_url = "http://localhost:5000"  # 默认值
            
            try:
                if request and hasattr(request, 'url_root'):
                    base_url = request.url_root.rstrip('/')
                    logger.debug(f"使用 request.url_root: {base_url}")
                else:
                    logger.debug(f"request 对象不可用，使用默认 base_url: {base_url}")
            except (RuntimeError, AttributeError) as e:
                logger.debug(f"无法访问 request.url_root ({type(e).__name__})，使用默认 base_url: {base_url}")
            
            base_url = base_url.rstrip('/')
            
            qr_content = f"{base_url}/api/users/wechat/qrcode/scan?scene_id={scene_id}"
            
            logger.info(f"生成本地二维码: scene_id={scene_id}, content={qr_content}")
            
            qr = qrcode.QRCode(
                version=1,  # 控制二维码大小（1-40）
                error_correction=qrcode.constants.ERROR_CORRECT_L,  # 错误纠正级别
                box_size=10,  # 每个格子的像素大小
                border=4  # 边框大小（格子数）
            )
            
            qr.add_data(qr_content)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            img_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            
            if not img_base64:
                raise Exception("Base64 编码结果为空")
            
            data_url = f"data:image/png;base64,{img_base64}"
            
            logger.info(f"本地二维码生成成功: scene_id={scene_id}, data_length={len(data_url)}")
            return data_url
            
        except Exception as e:
            error_msg = f"本地生成二维码异常: scene_id={scene_id}, error_type={type(e).__name__}, error={str(e)}"
            logger.error(error_msg, exc_info=True)
            raise Exception(error_msg) from e
