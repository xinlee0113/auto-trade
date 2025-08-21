#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
期权数据模型
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum

from ..config.option_config import OptionStrategy


@dataclass
class OptionData:
    """期权数据模型"""
    symbol: str
    strike: float
    right: str  # CALL or PUT
    expiry: str
    latest_price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    volume: int = 0
    open_interest: int = 0
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    implied_vol: float = 0.0
    
    # 计算字段
    bid_ask_spread: float = field(init=False)
    spread_percentage: float = field(init=False)
    intrinsic_value: float = field(init=False)
    time_value: float = field(init=False)
    moneyness: float = field(init=False)
    
    # 评分字段
    score: float = field(init=False, default=0.0)
    rank: int = field(init=False, default=0)
    score_details: Dict[str, float] = field(init=False, default_factory=dict)
    
    def __post_init__(self):
        """后初始化计算衍生字段"""
        self.bid_ask_spread = self.ask - self.bid
        self.spread_percentage = (
            self.bid_ask_spread / self.latest_price 
            if self.latest_price > 0 else 1.0
        )
    
    def calculate_intrinsic_value(self, current_price: float):
        """计算内在价值"""
        if self.right.upper() == 'CALL':
            self.intrinsic_value = max(current_price - self.strike, 0)
        else:  # PUT
            self.intrinsic_value = max(self.strike - current_price, 0)
        
        self.time_value = self.latest_price - self.intrinsic_value
    
    def calculate_moneyness(self, current_price: float):
        """计算价值状态（距离ATM的程度）"""
        self.moneyness = abs(self.strike - current_price) / current_price


@dataclass
class ScoreBreakdown:
    """评分明细"""
    liquidity: float
    spread: float
    greeks: float
    value: float
    strategy: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'liquidity': round(self.liquidity, 1),
            'spread': round(self.spread, 1),
            'greeks': round(self.greeks, 1),
            'value': round(self.value, 1),
            'strategy': self.strategy
        }


@dataclass
class OptionAnalysisResult:
    """期权分析结果"""
    calls: List[OptionData]
    puts: List[OptionData]
    strategy: str
    current_price: float
    total_contracts: int
    price_range: str
    timestamp: str
    message: Optional[str] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'calls': [self._option_to_dict(opt) for opt in self.calls],
            'puts': [self._option_to_dict(opt) for opt in self.puts],
            'strategy': self.strategy,
            'current_price': self.current_price,
            'total_contracts': self.total_contracts,
            'price_range': self.price_range,
            'timestamp': self.timestamp,
            'message': self.message,
            'error': self.error
        }
    
    def _option_to_dict(self, option: OptionData) -> Dict[str, Any]:
        """期权数据转字典"""
        return {
            'symbol': option.symbol,
            'strike': option.strike,
            'right': option.right,
            'expiry': option.expiry,
            'latest_price': option.latest_price,
            'bid': option.bid,
            'ask': option.ask,
            'volume': option.volume,
            'open_interest': option.open_interest,
            'delta': option.delta,
            'gamma': option.gamma,
            'theta': option.theta,
            'vega': option.vega,
            'implied_vol': option.implied_vol,
            'bid_ask_spread': option.bid_ask_spread,
            'spread_percentage': option.spread_percentage,
            'intrinsic_value': option.intrinsic_value,
            'time_value': option.time_value,
            'moneyness': option.moneyness,
            'score': option.score,
            'rank': option.rank,
            'score_details': option.score_details
        }


@dataclass
class OptionFilter:
    """期权筛选条件"""
    min_volume: Optional[int] = None
    min_open_interest: Optional[int] = None
    max_spread_percentage: Optional[float] = None
    price_range_percent: Optional[float] = None
    option_types: Optional[List[str]] = None  # ['CALL', 'PUT']
    
    def apply(self, options: List[OptionData]) -> List[OptionData]:
        """应用筛选条件"""
        filtered = options
        
        if self.min_volume is not None:
            filtered = [opt for opt in filtered if opt.volume >= self.min_volume]
        
        if self.min_open_interest is not None:
            filtered = [opt for opt in filtered if opt.open_interest >= self.min_open_interest]
        
        if self.max_spread_percentage is not None:
            filtered = [opt for opt in filtered if opt.spread_percentage <= self.max_spread_percentage]
        
        if self.option_types is not None:
            filtered = [opt for opt in filtered if opt.right.upper() in [t.upper() for t in self.option_types]]
        
        return filtered
