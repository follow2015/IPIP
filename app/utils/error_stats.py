# -*- coding: utf-8 -*-
"""
错误统计模块

提供错误频率统计和查询功能。
"""
from app.utils.logging import get_logger
import time
from collections import defaultdict
from datetime import datetime
from threading import Lock
from typing import Any, Dict, List, Optional

from config import get_config

config = get_config()
logger = get_logger(__name__)


class ErrorStats:

    def __init__(self):
        self.enabled = config.ERROR_STATS_ENABLED
        self.window = config.ERROR_STATS_WINDOW

        self._errors: Dict[str, List[tuple]] = defaultdict(list)

        self._error_counts: Dict[str, int] = defaultdict(int)

        self._lock = Lock()

        logger.info(f"错误统计器已初始化 | 启用: {self.enabled} | 统计窗口: {self.window}秒")

    def record_error(
        self,
        error_type: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        if not self.enabled:
            return

        try:
            with self._lock:
                timestamp = time.time()

                self._errors[error_type].append((timestamp, message, context or {}))

                self._error_counts[error_type] += 1

                self._cleanup_old_errors()

        except Exception as e:
            logger.error(f"记录错误统计失败: {str(e)}", exc_info=True)

    def get_error_count(self, error_type: Optional[str] = None) -> int:
        if not self.enabled:
            return 0

        try:
            with self._lock:
                self._cleanup_old_errors()

                if error_type:
                    return len(self._errors.get(error_type, []))
                else:
                    return sum(len(errors) for errors in self._errors.values())

        except Exception as e:
            logger.error(f"获取错误计数失败: {str(e)}", exc_info=True)
            return 0

    def get_error_types(self) -> List[str]:
        if not self.enabled:
            return []

        try:
            with self._lock:
                self._cleanup_old_errors()
                return list(self._errors.keys())

        except Exception as e:
            logger.error(f"获取错误类型失败: {str(e)}", exc_info=True)
            return []

    def get_error_stats(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"enabled": False}

        try:
            with self._lock:
                self._cleanup_old_errors()

                stats_by_type = {}
                for error_type, errors in self._errors.items():
                    if errors:
                        stats_by_type[error_type] = {
                            "count": len(errors),
                            "first_seen": datetime.fromtimestamp(errors[0][0]).isoformat(),
                            "last_seen": datetime.fromtimestamp(errors[-1][0]).isoformat(),
                            "recent_messages": [msg for _, msg, _ in errors[-5:]],
                        }

                total_errors = sum(len(errors) for errors in self._errors.values())

                return {
                    "enabled": True,
                    "window_seconds": self.window,
                    "total_errors": total_errors,
                    "error_types_count": len(self._errors),
                    "stats_by_type": stats_by_type,
                    "timestamp": datetime.now().isoformat(),
                }

        except Exception as e:
            logger.error(f"获取错误统计失败: {str(e)}", exc_info=True)
            return {"enabled": True, "error": str(e)}

    def get_top_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []

        try:
            with self._lock:
                self._cleanup_old_errors()

                sorted_errors = sorted(
                    self._errors.items(),
                    key=lambda x: len(x[1]),
                    reverse=True,
                )

                result = []
                for error_type, errors in sorted_errors[:limit]:
                    if errors:
                        result.append(
                            {
                                "error_type": error_type,
                                "count": len(errors),
                                "first_seen": datetime.fromtimestamp(errors[0][0]).isoformat(),
                                "last_seen": datetime.fromtimestamp(errors[-1][0]).isoformat(),
                                "last_message": errors[-1][1],
                            }
                        )

                return result

        except Exception as e:
            logger.error(f"获取高频错误失败: {str(e)}", exc_info=True)
            return []

    def clear_stats(self):
        if not self.enabled:
            return

        try:
            with self._lock:
                self._errors.clear()
                self._error_counts.clear()
                logger.info("错误统计数据已清除")

        except Exception as e:
            logger.error(f"清除错误统计失败: {str(e)}", exc_info=True)

    def _cleanup_old_errors(self):
        try:
            current_time = time.time()
            cutoff_time = current_time - self.window

            for error_type in list(self._errors.keys()):
                self._errors[error_type] = [
                    (ts, msg, ctx) for ts, msg, ctx in self._errors[error_type] if ts > cutoff_time
                ]

                if not self._errors[error_type]:
                    del self._errors[error_type]

        except Exception as e:
            logger.error(f"清理过期错误记录失败: {str(e)}", exc_info=True)


error_stats = ErrorStats()
