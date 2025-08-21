"""
API调用频率限制器
确保Tiger API调用不超过限制，防止账号冻结
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List
from collections import deque
from dataclasses import dataclass

from .logger_config import get_logger

logger = get_logger(__name__)


@dataclass
class APICallRecord:
    """API调用记录"""
    timestamp: datetime
    api_name: str
    success: bool
    

class APIRateLimiter:
    """API调用频率限制器"""
    
    def __init__(self):
        # Tiger API限制 (保守估计)
        self.limits = {
            'quote_api': {'per_second': 8, 'per_minute': 500},  # 行情API
            'trade_api': {'per_second': 2, 'per_minute': 100},  # 交易API
            'account_api': {'per_second': 1, 'per_minute': 50}  # 账户API
        }
        
        # 调用历史记录
        self.call_history: Dict[str, deque] = {
            api_type: deque(maxlen=1000) for api_type in self.limits.keys()
        }
        
        # 线程锁
        self.lock = threading.Lock()
        
        logger.info("API频率限制器初始化完成")
    
    def can_call_api(self, api_type: str) -> bool:
        """检查是否可以调用API"""
        with self.lock:
            if api_type not in self.limits:
                return True
            
            now = datetime.now()
            history = self.call_history[api_type]
            
            # 检查每秒限制
            second_ago = now - timedelta(seconds=1)
            recent_calls = sum(1 for record in history if record.timestamp > second_ago)
            
            if recent_calls >= self.limits[api_type]['per_second']:
                logger.warning(f"API {api_type} 达到每秒限制: {recent_calls}/{self.limits[api_type]['per_second']}")
                return False
            
            # 检查每分钟限制
            minute_ago = now - timedelta(minutes=1)
            minute_calls = sum(1 for record in history if record.timestamp > minute_ago)
            
            if minute_calls >= self.limits[api_type]['per_minute']:
                logger.warning(f"API {api_type} 达到每分钟限制: {minute_calls}/{self.limits[api_type]['per_minute']}")
                return False
            
            return True
    
    def record_api_call(self, api_type: str, api_name: str, success: bool = True):
        """记录API调用"""
        with self.lock:
            if api_type in self.call_history:
                record = APICallRecord(
                    timestamp=datetime.now(),
                    api_name=api_name,
                    success=success
                )
                self.call_history[api_type].append(record)
                
                logger.debug(f"记录API调用: {api_type}.{api_name} - {'成功' if success else '失败'}")
    
    def wait_if_needed(self, api_type: str) -> float:
        """如果需要等待，返回等待时间（秒）"""
        if self.can_call_api(api_type):
            return 0.0
        
        with self.lock:
            now = datetime.now()
            history = self.call_history[api_type]
            
            # 计算需要等待的时间
            wait_time = 0.0
            
            # 检查每秒限制
            second_ago = now - timedelta(seconds=1)
            recent_calls = [r for r in history if r.timestamp > second_ago]
            
            if len(recent_calls) >= self.limits[api_type]['per_second']:
                # 找到最早的调用，计算等待时间
                oldest_call = min(recent_calls, key=lambda x: x.timestamp)
                wait_time = max(wait_time, 1.1 - (now - oldest_call.timestamp).total_seconds())
            
            # 检查每分钟限制
            minute_ago = now - timedelta(minutes=1)
            minute_calls = [r for r in history if r.timestamp > minute_ago]
            
            if len(minute_calls) >= self.limits[api_type]['per_minute']:
                # 找到最早的调用，计算等待时间
                oldest_call = min(minute_calls, key=lambda x: x.timestamp)
                wait_time = max(wait_time, 61 - (now - oldest_call.timestamp).total_seconds())
            
            return max(0, wait_time)
    
    def get_api_stats(self) -> Dict:
        """获取API调用统计"""
        with self.lock:
            stats = {}
            now = datetime.now()
            
            for api_type, history in self.call_history.items():
                minute_ago = now - timedelta(minutes=1)
                hour_ago = now - timedelta(hours=1)
                
                minute_calls = sum(1 for r in history if r.timestamp > minute_ago)
                hour_calls = sum(1 for r in history if r.timestamp > hour_ago)
                success_rate = sum(1 for r in history if r.success and r.timestamp > hour_ago) / max(1, hour_calls) * 100
                
                stats[api_type] = {
                    'minute_calls': minute_calls,
                    'minute_limit': self.limits[api_type]['per_minute'],
                    'hour_calls': hour_calls,
                    'success_rate': success_rate,
                    'utilization': minute_calls / self.limits[api_type]['per_minute'] * 100
                }
            
            return stats


# 全局限制器实例
_rate_limiter: APIRateLimiter = None


def get_rate_limiter() -> APIRateLimiter:
    """获取全局API限制器"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = APIRateLimiter()
    return _rate_limiter


def safe_api_call(api_type: str, api_name: str, func, *args, **kwargs):
    """安全的API调用包装器"""
    limiter = get_rate_limiter()
    
    # 检查是否需要等待
    wait_time = limiter.wait_if_needed(api_type)
    if wait_time > 0:
        logger.info(f"API限制等待 {wait_time:.1f}秒: {api_type}.{api_name}")
        time.sleep(wait_time)
    
    # 执行API调用
    success = True
    result = None
    
    try:
        result = func(*args, **kwargs)
        logger.debug(f"API调用成功: {api_type}.{api_name}")
        
    except Exception as e:
        success = False
        logger.error(f"API调用失败: {api_type}.{api_name} - {e}")
        raise
        
    finally:
        # 记录调用
        limiter.record_api_call(api_type, api_name, success)
    
    return result
