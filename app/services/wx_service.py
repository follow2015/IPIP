# -*- coding: utf-8 -*-
"""
微信服务模块

提供微信Token管理和JS-SDK配置生成功能。
"""
import hashlib
import json
from app.utils.logging import get_logger
import random
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse, urlunparse

import requests

from app.utils.cache import cache_manager
from config import get_config

logger = get_logger(__name__)

WECHAT_API_TIMEOUT = 10  # 微信 API 请求超时时间（秒）


class WeChatTokenManager:
    """微信Token管理器

    负责管理微信access_token和jsapi_ticket的获取和缓存。
    使用Redis缓存来避免频繁调用微信API。
    """

    def __init__(self, cache=None):
        """初始化Token管理器

        Args:
            cache: 缓存管理器实例，如果为None则使用全局缓存管理器
        """
        self.config = get_config()
        self.cache = cache or cache_manager

        self.appid = getattr(self.config, "WX_APPID", None)
        self.secret = getattr(self.config, "WX_SECRET", None)

        if not self.appid or not self.secret:
            logger.warning("微信配置不完整，WX_APPID或WX_SECRET未设置")

    def get_access_token(self) -> Optional[str]:
        """获取access_token

        优先从缓存获取，如果缓存不存在或即将过期，则从微信API获取新token。

        Returns:
            access_token字符串，失败返回None
        """
        cache_key = "wx_access_token"

        try:
            cached_data = self.cache.get(cache_key)
            if cached_data:
                token_data = (
                    json.loads(cached_data) if isinstance(cached_data, str) else cached_data
                )
                if int(time.time()) < token_data.get("expires_at", 0) - 300:
                    logger.debug("从缓存获取access_token成功")
                    return token_data["access_token"]
                else:
                    logger.info("access_token即将过期，重新获取")
        except Exception as e:
            logger.error(f"从缓存获取access_token失败: {e}")

        return self._fetch_new_access_token(cache_key)

    def _fetch_new_access_token(self, cache_key: str) -> Optional[str]:
        """从微信API获取新的access_token

        Args:
            cache_key: 缓存键名

        Returns:
            access_token字符串，失败返回None
        """
        if not self.appid or not self.secret:
            logger.error("无法获取access_token：微信配置不完整")
            return None

        try:
            url = (
                f"https://api.weixin.qq.com/cgi-bin/token"
                f"?grant_type=client_credential"
                f"&appid={self.appid}"
                f"&secret={self.secret}"
            )

            response = requests.get(url, timeout=WECHAT_API_TIMEOUT)

            if response.status_code != 200:
                logger.error(f"获取access_token HTTP请求失败: status_code={response.status_code}")
                return None

            data = response.json()

            if "errcode" in data and data["errcode"] != 0:
                logger.error(
                    f"获取access_token失败: "
                    f"errcode={data['errcode']}, "
                    f"errmsg={data.get('errmsg', 'Unknown error')}"
                )
                return None

            access_token = data.get("access_token")
            expires_in = data.get("expires_in", 7200)  # 默认2小时

            if not access_token:
                logger.error("微信返回数据中缺少access_token")
                return None

            try:
                token_data = {
                    "access_token": access_token,
                    "expires_at": int(time.time()) + expires_in,
                    "created_at": int(time.time()),
                }
                cache_expires = expires_in - 300 if expires_in > 300 else expires_in
                self.cache.set(cache_key, json.dumps(token_data), ttl=cache_expires)
                logger.info(f"access_token缓存成功，过期时间: {cache_expires}秒")
            except Exception as e:
                logger.error(f"缓存access_token失败: {e}")

            logger.info("成功获取新的access_token")
            return access_token

        except requests.RequestException as e:
            logger.error(f"获取access_token网络请求失败: {e}")
            return None
        except Exception as e:
            logger.error(f"获取access_token异常: {e}")
            return None

    def get_jsapi_ticket(self, access_token: str) -> Optional[str]:
        """获取jsapi_ticket

        优先从缓存获取，如果缓存不存在或即将过期，则从微信API获取新ticket。

        Args:
            access_token: 微信access_token

        Returns:
            jsapi_ticket字符串，失败返回None
        """
        cache_key = f"wx_jsapi_ticket:{access_token[:10]}"

        try:
            cached_data = self.cache.get(cache_key)
            if cached_data:
                ticket_data = (
                    json.loads(cached_data) if isinstance(cached_data, str) else cached_data
                )
                if int(time.time()) < ticket_data.get("expires_at", 0) - 300:
                    logger.debug("从缓存获取jsapi_ticket成功")
                    return ticket_data["ticket"]
                else:
                    logger.info("jsapi_ticket即将过期，重新获取")
        except Exception as e:
            logger.error(f"从缓存获取jsapi_ticket失败: {e}")

        return self._fetch_new_jsapi_ticket(access_token, cache_key)

    def _fetch_new_jsapi_ticket(self, access_token: str, cache_key: str) -> Optional[str]:
        """从微信API获取新的jsapi_ticket

        Args:
            access_token: 微信access_token
            cache_key: 缓存键名

        Returns:
            jsapi_ticket字符串，失败返回None
        """
        try:
            url = (
                f"https://api.weixin.qq.com/cgi-bin/ticket/getticket"
                f"?access_token={access_token}"
                f"&type=jsapi"
            )

            response = requests.get(url, timeout=WECHAT_API_TIMEOUT)

            if response.status_code != 200:
                logger.error(f"获取jsapi_ticket HTTP请求失败: status_code={response.status_code}")
                return None

            data = response.json()

            if "errcode" in data and data["errcode"] != 0:
                logger.error(
                    f"获取jsapi_ticket失败: "
                    f"errcode={data['errcode']}, "
                    f"errmsg={data.get('errmsg', 'Unknown error')}"
                )
                return None

            ticket = data.get("ticket")
            expires_in = data.get("expires_in", 7200)  # 默认2小时

            if not ticket:
                logger.error("微信返回数据中缺少ticket")
                return None

            try:
                ticket_data = {
                    "ticket": ticket,
                    "expires_at": int(time.time()) + expires_in,
                    "created_at": int(time.time()),
                }
                cache_expires = expires_in - 300 if expires_in > 300 else expires_in
                self.cache.set(cache_key, json.dumps(ticket_data), ttl=cache_expires)
                logger.info(f"jsapi_ticket缓存成功，过期时间: {cache_expires}秒")
            except Exception as e:
                logger.error(f"缓存jsapi_ticket失败: {e}")

            logger.info("成功获取新的jsapi_ticket")
            return ticket

        except requests.RequestException as e:
            logger.error(f"获取jsapi_ticket网络请求失败: {e}")
            return None
        except Exception as e:
            logger.error(f"获取jsapi_ticket异常: {e}")
            return None

    def invalidate_cache(self) -> None:
        """清除所有微信相关缓存

        强制刷新access_token和jsapi_ticket。
        """
        try:
            self.cache.delete("wx_access_token")

            self.cache.invalidate_pattern("wx_jsapi_ticket:*")

            logger.info("微信缓存已清除")
        except Exception as e:
            logger.error(f"清除微信缓存失败: {e}")


class WeChatService:
    """微信服务类

    提供微信JS-SDK配置生成等功能。
    """

    def __init__(self, token_manager: Optional[WeChatTokenManager] = None):
        """初始化微信服务

        Args:
            token_manager: Token管理器实例，如果为None则创建新实例
        """
        self.config = get_config()
        self.token_manager = token_manager or WeChatTokenManager()

    def generate_js_sdk_config(self, url: str) -> Dict[str, Any]:
        """生成微信JS-SDK签名配置

        Args:
            url: 当前页面的完整URL

        Returns:
            包含appId、timestamp、nonceStr、signature等字段的配置字典

        Raises:
            Exception: 当配置不完整或获取token失败时
        """
        try:
            if not self.config.WX_APPID or not self.config.WX_SECRET:
                raise Exception("微信配置不完整，请检查WX_APPID和WX_SECRET是否正确配置")

            access_token = self.token_manager.get_access_token()
            if not access_token:
                raise Exception("获取微信access_token失败")

            jsapi_ticket = self.token_manager.get_jsapi_ticket(access_token)
            if not jsapi_ticket:
                raise Exception("获取微信jsapi_ticket失败")

            nonce_str = self._generate_nonce_str()
            timestamp = int(time.time())

            clean_url = self._clean_url(url)

            signature = self._generate_signature(jsapi_ticket, nonce_str, timestamp, clean_url)

            logger.info(f"成功生成微信JS-SDK配置，URL: {clean_url}")

            return {
                "appId": self.config.WX_APPID,
                "timestamp": timestamp,
                "nonceStr": nonce_str,
                "signature": signature,
                "url": clean_url,
            }

        except Exception as e:
            logger.error(f"生成微信JS-SDK配置失败: {str(e)}")
            raise

    def invalidate_cache(self) -> None:
        """清除微信相关缓存"""
        self.token_manager.invalidate_cache()

    @staticmethod
    def _clean_url(url: str) -> str:
        """清理URL，去除fragment部分

        微信签名要求URL不包含#及其后面的部分。

        Args:
            url: 原始URL

        Returns:
            清理后的URL
        """
        parsed_url = urlparse(url)
        return urlunparse(
            (
                parsed_url.scheme,
                parsed_url.netloc,
                parsed_url.path,
                parsed_url.params,
                parsed_url.query,
                None,  # 不包括fragment (#部分)
            )
        )

    @staticmethod
    def _generate_nonce_str(length: int = 16) -> str:
        """生成随机字符串

        Args:
            length: 字符串长度，默认16

        Returns:
            随机字符串
        """
        chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        return "".join(random.choice(chars) for _ in range(length))

    @staticmethod
    def _generate_signature(jsapi_ticket: str, nonce_str: str, timestamp: int, url: str) -> str:
        """生成微信JS-SDK签名

        Args:
            jsapi_ticket: 微信jsapi_ticket
            nonce_str: 随机字符串
            timestamp: 时间戳
            url: 页面URL

        Returns:
            SHA1签名字符串
        """
        string = f"jsapi_ticket={jsapi_ticket}&noncestr={nonce_str}&timestamp={timestamp}&url={url}"
        return hashlib.sha1(string.encode("utf-8")).hexdigest()


_token_manager = WeChatTokenManager()
_wx_service = WeChatService(_token_manager)


def generate_wx_config(url: str) -> Dict[str, Any]:
    """生成微信JS-SDK配置（向后兼容接口）

    Args:
        url: 当前页面的完整URL

    Returns:
        微信JS-SDK配置字典
    """
    return _wx_service.generate_js_sdk_config(url)


def _get_wx_access_token() -> Optional[str]:
    """获取微信access_token（向后兼容接口）

    Returns:
        access_token字符串
    """
    return _token_manager.get_access_token()


def _get_wx_jsapi_ticket(access_token: str) -> Optional[str]:
    """获取微信jsapi_ticket（向后兼容接口）

    Args:
        access_token: 微信access_token

    Returns:
        jsapi_ticket字符串
    """
    return _token_manager.get_jsapi_ticket(access_token)
