#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
期权分析配置文件
"""

from dataclasses import dataclass
from typing import Dict, Any
from enum import Enum


class OptionStrategy(Enum):
    """期权策略枚举"""
    LIQUIDITY = "liquidity"
    BALANCED = "balanced"  
    VALUE = "value"


@dataclass
class OptionConfig:
    """期权分析配置"""
    
    # API限制
    MAX_SYMBOLS_PER_REQUEST: int = 20
    MAX_OPTION_BRIEFS_PER_REQUEST: int = 30
    
    # 筛选参数
    DEFAULT_PRICE_RANGE_PERCENT: float = 0.02  # ±2%
    MIN_VOLUME_THRESHOLD: int = 10
    MIN_OPEN_INTEREST_THRESHOLD: int = 100
    MAX_SPREAD_PERCENTAGE: float = 0.20  # 20%
    
    # 评分权重配置
    STRATEGY_WEIGHTS: Dict[OptionStrategy, Dict[str, float]] = None
    
    # 默认希腊字母值（当无法获取真实值时使用）
    DEFAULT_GAMMA: float = 0.1
    DEFAULT_THETA: float = -0.05
    DEFAULT_VEGA: float = 0.01
    DEFAULT_IMPLIED_VOL: float = 0.2
    
    # Delta估算阈值
    DELTA_THRESHOLDS: Dict[str, float] = None
    
    def __post_init__(self):
        """后初始化设置默认值"""
        if self.STRATEGY_WEIGHTS is None:
            self.STRATEGY_WEIGHTS = {
                OptionStrategy.LIQUIDITY: {
                    'liquidity': 0.5,
                    'spread': 0.3,
                    'greeks': 0.1,
                    'value': 0.1
                },
                OptionStrategy.BALANCED: {
                    'liquidity': 0.25,
                    'spread': 0.25,
                    'greeks': 0.25,
                    'value': 0.25
                },
                OptionStrategy.VALUE: {
                    'value': 0.4,
                    'greeks': 0.3,
                    'liquidity': 0.2,
                    'spread': 0.1
                }
            }
        
        if self.DELTA_THRESHOLDS is None:
            self.DELTA_THRESHOLDS = {
                'deep_itm': 1.05,
                'light_itm': 1.02,
                'atm_upper': 1.02,
                'atm_lower': 0.98,
                'light_otm': 0.95,
                'deep_otm': 0.95
            }


# 全局配置实例
OPTION_CONFIG = OptionConfig()


class OptionConstants:
    """期权相关常量"""
    
    # 期权类型
    CALL = "CALL"
    PUT = "PUT"
    
    # DataFrame字段映射
    FIELD_MAPPINGS = {
        'right': 'put_call',
        'bid': 'bid_price', 
        'ask': 'ask_price',
        'latest_price': 'latest_price',
        'volume': 'volume',
        'open_interest': 'open_interest',
        'delta': 'delta',
        'gamma': 'gamma',
        'theta': 'theta',
        'vega': 'vega',
        'implied_vol': 'implied_vol'
    }
    
    # 评分范围
    MIN_SCORE = 0.0
    MAX_SCORE = 100.0
    
    # 流动性评分基准
    VOLUME_BENCHMARK = 100  # 成交量基准
    OPEN_INTEREST_BENCHMARK = 1000  # 未平仓基准
    
    # 希腊字母基准
    IDEAL_DELTA = 0.5  # 理想Delta值
    GAMMA_MULTIPLIER = 1000  # Gamma评分乘数
