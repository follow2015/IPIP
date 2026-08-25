# -*- coding: utf-8 -*-
"""
健康检查模块

提供系统健康检查和错误统计功能。
"""
from app.utils.logging import get_logger
import shutil
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List

from app.utils.cache import cache_manager
from extensions import db

logger = get_logger(__name__)


class HealthChecker:

    @staticmethod
    def check_database() -> Dict[str, Any]:
        try:
            db.session.execute(db.text("SELECT 1"))
            return {"status": "healthy", "message": "数据库连接正常"}
        except Exception as e:
            logger.error(f"数据库健康检查失败: {e}", exc_info=True)
            return {"status": "unhealthy", "message": f"数据库连接异常: {str(e)}"}

    @staticmethod
    def check_redis() -> Dict[str, Any]:
        try:
            redis_client = None
            if hasattr(cache_manager, 'primary_storage') and hasattr(cache_manager.primary_storage, 'redis_client'):
                redis_client = cache_manager.primary_storage.redis_client
                
            if redis_client and redis_client.ping():
                return {"status": "healthy", "message": "Redis连接正常"}
            else:
                return {"status": "unhealthy", "message": "Redis连接失败"}
        except Exception as e:
            logger.error(f"Redis健康检查失败: {e}", exc_info=True)
            return {"status": "unhealthy", "message": f"Redis连接异常: {str(e)}"}

    @staticmethod
    def check_disk_space(threshold: float = 0.9) -> Dict[str, Any]:
        try:
            disk_usage = shutil.disk_usage("/")

            total = disk_usage.total
            used = disk_usage.used
            free = disk_usage.free
            usage_percent = used / total

            status = "healthy" if usage_percent < threshold else "warning"

            return {
                "status": status,
                "message": f"磁盘使用率: {usage_percent:.1%}",
                "total": total,
                "used": used,
                "free": free,
                "usage_percent": usage_percent,
            }
        except Exception as e:
            logger.error(f"磁盘空间检查失败: {e}", exc_info=True)
            return {"status": "unhealthy", "message": f"磁盘空间检查异常: {str(e)}"}

    @staticmethod
    def check_all() -> Dict[str, Any]:
        results = {
            "timestamp": datetime.now().isoformat(),
            "checks": {
                "database": HealthChecker.check_database(),
                "redis": HealthChecker.check_redis(),
                "disk": HealthChecker.check_disk_space(),
            },
        }

        all_healthy = all(check["status"] == "healthy" for check in results["checks"].values())

        results["overall_status"] = "healthy" if all_healthy else "unhealthy"

        return results


class ErrorStatistics:

    def __init__(self):
        self.error_counts = defaultdict(int)
        self.error_details = []
        self.max_details = 100

    def record_error(self, error_type: str, message: str, context: Dict[str, Any] = None):
        self.error_counts[error_type] += 1

        error_detail = {
            "type": error_type,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "context": context or {},
        }

        self.error_details.append(error_detail)

        if len(self.error_details) > self.max_details:
            self.error_details = self.error_details[-self.max_details :]

        try:
            cache_key = f"error_stats:{error_type}"
            cache_manager.increment(cache_key)
        except Exception as e:
            logger.error(f"记录错误统计到Redis失败: {e}")

    def get_statistics(self, time_range: int = 3600) -> Dict[str, Any]:
        cutoff_time = datetime.now() - timedelta(seconds=time_range)

        recent_errors = [
            error
            for error in self.error_details
            if datetime.fromisoformat(error["timestamp"]) > cutoff_time
        ]

        type_counts = defaultdict(int)
        for error in recent_errors:
            type_counts[error["type"]] += 1

        return {
            "time_range": time_range,
            "total_errors": len(recent_errors),
            "error_types": dict(type_counts),
            "recent_errors": recent_errors[-10:],
        }

    def get_top_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        sorted_errors = sorted(self.error_counts.items(), key=lambda x: x[1], reverse=True)

        return [{"type": error_type, "count": count} for error_type, count in sorted_errors[:limit]]

    def clear_statistics(self):
        self.error_counts.clear()
        self.error_details.clear()

        logger.info("错误统计数据已清空")


health_checker = HealthChecker()
error_statistics = ErrorStatistics()
