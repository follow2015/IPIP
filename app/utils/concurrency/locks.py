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

    def __init__(self):
        self._lock = threading.RLock()
        self._readers = 0
        self._writers_waiting = 0
        self._writer_active = False
        self._read_ready = threading.Condition(self._lock)
        self._write_ready = threading.Condition(self._lock)

    def acquire_read(self):
        with self._read_ready:
            while self._writer_active or self._writers_waiting > 0:
                self._read_ready.wait()
            self._readers += 1

    def release_read(self):
        with self._read_ready:
            self._readers -= 1
            if self._readers == 0:
                self._write_ready.notify_all()

    def acquire_write(self):
        with self._write_ready:
            self._writers_waiting += 1
            while self._readers > 0 or self._writer_active:
                self._write_ready.wait()
            self._writers_waiting -= 1
            self._writer_active = True

    def release_write(self):
        with self._write_ready:
            self._writer_active = False
            self._write_ready.notify_all()
            self._read_ready.notify_all()
    
    def read_lock(self):
        return _ReadLockContext(self)
    
    def write_lock(self):
        return _WriteLockContext(self)


class _ReadLockContext:
    
    def __init__(self, lock: ReadWriteLock):
        self.lock = lock
    
    def __enter__(self):
        self.lock.acquire_read()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.lock.release_read()


class _WriteLockContext:
    
    def __init__(self, lock: ReadWriteLock):
        self.lock = lock
    
    def __enter__(self):
        self.lock.acquire_write()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.lock.release_write()


class TimeoutLock:
    
    def __init__(self, timeout: float = 10.0):
        self._lock = threading.RLock()
        self.timeout = timeout
    
    def acquire(self, timeout: Optional[float] = None) -> bool:
        timeout = timeout or self.timeout
        return self._lock.acquire(timeout=timeout)
    
    def release(self):
        self._lock.release()
    
    def __enter__(self):
        if not self.acquire():
            raise TimeoutError(f"无法在{self.timeout}秒内获取锁")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


class ThreadSafeSingleton(type):
    
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
        with cls._lock:
            cls._instances.clear()


def thread_safe(func: Callable[..., T]) -> Callable[..., T]:
    lock = threading.RLock()
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        with lock:
            return func(*args, **kwargs)
    
    return wrapper


def singleton(cls: Type[T]) -> Type[T]:
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
    
    def __init__(self, initial_value: int = 0):
        self._value = initial_value
        self._lock = threading.RLock()
    
    def increment(self, delta: int = 1) -> int:
        with self._lock:
            self._value += delta
            return self._value
    
    def decrement(self, delta: int = 1) -> int:
        with self._lock:
            self._value -= delta
            return self._value
    
    def get(self) -> int:
        with self._lock:
            return self._value
    
    def set(self, value: int) -> int:
        with self._lock:
            self._value = value
            return self._value
    
    def reset(self) -> int:
        return self.set(0)


class ThreadSafeDict:
    
    def __init__(self, initial_data: Optional[Dict] = None):
        self._data = initial_data or {}
        self._lock = threading.RLock()
    
    def get(self, key: Any, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)
    
    def set(self, key: Any, value: Any) -> None:
        with self._lock:
            self._data[key] = value
    
    def delete(self, key: Any) -> bool:
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False
    
    def has(self, key: Any) -> bool:
        with self._lock:
            return key in self._data
    
    def keys(self) -> list:
        with self._lock:
            return list(self._data.keys())
    
    def values(self) -> list:
        with self._lock:
            return list(self._data.values())
    
    def items(self) -> list:
        with self._lock:
            return list(self._data.items())
    
    def clear(self) -> None:
        with self._lock:
            self._data.clear()
    
    def size(self) -> int:
        with self._lock:
            return len(self._data)
    
    def update(self, other: Dict) -> None:
        with self._lock:
            self._data.update(other)
    
    def copy(self) -> Dict:
        with self._lock:
            return self._data.copy()


class ThreadSafeSet:
    
    def __init__(self, initial_data: Optional[set] = None):
        self._data = initial_data or set()
        self._lock = threading.RLock()
    
    def add(self, item: Any) -> None:
        with self._lock:
            self._data.add(item)
    
    def remove(self, item: Any) -> bool:
        with self._lock:
            if item in self._data:
                self._data.remove(item)
                return True
            return False
    
    def has(self, item: Any) -> bool:
        with self._lock:
            return item in self._data
    
    def clear(self) -> None:
        with self._lock:
            self._data.clear()
    
    def size(self) -> int:
        with self._lock:
            return len(self._data)
    
    def copy(self) -> set:
        with self._lock:
            return self._data.copy()
    
    def union(self, other: set) -> set:
        with self._lock:
            return self._data.union(other)
    
    def intersection(self, other: set) -> set:
        with self._lock:
            return self._data.intersection(other)
    
    def difference(self, other: set) -> set:
        with self._lock:
            return self._data.difference(other)


class WeakValueDict:
    
    def __init__(self):
        self._data = weakref.WeakValueDictionary()
        self._lock = threading.RLock()
    
    def get(self, key: Any, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)
    
    def set(self, key: Any, value: Any) -> None:
        with self._lock:
            self._data[key] = value
    
    def delete(self, key: Any) -> bool:
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False
    
    def has(self, key: Any) -> bool:
        with self._lock:
            return key in self._data
    
    def keys(self) -> list:
        with self._lock:
            return list(self._data.keys())
    
    def size(self) -> int:
        with self._lock:
            return len(self._data)
    
    def clear(self) -> None:
        with self._lock:
            self._data.clear()
