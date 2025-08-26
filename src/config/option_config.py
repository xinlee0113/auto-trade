#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
期权分析配置文件
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
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
    
    # 筛选参数 - 针对0DTE期权优化
    DEFAULT_PRICE_RANGE_PERCENT: float = 0.03  # ±3% (0DTE期权需要更大范围捕获OTM机会)
    MIN_VOLUME_THRESHOLD: int = 10
    MIN_OPEN_INTEREST_THRESHOLD: int = 100
    MAX_SPREAD_PERCENTAGE: float = 0.20  # 20%
    
    # 评分权重配置
    STRATEGY_WEIGHTS: Optional[Dict[OptionStrategy, Dict[str, float]]] = None
    
    # 默认希腊字母值（当无法获取真实值时使用）
    DEFAULT_GAMMA: float = 0.1
    DEFAULT_THETA: float = -0.05
    DEFAULT_VEGA: float = 0.01
    DEFAULT_IMPLIED_VOL: float = 0.2
    
    # Delta估算阈值
    DELTA_THRESHOLDS: Optional[Dict[str, float]] = None
    
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
                    # 针对0DTE期权优化的权重配置
                    'value': 0.35,      # 略降价值权重，为Greeks让路
                    'greeks': 0.35,     # 提升Greeks权重 (0DTE极度敏感)
                    'liquidity': 0.20,  # 保持流动性权重 (执行保障)
                    'spread': 0.10      # 保持价差权重 (成本控制)
                }
            }
        
        if self.DELTA_THRESHOLDS is None:
            # 针对0DTE期权的精确Delta阈值 - 更敏感的价格区间划分
            self.DELTA_THRESHOLDS = {
                'deep_itm': 1.03,    # 深度ITM (3% vs 5%) - 0DTE对价格更敏感
                'light_itm': 1.01,   # 浅度ITM (1% vs 2%) - 更精确的ITM界定
                'atm_upper': 1.01,   # ATM上限 (1%)
                'atm_lower': 0.99,   # ATM下限 (-1%) - 更紧的ATM范围
                'light_otm': 0.97,   # 浅度OTM (-3%)
                'deep_otm': 0.97     # 深度OTM
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
    
    # 流动性评分基准 - 基于QQQ期权实际交易数据优化
    VOLUME_BENCHMARK = 1000  # 成交量基准 (提升10倍，符合QQQ期权实际流动性)
    OPEN_INTEREST_BENCHMARK = 5000  # 未平仓基准 (提升5倍，匹配活跃期权OI水平)
    
    # 希腊字母基准
    IDEAL_DELTA = 0.5  # 理想Delta值
    GAMMA_MULTIPLIER = 1000  # Gamma评分乘数
