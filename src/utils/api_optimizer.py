#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API调用优化工具

提供多种API调用优化策略，目标延迟<50ms：
1. 批量调用优化
2. 并行调用优化  
3. 智能缓存机制
4. 连接池管理

Author: AI Assistant
Date: 2024-01-22
"""

import asyncio
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import logging

from ..utils.logger_config import get_logger

logger = get_logger(__name__)


@dataclass
class CacheEntry:
    """缓存条目"""
    data: Any
    timestamp: datetime
    ttl_seconds: int
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        return datetime.now() > self.timestamp + timedelta(seconds=self.ttl_seconds)


@dataclass
class APICallResult:
    """API调用结果"""
    success: bool
    data: Any
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    from_cache: bool = False


class APIOptimizer:
    """API调用优化器
    
    提供多种优化策略来降低API调用延迟
    """
    
    def __init__(self, max_workers: int = 4, enable_cache: bool = True):
        """初始化优化器"""
        self.max_workers = max_workers
        self.enable_cache = enable_cache
        self.logger = get_logger(f"{__name__}.APIOptimizer")
        
        # 线程池
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        # 缓存系统
        self._cache: Dict[str, CacheEntry] = {}
        self._cache_lock = threading.RLock()
        
        # 性能统计
        self.stats = {
            'total_calls': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'total_time_ms': 0.0,
            'avg_time_ms': 0.0
        }
        
        self.logger.info(f"API优化器初始化 - 工作线程: {max_workers}, 缓存: {enable_cache}")
    
    def batch_call(self, api_client, method_calls: List[Tuple[str, List, Dict]], 
                  cache_ttl: int = 0) -> Dict[str, APICallResult]:
        """批量API调用优化
        
        Args:
            api_client: API客户端对象
            method_calls: [(method_name, args, kwargs), ...]
            cache_ttl: 缓存TTL (秒)，0表示不缓存
            
        Returns:
            Dict[call_id, APICallResult]
        """
        start_time = time.time()
        results = {}
        
        try:
            # 检查缓存
            cached_results, remaining_calls = self._check_batch_cache(method_calls, cache_ttl)
            results.update(cached_results)
            
            if remaining_calls:
                # 执行剩余的API调用
                fresh_results = self._execute_batch_calls(api_client, remaining_calls)
                results.update(fresh_results)
                
                # 更新缓存
                if cache_ttl > 0:
                    self._update_batch_cache(fresh_results, cache_ttl)
            
            # 更新统计
            total_time = (time.time() - start_time) * 1000
            self._update_stats(len(method_calls), total_time, len(cached_results))
            
            self.logger.debug(f"批量调用完成 - 总数: {len(method_calls)}, "
                            f"缓存命中: {len(cached_results)}, 延迟: {total_time:.2f}ms")
            
            return results
            
        except Exception as e:
            self.logger.error(f"批量调用失败: {e}")
            # 返回失败结果
            for i, (method_name, args, kwargs) in enumerate(method_calls):
                call_id = f"{method_name}_{i}"
                results[call_id] = APICallResult(
                    success=False,
                    data=None,
                    error=str(e),
                    execution_time_ms=(time.time() - start_time) * 1000
                )
            return results
    
    def parallel_call(self, api_calls: List[Callable], cache_ttl: int = 0) -> List[APICallResult]:
        """并行API调用优化
        
        Args:
            api_calls: [callable, ...]
            cache_ttl: 缓存TTL (秒)
            
        Returns:
            List[APICallResult]
        """
        start_time = time.time()
        results = []
        
        try:
            # 提交并行任务
            future_to_index = {}
            for i, api_call in enumerate(api_calls):
                future = self.executor.submit(self._execute_single_call, api_call, cache_ttl)
                future_to_index[future] = i
            
            # 收集结果 (保持顺序)
            results: List[APICallResult] = [APICallResult(success=False, data=None, error="未初始化")] * len(api_calls)
            for future in as_completed(future_to_index.keys()):
                index = future_to_index[future]
                try:
                    results[index] = future.result()
                except Exception as e:
                    results[index] = APICallResult(
                        success=False,
                        data=None,
                        error=str(e),
                        execution_time_ms=0.0
                    )
            
            # 更新统计
            total_time = (time.time() - start_time) * 1000
            cache_hits = sum(1 for r in results if r and r.from_cache)
            self._update_stats(len(api_calls), total_time, cache_hits)
            
            self.logger.debug(f"并行调用完成 - 总数: {len(api_calls)}, "
                            f"缓存命中: {cache_hits}, 延迟: {total_time:.2f}ms")
            
            return results
            
        except Exception as e:
            self.logger.error(f"并行调用失败: {e}")
            return [APICallResult(success=False, data=None, error=str(e)) 
                   for _ in api_calls]
    
    def cached_call(self, cache_key: str, api_call: Callable, 
                   cache_ttl: int = 300) -> APICallResult:
        """带缓存的单个API调用
        
        Args:
            cache_key: 缓存键
            api_call: API调用函数
            cache_ttl: 缓存TTL (秒)
            
        Returns:
            APICallResult
        """
        start_time = time.time()
        
        # 检查缓存
        if self.enable_cache and cache_ttl > 0:
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                execution_time = (time.time() - start_time) * 1000
                self._update_stats(1, execution_time, 1)
                return APICallResult(
                    success=True,
                    data=cached_result,
                    execution_time_ms=execution_time,
                    from_cache=True
                )
        
        # 执行API调用
        try:
            data = api_call()
            execution_time = (time.time() - start_time) * 1000
            
            # 更新缓存
            if self.enable_cache and cache_ttl > 0:
                self._set_cache(cache_key, data, cache_ttl)
            
            # 更新统计
            self._update_stats(1, execution_time, 0)
            
            return APICallResult(
                success=True,
                data=data,
                execution_time_ms=execution_time,
                from_cache=False
            )
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self.logger.error(f"API调用失败 [{cache_key}]: {e}")
            return APICallResult(
                success=False,
                data=None,
                error=str(e),
                execution_time_ms=execution_time,
                from_cache=False
            )
    
    def _check_batch_cache(self, method_calls: List[Tuple[str, List, Dict]], 
                          cache_ttl: int) -> Tuple[Dict[str, APICallResult], List[Tuple[str, str, List, Dict]]]:
        """检查批量调用的缓存"""
        cached_results = {}
        remaining_calls = []
        
        if not self.enable_cache or cache_ttl == 0:
            # 不使用缓存，返回所有调用
            for i, (method_name, args, kwargs) in enumerate(method_calls):
                call_id = f"{method_name}_{i}"
                remaining_calls.append((call_id, method_name, args, kwargs))
            return cached_results, remaining_calls
        
        for i, (method_name, args, kwargs) in enumerate(method_calls):
            call_id = f"{method_name}_{i}"
            cache_key = f"{method_name}_{hash(str(args) + str(kwargs))}"
            
            cached_data = self._get_from_cache(cache_key)
            if cached_data:
                cached_results[call_id] = APICallResult(
                    success=True,
                    data=cached_data,
                    from_cache=True
                )
            else:
                remaining_calls.append((call_id, method_name, args, kwargs))
        
        return cached_results, remaining_calls
    
    def _execute_batch_calls(self, api_client, calls: List[Tuple[str, str, List, Dict]]) -> Dict[str, APICallResult]:
        """执行批量API调用"""
        results = {}
        
        for call_id, method_name, args, kwargs in calls:
            start_time = time.time()
            try:
                method = getattr(api_client, method_name)
                data = method(*args, **kwargs)
                execution_time = (time.time() - start_time) * 1000
                
                results[call_id] = APICallResult(
                    success=True,
                    data=data,
                    execution_time_ms=execution_time,
                    from_cache=False
                )
                
            except Exception as e:
                execution_time = (time.time() - start_time) * 1000
                results[call_id] = APICallResult(
                    success=False,
                    data=None,
                    error=str(e),
                    execution_time_ms=execution_time,
                    from_cache=False
                )
        
        return results
    
    def _execute_single_call(self, api_call: Callable, cache_ttl: int) -> APICallResult:
        """执行单个API调用"""
        start_time = time.time()
        try:
            data = api_call()
            execution_time = (time.time() - start_time) * 1000
            
            return APICallResult(
                success=True,
                data=data,
                execution_time_ms=execution_time,
                from_cache=False
            )
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            return APICallResult(
                success=False,
                data=None,
                error=str(e),
                execution_time_ms=execution_time,
                from_cache=False
            )
    
    def _get_from_cache(self, cache_key: str) -> Optional[Any]:
        """从缓存获取数据"""
        with self._cache_lock:
            entry = self._cache.get(cache_key)
            if entry and not entry.is_expired():
                return entry.data
            elif entry:
                # 清理过期缓存
                del self._cache[cache_key]
            return None
    
    def _set_cache(self, cache_key: str, data: Any, ttl_seconds: int):
        """设置缓存"""
        with self._cache_lock:
            self._cache[cache_key] = CacheEntry(
                data=data,
                timestamp=datetime.now(),
                ttl_seconds=ttl_seconds
            )
    
    def _update_batch_cache(self, results: Dict[str, APICallResult], cache_ttl: int):
        """更新批量调用缓存"""
        if not self.enable_cache or cache_ttl == 0:
            return
        
        for call_id, result in results.items():
            if result.success and not result.from_cache:
                # 根据call_id生成缓存键
                cache_key = f"batch_{call_id}"
                self._set_cache(cache_key, result.data, cache_ttl)
    
    def _update_stats(self, call_count: int, total_time_ms: float, cache_hits: int):
        """更新性能统计"""
        self.stats['total_calls'] += call_count
        self.stats['cache_hits'] += cache_hits
        self.stats['cache_misses'] += (call_count - cache_hits)
        self.stats['total_time_ms'] += total_time_ms
        
        if self.stats['total_calls'] > 0:
            self.stats['avg_time_ms'] = self.stats['total_time_ms'] / self.stats['total_calls']
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        cache_hit_rate = 0.0
        if self.stats['total_calls'] > 0:
            cache_hit_rate = self.stats['cache_hits'] / self.stats['total_calls']
        
        return {
            **self.stats,
            'cache_hit_rate': cache_hit_rate,
            'cache_size': len(self._cache)
        }
    
    def clear_cache(self):
        """清空缓存"""
        with self._cache_lock:
            self._cache.clear()
        self.logger.info("缓存已清空")
    
    def cleanup_expired_cache(self):
        """清理过期缓存"""
        with self._cache_lock:
            expired_keys = [
                key for key, entry in self._cache.items() 
                if entry.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
            
            if expired_keys:
                self.logger.debug(f"清理过期缓存: {len(expired_keys)} 项")
    
    def shutdown(self):
        """关闭优化器"""
        self.executor.shutdown(wait=True)
        self.clear_cache()
        self.logger.info("API优化器已关闭")


# 全局优化器实例
_global_optimizer: Optional[APIOptimizer] = None


def get_api_optimizer(max_workers: int = 4, enable_cache: bool = True) -> APIOptimizer:
    """获取全局API优化器实例"""
    global _global_optimizer
    if _global_optimizer is None:
        _global_optimizer = APIOptimizer(max_workers=max_workers, enable_cache=enable_cache)
    return _global_optimizer


def optimize_tiger_api_calls(quote_client, symbols: List[str], include_vix: bool = True, 
                           include_volume: bool = True, include_status: bool = True,
                           ultra_fast_mode: bool = False) -> Dict[str, Any]:
    """Tiger API调用优化的便捷函数
    
    一次性获取所有需要的市场数据，延迟目标<50ms
    
    Args:
        quote_client: Tiger API客户端
        symbols: 标的符号列表
        include_vix: 是否包含VIX数据
        include_volume: 是否包含成交量数据  
        include_status: 是否包含市场状态
        ultra_fast_mode: 超快模式(只获取核心数据)
        
    Returns:
        {
            'briefs': [...],
            'vix_data': ...,
            'trade_ticks': ...,
            'market_status': ...,
            'execution_time_ms': float,
            'cache_hits': int
        }
    """
    start_time = time.time()
    optimizer = get_api_optimizer()
    
    # 准备批量调用 - 根据模式优化
    calls = []
    
    # 差异化缓存策略 - 根据数据特性设置合理的TTL
    price_cache_ttl = 3 if ultra_fast_mode else 1     # 价格数据：1-3秒（最重要）
    vix_cache_ttl = 30 if ultra_fast_mode else 15     # VIX数据：15-30秒（变化较慢）
    volume_cache_ttl = 5 if ultra_fast_mode else 2    # 成交量：2-5秒（较重要）
    status_cache_ttl = 300                             # 市场状态：5分钟（变化很慢）
    
    if ultra_fast_mode:
        # 超快模式：只获取核心数据，最小化API调用
        # 1. 只获取主要标的 (最多3个)
        core_symbols = symbols[:3] if len(symbols) > 3 else symbols
        if include_vix:
            core_symbols.append('VIX')
        calls.append(('get_briefs', [core_symbols], {}))
        
        # 2. 跳过成交量和市场状态（使用缓存或估算）
    else:
        # 标准模式：获取全部数据
        # 1. 主要标的价格数据 (批量获取)
        all_symbols = symbols.copy()
        if include_vix:
            all_symbols.append('VIX')
        
        calls.append(('get_briefs', [all_symbols], {}))
        
        # 2. 成交量数据 (选择主要标的)
        if include_volume and symbols:
            # 只获取第一个标的的成交量数据以减少延迟
            calls.append(('get_trade_ticks', [symbols[:1]], {}))
        
        # 3. 市场状态 (缓存5分钟)
        if include_status:
            try:
                from tigeropen.common.consts import Market
                calls.append(('get_market_status', [Market.US], {}))
            except ImportError:
                logger.warning("Tiger API未安装，跳过市场状态获取")
    
    # 执行优化调用 - 使用价格数据的缓存策略
    results = optimizer.batch_call(quote_client, calls, cache_ttl=price_cache_ttl)
    
    # 整理结果
    response = {
        'briefs': None,
        'vix_data': None,
        'trade_ticks': None,
        'market_status': None,
        'execution_time_ms': (time.time() - start_time) * 1000,
        'cache_hits': sum(1 for r in results.values() if r.from_cache),
        'total_calls': len(calls)
    }
    
    # 解析结果
    for call_id, result in results.items():
        if result.success:
            if 'get_briefs' in call_id:
                all_briefs = result.data
                if all_briefs:
                    # 分离主要标的和VIX数据
                    response['briefs'] = [b for b in all_briefs if b.symbol in symbols]
                    if include_vix:
                        vix_briefs = [b for b in all_briefs if b.symbol == 'VIX']
                        response['vix_data'] = vix_briefs[0] if vix_briefs else None
            elif 'get_trade_ticks' in call_id:
                response['trade_ticks'] = result.data
            elif 'get_market_status' in call_id:
                response['market_status'] = result.data
    
    logger.debug(f"Tiger API优化调用完成 - 延迟: {response['execution_time_ms']:.2f}ms, "
                f"缓存命中: {response['cache_hits']}/{response['total_calls']}")
    
    return response
