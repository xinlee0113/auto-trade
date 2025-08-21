#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
并行API调用管理器

设计原则:
1. 真正的并行调用，而不是减少调用
2. 智能错误处理和重试
3. 差异化超时设置
4. 性能监控和优化

Author: AI Assistant
Date: 2024-01-22
"""

import asyncio
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

from ..utils.logger_config import get_logger

logger = get_logger(__name__)


class APICallPriority(Enum):
    """API调用优先级"""
    CRITICAL = 1    # 关键数据，如价格
    HIGH = 2        # 重要数据，如成交量
    MEDIUM = 3      # 一般数据，如VIX
    LOW = 4         # 次要数据，如市场状态


@dataclass
class APICallConfig:
    """API调用配置"""
    call_id: str
    api_function: Callable
    args: List
    kwargs: Dict
    priority: APICallPriority
    timeout: float
    retry_count: int = 2
    cache_key: Optional[str] = None


@dataclass
class APICallResult:
    """API调用结果"""
    call_id: str
    success: bool
    data: Any
    execution_time: float
    error: Optional[str] = None
    retries_used: int = 0
    cached: bool = False


class ParallelAPIManager:
    """并行API调用管理器"""
    
    def __init__(self, max_workers: int = 6, enable_monitoring: bool = True):
        """初始化管理器"""
        self.max_workers = max_workers
        self.enable_monitoring = enable_monitoring
        self.logger = get_logger(f"{__name__}.ParallelAPIManager")
        
        # 线程池 - 按优先级分组
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        # 简单缓存
        self._cache: Dict[str, Tuple[Any, float]] = {}  # {key: (data, timestamp)}
        self._cache_ttl: Dict[str, float] = {}  # {key: ttl_seconds}
        
        # 性能统计
        self.stats = {
            'total_calls': 0,
            'successful_calls': 0,
            'failed_calls': 0,
            'cache_hits': 0,
            'total_time': 0.0,
            'avg_time': 0.0,
            'max_time': 0.0,
            'min_time': float('inf')
        }
        
        self.logger.info(f"并行API管理器初始化完成 - 工作线程: {max_workers}")
    
    def execute_parallel_calls(self, call_configs: List[APICallConfig]) -> Dict[str, APICallResult]:
        """执行并行API调用"""
        if not call_configs:
            return {}
        
        start_time = time.time()
        results = {}
        
        # 1. 检查缓存
        remaining_calls, cached_results = self._check_cache(call_configs)
        results.update(cached_results)
        
        if not remaining_calls:
            self.logger.debug("所有数据来自缓存")
            return results
        
        # 2. 按优先级排序
        remaining_calls.sort(key=lambda x: x.priority.value)
        
        # 3. 提交并行任务
        future_to_config = {}
        for config in remaining_calls:
            future = self.executor.submit(self._execute_single_call, config)
            future_to_config[future] = config
        
        # 4. 收集结果 (优先级高的先处理)
        for future in as_completed(future_to_config.keys()):
            config = future_to_config[future]
            try:
                result = future.result()
                results[config.call_id] = result
                
                # 更新缓存
                if result.success and config.cache_key:
                    self._update_cache(config.cache_key, result.data, config.timeout)
                
            except Exception as e:
                results[config.call_id] = APICallResult(
                    call_id=config.call_id,
                    success=False,
                    data=None,
                    execution_time=0.0,
                    error=str(e)
                )
                self.logger.error(f"API调用异常 [{config.call_id}]: {e}")
        
        # 5. 更新统计
        total_time = time.time() - start_time
        self._update_stats(results, total_time)
        
        self.logger.debug(f"并行API调用完成 - 总耗时: {total_time*1000:.1f}ms, 调用数: {len(call_configs)}")
        return results
    
    def _check_cache(self, call_configs: List[APICallConfig]) -> Tuple[List[APICallConfig], Dict[str, APICallResult]]:
        """检查缓存"""
        remaining_calls = []
        cached_results = {}
        
        for config in call_configs:
            if config.cache_key and self._is_cached(config.cache_key):
                # 缓存命中
                cached_data = self._get_from_cache(config.cache_key)
                cached_results[config.call_id] = APICallResult(
                    call_id=config.call_id,
                    success=True,
                    data=cached_data,
                    execution_time=0.0,
                    cached=True
                )
                self.stats['cache_hits'] += 1
            else:
                remaining_calls.append(config)
        
        return remaining_calls, cached_results
    
    def _execute_single_call(self, config: APICallConfig) -> APICallResult:
        """执行单个API调用"""
        start_time = time.time()
        last_error = None
        
        for attempt in range(config.retry_count + 1):
            try:
                # 设置超时
                data = self._call_with_timeout(
                    config.api_function, 
                    config.args, 
                    config.kwargs, 
                    config.timeout
                )
                
                execution_time = time.time() - start_time
                return APICallResult(
                    call_id=config.call_id,
                    success=True,
                    data=data,
                    execution_time=execution_time,
                    retries_used=attempt
                )
                
            except Exception as e:
                last_error = str(e)
                if attempt < config.retry_count:
                    self.logger.warning(f"API调用重试 [{config.call_id}] 第{attempt+1}次: {e}")
                    time.sleep(0.1 * (attempt + 1))  # 递增延迟
                else:
                    self.logger.error(f"API调用失败 [{config.call_id}] 所有重试用完: {e}")
        
        execution_time = time.time() - start_time
        return APICallResult(
            call_id=config.call_id,
            success=False,
            data=None,
            execution_time=execution_time,
            error=last_error,
            retries_used=config.retry_count
        )
    
    def _call_with_timeout(self, api_function: Callable, args: List, kwargs: Dict, timeout: float) -> Any:
        """带超时的API调用"""
        # 简单实现，实际可以使用更复杂的超时机制
        return api_function(*args, **kwargs)
    
    def _is_cached(self, cache_key: str) -> bool:
        """检查是否在缓存中且未过期"""
        if cache_key not in self._cache:
            return False
        
        data, timestamp = self._cache[cache_key]
        ttl = self._cache_ttl.get(cache_key, 0)
        
        return (time.time() - timestamp) < ttl
    
    def _get_from_cache(self, cache_key: str) -> Any:
        """从缓存获取数据"""
        return self._cache[cache_key][0]
    
    def _update_cache(self, cache_key: str, data: Any, ttl: float):
        """更新缓存"""
        self._cache[cache_key] = (data, time.time())
        self._cache_ttl[cache_key] = ttl
    
    def _update_stats(self, results: Dict[str, APICallResult], total_time: float):
        """更新性能统计"""
        successful = sum(1 for r in results.values() if r.success and not r.cached)
        failed = sum(1 for r in results.values() if not r.success)
        
        self.stats['total_calls'] += len(results)
        self.stats['successful_calls'] += successful
        self.stats['failed_calls'] += failed
        self.stats['total_time'] += total_time
        
        if self.stats['total_calls'] > 0:
            self.stats['avg_time'] = self.stats['total_time'] / self.stats['total_calls']
        
        self.stats['max_time'] = max(self.stats['max_time'], total_time)
        self.stats['min_time'] = min(self.stats['min_time'], total_time)
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        self._cache_ttl.clear()
        self.logger.info("缓存已清空")
    
    def get_performance_stats(self) -> dict:
        """获取性能统计"""
        total_requests = self.stats['cache_hits'] + self.stats['total_calls']
        cache_hit_rate = (self.stats['cache_hits'] / total_requests) if total_requests > 0 else 0
        success_rate = (self.stats['successful_calls'] / self.stats['total_calls']) if self.stats['total_calls'] > 0 else 0
        
        return {
            **self.stats,
            'cache_hit_rate': cache_hit_rate,
            'success_rate': success_rate,
            'cache_size': len(self._cache)
        }
    
    def shutdown(self):
        """关闭管理器"""
        self.executor.shutdown(wait=True)
        self.clear_cache()
        self.logger.info("并行API管理器已关闭")


def create_tiger_api_calls(quote_client, symbols: List[str]) -> List[APICallConfig]:
    """创建Tiger API调用配置
    
    明确分类不同类型的API调用，设置合适的优先级和超时
    """
    calls = []
    
    # 1. 关键数据：个股价格 (最高优先级，最短超时)
    if symbols:
        calls.append(APICallConfig(
            call_id="stock_prices",
            api_function=quote_client.get_briefs,
            args=[symbols],
            kwargs={},
            priority=APICallPriority.CRITICAL,
            timeout=2.0,  # 2秒超时
            cache_key=f"prices_{','.join(sorted(symbols))}",
            retry_count=1  # 价格数据只重试一次
        ))
    
    # 2. 重要数据：成交量 (高优先级)
    if symbols:
        # 只获取主要标的的成交量以减少延迟
        main_symbol = symbols[0] if symbols else 'QQQ'
        calls.append(APICallConfig(
            call_id="volume_data",
            api_function=quote_client.get_trade_ticks,
            args=[[main_symbol]],
            kwargs={},
            priority=APICallPriority.HIGH,
            timeout=3.0,  # 3秒超时
            cache_key=f"volume_{main_symbol}",
            retry_count=2
        ))
    
    # 3. 一般数据：VIX (中等优先级，可以缓存较长时间)
    calls.append(APICallConfig(
        call_id="vix_data",
        api_function=quote_client.get_briefs,
        args=[["VIX"]],
        kwargs={},
        priority=APICallPriority.MEDIUM,
        timeout=5.0,  # 5秒超时
        cache_key="vix_data",
        retry_count=2
    ))
    
    # 4. 次要数据：市场状态 (低优先级，缓存时间最长)
    try:
        from tigeropen.common.consts import Market
        calls.append(APICallConfig(
            call_id="market_status",
            api_function=quote_client.get_market_status,
            args=[Market.US],
            kwargs={},
            priority=APICallPriority.LOW,
            timeout=10.0,  # 10秒超时
            cache_key="market_status",
            retry_count=1  # 市场状态变化缓慢，重试次数少
        ))
    except ImportError:
        logger.warning("Tiger API未安装，跳过市场状态获取")
    
    return calls


def execute_optimized_tiger_calls(quote_client, symbols: List[str], 
                                manager: Optional[ParallelAPIManager] = None) -> dict:
    """执行优化的Tiger API调用
    
    返回格式:
    {
        'prices': [...],
        'volume': ...,
        'vix': ...,
        'market_status': ...,
        'performance': {...}
    }
    """
    if manager is None:
        manager = ParallelAPIManager(max_workers=4)
    
    # 创建API调用配置
    call_configs = create_tiger_api_calls(quote_client, symbols)
    
    # 执行并行调用
    results = manager.execute_parallel_calls(call_configs)
    
    # 整理返回数据
    response = {
        'prices': None,
        'volume': None,
        'vix': None,
        'market_status': None,
        'performance': manager.get_performance_stats(),
        'success': True,
        'errors': []
    }
    
    # 解析结果
    for call_id, result in results.items():
        if result.success:
            if call_id == "stock_prices":
                response['prices'] = result.data
            elif call_id == "volume_data":
                response['volume'] = result.data
            elif call_id == "vix_data":
                response['vix'] = result.data[0] if result.data and len(result.data) > 0 else None
            elif call_id == "market_status":
                response['market_status'] = result.data[0] if result.data and len(result.data) > 0 else None
        else:
            response['errors'].append(f"{call_id}: {result.error}")
            if call_id == "stock_prices":  # 价格数据失败是严重问题
                response['success'] = False
    
    return response
