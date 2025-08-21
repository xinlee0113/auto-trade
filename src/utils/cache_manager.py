#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
缓存管理器
"""

import threading
import time
from typing import Any, Dict, Optional, Callable, Tuple
from datetime import datetime, timedelta
import hashlib
import json
import logging

logger = logging.getLogger(__name__)


class CacheEntry:
    """缓存条目"""
    
    def __init__(self, value: Any, ttl: int = 300):
        """
        初始化缓存条目
        
        Args:
            value: 缓存值
            ttl: 生存时间（秒）
        """
        self.value = value
        self.created_at = datetime.now()
        self.expires_at = self.created_at + timedelta(seconds=ttl)
        self.access_count = 0
        self.last_accessed = self.created_at
    
    def is_expired(self) -> bool:
        """检查是否已过期"""
        return datetime.now() > self.expires_at
    
    def access(self) -> Any:
        """访问缓存值"""
        self.access_count += 1
        self.last_accessed = datetime.now()
        return self.value
    
    def get_age(self) -> float:
        """获取缓存年龄（秒）"""
        return (datetime.now() - self.created_at).total_seconds()


class SimpleCache:
    """简单内存缓存"""
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        """
        初始化缓存
        
        Args:
            max_size: 最大缓存大小
            default_ttl: 默认生存时间（秒）
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
    
    def _generate_key(self, key_parts: Tuple[Any, ...]) -> str:
        """生成缓存键"""
        key_str = json.dumps(key_parts, sort_keys=True, default=str)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if entry.is_expired():
                    del self._cache[key]
                    self._misses += 1
                    return None
                else:
                    self._hits += 1
                    return entry.access()
            else:
                self._misses += 1
                return None
    
    def put(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置缓存值"""
        with self._lock:
            if ttl is None:
                ttl = self.default_ttl
            
            # 如果缓存已满，清理过期项或删除最老的项
            if len(self._cache) >= self.max_size:
                self._evict()
            
            self._cache[key] = CacheEntry(value, ttl)
    
    def _evict(self) -> None:
        """清理缓存"""
        # 首先删除已过期的项
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired()
        ]
        
        for key in expired_keys:
            del self._cache[key]
        
        # 如果还是满的，删除最老的项
        if len(self._cache) >= self.max_size:
            oldest_key = min(
                self._cache.keys(),
                key=lambda k: self._cache[k].created_at
            )
            del self._cache[oldest_key]
    
    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else 0
            
            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': hit_rate,
                'total_requests': total_requests
            }


class CacheManager:
    """缓存管理器"""
    
    def __init__(self):
        self._caches: Dict[str, SimpleCache] = {}
        self._lock = threading.RLock()
    
    def get_cache(self, name: str, max_size: int = 1000, default_ttl: int = 300) -> SimpleCache:
        """获取命名缓存"""
        with self._lock:
            if name not in self._caches:
                self._caches[name] = SimpleCache(max_size, default_ttl)
            return self._caches[name]
    
    def clear_all(self) -> None:
        """清空所有缓存"""
        with self._lock:
            for cache in self._caches.values():
                cache.clear()
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有缓存统计"""
        with self._lock:
            return {
                name: cache.get_stats()
                for name, cache in self._caches.items()
            }


# 全局缓存管理器实例
cache_manager = CacheManager()


def cache_result(
    cache_name: str = "default",
    ttl: int = 300,
    key_func: Optional[Callable] = None
):
    """
    缓存函数结果装饰器
    
    Args:
        cache_name: 缓存名称
        ttl: 缓存生存时间
        key_func: 自定义键生成函数
    """
    def decorator(func: Callable) -> Callable:
        cache = cache_manager.get_cache(cache_name, default_ttl=ttl)
        
        def wrapper(*args, **kwargs):
            # 生成缓存键
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = cache._generate_key((func.__name__, args, tuple(sorted(kwargs.items()))))
            
            # 尝试从缓存获取结果
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"缓存命中: {func.__name__}")
                return cached_result
            
            # 执行函数并缓存结果
            logger.debug(f"缓存未命中，执行函数: {func.__name__}")
            result = func(*args, **kwargs)
            
            # 只缓存成功的结果（非None且不包含错误）
            if result is not None:
                if isinstance(result, dict) and 'error' not in result:
                    cache.put(cache_key, result, ttl)
                elif not isinstance(result, dict):
                    cache.put(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self):
        self._metrics: Dict[str, list] = {}
        self._lock = threading.RLock()
    
    def record_execution_time(self, func_name: str, execution_time: float):
        """记录执行时间"""
        with self._lock:
            if func_name not in self._metrics:
                self._metrics[func_name] = []
            
            self._metrics[func_name].append({
                'execution_time': execution_time,
                'timestamp': datetime.now().isoformat()
            })
            
            # 保留最近1000次记录
            if len(self._metrics[func_name]) > 1000:
                self._metrics[func_name] = self._metrics[func_name][-1000:]
    
    def get_stats(self, func_name: str) -> Optional[Dict[str, Any]]:
        """获取函数性能统计"""
        with self._lock:
            if func_name not in self._metrics:
                return None
            
            times = [record['execution_time'] for record in self._metrics[func_name]]
            
            if not times:
                return None
            
            return {
                'count': len(times),
                'avg_time': sum(times) / len(times),
                'min_time': min(times),
                'max_time': max(times),
                'total_time': sum(times)
            }
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有函数性能统计"""
        with self._lock:
            return {
                func_name: self.get_stats(func_name)
                for func_name in self._metrics.keys()
            }


# 全局性能监控器实例
performance_monitor = PerformanceMonitor()


def monitor_performance(func: Callable) -> Callable:
    """性能监控装饰器"""
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            execution_time = time.time() - start_time
            performance_monitor.record_execution_time(func.__name__, execution_time)
            
            if execution_time > 1.0:  # 记录超过1秒的慢查询
                logger.warning(f"慢查询检测: {func.__name__} 耗时 {execution_time:.2f}秒")
    
    return wrapper
