# -*- coding: utf-8 -*-
"""
并发管理器

提供资源池、线程本地存储等并发管理工具。
"""
import threading
import time
import queue
from typing import Any, Callable, Dict, List, Optional, TypeVar, Generic
from contextlib import contextmanager
from app.utils.logging import get_logger

logger = get_logger(__name__)

LOCK_ACQUIRE_TIMEOUT = 1  # 工作线程队列获取超时时间（秒）

T = TypeVar('T')


class ConcurrencyManager:
    """并发管理器
    
    提供系统级的并发控制和监控功能。
    """
    
    def __init__(self):
        self._active_threads = {}
        self._thread_stats = {}
        self._lock = threading.RLock()
        self._shutdown_event = threading.Event()
    
    def register_thread(self, thread_id: str, thread_name: str = None) -> None:
        """注册线程
        
        Args:
            thread_id: 线程ID
            thread_name: 线程名称
        """
        with self._lock:
            self._active_threads[thread_id] = {
                'name': thread_name or thread_id,
                'start_time': time.time(),
                'status': 'running'
            }
            logger.debug(f"注册线程: {thread_id}")
    
    def unregister_thread(self, thread_id: str) -> None:
        """注销线程
        
        Args:
            thread_id: 线程ID
        """
        with self._lock:
            if thread_id in self._active_threads:
                thread_info = self._active_threads.pop(thread_id)
                duration = time.time() - thread_info['start_time']
                
                if thread_id not in self._thread_stats:
                    self._thread_stats[thread_id] = {
                        'total_runs': 0,
                        'total_duration': 0,
                        'avg_duration': 0
                    }
                
                stats = self._thread_stats[thread_id]
                stats['total_runs'] += 1
                stats['total_duration'] += duration
                stats['avg_duration'] = stats['total_duration'] / stats['total_runs']
                
                logger.debug(f"注销线程: {thread_id}, 运行时长: {duration:.2f}秒")
    
    def get_active_threads(self) -> Dict[str, Dict]:
        """获取活跃线程信息
        
        Returns:
            Dict: 活跃线程信息
        """
        with self._lock:
            return self._active_threads.copy()
    
    def get_thread_stats(self) -> Dict[str, Dict]:
        """获取线程统计信息
        
        Returns:
            Dict: 线程统计信息
        """
        with self._lock:
            return self._thread_stats.copy()
    
    def shutdown(self, timeout: float = 30.0) -> bool:
        """关闭并发管理器
        
        Args:
            timeout: 等待超时时间
            
        Returns:
            bool: 是否成功关闭
        """
        logger.info("开始关闭并发管理器")
        self._shutdown_event.set()
        
        start_time = time.time()
        while self._active_threads and (time.time() - start_time) < timeout:
            time.sleep(0.1)
        
        success = len(self._active_threads) == 0
        if success:
            logger.info("并发管理器已成功关闭")
        else:
            logger.warning(f"并发管理器关闭超时，仍有{len(self._active_threads)}个活跃线程")
        
        return success
    
    def is_shutdown(self) -> bool:
        """检查是否已关闭
        
        Returns:
            bool: 是否已关闭
        """
        return self._shutdown_event.is_set()


class ResourcePool(Generic[T]):
    """资源池
    
    管理有限的资源，支持资源的获取、释放和回收。
    """
    
    def __init__(self, 
                 factory: Callable[[], T],
                 max_size: int = 10,
                 timeout: float = 30.0,
                 validator: Optional[Callable[[T], bool]] = None):
        """初始化资源池
        
        Args:
            factory: 资源创建工厂函数
            max_size: 最大资源数量
            timeout: 获取资源超时时间
            validator: 资源验证函数
        """
        self.factory = factory
        self.max_size = max_size
        self.timeout = timeout
        self.validator = validator
        
        self._pool = queue.Queue(maxsize=max_size)
        self._created_count = 0
        self._lock = threading.RLock()
        self._stats = {
            'created': 0,
            'acquired': 0,
            'released': 0,
            'validated': 0,
            'discarded': 0
        }
    
    @contextmanager
    def acquire(self):
        """获取资源上下文管理器
        
        Yields:
            T: 资源对象
        """
        resource = self.get_resource()
        try:
            yield resource
        finally:
            self.return_resource(resource)
    
    def get_resource(self) -> T:
        """获取资源
        
        Returns:
            T: 资源对象
            
        Raises:
            TimeoutError: 获取资源超时
        """
        try:
            resource = self._pool.get(timeout=self.timeout)
            
            if self.validator and not self.validator(resource):
                self._stats['discarded'] += 1
                logger.debug("资源验证失败，重新创建")
                resource = self._create_resource()
            
            self._stats['acquired'] += 1
            return resource
            
        except queue.Empty:
            with self._lock:
                if self._created_count < self.max_size:
                    resource = self._create_resource()
                    self._stats['acquired'] += 1
                    return resource
            
            raise TimeoutError(f"无法在{self.timeout}秒内获取资源")
    
    def return_resource(self, resource: T) -> None:
        """归还资源
        
        Args:
            resource: 要归还的资源
        """
        if resource is None:
            return
        
        try:
            if self.validator and not self.validator(resource):
                self._stats['discarded'] += 1
                with self._lock:
                    self._created_count -= 1
                logger.debug("归还的资源无效，已丢弃")
                return
            
            self._pool.put_nowait(resource)
            self._stats['released'] += 1
            
        except queue.Full:
            self._stats['discarded'] += 1
            with self._lock:
                self._created_count -= 1
            logger.debug("资源池已满，丢弃资源")
    
    def _create_resource(self) -> T:
        """创建新资源
        
        Returns:
            T: 新创建的资源
        """
        with self._lock:
            resource = self.factory()
            self._created_count += 1
            self._stats['created'] += 1
            logger.debug(f"创建新资源，当前总数: {self._created_count}")
            return resource
    
    def get_stats(self) -> Dict[str, Any]:
        """获取资源池统计信息
        
        Returns:
            Dict: 统计信息
        """
        with self._lock:
            return {
                **self._stats,
                'pool_size': self._pool.qsize(),
                'created_count': self._created_count,
                'max_size': self.max_size
            }
    
    def clear(self) -> None:
        """清空资源池"""
        with self._lock:
            while not self._pool.empty():
                try:
                    self._pool.get_nowait()
                except queue.Empty:
                    break
            
            self._created_count = 0
            self._stats = {key: 0 for key in self._stats}
            logger.info("资源池已清空")


class ThreadLocalStorage:
    """线程本地存储
    
    为每个线程提供独立的存储空间。
    """
    
    def __init__(self):
        self._storage = threading.local()
        self._keys = set()
        self._lock = threading.RLock()
    
    def set(self, key: str, value: Any) -> None:
        """设置线程本地值
        
        Args:
            key: 键
            value: 值
        """
        if not hasattr(self._storage, 'data'):
            self._storage.data = {}
        
        self._storage.data[key] = value
        
        with self._lock:
            self._keys.add(key)
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取线程本地值
        
        Args:
            key: 键
            default: 默认值
            
        Returns:
            Any: 值
        """
        if not hasattr(self._storage, 'data'):
            return default
        
        return self._storage.data.get(key, default)
    
    def delete(self, key: str) -> bool:
        """删除线程本地值
        
        Args:
            key: 键
            
        Returns:
            bool: 是否成功删除
        """
        if not hasattr(self._storage, 'data'):
            return False
        
        if key in self._storage.data:
            del self._storage.data[key]
            return True
        
        return False
    
    def has(self, key: str) -> bool:
        """检查键是否存在
        
        Args:
            key: 键
            
        Returns:
            bool: 是否存在
        """
        if not hasattr(self._storage, 'data'):
            return False
        
        return key in self._storage.data
    
    def clear(self) -> None:
        """清空当前线程的存储"""
        if hasattr(self._storage, 'data'):
            self._storage.data.clear()
    
    def get_all_keys(self) -> List[str]:
        """获取所有键
        
        Returns:
            List[str]: 所有键的列表
        """
        with self._lock:
            return list(self._keys)
    
    def get_current_data(self) -> Dict[str, Any]:
        """获取当前线程的所有数据
        
        Returns:
            Dict: 当前线程的数据
        """
        if not hasattr(self._storage, 'data'):
            return {}
        
        return self._storage.data.copy()


class WorkerPool:
    """工作线程池
    
    管理一组工作线程，支持任务分发和结果收集。
    """
    
    def __init__(self, 
                 worker_count: int = 4,
                 queue_size: int = 100,
                 timeout: float = 30.0):
        """初始化工作线程池
        
        Args:
            worker_count: 工作线程数量
            queue_size: 任务队列大小
            timeout: 任务执行超时时间
        """
        self.worker_count = worker_count
        self.timeout = timeout
        
        self._task_queue = queue.Queue(maxsize=queue_size)
        self._result_queue = queue.Queue()
        self._workers = []
        self._shutdown_event = threading.Event()
        self._stats = {
            'submitted': 0,
            'completed': 0,
            'failed': 0,
            'timeout': 0
        }
        self._lock = threading.RLock()
        
        self._start_workers()
    
    def _start_workers(self) -> None:
        """启动工作线程"""
        for i in range(self.worker_count):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"Worker-{i}",
                daemon=True
            )
            worker.start()
            self._workers.append(worker)
        
        logger.info(f"启动了{self.worker_count}个工作线程")
    
    def _worker_loop(self) -> None:
        """工作线程主循环"""
        thread_name = threading.current_thread().name
        logger.debug(f"工作线程 {thread_name} 开始运行")
        
        while not self._shutdown_event.is_set():
            try:
                task_id, func, args, kwargs = self._task_queue.get(timeout=LOCK_ACQUIRE_TIMEOUT)
                
                try:
                    start_time = time.time()
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time
                    
                    self._result_queue.put((task_id, 'success', result, duration))
                    
                    with self._lock:
                        self._stats['completed'] += 1
                    
                except Exception as e:
                    self._result_queue.put((task_id, 'error', str(e), 0))
                    
                    with self._lock:
                        self._stats['failed'] += 1
                    
                    logger.error(f"任务 {task_id} 执行失败: {e}")
                
                finally:
                    self._task_queue.task_done()
            
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"工作线程 {thread_name} 发生错误: {e}")
        
        logger.debug(f"工作线程 {thread_name} 已停止")
    
    def submit(self, func: Callable, *args, **kwargs) -> str:
        """提交任务
        
        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            str: 任务ID
            
        Raises:
            queue.Full: 任务队列已满
        """
        task_id = f"task_{int(time.time() * 1000000)}"
        
        self._task_queue.put((task_id, func, args, kwargs), timeout=self.timeout)
        
        with self._lock:
            self._stats['submitted'] += 1
        
        logger.debug(f"提交任务: {task_id}")
        return task_id
    
    def get_result(self, timeout: Optional[float] = None) -> tuple:
        """获取任务结果
        
        Args:
            timeout: 超时时间
            
        Returns:
            tuple: (task_id, status, result, duration)
            
        Raises:
            queue.Empty: 没有可用结果
        """
        return self._result_queue.get(timeout=timeout)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息
        
        Returns:
            Dict: 统计信息
        """
        with self._lock:
            return {
                **self._stats,
                'worker_count': self.worker_count,
                'task_queue_size': self._task_queue.qsize(),
                'result_queue_size': self._result_queue.qsize(),
                'active_workers': sum(1 for w in self._workers if w.is_alive())
            }
    
    def shutdown(self, timeout: float = 30.0) -> bool:
        """关闭工作线程池
        
        Args:
            timeout: 等待超时时间
            
        Returns:
            bool: 是否成功关闭
        """
        logger.info("开始关闭工作线程池")
        
        self._shutdown_event.set()
        
        self._task_queue.join()
        
        start_time = time.time()
        for worker in self._workers:
            remaining_time = timeout - (time.time() - start_time)
            if remaining_time > 0:
                worker.join(timeout=remaining_time)
        
        active_workers = sum(1 for w in self._workers if w.is_alive())
        success = active_workers == 0
        
        if success:
            logger.info("工作线程池已成功关闭")
        else:
            logger.warning(f"工作线程池关闭超时，仍有{active_workers}个活跃线程")
        
        return success


concurrency_manager = ConcurrencyManager()