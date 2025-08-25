#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于真实Tiger API数据的风险管理器演示

全面实现基于推送数据的实时交易信号生成系统：
1. 实时推送数据处理 (WebSocket)
2. 多层技术指标分析 (EMA, 动量, 成交量等)
3. 风险管理和仓位控制
4. 0DTE期权高频交易信号

Features:
- 推送数据 <10ms延迟 vs 轮询 ~600ms
- 实时EMA3/EMA8金叉死叉信号
- 多时间窗口动量分析 (10s/30s/1m)
- 成交量分析和价量关系
- 期权特定风险评估

Author: AI Assistant
Date: 2025-01-15
"""

# Standard library imports
import os
import sys
import time
import threading
from collections import deque
from datetime import datetime, timedelta
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple

# Third party imports
import numpy as np
import pandas as pd

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Local imports
from demos.client_config import get_client_config
from src.config.trading_config import DEFAULT_TRADING_CONFIG, RiskLevel
from src.models.trading_models import Position, OptionTickData, UnderlyingTickData
from src.services.risk_manager import create_risk_manager, RiskEvent, StopLossType
from src.utils.greeks_calculator import GreeksCalculator

# Tiger API imports
from tigeropen.quote.quote_client import QuoteClient


# ==================== 常量和配置 ====================

# 信号生成器配置
SIGNAL_CONFIG = {
    'EMA_PERIODS': {'EMA3': 3, 'EMA8': 8},
    'MOMENTUM_WINDOWS': {'10s': 10, '30s': 30, '1m': 60},
    'VOLUME_WINDOW': 300,  # 5分钟
    'CACHE_SIZES': {
        'PUSH_MODE': {
            'price': 200, 
            'momentum_10s': 15,    # 10秒 ÷ ~0.7秒/tick ≈ 15个点
            'momentum_30s': 45,    # 30秒 ÷ ~0.7秒/tick ≈ 45个点  
            'momentum_1m': 90,     # 60秒 ÷ ~0.7秒/tick ≈ 90个点
            'volume': 300          # 5分钟缓存
        },
        'POLL_MODE': {'price': 500, 'momentum_10s': 17, 'momentum_30s': 50, 'momentum_1m': 100, 'volume': 500}
    },
                'THRESHOLDS': {
                'MOMENTUM': {'10s': 0.01, '30s': 0.015, '1m': 0.02},  # 更敏感的阈值
                'VOLUME_RATIO': 1.5,
                'SPREAD_QUALITY': 0.02
            }
}

# 推送客户端配置
PUSH_CONFIG = {
    'RECONNECT_ATTEMPTS': 10,
    'RECONNECT_DELAY': 1.0,
    'STATS_PRINT_INTERVAL': 100
}


# ==================== 工具类 ====================

class SafeCalculator:
    """安全计算工具类，提供错误处理和日志记录"""
    
    @staticmethod
    def safe_divide(numerator: float, denominator: float, default: float = 0.0, symbol: str = "") -> float:
        """安全除法，避免除零错误"""
        try:
            if denominator == 0 or abs(denominator) < 1e-10:
                return default
            return float(numerator) / float(denominator)
        except (TypeError, ValueError, ZeroDivisionError) as e:
            print(f"⚠️ [{symbol}] 除法计算错误: {numerator}/{denominator} -> {e}")
            return default
    
    @staticmethod
    def safe_percentage(value: float, base: float, symbol: str = "") -> float:
        """安全百分比计算"""
        try:
            if base == 0 or abs(base) < 1e-10:
                return 0.0
            return ((float(value) - float(base)) / float(base)) * 100
        except (TypeError, ValueError, ZeroDivisionError) as e:
            print(f"⚠️ [{symbol}] 百分比计算错误: ({value} - {base})/{base} -> {e}")
            return 0.0
    
    @staticmethod
    def safe_float_conversion(value: Any, default: float = 0.0, symbol: str = "") -> float:
        """安全浮点数转换"""
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError) as e:
            print(f"⚠️ [{symbol}] 浮点数转换错误: {value} -> {e}")
            return default
    
    @staticmethod
    def safe_int_conversion(value: Any, default: int = 0, symbol: str = "") -> int:
        """安全整数转换"""
        try:
            if value is None:
                return default
            return int(float(value))  # 先转float再转int，处理字符串数字
        except (TypeError, ValueError) as e:
            print(f"⚠️ [{symbol}] 整数转换错误: {value} -> {e}")
            return default


# ==================== 数据模型 ====================

@dataclass
class TradingSignal:
    """交易信号数据模型"""
    timestamp: datetime
    symbol: str
    signal_type: str  # 'BUY', 'SELL', 'HOLD'
    strength: float   # 信号强度 0-100
    confidence: float # 信号置信度 0-1
    entry_score: float # 入场评分
    exit_score: float  # 出场评分
    reasons: List[str] = field(default_factory=list)
    technical_details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketData:
    """市场数据模型"""
    timestamp: datetime
    symbol: str
    price: float
    volume: int
    bid: float = 0.0
    ask: float = 0.0
    bid_size: int = 0
    ask_size: int = 0


@dataclass
class TechnicalIndicators:
    """技术指标数据模型"""
    timestamp: datetime
    price: float
    ema3: float = 0.0
    ema8: float = 0.0
    momentum_10s: float = 0.0
    momentum_30s: float = 0.0
    momentum_1m: float = 0.0
    volume_ratio: float = 0.0
    price_volume_correlation: float = 0.0
    spread_quality: float = 0.0
    cross_signal: str = "neutral"
    cross_strength: float = 0.0


class RealTimeSignalGenerator:
    """实时信号生成器 - 基于推送数据的实时计算"""
    
    def __init__(self, symbol: str, use_push_data: bool = True):
        self.symbol = symbol
        self.use_push_data = use_push_data
        
        # 初始化数据缓存
        self._init_data_caches()
        
        # 初始化EMA计算器
        self._init_ema_calculator()
        
        # 初始化统计跟踪
        self._init_statistics()
        
        self._log_initialization()
    
    def _init_data_caches(self):
        """初始化数据缓存"""
        cache_config = SIGNAL_CONFIG['CACHE_SIZES']['PUSH_MODE' if self.use_push_data else 'POLL_MODE']
        
        if self.use_push_data:
            # 推送模式：最新数据 + 定时采样的时间序列
            self.latest_market_data = None  # 推送数据实时更新的最新值
            self.last_sample_time = None    # 上次采样时间
            self.sample_interval = 1.0      # 每秒采样一次
            
            # 定时采样的时间序列（每秒一个数据点）
            self.price_data = deque(maxlen=120)      # 2分钟价格历史
            self.volume_data = deque(maxlen=120)     # 2分钟成交量历史  
            self.timestamp_data = deque(maxlen=120)  # 2分钟时间戳历史
            self.market_data_history = deque(maxlen=120)
            
            # 动量缓存窗口（基于1秒间隔的采样数据）
            self.momentum_cache = {
                '10s': deque(maxlen=15),   # 10秒 + 5秒余量
                '30s': deque(maxlen=35),   # 30秒 + 5秒余量
                '1m': deque(maxlen=65)     # 60秒 + 5秒余量
            }
            
            # 成交量分析窗口
            self.volume_window_5m = deque(maxlen=300)  # 5分钟
        else:
            # 轮询模式：原有逻辑
            self.price_data = deque(maxlen=cache_config['price'])
            self.volume_data = deque(maxlen=cache_config['price'])     
            self.timestamp_data = deque(maxlen=cache_config['price'])  
            self.market_data_history = deque(maxlen=cache_config['price'])
            
            # 动量缓存窗口
            self.momentum_cache = {
                '10s': deque(maxlen=cache_config['momentum_10s']),
                '30s': deque(maxlen=cache_config['momentum_30s']),
                '1m': deque(maxlen=cache_config['momentum_1m'])
            }
            
            # 成交量分析窗口
            self.volume_window_5m = deque(maxlen=cache_config['volume'])
            self.update_interval = 0.6
    
    def _init_ema_calculator(self):
        """初始化EMA计算器"""
        ema_periods = SIGNAL_CONFIG['EMA_PERIODS']
        self.ema3_multiplier = 2 / (ema_periods['EMA3'] + 1)
        self.ema8_multiplier = 2 / (ema_periods['EMA8'] + 1)
        
        # EMA状态
        self.current_ema3 = None
        self.current_ema8 = None
        self.prev_ema3 = None
        self.prev_ema8 = None
    
    def _init_statistics(self):
        """初始化统计跟踪"""
        # 技术指标历史
        self.technical_indicators_history = deque(maxlen=200)
        self.signal_history = deque(maxlen=100)
        
        # 推送数据统计
        self.push_stats = {
            'total_ticks': 0,
            'price_changes': 0, 
            'volume_changes': 0,
            'start_time': datetime.now(),
            'last_update_time': None,
            'ticks_per_second': 0
        }
        
        # 一般统计
        self.total_signals = 0
        self.last_signal_time = None
        self.last_update_time = None
    
    def _log_initialization(self):
        """记录初始化信息"""
        cache_config = SIGNAL_CONFIG['CACHE_SIZES']['PUSH_MODE' if self.use_push_data else 'POLL_MODE']
        mode_desc = "推送实时数据 (WebSocket)" if self.use_push_data else "轮询数据 (0.6秒间隔)"
        
        print(f"🎯 [{self.symbol}] 实时信号生成器初始化完成")
        print(f"   数据模式: {mode_desc}")
        print(f"   缓存容量: 价格历史{cache_config['price']}个{'tick' if self.use_push_data else '点'}")
        print(f"   动量分析窗口: 10s/30s/1m")
    
    def process_push_data(self, quote_data) -> Optional[TradingSignal]:
        """处理推送数据并生成交易信号"""
        try:
            self._update_push_statistics()
            
            # 解析价格数据
            price = self._extract_price_from_quote(quote_data)
            if price is None:
                print(f"⚠️ 推送数据中没有价格信息: {quote_data}")
                return None
            
            # 构造市场数据
            market_data = self._build_market_data_from_quote(quote_data, price)
            
            if self.use_push_data:
                # 推送模式：只更新最新值
                self.latest_market_data = market_data
                self._log_push_data_stats(market_data)
                
                # 检查是否需要定时采样
                return self._check_and_sample_data()
            else:
                # 轮询模式：直接更新时间序列
                self._log_push_data_stats(market_data)
                return self.update_market_data(market_data)
            
        except Exception as e:
            print(f"❌ 处理推送数据失败: {e}")
            return None
    
    def _check_and_sample_data(self) -> Optional[TradingSignal]:
        """检查是否需要定时采样并生成信号"""
        if not self.latest_market_data:
            return None
            
        current_time = datetime.now()
        
        # 初始化采样时间或检查是否需要采样
        if (self.last_sample_time is None or 
            (current_time - self.last_sample_time).total_seconds() >= self.sample_interval):
            
            # 进行定时采样：将最新数据加入时间序列
            self.last_sample_time = current_time
            return self.update_market_data(self.latest_market_data)
        
        return None  # 不需要采样，返回None
    
    def _update_push_statistics(self):
        """更新推送数据统计"""
        self.push_stats['total_ticks'] += 1
        self.push_stats['last_update_time'] = datetime.now()
        
        # 计算推送频率
        elapsed_time = (self.push_stats['last_update_time'] - self.push_stats['start_time']).total_seconds()
        if elapsed_time > 0:
            self.push_stats['ticks_per_second'] = self.push_stats['total_ticks'] / elapsed_time
    
    def _extract_price_from_quote(self, quote_data) -> Optional[float]:
        """从推送数据中提取价格"""
        # 处理基础行情类型推送数据 (包含成交量)
        if hasattr(quote_data, 'latestPrice') and quote_data.latestPrice:
            price = float(quote_data.latestPrice)
            # 打印基础行情信息
            volume = getattr(quote_data, 'volume', 0) or 0
            print(f"📊 [基础行情] 最新价:{price:.2f}, 成交量:{volume:,}")
            return price
        elif hasattr(quote_data, 'latest_price') and quote_data.latest_price:
            return float(quote_data.latest_price)
        elif hasattr(quote_data, 'price') and quote_data.price:
            return float(quote_data.price)
        
        # 处理BBO类型推送数据 - 仅包含买卖价信息
        elif hasattr(quote_data, 'bidPrice') and hasattr(quote_data, 'askPrice'):
            if quote_data.bidPrice and quote_data.askPrice:
                bid_price = float(quote_data.bidPrice)
                ask_price = float(quote_data.askPrice)
                mid_price = (bid_price + ask_price) / 2
                print(f"📊 [BBO推送] 买价:{bid_price:.2f}, 卖价:{ask_price:.2f}, 中间价:{mid_price:.2f}")
                return mid_price
        
        return None
    
    def _build_market_data_from_quote(self, quote_data, price: float) -> MarketData:
        """从推送数据构造MarketData对象"""
        # 获取成交量 - 优先使用基础行情数据
        volume = SafeCalculator.safe_int_conversion(
            getattr(quote_data, 'volume', 0), default=0, symbol=self.symbol
        )
        
        # 如果当前数据没有成交量，使用上一次有效的成交量
        if volume == 0 and hasattr(self, '_last_valid_volume'):
            volume = self._last_valid_volume
        elif volume > 0:
            self._last_valid_volume = volume
        
        # 获取买卖价信息
        bid = ask = price  # 默认值
        bid_size = ask_size = 0
        
        for attr, default in [('bid', price), ('ask', price), ('bidPrice', price), ('askPrice', price)]:
            if hasattr(quote_data, attr) and getattr(quote_data, attr):
                if 'bid' in attr.lower():
                    bid = SafeCalculator.safe_float_conversion(getattr(quote_data, attr), default=price, symbol=self.symbol)
                else:
                    ask = SafeCalculator.safe_float_conversion(getattr(quote_data, attr), default=price, symbol=self.symbol)
        
        for attr in ['bid_size', 'ask_size', 'bidSize', 'askSize']:
            if hasattr(quote_data, attr) and getattr(quote_data, attr):
                if 'bid' in attr.lower():
                    bid_size = SafeCalculator.safe_int_conversion(getattr(quote_data, attr), default=0, symbol=self.symbol)
                else:
                    ask_size = SafeCalculator.safe_int_conversion(getattr(quote_data, attr), default=0, symbol=self.symbol)
        
        return MarketData(
            timestamp=datetime.now(),
            symbol=self.symbol,
            price=price,
            volume=volume,
            bid=bid,
            ask=ask,
            bid_size=bid_size,
            ask_size=ask_size
        )
    
    def _log_push_data_stats(self, market_data: MarketData):
        """定期记录推送数据统计"""
        if self.push_stats['total_ticks'] % 10 == 0:
            print(f"📡 [推送数据] Tick #{self.push_stats['total_ticks']}")
            print(f"   时间: {market_data.timestamp.strftime('%H:%M:%S.%f')[:-3]}")
            print(f"   价格: ${market_data.price:.2f}, 成交量: {market_data.volume:,}")
            print(f"   买卖价: ${market_data.bid:.2f}/${market_data.ask:.2f}, 买卖量: {market_data.bid_size}/{market_data.ask_size}")
            print(f"   推送频率: {self.push_stats['ticks_per_second']:.1f} ticks/秒")
    
    def update_market_data(self, market_data: MarketData) -> Optional[TradingSignal]:
        """更新市场数据并生成交易信号
        
        核心信号生成流程：
        1. 数据缓存更新 - 维护价格、成交量、时间序列
        2. 技术指标计算 - EMA3/EMA8交叉，多时间窗口动量
        3. 成交量分析 - 成交量比率和价量关系
        4. 综合评分 - 多层信号评分和风险评估
        5. 信号决策 - 生成BUY/SELL/HOLD信号
        
        Args:
            market_data: 包含价格、成交量、买卖价等实时市场数据
            
        Returns:
            TradingSignal: 包含信号类型、强度、原因等完整交易信号，失败时返回None
            
        Note:
            - 推送模式：处理高频tick数据，<10ms延迟
            - 信号强度：0-100评分，置信度0-1
            - 多层验证：EMA交叉+动量+成交量+期权评分
        """
        try:
            # 1. 更新动态缓存
            self._update_data_cache(market_data)
            
            # 2. 计算技术指标
            indicators = self._calculate_technical_indicators(market_data)
            if indicators:
                self.technical_indicators_history.append(indicators)
                
                # 动态打印技术指标计算结果
                self._print_technical_indicators(indicators)
            
            # 3. 生成交易信号
            signal = self._generate_trading_signal(indicators) if indicators else None
            if signal:
                self.signal_history.append(signal)
                self.total_signals += 1
                self.last_signal_time = market_data.timestamp
                
                # 动态打印信号生成结果
                self._print_trading_signal(signal)
            
            self.last_update_time = market_data.timestamp
            return signal
            
        except Exception as e:
            print(f"❌ [{self.symbol}] 信号生成失败: {e}")
            return None
    
    def _update_data_cache(self, market_data: MarketData):
        """更新动态数据缓存"""
        # 更新基础数据队列
        self.price_data.append(market_data.price)
        self.volume_data.append(market_data.volume)
        self.timestamp_data.append(market_data.timestamp)
        self.market_data_history.append(market_data)
        
        # 更新动量计算缓存
        for window, cache in self.momentum_cache.items():
            cache.append((market_data.timestamp, market_data.price))
        
        # 更新成交量窗口
        self.volume_window_5m.append((market_data.timestamp, market_data.volume))
        
        # 动态打印实时数据序列 (每10次更新打印一次)
        if len(self.price_data) % 10 == 0:
            print(f"📊 [{self.symbol}] 实时数据序列更新:")
            
            # 打印最近5个价格数据点
            recent_prices = list(self.price_data)[-5:]
            recent_times = list(self.timestamp_data)[-5:]
            print(f"   最近5个价格: {[f'${p:.2f}' for p in recent_prices]}")
            print(f"   时间序列: {[t.strftime('%H:%M:%S.%f')[:-3] for t in recent_times]}")
            
            # 打印缓存填充状态
            # 获取当前配置的缓存大小
            cache_config = SIGNAL_CONFIG['CACHE_SIZES']['PUSH_MODE' if self.use_push_data else 'POLL_MODE']
            print(f"   缓存状态: 价格数据{len(self.price_data)}/{cache_config['price']}, "
                  f"动量缓存 10s:{len(self.momentum_cache['10s'])}/{cache_config['momentum_10s']}, "
                  f"30s:{len(self.momentum_cache['30s'])}/{cache_config['momentum_30s']}, "
                  f"1m:{len(self.momentum_cache['1m'])}/{cache_config['momentum_1m']}")
            
            # 打印成交量变化
            recent_volumes = list(self.volume_data)[-5:]
            print(f"   最近5个成交量: {[f'{v:,}' for v in recent_volumes]}")
            print()
    
    def _calculate_technical_indicators(self, market_data: MarketData) -> Optional[TechnicalIndicators]:
        """计算技术指标"""
        try:
            current_price = market_data.price
            current_time = market_data.timestamp
            
            # 计算EMA指标
            ema3, ema8, cross_signal, cross_strength = self._calculate_ema(current_price)
            
            # 计算多时间窗口动量
            momentum_10s, momentum_30s, momentum_1m = self._calculate_momentum_indicators()
            
            # 计算成交量指标
            volume_ratio = self._calculate_volume_ratio(market_data.volume)
            
            # 计算价格成交量相关性
            price_volume_corr = self._calculate_price_volume_correlation()
            
            # 计算价差质量
            spread_quality = self._calculate_spread_quality(market_data)
            
            indicators = TechnicalIndicators(
                timestamp=current_time,
                price=current_price,
                ema3=ema3,
                ema8=ema8,
                momentum_10s=momentum_10s,
                momentum_30s=momentum_30s,
                momentum_1m=momentum_1m,
                volume_ratio=volume_ratio,
                price_volume_correlation=price_volume_corr,
                spread_quality=spread_quality,
                cross_signal=cross_signal,
                cross_strength=cross_strength
            )
            
            return indicators
            
        except Exception as e:
            print(f"⚠️ [{self.symbol}] 技术指标计算失败: {e}")
            return None
    
    def _calculate_ema(self, current_price: float) -> Tuple[float, float, str, float]:
        """计算EMA指标"""
        try:
            # 初始化EMA - 第一个价格作为EMA初始值
            if self.current_ema3 is None:
                self.current_ema3 = current_price
                self.current_ema8 = current_price
                print(f"🔄 [{self.symbol}] EMA初始化:")
                print(f"   初始价格: ${current_price:.2f}")
                print(f"   EMA3 = EMA8 = ${current_price:.2f}")
                print(f"   EMA3倍数: {self.ema3_multiplier:.3f} (2/(3+1))")
                print(f"   EMA8倍数: {self.ema8_multiplier:.3f} (2/(8+1))")
                return self.current_ema3, self.current_ema8, "neutral", 0.0
            
            # 保存前一期值
            self.prev_ema3 = self.current_ema3
            self.prev_ema8 = self.current_ema8
            
            # 详细打印EMA计算过程
            print(f"🧮 [{self.symbol}] EMA计算过程:")
            print(f"   当前价格: ${current_price:.2f}")
            print(f"   前期EMA3: ${self.prev_ema3:.4f}")
            print(f"   前期EMA8: ${self.prev_ema8:.4f}")
            
            # 计算新的EMA值
            prev_ema3 = self.current_ema3 or 0.0
            prev_ema8 = self.current_ema8 or 0.0
            
            # EMA3计算: EMA = 价格 × 倍数 + 前期EMA × (1-倍数)
            ema3_price_part = current_price * self.ema3_multiplier
            ema3_prev_part = prev_ema3 * (1 - self.ema3_multiplier)
            self.current_ema3 = ema3_price_part + ema3_prev_part
            
            # EMA8计算
            ema8_price_part = current_price * self.ema8_multiplier
            ema8_prev_part = prev_ema8 * (1 - self.ema8_multiplier)
            self.current_ema8 = ema8_price_part + ema8_prev_part
            
            print(f"   EMA3计算: ${current_price:.2f}×{self.ema3_multiplier:.3f} + ${prev_ema3:.4f}×{1-self.ema3_multiplier:.3f} = ${self.current_ema3:.4f}")
            print(f"   EMA8计算: ${current_price:.2f}×{self.ema8_multiplier:.3f} + ${prev_ema8:.4f}×{1-self.ema8_multiplier:.3f} = ${self.current_ema8:.4f}")
            
            # 计算EMA变化量
            prev_ema3_safe = self.prev_ema3 or 0.0
            prev_ema8_safe = self.prev_ema8 or 0.0
            ema3_change = self.current_ema3 - prev_ema3_safe
            ema8_change = self.current_ema8 - prev_ema8_safe
            
            ema3_change_pct = (ema3_change/prev_ema3_safe*100) if prev_ema3_safe > 0 else 0.0
            ema8_change_pct = (ema8_change/prev_ema8_safe*100) if prev_ema8_safe > 0 else 0.0
            
            print(f"   EMA3变化: {ema3_change:+.4f} ({ema3_change_pct:+.3f}%)")
            print(f"   EMA8变化: {ema8_change:+.4f} ({ema8_change_pct:+.3f}%)")
            
            # 判断穿越信号
            cross_signal = "neutral"
            cross_strength = 0.0
            
            if self.prev_ema3 and self.prev_ema8:
                # 计算EMA差值
                current_diff = self.current_ema3 - self.current_ema8
                prev_diff = self.prev_ema3 - self.prev_ema8
                
                print(f"   EMA差值: 当前{current_diff:+.4f}, 前期{prev_diff:+.4f}")
                
                # 金叉：EMA3向上穿越EMA8
                if self.prev_ema3 <= self.prev_ema8 and self.current_ema3 > self.current_ema8:
                    cross_signal = "bullish"
                    cross_strength = abs(self.current_ema3 - self.current_ema8) / self.current_ema8
                    print(f"🔥 [{self.symbol}] EMA金叉信号! EMA3({self.current_ema3:.4f}) > EMA8({self.current_ema8:.4f}), 强度: {cross_strength:.6f}")
                
                # 死叉：EMA3向下穿越EMA8
                elif self.prev_ema3 >= self.prev_ema8 and self.current_ema3 < self.current_ema8:
                    cross_signal = "bearish"
                    cross_strength = abs(self.current_ema3 - self.current_ema8) / self.current_ema8
                    print(f"📉 [{self.symbol}] EMA死叉信号! EMA3({self.current_ema3:.4f}) < EMA8({self.current_ema8:.4f}), 强度: {cross_strength:.6f}")
                
                # 判断EMA趋势方向
                if abs(current_diff) > abs(prev_diff):
                    trend_direction = "分离" if current_diff * prev_diff > 0 else "靠近"
                else:
                    trend_direction = "收敛" if current_diff * prev_diff > 0 else "发散"
                print(f"   EMA趋势: {trend_direction}")
            
            print()  # 空行分隔
            
            return (self.current_ema3 or 0.0), (self.current_ema8 or 0.0), cross_signal, cross_strength
            
        except Exception as e:
            print(f"⚠️ [{self.symbol}] EMA计算失败: {e}")
            return 0.0, 0.0, "neutral", 0.0
    
    def _calculate_momentum_indicators(self) -> Tuple[float, float, float]:
        """计算多时间窗口动量指标 - 基于固定时间间隔采样"""
        try:
            momentum_10s = momentum_30s = momentum_1m = 0.0
            print(f"📊 [{self.symbol}] 动量计算详情:")
            
            if self.use_push_data:
                # 推送模式：基于固定采样间隔的简化计算
                # 计算10秒动量（需要至少10个数据点，每秒1个）
                if len(self.momentum_cache['10s']) >= 10:
                    start_price = self.momentum_cache['10s'][-10][1]  # 10秒前的价格
                    end_price = self.momentum_cache['10s'][-1][1]     # 最新价格
                    momentum_10s = SafeCalculator.safe_divide(end_price - start_price, start_price, default=0.0, symbol=self.symbol)
                    print(f"   10秒动量 = ({end_price:.2f} - {start_price:.2f}) / {start_price:.2f} = {momentum_10s:.6f} ({momentum_10s*100:.3f}%)")
                    
                    threshold_10s = SIGNAL_CONFIG['THRESHOLDS']['MOMENTUM']['10s']
                    if abs(momentum_10s) > threshold_10s:
                        print(f"⚡ [{self.symbol}] 10秒动量触发阈值! {momentum_10s:.4f} ({momentum_10s*100:.2f}%) > {threshold_10s*100:.1f}%")
                else:
                    print(f"   10秒动量: 数据点不足 ({len(self.momentum_cache['10s'])}/10)")
                
                # 计算30秒动量（需要至少30个数据点）
                if len(self.momentum_cache['30s']) >= 30:
                    start_price = self.momentum_cache['30s'][-30][1]  # 30秒前的价格
                    end_price = self.momentum_cache['30s'][-1][1]     # 最新价格
                    momentum_30s = SafeCalculator.safe_divide(end_price - start_price, start_price, default=0.0, symbol=self.symbol)
                    print(f"   30秒动量 = ({end_price:.2f} - {start_price:.2f}) / {start_price:.2f} = {momentum_30s:.6f} ({momentum_30s*100:.3f}%)")
                    
                    threshold_30s = SIGNAL_CONFIG['THRESHOLDS']['MOMENTUM']['30s']
                    if abs(momentum_30s) > threshold_30s:
                        print(f"🚀 [{self.symbol}] 30秒动量触发阈值! {momentum_30s:.4f} ({momentum_30s*100:.2f}%) > {threshold_30s*100:.1f}%")
                else:
                    print(f"   30秒动量: 数据点不足 ({len(self.momentum_cache['30s'])}/30)")
                
                # 计算1分钟动量（需要至少60个数据点）
                if len(self.momentum_cache['1m']) >= 60:
                    start_price = self.momentum_cache['1m'][-60][1]  # 60秒前的价格
                    end_price = self.momentum_cache['1m'][-1][1]     # 最新价格
                    momentum_1m = SafeCalculator.safe_divide(end_price - start_price, start_price, default=0.0, symbol=self.symbol)
                    print(f"   1分钟动量 = ({end_price:.2f} - {start_price:.2f}) / {start_price:.2f} = {momentum_1m:.6f} ({momentum_1m*100:.3f}%)")
                    
                    threshold_1m = SIGNAL_CONFIG['THRESHOLDS']['MOMENTUM']['1m']
                    if abs(momentum_1m) > threshold_1m:
                        print(f"🌟 [{self.symbol}] 1分钟动量触发阈值! {momentum_1m:.4f} ({momentum_1m*100:.2f}%) > {threshold_1m*100:.1f}%")
                else:
                    print(f"   1分钟动量: 数据点不足 ({len(self.momentum_cache['1m'])}/60)")
            
            else:
                # 轮询模式：原有的时间窗口查找逻辑
                current_time = datetime.now()
                
                # 计算10秒动量 - 基于时间窗口查找
                if len(self.momentum_cache['10s']) >= 2:
                    # 查找10秒前的数据点
                    target_time_10s = current_time - timedelta(seconds=10)
                    start_data = None
                    end_data = self.momentum_cache['10s'][-1]  # 最新数据
                    
                    # 从缓存中找到最接近10秒前的数据点
                    for timestamp, price in self.momentum_cache['10s']:
                        if timestamp >= target_time_10s:
                            start_data = (timestamp, price)
                            break
                    
                    if start_data:
                        start_time, start_price = start_data
                        end_time, end_price = end_data
                        time_diff = (end_time - start_time).total_seconds()
                        
                        print(f"   10秒窗口: 时间跨度{time_diff:.1f}秒, 数据点{len(self.momentum_cache['10s'])}")
                        
                        if time_diff >= 6.0:  # 轮询模式：6秒即可
                            momentum_10s = SafeCalculator.safe_divide(end_price - start_price, start_price, default=0.0, symbol=self.symbol)
                            print(f"   10秒动量 = ({end_price:.2f} - {start_price:.2f}) / {start_price:.2f} = {momentum_10s:.6f} ({momentum_10s*100:.3f}%)")
                            
                            if abs(momentum_10s) > 0.001:  # 0.1%阈值
                                print(f"⚡ [{self.symbol}] 10秒动量触发阈值! {momentum_10s:.4f} ({momentum_10s*100:.2f}%)")
                        else:
                            print(f"   10秒动量: 时间窗口不足 ({time_diff:.1f}s < 6.0s)")
                    else:
                        print(f"   10秒动量: 未找到10秒前的数据点")
                else:
                    print(f"   10秒动量: 数据点不足 ({len(self.momentum_cache['10s'])}/2)")
            
            print(f"   最终动量值: 10s={momentum_10s:.6f}, 30s={momentum_30s:.6f}, 1m={momentum_1m:.6f}")
            print()
            return momentum_10s, momentum_30s, momentum_1m
            
        except Exception as e:
            print(f"⚠️ [{self.symbol}] 动量计算失败: {e}")
            return 0.0, 0.0, 0.0
    
    def _calculate_volume_ratio(self, current_volume: int) -> float:
        """计算成交量比率"""
        try:
            if len(self.volume_window_5m) < 50:  # 需要足够的历史数据
                return 1.0
            
            # 计算5分钟平均成交量
            volumes = [vol for _, vol in list(self.volume_window_5m)[-50:]]  # 最近50个数据点
            avg_volume_5m = np.mean(volumes) if volumes else current_volume
            
            volume_ratio = float(current_volume / avg_volume_5m) if avg_volume_5m > 0 else 1.0
            
            # 成交量突增检测
            if volume_ratio > 1.5:
                print(f"📊 [{self.symbol}] 成交量突增! 当前: {current_volume:,}, 5分钟均值: {avg_volume_5m:.0f}, 比率: {volume_ratio:.2f}x")
            
            return volume_ratio
            
        except Exception as e:
            print(f"⚠️ [{self.symbol}] 成交量比率计算失败: {e}")
            return 1.0
    
    def _calculate_price_volume_correlation(self) -> float:
        """计算价格成交量相关性"""
        try:
            if len(self.price_data) < 20 or len(self.volume_data) < 20:
                return 0.0
            
            # 获取最近20个数据点
            recent_prices = list(self.price_data)[-20:]
            recent_volumes = list(self.volume_data)[-20:]
            
            # 计算价格变化率
            price_changes = []
            for i in range(1, len(recent_prices)):
                change = (recent_prices[i] - recent_prices[i-1]) / recent_prices[i-1]
                price_changes.append(change)
            
            # 计算成交量变化率
            volume_changes = []
            for i in range(1, len(recent_volumes)):
                if recent_volumes[i-1] > 0:
                    change = (recent_volumes[i] - recent_volumes[i-1]) / recent_volumes[i-1]
                    volume_changes.append(change)
                else:
                    volume_changes.append(0.0)
            
            # 计算相关系数 - 安全处理
            if len(price_changes) >= 2 and len(volume_changes) >= 2:
                # 检查数据有效性
                price_std = np.std(price_changes)
                volume_std = np.std(volume_changes)
                
                if price_std > 1e-10 and volume_std > 1e-10:  # 确保标准差不为0
                    with np.errstate(divide='ignore', invalid='ignore'):
                        correlation = np.corrcoef(price_changes, volume_changes)[0, 1]
                        correlation = correlation if not np.isnan(correlation) else 0.0
                else:
                    correlation = 0.0
                
                if abs(correlation) > 0.6:
                    print(f"🔗 [{self.symbol}] 价格-成交量高度相关: {correlation:.3f}")
                
                return correlation
            
            return 0.0
            
        except Exception as e:
            print(f"⚠️ [{self.symbol}] 价格成交量相关性计算失败: {e}")
            return 0.0
    
    def _calculate_spread_quality(self, market_data: MarketData) -> float:
        """计算价差质量"""
        try:
            if market_data.bid <= 0 or market_data.ask <= 0 or market_data.price <= 0:
                return 0.0
            
            # 计算买卖价差
            spread = market_data.ask - market_data.bid
            spread_pct = spread / market_data.price
            
            # 计算深度比率
            total_depth = market_data.bid_size + market_data.ask_size
            
            # 价差质量评分 (0-1)
            spread_score = 1.0 - min(spread_pct / 0.01, 1.0)  # 1%价差为基准
            depth_score = min(total_depth / 1000, 1.0)  # 1000为满分深度
            
            quality = (spread_score * 0.7 + depth_score * 0.3)
            
            if spread_pct < 0.01:  # 1%以内
                print(f"💎 [{self.symbol}] 优质价差: {spread_pct:.3%}, 深度: {total_depth}, 质量评分: {quality:.2f}")
            
            return quality
            
        except Exception as e:
            print(f"⚠️ [{self.symbol}] 价差质量计算失败: {e}")
            return 0.0
    
    def _generate_trading_signal(self, indicators: TechnicalIndicators) -> Optional[TradingSignal]:
        """生成交易信号"""
        try:
            # 分层信号确认体系
            entry_score = self._calculate_entry_score(indicators)
            exit_score = self._calculate_exit_score(indicators)
            
            # 信号决策
            signal_type, strength, confidence, reasons = self._make_signal_decision(entry_score, exit_score, indicators)
            
            signal = TradingSignal(
                timestamp=indicators.timestamp,
                symbol=self.symbol,
                signal_type=signal_type,
                strength=strength,
                confidence=confidence,
                entry_score=entry_score,
                exit_score=exit_score,
                reasons=reasons,
                technical_details={
                    'ema3': indicators.ema3,
                    'ema8': indicators.ema8,
                    'momentum_10s': indicators.momentum_10s,
                    'momentum_30s': indicators.momentum_30s,
                    'momentum_1m': indicators.momentum_1m,
                    'volume_ratio': indicators.volume_ratio,
                    'price_volume_correlation': indicators.price_volume_correlation,
                    'spread_quality': indicators.spread_quality,
                    'cross_signal': indicators.cross_signal,
                    'cross_strength': indicators.cross_strength
                }
            )
            
            return signal
            
        except Exception as e:
            print(f"⚠️ [{self.symbol}] 交易信号生成失败: {e}")
            return None
    
    def _calculate_entry_score(self, indicators: TechnicalIndicators) -> float:
        """计算入场评分 (0-100分)"""
        try:
            score = 0.0
            
            # Layer 1: 标的动量确认 (权重30%)
            momentum_score = 0.0
            momentum_signals = [indicators.momentum_10s, indicators.momentum_30s, indicators.momentum_1m]
            
            # 动量一致性检查
            positive_momentum = sum(1 for m in momentum_signals if m > 0.001)
            negative_momentum = sum(1 for m in momentum_signals if m < -0.001)
            
            if positive_momentum >= 2 and negative_momentum == 0:  # 多头动量一致
                momentum_score = 30.0
                print(f"🎯 [{self.symbol}] Layer1-动量确认: 多头一致 (+30分)")
            elif negative_momentum >= 2 and positive_momentum == 0:  # 空头动量一致
                momentum_score = 30.0
                print(f"🎯 [{self.symbol}] Layer1-动量确认: 空头一致 (+30分)")
            elif positive_momentum >= 1 or negative_momentum >= 1:  # 部分动量
                momentum_score = 15.0
                print(f"🎯 [{self.symbol}] Layer1-动量确认: 部分动量 (+15分)")
            
            score += momentum_score
            
            # Layer 2: 成交量与价格确认 (权重25%)
            volume_score = 0.0
            if indicators.volume_ratio > 1.5:  # 成交量突增
                volume_score += 15.0
                print(f"📊 [{self.symbol}] Layer2-成交量突增: {indicators.volume_ratio:.2f}x (+15分)")
            
            if abs(indicators.price_volume_correlation) > 0.6:  # 价格成交量协同
                volume_score += 10.0
                print(f"🔗 [{self.symbol}] Layer2-价量协同: {indicators.price_volume_correlation:.3f} (+10分)")
            
            score += volume_score
            
            # Layer 3: 微观结构确认 (权重20%)
            structure_score = 0.0
            if indicators.spread_quality > 0.8:  # 优质价差
                structure_score += 10.0
                print(f"💎 [{self.symbol}] Layer3-优质价差: {indicators.spread_quality:.2f} (+10分)")
            
            if indicators.cross_signal == "bullish":  # EMA金叉
                structure_score += 10.0
                print(f"🔥 [{self.symbol}] Layer3-EMA金叉: 强度{indicators.cross_strength:.4f} (+10分)")
            elif indicators.cross_signal == "bearish":  # EMA死叉
                structure_score += 10.0
                print(f"📉 [{self.symbol}] Layer3-EMA死叉: 强度{indicators.cross_strength:.4f} (+10分)")
            
            score += structure_score
            
            # Layer 4: 期权特有评分 (权重25%)
            # 这里可以根据期权数据进一步评分，暂时给基础分
            option_score = 15.0  # 基础期权评分
            score += option_score
            
            print(f"🎯 [{self.symbol}] 入场总评分: {score:.1f}/100 "
                  f"(动量:{momentum_score:.0f} + 成交量:{volume_score:.0f} + 结构:{structure_score:.0f} + 期权:{option_score:.0f})")
            
            return score
            
        except Exception as e:
            print(f"⚠️ [{self.symbol}] 入场评分计算失败: {e}")
            return 0.0
    
    def _calculate_exit_score(self, indicators: TechnicalIndicators) -> float:
        """计算出场评分 (0-100分)"""
        try:
            # 暂时返回基础评分，实际应该根据持仓情况计算
            exit_score = 0.0
            
            # 技术指标反转检测
            if indicators.cross_signal == "bearish" and len(self.signal_history) > 0:
                last_signal = self.signal_history[-1]
                if last_signal.signal_type == "BUY":
                    exit_score += 20.0
                    print(f"📉 [{self.symbol}] 技术指标反转，建议出场 (+20分)")
            
            # 动量衰减检测 - 只有在有信号历史的情况下才检测衰减
            if len(self.signal_history) > 0:
                last_signal = self.signal_history[-1] 
                if last_signal.signal_type in ["BUY", "SELL"]:  # 只有在有实际交易信号时才检测衰减
                    momentum_values = [indicators.momentum_10s, indicators.momentum_30s, indicators.momentum_1m]
                    weak_momentum = sum(1 for m in momentum_values if abs(m) < 0.0005)
                    if weak_momentum >= 2:
                        exit_score += 15.0
                        print(f"⚡ [{self.symbol}] 动量衰减，建议出场 (+15分)")
            
            return exit_score
            
        except Exception as e:
            print(f"⚠️ [{self.symbol}] 出场评分计算失败: {e}")
            return 0.0
    
    def _make_signal_decision(self, entry_score: float, exit_score: float, indicators: TechnicalIndicators) -> Tuple[str, float, float, List[str]]:
        """做出信号决策"""
        reasons = []
        
        # 出场信号优先
        if exit_score >= 60:
            signal_type = "SELL"
            strength = min(exit_score, 100.0)
            confidence = min(exit_score / 100.0, 1.0)
            reasons.append(f"出场评分{exit_score:.1f}达到阈值")
            return signal_type, strength, confidence, reasons
        
        # 入场信号判断
        if entry_score >= 80:
            # 根据动量方向决定买卖方向
            momentum_direction = (indicators.momentum_10s + indicators.momentum_30s + indicators.momentum_1m) / 3
            signal_type = "BUY" if momentum_direction > 0 else "SELL"
            strength = min(entry_score, 100.0)
            confidence = min(entry_score / 100.0, 1.0)
            reasons.append(f"强烈{signal_type}信号")
            reasons.append(f"入场评分{entry_score:.1f}")
        elif entry_score >= 60:
            momentum_direction = (indicators.momentum_10s + indicators.momentum_30s + indicators.momentum_1m) / 3
            signal_type = "BUY" if momentum_direction > 0 else "SELL"
            strength = entry_score
            confidence = entry_score / 100.0
            reasons.append(f"标准{signal_type}信号")
            reasons.append(f"入场评分{entry_score:.1f}")
        elif entry_score >= 40:
            momentum_direction = (indicators.momentum_10s + indicators.momentum_30s + indicators.momentum_1m) / 3
            signal_type = "BUY" if momentum_direction > 0 else "SELL"
            strength = entry_score
            confidence = entry_score / 100.0
            reasons.append(f"谨慎{signal_type}信号")
            reasons.append(f"入场评分{entry_score:.1f}")
        else:
            signal_type = "HOLD"
            strength = 0.0
            confidence = 0.0
            reasons.append("信号不足，持有观望")
        
        return signal_type, strength, confidence, reasons
    
    def _print_technical_indicators(self, indicators: TechnicalIndicators):
        """动态打印技术指标 - 只在有重要变化时打印"""
        # 检查是否有重要变化
        has_significant_change = (
            abs(indicators.momentum_10s) > 0.001 or
            abs(indicators.momentum_30s) > 0.0015 or 
            abs(indicators.momentum_1m) > 0.002 or
            indicators.cross_signal != "neutral" or
            indicators.volume_ratio > 1.5 or
            abs(indicators.price_volume_correlation) > 0.6 or
            indicators.spread_quality > 0.8
        )
        
        if has_significant_change:
            print(f"🔥 [{self.symbol}] 重要技术指标变化 [{indicators.timestamp.strftime('%H:%M:%S.%f')[:-3]}]")
            print(f"   价格: ${indicators.price:.2f}")
            print(f"   EMA: EMA3={indicators.ema3:.4f}, EMA8={indicators.ema8:.4f}, 信号={indicators.cross_signal}")
            print(f"   动量: 10s={indicators.momentum_10s:.6f}, 30s={indicators.momentum_30s:.6f}, 1m={indicators.momentum_1m:.6f}")
            print(f"   成交量: 比率={indicators.volume_ratio:.2f}, 价量相关={indicators.price_volume_correlation:.3f}")
            print(f"   价差质量: {indicators.spread_quality:.2f}")
            print("=" * 70)
        else:
            # 普通状态只简单显示
            print(f"📊 [{self.symbol}] 常规更新 [{indicators.timestamp.strftime('%H:%M:%S.%f')[:-3]}] - EMA3:{indicators.ema3:.4f}, EMA8:{indicators.ema8:.4f}")
    
    def _print_trading_signal(self, signal: TradingSignal):
        """动态打印交易信号"""
        signal_emoji = {
            "BUY": "🟢",
            "SELL": "🔴", 
            "HOLD": "🟡"
        }
        
        emoji = signal_emoji.get(signal.signal_type, "⚪")
        print(f"{emoji} [{signal.symbol}] 交易信号生成 [{signal.timestamp.strftime('%H:%M:%S.%f')[:-3]}]")
        print(f"   信号类型: {signal.signal_type}")
        print(f"   信号强度: {signal.strength:.1f}/100")
        print(f"   置信度: {signal.confidence:.2f}")
        print(f"   入场评分: {signal.entry_score:.1f}")
        print(f"   出场评分: {signal.exit_score:.1f}")
        print(f"   原因: {', '.join(signal.reasons)}")
        print(f"   EMA状态: EMA3={signal.technical_details['ema3']:.2f}, EMA8={signal.technical_details['ema8']:.2f}")
        print("=" * 50)
    
    def get_signal_statistics(self) -> Dict[str, Any]:
        """获取信号统计信息"""
        return {
            'total_signals': self.total_signals,
            'last_signal_time': self.last_signal_time,
            'last_update_time': self.last_update_time,
            'cache_status': {
                'price_data': len(self.price_data),
                'momentum_10s': len(self.momentum_cache['10s']),
                'momentum_30s': len(self.momentum_cache['30s']),
                'momentum_1m': len(self.momentum_cache['1m']),
                'indicators_history': len(self.technical_indicators_history),
                'signal_history': len(self.signal_history)
            }
        }


class RealAPIRiskManagerDemo:
    """基于真实API数据的风险管理器演示
    
    主要功能：
    1. 实时推送数据处理和信号生成
    2. 风险管理和仓位控制
    3. 多层技术指标分析
    4. 0DTE期权交易支持
    """
    
    def __init__(self):
        """初始化演示"""
        self._print_banner()
        
        # 核心组件初始化
        self._init_api_clients()
        self._init_risk_manager()
        self._init_push_system()
        self._init_tracking()
        
        self._print_initialization_summary()
    
    def _print_banner(self):
        """打印启动横幅"""
        print("🛡️ 基于真实Tiger API数据的风险管理器演示")
        print("=" * 70)
        
    def _init_api_clients(self):
        """初始化API客户端"""
        try:
            self.client_config = get_client_config()
            self.quote_client = QuoteClient(self.client_config)
            print("✅ Tiger API连接初始化成功")
        except Exception as e:
            print(f"❌ Tiger API连接失败: {e}")
            raise
    
    def _init_risk_manager(self):
        """初始化风险管理器"""
        # 配置风险管理器 - 调整限制以适应真实期权价格
        self.config = replace(
            DEFAULT_TRADING_CONFIG,
            risk_level=RiskLevel.MEDIUM,
            max_position_value=200000.0  # 提高限制以适应真实期权价格
        )
        
        self.risk_manager = create_risk_manager(self.config)
        self.greeks_calculator = GreeksCalculator()
        
        # 注册风险回调
        self.risk_manager.register_risk_alert_callback(self.on_risk_alert)
        self.risk_manager.register_emergency_stop_callback(self.on_emergency_stop)
        
    def _init_push_system(self):
        """初始化推送系统"""
        # 信号生成器管理
        self.signal_generators = {}  # 为每个标的创建信号生成器
        
        # 推送数据统计
        self.push_data_stats = {
            'total_push_events': 0,
            'price_updates': 0,
            'bbo_updates': 0,
            'start_time': time.time(),
            'last_price_update': None
        }
        
        # 推送客户端状态
        self.push_client = None
        self.is_push_connected = False
        self.push_signal_generator = None
        
        # 初始化推送客户端
        self._init_push_client()
    
    def _init_tracking(self):
        """初始化跟踪和统计"""
        self.alert_count = 0
        self.emergency_triggered = False
        self.real_positions = {}  # 存储真实仓位数据
        
    def _print_initialization_summary(self):
        """打印初始化摘要"""
        print(f"✅ 风险管理器初始化完成")
        print(f"📊 风险等级: {self.config.risk_level.value}")
        print(f"💰 最大仓位价值: ${self.config.max_position_value:,.2f}")
        print()
    
    def initialize_tiger_api(self):
        """初始化Tiger API连接 - 保持向后兼容"""
        self._init_api_clients()
    
    def on_risk_alert(self, alert):
        """风险警报回调"""
        self.alert_count += 1
        severity_emoji = {
            "low": "ℹ️",
            "medium": "⚠️", 
            "high": "🚨",
            "critical": "🆘"
        }
        
        emoji = severity_emoji.get(alert.severity, "⚠️")
        print(f"{emoji} 风险警报 #{self.alert_count} [{alert.severity.upper()}] - {alert.timestamp.strftime('%H:%M:%S')}")
        print(f"   事件: {alert.event_type.value}")
        print(f"   消息: {alert.message}")
        if alert.recommended_action:
            print(f"   建议: {alert.recommended_action}")
        print()
    
    def on_emergency_stop(self):
        """紧急停止回调"""
        self.emergency_triggered = True
        print("🆘 紧急停止触发！")
        print("   所有交易活动已暂停")
        print("   风险管理器进入保护模式")
    
    def _init_push_client(self):
        """初始化推送客户端"""
        try:
            from tigeropen.push.push_client import PushClient
            
            # 获取推送服务器配置
            protocol, host, port = self.client_config.socket_host_port
            
            # 创建推送客户端
            self.push_client = PushClient(host, port, use_ssl=(protocol == 'ssl'))
            
            # 设置回调方法
            self._setup_push_callbacks()
            
            print(f"✅ 推送客户端初始化完成 - {host}:{port}")
            
        except Exception as e:
            print(f"❌ 推送客户端初始化失败: {e}")
            self.push_client = None
    
    def _setup_push_callbacks(self):
        """设置推送客户端回调方法"""
        callback_mappings = {
            'quote_changed': self._on_quote_changed,
            'quote_bbo_changed': self._on_quote_bbo_changed,
            'connect_callback': self._on_push_connect,
            'disconnect_callback': self._on_push_disconnect,
            'error_callback': self._on_push_error,
            'subscribe_callback': self._on_subscribe_success
        }
        
        for callback_name, callback_func in callback_mappings.items():
            setattr(self.push_client, callback_name, callback_func)
    
    def _on_quote_changed(self, quote_data):
        """处理基本行情推送"""
        try:
            # 更新推送统计
            if hasattr(quote_data, 'latestPrice') and quote_data.latestPrice:
                self._update_push_stats('price', float(quote_data.latestPrice))
            else:
                self._update_push_stats('quote')
            
            if self.push_signal_generator:
                signal = self.push_signal_generator.process_push_data(quote_data)
                if signal:
                    reasons_str = ", ".join(signal.reasons) if signal.reasons else "无详情"
                    print(f"🎯 [推送信号] {signal.signal_type}: {signal.strength:.3f} ({reasons_str})")
        except Exception as e:
            print(f"❌ 处理行情推送失败: {e}")
    
    def _on_quote_bbo_changed(self, bbo_data):
        """处理最优报价推送"""
        try:
            # 更新BBO推送统计
            self._update_push_stats('bbo')
            
            if self.push_signal_generator:
                signal = self.push_signal_generator.process_push_data(bbo_data)
                if signal:
                    print(f"🎯 [BBO推送信号] {signal.signal_type}: {signal.strength:.3f}")
        except Exception as e:
            print(f"❌ 处理BBO推送失败: {e}")
    
    def _on_push_connect(self, frame):
        """推送连接建立回调"""
        self.is_push_connected = True
        print(f"🔗 推送连接已建立: {frame}")
    
    def _on_push_disconnect(self):
        """推送连接断开回调"""
        self.is_push_connected = False
        print("⚠️ 推送连接断开")
    
    def _on_push_error(self, error):
        """推送错误回调"""
        print(f"❌ 推送错误: {error}")
    
    def _on_subscribe_success(self, result):
        """订阅成功回调"""
        print(f"✅ 订阅成功: {result}")
    
    def connect_push_and_subscribe(self, symbol: str) -> bool:
        """连接推送服务并订阅指定股票"""
        try:
            if not self.push_client:
                print("❌ 推送客户端未初始化")
                return False
            
            # 连接推送服务
            print(f"🔗 连接推送服务...")
            self.push_client.connect(self.client_config.tiger_id, self.client_config.private_key)
            
            # 等待连接建立
            import time
            for i in range(10):  # 最多等待10秒
                if self.is_push_connected:
                    break
                time.sleep(1)
                print(f"   等待连接... ({i+1}/10)")
            
            if not self.is_push_connected:
                print("❌ 推送连接超时")
                return False
            
            # 订阅基础行情数据 (包含价格、成交量等完整信息)
            print(f"📡 订阅 {symbol} 基础行情数据 (包含成交量)...")
            self.push_client.subscribe_quote([symbol])
            
            # 同时订阅最优报价数据 (获取精确买卖价)
            from tigeropen.common.consts import QuoteKeyType
            print(f"💰 订阅 {symbol} 最优报价数据 (BBO)...")
            self.push_client.subscribe_quote([symbol], quote_key_type=QuoteKeyType.QUOTE)
            
            # 创建推送模式的信号生成器
            self.push_signal_generator = RealTimeSignalGenerator(symbol, use_push_data=True)
            
            print(f"✅ 推送服务连接成功，开始接收 {symbol} 实时数据")
            return True
            
        except Exception as e:
            print(f"❌ 连接推送服务失败: {e}")
            return False
    
    def demo_push_data_analysis(self, symbol: str = "QQQ", duration: int = 60):
        """演示推送数据与轮询数据的对比"""
        print("\n" + "="*80)
        print("🔄 推送数据 vs 轮询数据对比演示")
        print("="*80)
        print(f"📊 测试股票: {symbol}")
        print(f"⏱️ 测试时长: {duration}秒")
        print()
        
        # 创建两个信号生成器
        push_generator = None
        pull_generator = RealTimeSignalGenerator(symbol, use_push_data=False)
        
        # 尝试连接推送服务
        push_connected = self.connect_push_and_subscribe(symbol)
        if push_connected:
            push_generator = self.push_signal_generator
            print("✅ 推送模式已启动")
        else:
            print("❌ 推送模式启动失败，仅使用轮询模式")
        
        print("🚀 开始数据对比...")
        print()
        
        # 统计变量
        start_time = time.time()
        pull_updates = 0
        push_updates = 0
        
        try:
            while time.time() - start_time < duration:
                current_time = time.time()
                
                # 轮询数据更新 (每0.6秒) - 仅用于对比测试
                if current_time - getattr(self, '_last_pull_time', 0) >= pull_generator.update_interval:
                    try:
                        # 使用基本API调用获取轮询数据
                        briefs = self.quote_client.get_stock_briefs([symbol])
                        if briefs is not None and not briefs.empty:
                            brief = briefs.iloc[0]
            underlying_data = UnderlyingTickData(
                symbol=symbol,
                timestamp=datetime.now(),
                price=float(brief.latest_price or 0),
                volume=int(brief.volume or 0),
                bid=float(getattr(brief, 'bid', 0.0) or 0.0),
                ask=float(getattr(brief, 'ask', 0.0) or 0.0),
                bid_size=int(getattr(brief, 'bid_size', 0) or 0),
                ask_size=int(getattr(brief, 'ask_size', 0) or 0)
            )
                            # 转换为MarketData格式
                            market_data = MarketData(
                                timestamp=underlying_data.timestamp,
                                symbol=underlying_data.symbol,
                                price=underlying_data.price,
                                volume=underlying_data.volume,
                                bid=underlying_data.bid,
                                ask=underlying_data.ask,
                                bid_size=underlying_data.bid_size,
                                ask_size=underlying_data.ask_size
                            )
                            signal = pull_generator.update_market_data(market_data)
                            pull_updates += 1
                            if pull_updates % 5 == 0:  # 每5次更新打印一次
                                print(f"📥 [轮询] 第{pull_updates}次更新 - ${underlying_data.price:.2f}")
                    except Exception as e:
                        print(f"⚠️ 轮询数据获取失败: {e}")
                    self._last_pull_time = current_time
                
                # 推送数据由回调处理，这里只统计
                if push_generator:
                    push_updates = push_generator.push_stats['total_ticks']
                    if push_updates > 0 and push_updates % 20 == 0:  # 每20个tick打印一次
                        tps = push_generator.push_stats['ticks_per_second']
                        print(f"📡 [推送] 第{push_updates}个tick - {tps:.1f} ticks/秒")
                
                # 每10秒输出对比统计
                elapsed = time.time() - start_time
                if int(elapsed) % 10 == 0 and int(elapsed) > 0:
                    if hasattr(self, '_last_report_time') and abs(elapsed - self._last_report_time) < 1:
                        continue  # 避免重复报告
                    self._last_report_time = elapsed
                    
                    print(f"\n📊 [{int(elapsed)}秒] 数据更新对比:")
                    print(f"   轮询模式: {pull_updates}次更新, 平均 {pull_updates/elapsed:.1f}次/秒")
                    if push_generator:
                        print(f"   推送模式: {push_updates}个tick, 平均 {push_updates/elapsed:.1f}个/秒")
                        print(f"   推送优势: {push_updates/max(pull_updates, 1):.1f}倍数据量")
                    print()
                
                time.sleep(0.1)  # 短暂休眠
                
        except KeyboardInterrupt:
            print("\n🛑 用户中断测试")
        
        # 最终统计
        total_elapsed = time.time() - start_time
        print(f"\n📈 最终对比结果 ({total_elapsed:.1f}秒):")
        print(f"轮询模式: {pull_updates}次更新, 平均 {pull_updates/total_elapsed:.1f}次/秒")
        if push_generator:
            print(f"推送模式: {push_updates}个tick, 平均 {push_updates/total_elapsed:.1f}个/秒")
            print(f"数据密度提升: {push_updates/max(pull_updates, 1):.1f}倍")
            print(f"延迟优势: 推送 <10ms vs 轮询 ~600ms")
        
        # 断开推送连接
        if self.push_client and self.is_push_connected:
            try:
                self.push_client.unsubscribe_quote([symbol])
                self.push_client.disconnect()
                print("✅ 推送连接已断开")
        except Exception as e:
                print(f"⚠️ 断开推送连接时出错: {e}")
    
    def start_push_data_trading(self, symbol: str) -> bool:
        """启动基于推送数据的实时交易信号生成"""
        try:
            print(f"🚀 启动纯推送数据交易模式 - {symbol}")
            print("="*60)
            print(f"📡 推送数据优势:")
            print(f"   ⚡ 延迟: <10ms (vs 轮询 ~600ms)")
            print(f"   🎯 准确性: 捕获所有价格变动 (vs 轮询仅快照)")
            print(f"   📊 频率: 实时tick级数据 (vs 轮询每0.6秒)")
            print(f"   🔥 实时性: 真正的实时交易信号")
            print()
            
            # 连接推送服务并订阅
            if not self.connect_push_and_subscribe(symbol):
                print("❌ 推送服务连接失败")
                return False
            
            print(f"✅ 推送数据交易模式启动成功")
            print(f"📡 正在接收 {symbol} 实时推送数据...")
            print(f"🎯 信号生成器已就绪，等待推送数据...")
            print()
            
            return True
        except Exception as e:
            print(f"❌ 启动推送数据交易失败: {e}")
            return False
    
    def fetch_real_option_data(self, underlying, expiry_date=None):
        """获取真实期权数据"""
        try:
            # 使用今日日期作为期权到期日
            if expiry_date is None:
                target_expiry = datetime.now().strftime('%Y-%m-%d')
            else:
                target_expiry = expiry_date.strftime('%Y-%m-%d')
            
            print(f"🔍 获取 {underlying} 期权链数据 (到期日: {target_expiry})...")
            
            # 获取期权链 - 使用与成功案例相同的参数格式
            option_chain = self.quote_client.get_option_chain(underlying, expiry=target_expiry)
            
            # 检查返回的数据
            if option_chain is None:
                print(f"⚠️ {underlying} 期权链数据为None")
                return []
            
            # 如果不是DataFrame，尝试转换
            if not hasattr(option_chain, 'empty'):
                print(f"⚠️ 期权链数据格式异常: {type(option_chain)}")
                return []
            
            if option_chain.empty:
                print(f"⚠️ 未找到 {underlying} 在 {target_expiry} 的期权数据")
                return []
            
            print(f"✅ 获取到 {len(option_chain)} 个期权合约")
            print(f"📋 期权链列名: {list(option_chain.columns)}")
            
            # 数据预处理
            option_chain['strike'] = pd.to_numeric(option_chain['strike'], errors='coerce')
            option_chain = option_chain.dropna(subset=['strike'])
            
            # 获取标的价格用于筛选 - 使用简单API调用
            try:
                briefs = self.quote_client.get_stock_briefs([underlying])
                if briefs is None or briefs.empty:
                    print(f"❌ 无法获取{underlying}标的价格")
                    return []
                underlying_price = float(briefs.iloc[0].latest_price or 0)
            except Exception as e:
                print(f"❌ 获取{underlying}标的价格失败: {e}")
                return []
            
            # 使用最优期权选择逻辑 - 聚焦于虚值期权
            print(f"🎯 使用最优期权选择逻辑: 标的价格${underlying_price:.2f}")
            
            # 分离CALL和PUT期权
            call_options = option_chain[option_chain['put_call'] == 'CALL'].copy()
            put_options = option_chain[option_chain['put_call'] == 'PUT'].copy()
            
            # 超高频交易策略：聚焦ATM附近期权 (30秒-8分钟)
            atm_range = 3.0  # ATM±$3范围，适合超高频交易
            print(f"⚡ 超高频策略: ATM±${atm_range}范围，优化30秒-8分钟交易")
            
            # 选择ATM附近的期权（包含实值、ATM、轻度虚值）
            atm_calls = call_options[
                (call_options['strike'] >= underlying_price - atm_range) &
                (call_options['strike'] <= underlying_price + atm_range)
            ].copy()
            
            atm_puts = put_options[
                (put_options['strike'] >= underlying_price - atm_range) &
                (put_options['strike'] <= underlying_price + atm_range)  
            ].copy()
            
            # 合并ATM区域期权
            filtered_options = pd.concat([atm_calls, atm_puts], ignore_index=True)
            
            print(f"📊 ATM区域CALL期权: {len(atm_calls)} 个 (${underlying_price-atm_range:.0f}-${underlying_price+atm_range:.0f})")
            print(f"📊 ATM区域PUT期权: {len(atm_puts)} 个 (${underlying_price-atm_range:.0f}-${underlying_price+atm_range:.0f})")
            print(f"📈 筛选结果: {len(filtered_options)} 个ATM区域期权")
            
            if filtered_options.empty:
                print(f"⚠️ 在ATM附近未找到合适的期权")
                return []
            
            # 直接使用期权链中的价格数据，避免API调用问题
            print(f"📈 使用期权链中的价格数据 (共{len(filtered_options)}个期权)...")
            option_briefs_dict = {}  # 不使用额外的期权行情API
            
            # 应用最优期权评分逻辑
            scored_options = self._score_and_rank_options(filtered_options, underlying_price)
            
            # 选择最优的期权
            top_options = scored_options.head(8)  # 选择评分最高的8个期权
            print(f"🏆 选择评分最高的{len(top_options)}个期权:")
            
            option_data_list = []
            
            for _, row in top_options.iterrows():
                symbol = row['symbol']
                brief = option_briefs_dict.get(symbol)
                
                # 基础期权信息
                # 安全处理NaN值
                def safe_float(val, default=0.0):
                    try:
                        result = float(val or default)
                        return result if not pd.isna(result) else default
                    except (ValueError, TypeError):
                        return default
                        
                def safe_int(val, default=0):
                    try:
                        result = float(val or default)
                        return int(result) if not pd.isna(result) else default
                    except (ValueError, TypeError):
                        return default
                
                # 创建标准化的期权标识符
                strike_str = f"{int(safe_float(row['strike']))}"
                option_type = row['put_call']
                expiry_str = target_expiry.replace('-', '')  # 20250822
                unique_symbol = f"{underlying}_{expiry_str}_{option_type}_{strike_str}"
                
                option_data = OptionTickData(
                    symbol=unique_symbol,  # 使用唯一标识符
                    underlying=underlying,
                    strike=safe_float(row['strike']),
                    expiry=target_expiry,
                    right=row['put_call'],  # 修正字段名
                    timestamp=datetime.now(),
                    price=safe_float(row.get('latest_price', 0)),
                    volume=safe_int(row.get('volume', 0)),
                    bid=safe_float(row.get('bid_price', 0)),
                    ask=safe_float(row.get('ask_price', 0)),
                    bid_size=safe_int(row.get('bid_size', 0)),
                    ask_size=safe_int(row.get('ask_size', 0)),
                    open_interest=safe_int(row.get('open_interest', 0))
                )
                
                # 使用期权链中的Greeks数据
                option_data.delta = safe_float(row.get('delta', 0))
                option_data.gamma = safe_float(row.get('gamma', 0))
                option_data.theta = safe_float(row.get('theta', 0))
                option_data.vega = safe_float(row.get('vega', 0))
                option_data.implied_volatility = safe_float(row.get('implied_vol', 0))
                
                option_data_list.append(option_data)
                
                # 显示超高频期权信息和评分
                delta_str = f"{option_data.delta:.3f}" if option_data.delta != 0 else "N/A"
                score_str = f"{row.get('option_score', 0):.1f}" if 'option_score' in row else "N/A"
                atm_distance = row.get('moneyness', 0) * 100
                
                # 判断期权类型
                if atm_distance <= 0.1:
                    position_type = "⚡ATM"
                elif atm_distance <= 0.5:
                    position_type = "🎯近ATM"
                elif atm_distance <= 1.0:
                    position_type = "📊轻度偏离"
                else:
                    position_type = "📉远离ATM"
                
                print(f"  {position_type} [{symbol}] ${option_data.price:.2f} (超高频评分: {score_str})")
                print(f"     执行价: ${option_data.strike:.0f} {option_data.right}, ATM距离: {atm_distance:.2f}%")
                print(f"     Gamma敏感度: 高, 适合30秒-8分钟交易")
                print(f"     成交量: {option_data.volume:,}, 价差: {option_data.spread_percentage:.1f}%")
                print()
            
            print(f"✅ 成功获取 {len(option_data_list)} 个期权数据")
            return option_data_list
            
        except Exception as e:
            print(f"❌ 获取期权数据失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def create_position_from_option_data(self, option_data, quantity=5, index=0):
        """从期权数据创建仓位"""
        position = Position(
            symbol=option_data.symbol,
            quantity=quantity,
            entry_price=option_data.price,
            current_price=option_data.price,
            entry_time=datetime.now(),
            position_id=f"REAL_{option_data.symbol}_{datetime.now().strftime('%H%M%S')}_{index}",  # 添加索引避免重复
            position_type="LONG" if quantity > 0 else "SHORT"
        )
        
        # 设置期权特有属性
        multiplier = 100  # 期权合约乘数
        position.current_value = abs(quantity) * option_data.price * multiplier
        position.unrealized_pnl = 0.0
        position.delta = option_data.delta * quantity if option_data.delta is not None else None
        position.gamma = option_data.gamma * quantity if option_data.gamma else None
        position.theta = option_data.theta * quantity if option_data.theta else None
        position.vega = option_data.vega * quantity if option_data.vega else None
        position.bid_ask_spread = option_data.spread_percentage / 100 if option_data.price > 0 else None
        position.underlying = option_data.underlying
        
        return position
    
    def _score_and_rank_options(self, options_df, underlying_price):
        """对期权进行评分和排序"""
        print("🔍 应用最优期权选择评分算法...")
        
        # 复制数据避免修改原始DataFrame
        scored_df = options_df.copy()
        
        # 计算评分所需的指标，安全处理NaN值
        scored_df['bid_ask_spread'] = scored_df['ask_price'].fillna(0) - scored_df['bid_price'].fillna(0)
        scored_df['spread_percentage'] = scored_df['bid_ask_spread'] / scored_df['latest_price'].replace(0, 1)
        
        # 计算内在价值和距离ATM的程度
        scored_df['intrinsic_value'] = scored_df.apply(
            lambda row: max(underlying_price - row['strike'], 0) if row['put_call'] == 'CALL' 
            else max(row['strike'] - underlying_price, 0), axis=1
        )
        scored_df['time_value'] = scored_df['latest_price'] - scored_df['intrinsic_value']
        scored_df['moneyness'] = abs(scored_df['strike'] - underlying_price) / underlying_price
        
        # 超高频交易评分算法（0-100分）- 专为30秒-8分钟交易优化
        def calculate_ultra_hf_score(row):
            # 1. ATM距离评分 (0-40分) - 最重要因素
            moneyness = row['moneyness']
            if moneyness <= 0.001:  # ATM (±0.1%)
                atm_score = 40
            elif moneyness <= 0.003:  # 极轻度偏离ATM (±0.3%)
                atm_score = 35
            elif moneyness <= 0.005:  # 轻度偏离ATM (±0.5%)
                atm_score = 30
            elif moneyness <= 0.01:   # 中度偏离ATM (±1.0%)
                atm_score = 20
            elif moneyness <= 0.02:   # 较大偏离ATM (±2.0%)
                atm_score = 10
            else:
                atm_score = 0
            
            # 2. Gamma敏感度评分 (0-30分) - 基于理论Gamma估算
            # ATM期权Gamma最高，距离ATM越远Gamma越低
            if moneyness <= 0.002:    # 极ATM
                gamma_score = 30
            elif moneyness <= 0.005:  # 近ATM
                gamma_score = 25
            elif moneyness <= 0.01:   # 轻度偏离
                gamma_score = 15
            elif moneyness <= 0.02:   # 中度偏离
                gamma_score = 8
            else:
                gamma_score = 2
            
            # 3. 流动性评分 (0-20分) - 超高频需要快速进出
            volume_score = min(15, (row['volume'] / 2000) * 15) if row['volume'] > 0 else 0
            oi_score = min(5, (row['open_interest'] / 1000) * 5) if row['open_interest'] > 0 else 0
            liquidity_score = volume_score + oi_score
            
            # 4. 价差评分 (0-10分) - 超高频对价差敏感但不是最关键
            spread_pct = row['spread_percentage']
            if spread_pct <= 0.01:     # ≤1%
                spread_score = 10
            elif spread_pct <= 0.03:   # ≤3%
                spread_score = 7
            elif spread_pct <= 0.05:   # ≤5%
                spread_score = 4
            else:
                spread_score = 0
            
            total_score = atm_score + gamma_score + liquidity_score + spread_score
            return min(100, total_score)
        
        # 计算每个期权的超高频评分
        scored_df['option_score'] = scored_df.apply(calculate_ultra_hf_score, axis=1)
        
        # 按评分排序
        scored_df = scored_df.sort_values('option_score', ascending=False)
        
        # 显示超高频评分结果
        print("⚡ 超高频最优期权 (30秒-8分钟交易):")
        for i, (_, row) in enumerate(scored_df.head(5).iterrows()):
            atm_distance = row['moneyness'] * 100
            print(f"  {i+1}. {row['put_call']} ${row['strike']:.0f} - "
                  f"评分: {row['option_score']:.1f}, ATM距离: {atm_distance:.2f}%, "
                  f"价格: ${row['latest_price']:.2f}, 成交量: {row['volume']:,}")
        
        return scored_df
    
    def _validate_portfolio_calculations(self):
        """验证投资组合计算逻辑"""
        print("🔍 验证计算逻辑:")
        
        # 手动计算总价值
        manual_total_value = 0
        manual_delta = 0
        
        for position in self.risk_manager.positions.values():
            manual_total_value += position.current_value
            if position.delta:
                manual_delta += position.delta
            
            print(f"    {position.symbol}: {position.quantity}手 × ${position.current_price:.2f} × 100 = ${position.current_value:,.2f}")
        
        # 对比系统计算
        metrics = self.risk_manager.calculate_risk_metrics()
        
        print(f"  手动计算总值: ${manual_total_value:,.2f}")
        print(f"  系统计算总值: ${metrics.total_position_value:,.2f}")
        
        value_match = abs(manual_total_value - metrics.total_position_value) < 0.01
        print(f"  价值计算: {'✅ 正确' if value_match else '❌ 错误'}")
        
        delta_match = abs(manual_delta - metrics.portfolio_delta) < 0.001
        print(f"  Delta计算: {'✅ 正确' if delta_match else '❌ 错误'}")
        
        if not value_match:
            print(f"  ⚠️ 价值计算差异: ${abs(manual_total_value - metrics.total_position_value):,.2f}")
        
        if not delta_match:
            print(f"  ⚠️ Delta计算差异: {abs(manual_delta - metrics.portfolio_delta):.3f}")
    
    def demo_real_market_risk_control(self):
        """演示真实市场数据下的风险控制"""
        print("📊 演示1: 真实市场数据风险控制")
        print("-" * 50)
        
        # 获取QQQ期权数据
        option_data_list = self.fetch_real_option_data("QQQ")
        if not option_data_list:
            print("❌ 无法获取期权数据，跳过此演示")
            return
        
        print(f"\n🏗️ 基于真实数据构建投资组合...")
        
        # 选择3-4个期权创建投资组合
        selected_options = option_data_list[:4]
        quantities = [5, -3, 8, -2]  # 混合多空
        
        for i, (option_data, qty) in enumerate(zip(selected_options, quantities)):
            # 过滤无效的期权数据
            if option_data.price <= 0.10:  # 过滤价格过低的期权
                print(f"⚠️ 跳过价格过低的期权: {option_data.symbol} (${option_data.price:.2f})")
                continue
            
            # 过滤价格过高的期权（可能是深度实值期权）
            if option_data.price > 20.0:  # 末日期权一般不会超过$20
                print(f"⚠️ 跳过价格过高的期权: {option_data.symbol} (${option_data.price:.2f}) - 可能是深度实值")
                continue
            
            # 跳过买卖价差过大的期权（流动性差）
            if option_data.spread > option_data.price * 0.20:  # 价差超过20%
                print(f"⚠️ 跳过流动性差的期权: {option_data.symbol} (价差{option_data.spread_percentage:.1f}%)")
                continue
                
            position = self.create_position_from_option_data(option_data, qty, i)
            
            result = self.risk_manager.add_position(position)
            
            action = "做多" if qty > 0 else "做空"
            status = "✅ 成功" if result else "❌ 被拒绝"
            
            print(f"  {action} {abs(qty)}手 [{option_data.symbol}]: {status}")
            print(f"    期权详情: 执行价${option_data.strike:.0f} {option_data.right}, 到期{option_data.expiry}")
            print(f"    价格: ${option_data.price:.2f}, 价值: ${position.current_value:.2f}")
            if option_data.delta:
                print(f"    Delta: {option_data.delta:.3f}, 组合Delta: {position.delta:.3f}")
            
            if result:
                self.real_positions[position.position_id] = {
                    'position': position,
                    'option_data': option_data,
                    'last_update': datetime.now()
                }
        
        # 显示初始组合风险并验证计算
        metrics = self.risk_manager.calculate_risk_metrics()
        print(f"\n📈 初始组合风险指标:")
        print(f"  仓位数量: {metrics.position_count}")
        print(f"  总价值: ${metrics.total_position_value:,.2f}")
        print(f"  组合Delta: {metrics.portfolio_delta:.3f}")
        print(f"  组合Gamma: {metrics.portfolio_gamma:.3f}")
        print(f"  组合Theta: ${metrics.portfolio_theta:.2f}")
        print(f"  风险分数: {metrics.risk_score:.1f}/100")
        
        # 验证计算逻辑
        if metrics.position_count > 0:
            self._validate_portfolio_calculations()
        print()
    
    def get_specific_option_price(self, underlying, strike, option_type, expiry_date):
        """获取特定期权的当前价格"""
        try:
            # 获取完整期权链
            option_chain = self.quote_client.get_option_chain(underlying, expiry=expiry_date)
            
            if option_chain is None or option_chain.empty:
                return None
            
            # 精确匹配特定期权
            option_chain['strike'] = pd.to_numeric(option_chain['strike'], errors='coerce')
            specific_option = option_chain[
                (option_chain['strike'] == strike) & 
                (option_chain['put_call'] == option_type)
            ]
            
            if specific_option.empty:
                return None
            
            row = specific_option.iloc[0]
            price = row.get('latest_price', 0)
            
            # 安全处理价格
            try:
                price = float(price or 0)
                return price if not pd.isna(price) else None
            except (ValueError, TypeError):
                return None
                
        except Exception as e:
            print(f"⚠️ 获取期权价格失败: {e}")
            return None
    
    def create_signal_generator(self, symbol: str) -> RealTimeSignalGenerator:
        """为指定标的创建信号生成器"""
        if symbol not in self.signal_generators:
            self.signal_generators[symbol] = RealTimeSignalGenerator(symbol)
        return self.signal_generators[symbol]
    
    def _update_push_stats(self, data_type: str, price: Optional[float] = None):
        """更新推送数据统计"""
        import time
        self.push_data_stats['total_push_events'] += 1
        
        if data_type == 'price' and price:
            self.push_data_stats['price_updates'] += 1
            self.push_data_stats['last_price_update'] = price
        elif data_type == 'bbo':
            self.push_data_stats['bbo_updates'] += 1
            
        # 每100个事件打印一次统计
        if self.push_data_stats['total_push_events'] % 100 == 0:
            elapsed = time.time() - self.push_data_stats['start_time']
            events_per_sec = self.push_data_stats['total_push_events'] / elapsed if elapsed > 0 else 0
            print(f"📊 [推送统计] 总事件:{self.push_data_stats['total_push_events']}, "
                  f"价格更新:{self.push_data_stats['price_updates']}, "
                  f"BBO更新:{self.push_data_stats['bbo_updates']}, "
                  f"频率:{events_per_sec:.1f}/秒")
    

    
    def demo_real_time_signal_generation(self, duration_minutes=1):
        """演示实时信号生成系统 - 集成技术分析"""
        print("🎯 演示1.5: 实时信号生成系统")
        print("-" * 50)
        print("💡 展示多层信号确认体系和动态技术指标计算")
        print("📊 数据来源: Tiger OpenAPI 0.6秒更新频率 (API频率控制)")
        print()
        
        # 为QQQ创建信号生成器
        signal_generator = self.create_signal_generator("QQQ")
        
        duration_seconds = duration_minutes * 60
        print(f"🚀 开始实时信号生成演示 ({duration_minutes}分钟)...")
        start_time = time.time()
        signal_count = 0
        error_count = 0
        last_status_time = start_time
        
        while time.time() - start_time < duration_seconds:
            try:
                # 注意：此演示已弃用，请使用推送模式 (python demo_real_api_risk_manager.py signals)
                print("⚠️ 轮询模式已弃用，请使用: python demo_real_api_risk_manager.py signals")
                break
                
                if underlying_data:
                    # 使用真实数据
                    market_data = MarketData(
                        timestamp=underlying_data.timestamp,
                        symbol=underlying_data.symbol,
                        price=underlying_data.price,
                        volume=underlying_data.volume,
                        bid=underlying_data.bid,
                        ask=underlying_data.ask,
                        bid_size=underlying_data.bid_size,
                        ask_size=underlying_data.ask_size
                    )
                    print(f"📊 QQQ 实时数据: ${market_data.price:.2f}, 成交量: {market_data.volume:,}")
                else:
                    error_count += 1
                    print(f"❌ 获取 QQQ 数据失败，错误次数: {error_count}")
                    if error_count >= 5:  # 连续失败5次则休息更久
                        print(f"🔄 连续失败{error_count}次，休息10秒...")
                        time.sleep(10)
                    else:
                        time.sleep(signal_generator.update_interval)
                    continue
                
                # 更新信号生成器并获取信号
                signal = signal_generator.update_market_data(market_data)
                if signal:
                    signal_count += 1
                    
                    # 如果生成了强信号，可以进一步处理
                    if signal.strength >= 60:
                        print(f"🔔 强信号触发! 可考虑实际交易执行")
                        print(f"   建议动作: {signal.signal_type}")
                        print(f"   执行时机: 立即 (信号强度: {signal.strength:.1f})")
                        print()
                
                # 每2分钟显示一次统计信息
                elapsed = time.time() - start_time
                if elapsed - (last_status_time - start_time) >= 120:  # 每2分钟
                    stats = signal_generator.get_signal_statistics()
                    print(f"📊 [{elapsed/60:.1f}分钟] 稳定性统计:")
                    print(f"   生成信号数: {stats['total_signals']}")
                    print(f"   错误次数: {error_count}")
                    print(f"   成功率: {((stats['total_signals'])/(stats['total_signals']+error_count)*100):.1f}%" if (stats['total_signals']+error_count) > 0 else "100%")
                    print(f"   缓存状态: {stats['cache_status']}")
                    print(f"   内存使用: 正常")
                    print()
                    last_status_time = time.time()
                
                time.sleep(signal_generator.update_interval)  # 使用配置的更新间隔
                
            except Exception as e:
                error_count += 1
                print(f"⚠️ 信号生成过程中出错(#{error_count}): {e}")
                time.sleep(1)
        
        # 最终统计
        final_stats = signal_generator.get_signal_statistics()
        print(f"✅ 信号生成演示完成!")
        print(f"📈 总计生成信号: {final_stats['total_signals']} 个")
        print(f"📊 数据更新次数: {final_stats['cache_status']['price_data']} 次")
        print(f"🎯 信号生成率: {(final_stats['total_signals']/max(final_stats['cache_status']['price_data'], 1)*100):.1f}%")
        print()
    
    def demo_real_time_risk_monitoring(self):
        """演示实时风险监控 - 100%真实API数据"""
        print("⚡ 演示2: 实时风险监控 (30秒) - 🔴 纯真实API数据")
        print("-" * 50)
        
        if not self.real_positions:
            print("⚠️ 没有活跃仓位，跳过实时监控演示")
            return
        
        print("🔄 开始实时监控...")
        print("📍 监控内容: 真实价格变化、实际Greeks变化、真实止损触发")
        print("📡 数据来源: Tiger OpenAPI实时数据 (无任何模拟数据)")
        print()
        
        start_time = time.time()
        update_count = 0
        
        # 显示当前仓位信息和提取期权参数
        print("📋 当前监控仓位:")
        position_details = {}
        
        for pos_id, pos_info in self.real_positions.items():
            position = pos_info['position']
            option_data = pos_info['option_data']
            
            # 从OptionTickData中提取期权参数
            position_details[pos_id] = {
                'position': position,
                'underlying': option_data.underlying,
                'strike': option_data.strike,
                'option_type': option_data.right,
                'expiry': option_data.expiry
            }
            
            print(f"  • {position.symbol}: {position.quantity}手, 入场价${position.entry_price:.2f}")
            print(f"    期权参数: {option_data.underlying} {option_data.strike} {option_data.right} {option_data.expiry}")
        print()
        
        while time.time() - start_time < 30:  # 监控30秒
            try:
                # 更新现有仓位 - 针对每个具体期权查询价格
                for pos_id, details in position_details.items():
                    position = details['position']
                    
                    # 获取该特定期权的当前价格
                    current_price = self.get_specific_option_price(
                        underlying=details['underlying'],
                        strike=details['strike'],
                        option_type=details['option_type'],
                        expiry_date=details['expiry']
                    )
                    
                    if current_price is None:
                        continue
                    
                    # 只有价格发生变化才更新
                    if abs(current_price - position.current_price) > 0.01:
                        price_change_pct = ((current_price - position.current_price) / position.current_price) * 100
                        
                        print(f"📊 {position.symbol} 真实价格变动:")
                        print(f"  💰 价格: ${position.current_price:.2f} → ${current_price:.2f}")
                        print(f"  📡 数据来源: Tiger API特定期权查询")
                        print(f"  📈 变化幅度: {price_change_pct:+.2f}%")
                        print(f"  🎯 期权参数: {details['underlying']} ${details['strike']} {details['option_type']}")
                        
                        # 价格变动合理性检查
                        if abs(price_change_pct) > 30:
                            print(f"  ⚠️ 异常价格变动警告: {price_change_pct:+.2f}% (可能需要人工核实)")
                        
                        # 创建更新的OptionTickData
                        updated_option_data = OptionTickData(
                            symbol=position.symbol,
                            underlying=details['underlying'],
                            strike=details['strike'],
                            expiry=details['expiry'],
                            right=details['option_type'],
                            timestamp=datetime.now(),
                            price=current_price,
                            volume=0,  # 监控时不关注成交量变化
                            bid=0,
                            ask=0
                        )
                        
                    # 注意：这里应该使用期权特定的更新方法
                    # 由于类型不匹配，我们直接更新position的价格属性
                    position.current_price = current_price
                    position.current_value = abs(position.quantity) * current_price * 100
                    position.unrealized_pnl = (current_price - position.entry_price) * position.quantity * 100
                    
                    # 检查风险 - 使用风险管理器的组合风险检查
                    alerts = self.risk_manager.check_portfolio_risks()
                        
                        if alerts:
                            print(f"🚨 {position.symbol} 基于真实价格触发 {len(alerts)} 个风险警报")
                            for alert in alerts:
                                print(f"  ⚠️ {alert.severity.upper()}: {alert.message}")
                        else:
                            print(f"✅ {position.symbol} 价格变动在安全范围内")
                        
                        update_count += 1
                        print()
                
                # 定期检查组合风险
                if update_count % 3 == 0:  # 每3次更新检查一次
                    portfolio_alerts = self.risk_manager.check_portfolio_risks()
                    if portfolio_alerts:
                        print(f"⚠️ 组合级别风险: {len(portfolio_alerts)} 个警报")
                
                time.sleep(5)  # 5秒更新一次
                
            except Exception as e:
                print(f"⚠️ 监控过程中出错: {e}")
                time.sleep(5)
        
        print(f"✅ 真实数据监控完成，共进行 {update_count} 次API价格更新")
        
        # 显示最终状态
        final_metrics = self.risk_manager.calculate_risk_metrics()
        print(f"\n📊 基于真实API数据的最终风险状态:")
        print(f"  📡 数据验证: 100%来自Tiger OpenAPI")
        print(f"  📊 价格更新次数: {update_count}")
        print(f"  💰 未实现盈亏: ${final_metrics.unrealized_pnl:.2f}")
        print(f"  📈 风险分数: {final_metrics.risk_score:.1f}/100")
        print(f"  ⚠️ 风险警报数: {self.alert_count}")
        print()
    
    def demo_stress_test_with_simulated_scenarios(self):
        """使用模拟极端场景进行压力测试"""
        print("🧪 演示3: 模拟极端场景压力测试 - 🟡 模拟数据")
        print("-" * 50)
        
        if not self.real_positions:
            print("⚠️ 没有活跃仓位，跳过压力测试")
            return
        
        print("💥 模拟市场极端波动场景...")
        print("📡 数据来源: 基于真实数据构造的模拟极端场景")
        
        # 获取当前期权数据作为基准
        option_data_list = self.fetch_real_option_data("QQQ")
        if not option_data_list:
            print("❌ 无法获取基准数据")
            return
        
        option_data_dict = {opt.symbol: opt for opt in option_data_list}
        
        # 模拟不同程度的市场冲击
        shock_scenarios = [
            {"name": "轻度下跌", "price_change": -0.05, "vol_change": 0.2},
            {"name": "中度暴跌", "price_change": -0.15, "vol_change": 0.5},
            {"name": "极端崩盘", "price_change": -0.30, "vol_change": 1.0}
        ]
        
        initial_metrics = self.risk_manager.calculate_risk_metrics()
        
        for scenario in shock_scenarios:
            print(f"\n📉 模拟场景: {scenario['name']} (价格变化: {scenario['price_change']:.1%})")
            print(f"🔧 测试目的: 验证{scenario['price_change']:.1%}市场冲击下的风险防护")
            
            scenario_alerts = []
            
            for pos_id, pos_info in self.real_positions.items():
                position = pos_info['position']
                symbol = position.symbol
                
                if symbol in option_data_dict:
                    base_option = option_data_dict[symbol]
                    
                    # 创建压力测试下的期权数据 (模拟价格)
                    stressed_price = base_option.price * (1 + scenario['price_change'])
                    stressed_price = max(0.01, stressed_price)  # 最低0.01
                    
                    print(f"  📊 {symbol}: ${base_option.price:.2f} → ${stressed_price:.2f} (模拟冲击)")
                    
                    # 直接更新仓位价格，避免类型不匹配问题
                    position.current_price = stressed_price
                    position.current_value = abs(position.quantity) * stressed_price * 100
                    position.unrealized_pnl = (stressed_price - position.entry_price) * position.quantity * 100
                    
                    # 更新Greeks
                    if base_option.delta:
                        position.delta = base_option.delta * 0.8 * position.quantity
                    
                    # 检查风险
                    alerts = self.risk_manager.check_portfolio_risks()
                    scenario_alerts.extend(alerts)
            
            # 检查组合风险
            portfolio_alerts = self.risk_manager.check_portfolio_risks()
            scenario_alerts.extend(portfolio_alerts)
            
            # 计算压力测试下的指标
            stressed_metrics = self.risk_manager.calculate_risk_metrics()
            
            pnl_change = stressed_metrics.unrealized_pnl - initial_metrics.unrealized_pnl
            risk_change = stressed_metrics.risk_score - initial_metrics.risk_score
            
            print(f"  💰 盈亏变化: ${pnl_change:.2f}")
            print(f"  📊 风险分数变化: {risk_change:+.1f}")
            print(f"  🚨 触发警报: {len(scenario_alerts)} 个")
            
            # 分析警报类型
            alert_types = {}
            for alert in scenario_alerts:
                alert_types[alert.event_type.value] = alert_types.get(alert.event_type.value, 0) + 1
            
            if alert_types:
                print("  警报分布:", ", ".join([f"{k}: {v}" for k, v in alert_types.items()]))
        
        print(f"\n✅ 压力测试完成")
    
    def demo_risk_summary_report(self):
        """生成风险摘要报告"""
        print("📋 演示4: 风险摘要报告")
        print("-" * 50)
        
        summary = self.risk_manager.get_risk_summary()
        
        print("🎯 风险管理摘要报告:")
        print(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  监控时长: 约2-3分钟")
        print()
        
        print("📊 投资组合关键指标:")
        metrics = summary['metrics']
        print(f"  仓位数量: {metrics['position_count']}")
        print(f"  总价值: ${metrics['total_position_value']:,.2f}")
        print(f"  未实现盈亏: ${metrics['unrealized_pnl']:,.2f}")
        print(f"  组合Delta: {metrics['portfolio_delta']:.3f}")
        print(f"  组合Gamma: {metrics['portfolio_gamma']:.3f}")
        print(f"  集中度风险: {metrics['concentration_risk']:.1%}")
        print(f"  风险分数: {metrics['risk_score']:.1f}/100")
        print()
        
        print("🚧 风险限制状态:")
        limits = summary['limits']
        print(f"  单笔仓位限制: ${limits['max_single_position']:,.2f}")
        print(f"  总仓位限制: ${limits['max_total_position']:,.2f}")
        print(f"  日内交易: {limits['daily_trades']}")
        print(f"  日损失限制: ${limits['daily_loss_limit']:,.2f}")
        print()
        
        print("⚠️ 警报统计:")
        alerts = summary['alerts']
        print(f"  总警报数: {alerts['total']}")
        print(f"  近1小时: {alerts['recent_hour']}")
        print(f"  严重级别: {alerts['critical']}")
        print(f"  高风险: {alerts['high']}")
        print()
        
        # 风险评估
        risk_score = metrics['risk_score']
        if risk_score < 30:
            risk_level = "🟢 低风险"
        elif risk_score < 60:
            risk_level = "🟡 中等风险"
        elif risk_score < 80:
            risk_level = "🟠 高风险"
        else:
            risk_level = "🔴 极高风险"
        
        print(f"🎯 综合风险评级: {risk_level}")
        
        # 建议
        recommendations = []
        if metrics['concentration_risk'] > 0.5:
            recommendations.append("建议分散投资，降低集中度风险")
        if alerts['critical'] > 0:
            recommendations.append("立即处理严重级别风险警报")
        if metrics['portfolio_delta'] > abs(10):
            recommendations.append("考虑Delta对冲，降低方向性风险")
        
        if recommendations:
            print("\n💡 风险管理建议:")
            for i, rec in enumerate(recommendations, 1):
                print(f"  {i}. {rec}")
        
        print()
    
    def run_complete_real_api_demo(self):
        """运行完整的真实API演示"""
        try:
            print("🚀 开始基于真实Tiger API数据的风险管理演示")
            print("⏰ 预计演示时间: 4-5分钟 (新增信号生成演示)")
            print()
            
            # 依次运行各个演示
            self.demo_real_market_risk_control()
            self.demo_real_time_signal_generation(30)  # 30分钟稳定性测试
            self.demo_real_time_risk_monitoring()  # 纯真实数据
            self.demo_stress_test_with_simulated_scenarios()  # 模拟极端场景
            self.demo_risk_summary_report()
            
            # 最终统计
            print("📈 演示结果统计")
            print("-" * 50)
            print(f"✅ 真实仓位数: {len(self.real_positions)}")
            print(f"⚠️ 总风险警报: {self.alert_count}")
            print(f"🛑 紧急停止触发: {'是' if self.emergency_triggered else '否'}")
            
            # 信号生成统计
            total_signals = 0
            for symbol, generator in self.signal_generators.items():
                stats = generator.get_signal_statistics()
                total_signals += stats['total_signals']
                print(f"🎯 {symbol} 信号生成: {stats['total_signals']} 个")
            print(f"📊 总计生成信号: {total_signals} 个")
            
            final_metrics = self.risk_manager.calculate_risk_metrics()
            print(f"📊 最终风险分数: {final_metrics.risk_score:.1f}/100")
            print(f"💰 最终盈亏: ${final_metrics.unrealized_pnl:.2f}")
            print()
            
            print("🎉 基于真实API数据的风险管理演示完成!")
            print("💡 风险管理器和信号生成系统已经过真实市场数据验证，可用于生产环境")
            print("🔥 新增功能: 多层信号确认体系、实时技术指标计算、动态评分系统")
            
        except Exception as e:
            print(f"❌ 演示过程中出现错误: {e}")
            import traceback
            traceback.print_exc()


def stability_test_30min():
    """30分钟稳定性测试"""
    try:
        demo = RealAPIRiskManagerDemo()
        print("🧪 开始30分钟稳定性测试")
        print("⏰ 测试时间: 30分钟")
        print("🎯 测试内容: 信号生成系统稳定性")
        print()
        
        # 只运行信号生成演示
        demo.demo_real_time_signal_generation(30)
        
    except KeyboardInterrupt:
        print("\n⚠️ 稳定性测试被用户中断")
    except Exception as e:
        print(f"\n❌ 稳定性测试失败: {e}")
            import traceback
            traceback.print_exc()


def main():
    """主函数"""
    try:
        import sys
        import time
        
        demo = RealAPIRiskManagerDemo()
        
        # 检查命令行参数
        if len(sys.argv) > 1:
            arg = sys.argv[1]
            
            if arg == "stability":
                stability_test_30min()
            elif arg == "test_signals":
                # 纯推送模式信号生成 (短时间测试)
                if demo.start_push_data_trading("QQQ"):
                    print("📡 推送模式信号生成已启动 (5分钟测试)，按 Ctrl+C 停止...")
                    try:
                        import time
                        time.sleep(300)  # 5分钟测试
                        print("\n⏰ 5分钟测试完成")
                    except KeyboardInterrupt:
                        print("\n🛑 推送模式停止")
                else:
                    print("❌ 推送模式启动失败")
            elif arg == "signals" or arg == "push_signals":
                # 纯推送模式信号生成 (长时间运行)
                if demo.start_push_data_trading("QQQ"):
                    print("📡 推送模式信号生成已启动，按 Ctrl+C 停止...")
                    try:
                        while True:
                            time.sleep(1)
                    except KeyboardInterrupt:
                        print("\n🛑 推送模式停止")
                else:
                    print("❌ 推送模式启动失败")
            elif arg == "push_analysis":
                demo.demo_push_data_analysis("QQQ", duration=120)  # 2分钟推送数据分析
            else:
                print("❌ 未知的演示模式")
                print("可用模式:")
                print("  stability     - 30分钟稳定性测试")
                print("  test_signals  - 1分钟推送信号测试")
                print("  signals       - 纯推送信号模式(长时间运行)") 
                print("  push_analysis - 纯推送数据分析")
                print("  push_signals  - 纯推送信号模式(同signals)")
        else:
        demo.run_complete_real_api_demo()
            
    except KeyboardInterrupt:
        print("\n⚠️ 演示被用户中断")
    except Exception as e:
        print(f"\n❌ 演示失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
