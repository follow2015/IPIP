# -*- coding: utf-8 -*-
"""
线程安全锁和同步原语

提供各种线程安全的锁机制和同步工具。
"""
import threading
import weakref
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar, Type
from app.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


class ReadWriteLock:
    """读写锁实现（写者优先）

    允许多个读者同时访问，但写者独占访问。
    写者优先策略：当有写者等待时，新的读者需要等待，避免写者饥饿。
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._readers = 0
        self._writers_waiting = 0
        self._writer_active = False
        self._read_ready = threading.Condition(self._lock)
        self._write_ready = threading.Condition(self._lock)

    def acquire_read(self):
        """获取读锁

        写者优先：如果有写者正在等待或活跃，新读者需要等待。
        """
        with self._read_ready:
            while self._writer_active or self._writers_waiting > 0:
                self._read_ready.wait()
            self._readers += 1

    def release_read(self):
        """释放读锁"""
        with self._read_ready:
            self._readers -= 1
            if self._readers == 0:
                self._write_ready.notify_all()

    def acquire_write(self):
        """获取写锁

        写者优先：递增等待计数，阻止新读者获取读锁。
        """
        with self._write_ready:
            self._writers_waiting += 1
            while self._readers > 0 or self._writer_active:
                self._write_ready.wait()
            self._writers_waiting -= 1
            self._writer_active = True

    def release_write(self):
        """释放写锁"""
        with self._write_ready:
            self._writer_active = False
            self._write_ready.notify_all()
            self._read_ready.notify_all()
    
    def read_lock(self):
        """读锁上下文管理器"""
        return _ReadLockContext(self)
    
    def write_lock(self):
        """写锁上下文管理器"""
        return _WriteLockContext(self)


class _ReadLockContext:
    """读锁上下文管理器"""
    
    def __init__(self, lock: ReadWriteLock):
        self.lock = lock
    
    def __enter__(self):
        self.lock.acquire_read()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.lock.release_read()


class _WriteLockContext:
    """写锁上下文管理器"""
    
    def __init__(self, lock: ReadWriteLock):
        self.lock = lock
    
    def __enter__(self):
        self.lock.acquire_write()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.lock.release_write()


class TimeoutLock:
    """支持超时的锁"""
    
    def __init__(self, timeout: float = 10.0):
        self._lock = threading.RLock()
        self.timeout = timeout
    
    def acquire(self, timeout: Optional[float] = None) -> bool:
        """获取锁
        
        Args:
            timeout: 超时时间，None表示使用默认超时
            
        Returns:
            bool: 是否成功获取锁
        """
        timeout = timeout or self.timeout
        return self._lock.acquire(timeout=timeout)
    
    def release(self):
        """释放锁"""
        self._lock.release()
    
    def __enter__(self):
        if not self.acquire():
            raise TimeoutError(f"无法在{self.timeout}秒内获取锁")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


class ThreadSafeSingleton(type):
    """线程安全的单例元类"""
    
    _instances: Dict[Type, Any] = {}
    _lock = threading.RLock()
    
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    instance = super(ThreadSafeSingleton, cls).__call__(*args, **kwargs)
                    cls._instances[cls] = instance
        return cls._instances[cls]
    
    @classmethod
    def clear_instances(cls):
        """清空所有单例实例（主要用于测试）"""
        with cls._lock:
            cls._instances.clear()


def thread_safe(func: Callable[..., T]) -> Callable[..., T]:
    """线程安全装饰器
    
    为函数添加线程安全保护，确保同一时间只有一个线程可以执行该函数。
    
    Args:
        func: 要保护的函数
        
    Returns:
        Callable: 线程安全的函数
    """
    lock = threading.RLock()
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        with lock:
            return func(*args, **kwargs)
    
    return wrapper


def singleton(cls: Type[T]) -> Type[T]:
    """单例装饰器
    
    将类转换为线程安全的单例模式。
    
    Args:
        cls: 要转换的类
        
    Returns:
        Type[T]: 单例类
    """
    instances = {}
    lock = threading.RLock()
    
    def get_instance(*args, **kwargs):
        if cls not in instances:
            with lock:
                if cls not in instances:
                    instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    
    get_instance.__name__ = cls.__name__
    get_instance.__doc__ = cls.__doc__
    get_instance.__module__ = cls.__module__
    
    def clear_instance():
        with lock:
            instances.pop(cls, None)
    
    get_instance.clear_instance = clear_instance
    
    return get_instance


class ThreadSafeCounter:
    """线程安全计数器"""
    
    def __init__(self, initial_value: int = 0):
        self._value = initial_value
        self._lock = threading.RLock()
    
    def increment(self, delta: int = 1) -> int:
        """增加计数
        
        Args:
            delta: 增加的值
            
        Returns:
            int: 增加后的值
        """
        with self._lock:
            self._value += delta
            return self._value
    
    def decrement(self, delta: int = 1) -> int:
        """减少计数
        
        Args:
            delta: 减少的值
            
        Returns:
            int: 减少后的值
        """
        with self._lock:
            self._value -= delta
            return self._value
    
    def get(self) -> int:
        """获取当前值
        
        Returns:
            int: 当前计数值
        """
        with self._lock:
            return self._value
    
    def set(self, value: int) -> int:
        """设置计数值
        
        Args:
            value: 新的计数值
            
        Returns:
            int: 设置后的值
        """
        with self._lock:
            self._value = value
            return self._value
    
    def reset(self) -> int:
        """重置计数为0
        
        Returns:
            int: 重置后的值（总是0）
        """
        return self.set(0)


class ThreadSafeDict:
    """线程安全字典"""
    
    def __init__(self, initial_data: Optional[Dict] = None):
        self._data = initial_data or {}
        self._lock = threading.RLock()
    
    def get(self, key: Any, default: Any = None) -> Any:
        """获取值"""
        with self._lock:
            return self._data.get(key, default)
    
    def set(self, key: Any, value: Any) -> None:
        """设置值"""
        with self._lock:
            self._data[key] = value
    
    def delete(self, key: Any) -> bool:
        """删除键值对
        
        Returns:
            bool: 是否成功删除
        """
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False
    
    def has(self, key: Any) -> bool:
        """检查键是否存在"""
        with self._lock:
            return key in self._data
    
    def keys(self) -> list:
        """获取所有键"""
        with self._lock:
            return list(self._data.keys())
    
    def values(self) -> list:
        """获取所有值"""
        with self._lock:
            return list(self._data.values())
    
    def items(self) -> list:
        """获取所有键值对"""
        with self._lock:
            return list(self._data.items())
    
    def clear(self) -> None:
        """清空字典"""
        with self._lock:
            self._data.clear()
    
    def size(self) -> int:
        """获取字典大小"""
        with self._lock:
            return len(self._data)
    
    def update(self, other: Dict) -> None:
        """更新字典"""
        with self._lock:
            self._data.update(other)
    
    def copy(self) -> Dict:
        """复制字典"""
        with self._lock:
            return self._data.copy()


class ThreadSafeSet:
    """线程安全集合"""
    
    def __init__(self, initial_data: Optional[set] = None):
        self._data = initial_data or set()
        self._lock = threading.RLock()
    
    def add(self, item: Any) -> None:
        """添加元素"""
        with self._lock:
            self._data.add(item)
    
    def remove(self, item: Any) -> bool:
        """移除元素
        
        Returns:
            bool: 是否成功移除
        """
        with self._lock:
            if item in self._data:
                self._data.remove(item)
                return True
            return False
    
    def has(self, item: Any) -> bool:
        """检查元素是否存在"""
        with self._lock:
            return item in self._data
    
    def clear(self) -> None:
        """清空集合"""
        with self._lock:
            self._data.clear()
    
    def size(self) -> int:
        """获取集合大小"""
        with self._lock:
            return len(self._data)
    
    def copy(self) -> set:
        """复制集合"""
        with self._lock:
            return self._data.copy()
    
    def union(self, other: set) -> set:
        """并集"""
        with self._lock:
            return self._data.union(other)
    
    def intersection(self, other: set) -> set:
        """交集"""
        with self._lock:
            return self._data.intersection(other)
    
    def difference(self, other: set) -> set:
        """差集"""
        with self._lock:
            return self._data.difference(other)


class WeakValueDict:
    """弱引用值字典
    
    当值对象被垃圾回收时，自动从字典中移除对应的键值对。
    """
    
    def __init__(self):
        self._data = weakref.WeakValueDictionary()
        self._lock = threading.RLock()
    
    def get(self, key: Any, default: Any = None) -> Any:
        """获取值"""
        with self._lock:
            return self._data.get(key, default)
    
    def set(self, key: Any, value: Any) -> None:
        """设置值"""
        with self._lock:
            self._data[key] = value
    
    def delete(self, key: Any) -> bool:
        """删除键值对"""
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False
    
    def has(self, key: Any) -> bool:
        """检查键是否存在"""
        with self._lock:
            return key in self._data
    
    def keys(self) -> list:
        """获取所有键"""
        with self._lock:
            return list(self._data.keys())
    
    def size(self) -> int:
        """获取字典大小"""
        with self._lock:
            return len(self._data)
    
    def clear(self) -> None:
        """清空字典"""
        with self._lock:
            self._data.clear()