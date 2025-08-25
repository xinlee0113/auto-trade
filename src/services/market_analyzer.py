#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场分析器 - 明确分离整体市场和个股分析

设计原则:
1. 整体市场分析: 基于VIX、系统性风险指标
2. 个股趋势分析: 基于价格、成交量、技术指标
3. 不混合两种不同层面的分析
4. 为不同的交易策略提供明确的信号

Author: AI Assistant
Date: 2024-01-22
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np

from ..models.trading_models import UnderlyingTickData
from ..utils.logger_config import get_logger

logger = get_logger(__name__)


class OverallMarketState(Enum):
    """整体市场状态 - 基于系统性风险指标"""
    NORMAL = "normal"           # 正常: VIX<20, 系统性风险低
    ELEVATED_RISK = "elevated"  # 风险升高: VIX 20-25, 不确定性增加
    HIGH_RISK = "high_risk"     # 高风险: VIX 25-35, 市场担忧
    CRISIS = "crisis"           # 危机: VIX>35, 系统性危机


class SymbolTrendState(Enum):
    """个股趋势状态 - 基于技术分析"""
    SIDEWAYS = "sideways"          # 横盘整理
    UPTREND_WEAK = "uptrend_weak"  # 弱上涨趋势
    UPTREND_STRONG = "uptrend_strong"  # 强上涨趋势
    DOWNTREND_WEAK = "downtrend_weak"  # 弱下跌趋势
    DOWNTREND_STRONG = "downtrend_strong"  # 强下跌趋势
    BREAKOUT_UP = "breakout_up"    # 向上突破
    BREAKOUT_DOWN = "breakout_down"  # 向下突破


class VolumeState(Enum):
    """成交量状态"""
    LOW = "low"           # 成交量偏低
    NORMAL = "normal"     # 成交量正常
    HIGH = "high"         # 成交量偏高
    SPIKE = "spike"       # 成交量异常激增


@dataclass
class OverallMarketAnalysis:
    """整体市场分析结果"""
    timestamp: datetime
    state: OverallMarketState
    vix_value: float
    vix_level: str
    risk_score: float        # 0-1，系统性风险评分
    trading_recommended: bool  # 是否建议进行交易
    confidence: float        # 0-1，分析置信度
    reason: str             # 分析原因


@dataclass
class SymbolTrendAnalysis:
    """个股趋势分析结果"""
    symbol: str
    timestamp: datetime
    trend_state: SymbolTrendState
    volume_state: VolumeState
    momentum_score: float    # -1到1，动量评分
    volatility_score: float  # 0-1，波动率评分
    support_level: Optional[float]  # 支撑位
    resistance_level: Optional[float]  # 阻力位
    confidence: float        # 0-1，分析置信度
    signals: List[str]       # 交易信号列表


class OverallMarketAnalyzer:
    """整体市场分析器"""
    
    def __init__(self):
        self.logger = get_logger(f"{__name__}.OverallMarketAnalyzer")
        self.vix_history = []  # VIX历史数据
        self.market_history = []  # 市场状态历史
    
    def analyze_market(self, vix_value: float, market_status: dict) -> OverallMarketAnalysis:
        """分析整体市场状态"""
        timestamp = datetime.now()
        
        # 1. VIX分析
        vix_level, risk_score = self._analyze_vix(vix_value)
        
        # 2. 市场状态评估
        state = self._determine_market_state(vix_value, risk_score)
        
        # 3. 交易建议
        trading_recommended = self._should_trade(state, market_status)
        
        # 4. 置信度计算
        confidence = self._calculate_confidence(vix_value)
        
        # 5. 原因说明
        reason = self._generate_reason(state, vix_value, vix_level)
        
        analysis = OverallMarketAnalysis(
            timestamp=timestamp,
            state=state,
            vix_value=vix_value,
            vix_level=vix_level,
            risk_score=risk_score,
            trading_recommended=trading_recommended,
            confidence=confidence,
            reason=reason
        )
        
        # 保存历史
        self.market_history.append(analysis)
        if len(self.market_history) > 100:
            self.market_history.pop(0)
        
        return analysis
    
    def _analyze_vix(self, vix_value: float) -> Tuple[str, float]:
        """分析VIX水平"""
        if vix_value < 15:
            return "very_low", 0.1
        elif vix_value < 20:
            return "normal", 0.3
        elif vix_value < 25:
            return "elevated", 0.6
        elif vix_value < 35:
            return "high", 0.8
        else:
            return "extreme", 1.0
    
    def _determine_market_state(self, vix_value: float, risk_score: float) -> OverallMarketState:
        """确定整体市场状态"""
        if vix_value > 35:
            return OverallMarketState.CRISIS
        elif vix_value > 25:
            return OverallMarketState.HIGH_RISK
        elif vix_value > 20:
            return OverallMarketState.ELEVATED_RISK
        else:
            return OverallMarketState.NORMAL
    
    def _should_trade(self, state: OverallMarketState, market_status: dict) -> bool:
        """判断是否建议交易"""
        # 市场未开盘不交易
        if not market_status.get('is_trading', False):
            return False
        
        # 危机状态下谨慎交易
        if state == OverallMarketState.CRISIS:
            return False
        
        return True
    
    def _calculate_confidence(self, vix_value: float) -> float:
        """计算分析置信度"""
        # VIX数据质量较高，基础置信度0.8
        base_confidence = 0.8
        
        # 极端值时置信度稍低
        if vix_value > 50 or vix_value < 10:
            return base_confidence * 0.9
        
        return base_confidence
    
    def _generate_reason(self, state: OverallMarketState, vix_value: float, vix_level: str) -> str:
        """生成分析原因"""
        state_desc = {
            OverallMarketState.NORMAL: "市场波动率正常，系统性风险低",
            OverallMarketState.ELEVATED_RISK: "市场不确定性增加，需要谨慎",
            OverallMarketState.HIGH_RISK: "市场担忧情绪较重，高度警惕",
            OverallMarketState.CRISIS: "市场恐慌情绪严重，暂停交易"
        }
        
        return f"VIX {vix_value:.1f} ({vix_level}), {state_desc.get(state, '未知状态')}"


class SymbolTrendAnalyzer:
    """个股趋势分析器"""
    
    def __init__(self, lookback_periods: int = 20):
        self.logger = get_logger(f"{__name__}.SymbolTrendAnalyzer")
        self.lookback_periods = lookback_periods
        self.price_history: Dict[str, List[float]] = {}
        self.volume_history: Dict[str, List[int]] = {}
        self.analysis_history: Dict[str, List[SymbolTrendAnalysis]] = {}
    
    def analyze_symbol(self, tick_data: UnderlyingTickData) -> SymbolTrendAnalysis:
        """分析个股趋势"""
        symbol = tick_data.symbol
        timestamp = tick_data.timestamp
        
        # 更新历史数据
        self._update_history(tick_data)
        
        # 1. 趋势分析
        trend_state = self._analyze_trend(symbol, tick_data.price)
        
        # 2. 成交量分析
        volume_state = self._analyze_volume(symbol, tick_data.volume)
        
        # 3. 动量计算
        momentum_score = self._calculate_momentum(symbol)
        
        # 4. 波动率计算
        volatility_score = self._calculate_volatility(symbol)
        
        # 5. 支撑阻力位
        support_level, resistance_level = self._find_support_resistance(symbol)
        
        # 6. 交易信号
        signals = self._generate_signals(trend_state, volume_state, momentum_score)
        
        # 7. 置信度
        confidence = self._calculate_symbol_confidence(symbol)
        
        analysis = SymbolTrendAnalysis(
            symbol=symbol,
            timestamp=timestamp,
            trend_state=trend_state,
            volume_state=volume_state,
            momentum_score=momentum_score,
            volatility_score=volatility_score,
            support_level=support_level,
            resistance_level=resistance_level,
            confidence=confidence,
            signals=signals
        )
        
        # 保存历史
        if symbol not in self.analysis_history:
            self.analysis_history[symbol] = []
        self.analysis_history[symbol].append(analysis)
        if len(self.analysis_history[symbol]) > 100:
            self.analysis_history[symbol].pop(0)
        
        return analysis
    
    def _update_history(self, tick_data: UnderlyingTickData):
        """更新历史数据"""
        symbol = tick_data.symbol
        
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        if symbol not in self.volume_history:
            self.volume_history[symbol] = []
        
        self.price_history[symbol].append(tick_data.price)
        self.volume_history[symbol].append(tick_data.volume)
        
        # 保持指定长度
        if len(self.price_history[symbol]) > self.lookback_periods:
            self.price_history[symbol].pop(0)
        if len(self.volume_history[symbol]) > self.lookback_periods:
            self.volume_history[symbol].pop(0)
    
    def _analyze_trend(self, symbol: str, current_price: float) -> SymbolTrendState:
        """分析价格趋势"""
        prices = self.price_history.get(symbol, [])
        if len(prices) < 5:
            return SymbolTrendState.SIDEWAYS
        
        # 简单趋势分析：比较短期和长期均线
        short_ma = np.mean(prices[-5:])  # 5周期均线
        long_ma = np.mean(prices[-10:]) if len(prices) >= 10 else short_ma
        
        # 计算趋势强度
        trend_strength = abs(short_ma - long_ma) / long_ma if long_ma > 0 else 0
        
        if trend_strength < 0.005:  # 0.5%以内认为是横盘
            return SymbolTrendState.SIDEWAYS
        elif short_ma > long_ma:
            return SymbolTrendState.UPTREND_STRONG if trend_strength > 0.02 else SymbolTrendState.UPTREND_WEAK
        else:
            return SymbolTrendState.DOWNTREND_STRONG if trend_strength > 0.02 else SymbolTrendState.DOWNTREND_WEAK
    
    def _analyze_volume(self, symbol: str, current_volume: int) -> VolumeState:
        """分析成交量状态"""
        volumes = self.volume_history.get(symbol, [])
        if len(volumes) < 5:
            return VolumeState.NORMAL
        
        avg_volume = np.mean(volumes[:-1])  # 排除当前成交量
        if avg_volume == 0:
            return VolumeState.NORMAL
        
        volume_ratio = current_volume / avg_volume
        
        if volume_ratio > 3:
            return VolumeState.SPIKE
        elif volume_ratio > 1.5:
            return VolumeState.HIGH
        elif volume_ratio < 0.5:
            return VolumeState.LOW
        else:
            return VolumeState.NORMAL
    
    def _calculate_momentum(self, symbol: str) -> float:
        """计算动量评分 (-1到1)"""
        prices = self.price_history.get(symbol, [])
        if len(prices) < 3:
            return 0.0
        
        # 计算价格变化率
        price_change = (prices[-1] - prices[-3]) / prices[-3] if prices[-3] > 0 else 0
        
        # 归一化到 -1 到 1
        return max(-1, min(1, price_change * 50))  # 2%的变化对应1.0
    
    def _calculate_volatility(self, symbol: str) -> float:
        """计算波动率评分 (0到1)"""
        prices = self.price_history.get(symbol, [])
        if len(prices) < 5:
            return 0.0
        
        # 计算价格波动率
        returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices)) if prices[i-1] > 0]
        if not returns:
            return 0.0
        
        volatility = np.std(returns)
        # 归一化到 0-1，5%日波动率对应1.0
        return min(1.0, volatility * 100 / 5)
    
    def _find_support_resistance(self, symbol: str) -> Tuple[Optional[float], Optional[float]]:
        """寻找支撑位和阻力位"""
        prices = self.price_history.get(symbol, [])
        if len(prices) < 10:
            return None, None
        
        # 简单的支撑阻力位计算
        support = min(prices[-10:])
        resistance = max(prices[-10:])
        
        return support, resistance
    
    def _generate_signals(self, trend_state: SymbolTrendState, volume_state: VolumeState, momentum: float) -> List[str]:
        """生成交易信号"""
        signals = []
        
        # 趋势信号
        if trend_state in [SymbolTrendState.UPTREND_STRONG, SymbolTrendState.BREAKOUT_UP]:
            signals.append("趋势买入")
        elif trend_state in [SymbolTrendState.DOWNTREND_STRONG, SymbolTrendState.BREAKOUT_DOWN]:
            signals.append("趋势卖出")
        
        # 动量信号
        if momentum > 0.5:
            signals.append("动量买入")
        elif momentum < -0.5:
            signals.append("动量卖出")
        
        # 成交量信号
        if volume_state == VolumeState.SPIKE:
            signals.append("成交量突增")
        
        return signals
    
    def _calculate_symbol_confidence(self, symbol: str) -> float:
        """计算个股分析置信度"""
        prices = self.price_history.get(symbol, [])
        
        # 数据点越多，置信度越高
        data_confidence = min(1.0, len(prices) / self.lookback_periods)
        
        return 0.7 * data_confidence  # 基础置信度较低，需要更多数据


class MarketAnalyzer:
    """市场分析器 - 整合整体市场和个股分析"""
    
    def __init__(self):
        self.overall_analyzer = OverallMarketAnalyzer()
        self.symbol_analyzer = SymbolTrendAnalyzer()
        self.logger = get_logger(f"{__name__}.MarketAnalyzer")
    
    def analyze_market_and_symbols(self, vix_value: float, market_status: dict, 
                                 symbol_data: Dict[str, UnderlyingTickData]) -> Tuple[OverallMarketAnalysis, Dict[str, SymbolTrendAnalysis]]:
        """综合分析市场和个股"""
        
        # 1. 整体市场分析
        market_analysis = self.overall_analyzer.analyze_market(vix_value, market_status)
        
        # 2. 个股分析
        symbol_analyses = {}
        for symbol, tick_data in symbol_data.items():
            symbol_analyses[symbol] = self.symbol_analyzer.analyze_symbol(tick_data)
        
        self.logger.debug(f"市场状态: {market_analysis.state.value}, 分析{len(symbol_analyses)}个标的")
        
        return market_analysis, symbol_analyses
    
    def get_trading_recommendation(self, market_analysis: OverallMarketAnalysis, 
                                 symbol_analyses: Dict[str, SymbolTrendAnalysis]) -> dict:
        """获取交易建议"""
        
        # 整体市场不建议交易时，直接返回
        if not market_analysis.trading_recommended:
            return {
                'recommended': False,
                'reason': f"整体市场风险过高: {market_analysis.reason}",
                'market_state': market_analysis.state.value,
                'symbol_opportunities': []
            }
        
        # 寻找个股机会
        opportunities = []
        for symbol, analysis in symbol_analyses.items():
            if analysis.signals and analysis.confidence > 0.6:
                opportunities.append({
                    'symbol': symbol,
                    'trend': analysis.trend_state.value,
                    'signals': analysis.signals,
                    'confidence': analysis.confidence
                })
        
        return {
            'recommended': True,
            'reason': f"市场环境良好: {market_analysis.reason}",
            'market_state': market_analysis.state.value,
            'symbol_opportunities': opportunities
        }
