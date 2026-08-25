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

LOCK_ACQUIRE_TIMEOUT = 1

T = TypeVar('T')


class ConcurrencyManager:
    
    def __init__(self):
        self._active_threads = {}
        self._thread_stats = {}
        self._lock = threading.RLock()
        self._shutdown_event = threading.Event()
    
    def register_thread(self, thread_id: str, thread_name: str = None) -> None:
        with self._lock:
            self._active_threads[thread_id] = {
                'name': thread_name or thread_id,
                'start_time': time.time(),
                'status': 'running'
            }
            logger.debug(f"注册线程: {thread_id}")
    
    def unregister_thread(self, thread_id: str) -> None:
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
        with self._lock:
            return self._active_threads.copy()
    
    def get_thread_stats(self) -> Dict[str, Dict]:
        with self._lock:
            return self._thread_stats.copy()
    
    def shutdown(self, timeout: float = 30.0) -> bool:
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
        return self._shutdown_event.is_set()


class ResourcePool(Generic[T]):
    
    def __init__(self, 
                 factory: Callable[[], T],
                 max_size: int = 10,
                 timeout: float = 30.0,
                 validator: Optional[Callable[[T], bool]] = None):
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
        resource = self.get_resource()
        try:
            yield resource
        finally:
            self.return_resource(resource)
    
    def get_resource(self) -> T:
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
        with self._lock:
            resource = self.factory()
            self._created_count += 1
            self._stats['created'] += 1
            logger.debug(f"创建新资源，当前总数: {self._created_count}")
            return resource
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **self._stats,
                'pool_size': self._pool.qsize(),
                'created_count': self._created_count,
                'max_size': self.max_size
            }
    
    def clear(self) -> None:
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
    
    def __init__(self):
        self._storage = threading.local()
        self._keys = set()
        self._lock = threading.RLock()
    
    def set(self, key: str, value: Any) -> None:
        if not hasattr(self._storage, 'data'):
            self._storage.data = {}
        
        self._storage.data[key] = value
        
        with self._lock:
            self._keys.add(key)
    
    def get(self, key: str, default: Any = None) -> Any:
        if not hasattr(self._storage, 'data'):
            return default
        
        return self._storage.data.get(key, default)
    
    def delete(self, key: str) -> bool:
        if not hasattr(self._storage, 'data'):
            return False
        
        if key in self._storage.data:
            del self._storage.data[key]
            return True
        
        return False
    
    def has(self, key: str) -> bool:
        if not hasattr(self._storage, 'data'):
            return False
        
        return key in self._storage.data
    
    def clear(self) -> None:
        if hasattr(self._storage, 'data'):
            self._storage.data.clear()
    
    def get_all_keys(self) -> List[str]:
        with self._lock:
            return list(self._keys)
    
    def get_current_data(self) -> Dict[str, Any]:
        if not hasattr(self._storage, 'data'):
            return {}
        
        return self._storage.data.copy()


class WorkerPool:
    
    def __init__(self, 
                 worker_count: int = 4,
                 queue_size: int = 100,
                 timeout: float = 30.0):
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
        task_id = f"task_{int(time.time() * 1000000)}"
        
        self._task_queue.put((task_id, func, args, kwargs), timeout=self.timeout)
        
        with self._lock:
            self._stats['submitted'] += 1
        
        logger.debug(f"提交任务: {task_id}")
        return task_id
    
    def get_result(self, timeout: Optional[float] = None) -> tuple:
        return self._result_queue.get(timeout=timeout)
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **self._stats,
                'worker_count': self.worker_count,
                'task_queue_size': self._task_queue.qsize(),
                'result_queue_size': self._result_queue.qsize(),
                'active_workers': sum(1 for w in self._workers if w.is_alive())
            }
    
    def shutdown(self, timeout: float = 30.0) -> bool:
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
