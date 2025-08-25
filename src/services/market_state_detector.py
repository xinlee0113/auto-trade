#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场状态检测器

实现0DTE期权高频交易的核心市场环境判断：
1. 实时VIX监控和波动率状态评估
2. 成交量异动检测和流动性评估
3. 技术指标状态综合评估
4. 市场状态转换的平滑机制
5. 双轨制策略切换的触发条件

Author: AI Assistant
Date: 2024-01-22
"""

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple, Callable
import threading
import time
from collections import deque
import numpy as np

from ..config.trading_config import TradingConfig
from ..models.trading_models import MarketData, UnderlyingTickData
from ..utils.logger_config import get_logger

logger = get_logger(__name__)


class MarketState(Enum):
    """整体市场状态枚举 - 基于VIX、宏观流动性、系统性风险"""
    NORMAL = "normal"           # 常规市场：VIX<20，成交量正常，系统性风险低
    VOLATILE = "volatile"       # 波动市场：VIX 20-30，成交量升高，不确定性增加
    ANOMALY = "anomaly"        # 异动市场：VIX>30，成交量爆炸，系统性事件
    UNCERTAIN = "uncertain"    # 不确定：数据不足或API异常


class SymbolTrendState(Enum):
    """单个标的趋势状态枚举 - 基于价格动量、技术指标"""
    SIDEWAYS = "sideways"      # 横盘：价格区间震荡，无明确方向
    TRENDING_UP = "trending_up"    # 上涨趋势：价格持续上涨，动量积极
    TRENDING_DOWN = "trending_down"  # 下跌趋势：价格持续下跌，动量消极
    BREAKOUT = "breakout"      # 突破：突破关键阻力/支撑位
    REVERSAL = "reversal"      # 反转：趋势可能反转的信号


class VIXLevel(Enum):
    """VIX波动率等级"""
    LOW = "low"           # VIX < 15: 低波动
    NORMAL = "normal"     # 15 <= VIX < 20: 正常波动  
    ELEVATED = "elevated" # 20 <= VIX < 30: 升高波动
    HIGH = "high"         # 30 <= VIX < 40: 高波动
    EXTREME = "extreme"   # VIX >= 40: 极端波动


class VolumeState(Enum):
    """成交量状态"""
    LOW = "low"           # 低于平均成交量
    NORMAL = "normal"     # 正常成交量范围
    HIGH = "high"         # 高于平均成交量
    SPIKE = "spike"       # 成交量爆炸


@dataclass
class MarketStateData:
    """市场状态数据"""
    timestamp: datetime
    state: MarketState
    confidence: float          # 置信度 0-1
    vix_level: VIXLevel
    volume_state: VolumeState
    
    # VIX相关
    vix_value: Optional[float] = None
    vix_change: Optional[float] = None
    vix_zscore: Optional[float] = None
    
    # 成交量相关
    volume_ratio: Optional[float] = None
    volume_zscore: Optional[float] = None
    
    # 技术指标相关
    momentum_score: Optional[float] = None
    trend_strength: Optional[float] = None
    volatility_score: Optional[float] = None
    
    # 状态持续时间
    state_duration: Optional[int] = None  # 秒数
    
    # 附加信息
    underlying_prices: Optional[Dict[str, float]] = None
    market_sentiment: Optional[str] = None


@dataclass
class MarketStateConfig:
    """市场状态检测配置"""
    # VIX阈值设置
    vix_low_threshold: float = 15.0
    vix_normal_threshold: float = 20.0
    vix_elevated_threshold: float = 30.0
    vix_high_threshold: float = 40.0
    
    # 成交量异动阈值
    volume_spike_threshold: float = 2.5  # 2.5倍平均成交量
    volume_high_threshold: float = 1.5   # 1.5倍平均成交量
    
    # 状态转换阈值
    state_change_threshold: float = 0.7  # 置信度阈值
    min_state_duration: int = 30         # 最小状态持续时间(秒)
    
    # 历史数据窗口
    vix_history_window: int = 30         # VIX历史窗口(天)
    volume_history_window: int = 20      # 成交量历史窗口(天)
    price_history_window: int = 100      # 价格历史窗口(分钟)
    
    # 监控符号
    vix_symbol: str = "VIX"
    watch_symbols: List[str] = None      # 监控的标的列表
    
    def __post_init__(self):
        if self.watch_symbols is None:
            self.watch_symbols = ["QQQ", "SPY", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA", "META"]


class MarketStateDetector:
    """市场状态检测器
    
    负责实时监控市场状态，为0DTE期权高频交易提供环境判断
    """
    
    def __init__(self, config: MarketStateConfig = None, trading_config: TradingConfig = None):
        """初始化市场状态检测器"""
        self.config = config or MarketStateConfig()
        self.trading_config = trading_config
        self.logger = get_logger(f"{__name__}.MarketStateDetector")
        
        # 状态管理
        self.current_state: MarketStateData = None
        self.state_history: deque = deque(maxlen=1000)
        self.last_state_change: datetime = datetime.now()
        
        # 历史数据缓存
        self.vix_history: deque = deque(maxlen=self.config.vix_history_window * 24 * 60)  # 分钟级
        self.volume_history: Dict[str, deque] = {}
        self.price_history: Dict[str, deque] = {}
        
        # 计算缓存
        self._vix_stats_cache: Dict = {}
        self._volume_stats_cache: Dict[str, Dict] = {}
        self._cache_timestamp: datetime = datetime.min
        
        # 回调函数
        self.state_change_callbacks: List[Callable[[MarketStateData, MarketStateData], None]] = []
        
        # 线程安全
        self._lock = threading.RLock()
        self._running = False
        self._monitor_thread = None
        
        # 初始化
        self._initialize_history_data()
        
        self.logger.info("市场状态检测器初始化完成")
    
    def _initialize_history_data(self):
        """初始化历史数据"""
        # 为每个监控符号初始化历史数据缓存
        for symbol in self.config.watch_symbols:
            self.volume_history[symbol] = deque(maxlen=self.config.volume_history_window * 24 * 60)
            self.price_history[symbol] = deque(maxlen=self.config.price_history_window)
            self._volume_stats_cache[symbol] = {}
        
        self.logger.debug(f"初始化 {len(self.config.watch_symbols)} 个符号的历史数据缓存")
    
    def start_monitoring(self, update_interval: int = 30):
        """开始监控市场状态"""
        if self._running:
            self.logger.warning("市场状态监控已在运行")
            return
        
        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitoring_loop,
            args=(update_interval,),
            daemon=True
        )
        self._monitor_thread.start()
        
        self.logger.info(f"市场状态监控已启动，更新间隔: {update_interval}秒")
    
    def stop_monitoring(self):
        """停止监控市场状态"""
        self._running = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5)
        
        self.logger.info("市场状态监控已停止")
    
    def _monitoring_loop(self, update_interval: int):
        """监控循环"""
        while self._running:
            try:
                # 检测市场状态
                new_state = self.detect_market_state()
                
                if new_state:
                    self._update_market_state(new_state)
                
                time.sleep(update_interval)
                
            except Exception as e:
                self.logger.error(f"市场状态监控循环出错: {e}")
                time.sleep(update_interval)
    
    def detect_market_state(self, market_data: Dict[str, UnderlyingTickData] = None,
                          vix_data: float = None) -> MarketStateData:
        """检测当前市场状态"""
        try:
            with self._lock:
                timestamp = datetime.now()
                
                # 1. VIX分析
                vix_analysis = self._analyze_vix(vix_data)
                
                # 2. 成交量分析
                volume_analysis = self._analyze_volume(market_data)
                
                # 3. 技术指标分析
                technical_analysis = self._analyze_technical_indicators(market_data)
                
                # 4. 综合状态判断
                state, confidence = self._determine_market_state(
                    vix_analysis, volume_analysis, technical_analysis
                )
                
                # 5. 构建状态数据
                state_data = MarketStateData(
                    timestamp=timestamp,
                    state=state,
                    confidence=confidence,
                    vix_level=vix_analysis.get('level', VIXLevel.NORMAL),
                    vix_value=vix_analysis.get('value'),
                    vix_change=vix_analysis.get('change'),
                    vix_zscore=vix_analysis.get('zscore'),
                    volume_state=volume_analysis.get('state', VolumeState.NORMAL),
                    volume_ratio=volume_analysis.get('avg_ratio'),
                    volume_zscore=volume_analysis.get('avg_zscore'),
                    momentum_score=technical_analysis.get('momentum'),
                    trend_strength=technical_analysis.get('trend'),
                    volatility_score=technical_analysis.get('volatility'),
                    underlying_prices=self._extract_prices(market_data) if market_data else None
                )
                
                # 6. 计算状态持续时间
                if self.current_state and self.current_state.state == state:
                    duration = (timestamp - self.last_state_change).total_seconds()
                    state_data.state_duration = int(duration)
                
                return state_data
                
        except Exception as e:
            self.logger.error(f"市场状态检测失败: {e}")
            return None
    
    def _analyze_vix(self, vix_data: float = None) -> Dict:
        """分析VIX数据"""
        try:
            # 如果没有提供VIX数据，使用模拟数据或API获取
            if vix_data is None:
                vix_data = self._get_vix_data()
            
            if vix_data is None:
                return {'level': VIXLevel.NORMAL, 'confidence': 0.5}
            
            # 确定VIX等级
            if vix_data < self.config.vix_low_threshold:
                level = VIXLevel.LOW
            elif vix_data < self.config.vix_normal_threshold:
                level = VIXLevel.NORMAL
            elif vix_data < self.config.vix_elevated_threshold:
                level = VIXLevel.ELEVATED
            elif vix_data < self.config.vix_high_threshold:
                level = VIXLevel.HIGH
            else:
                level = VIXLevel.EXTREME
            
            # 计算VIX变化和Z-score
            vix_change = self._calculate_vix_change(vix_data)
            vix_zscore = self._calculate_vix_zscore(vix_data)
            
            return {
                'level': level,
                'value': vix_data,
                'change': vix_change,
                'zscore': vix_zscore,
                'confidence': 0.9 if level in [VIXLevel.HIGH, VIXLevel.EXTREME] else 0.7
            }
            
        except Exception as e:
            self.logger.error(f"VIX分析失败: {e}")
            return {'level': VIXLevel.NORMAL, 'confidence': 0.5}
    
    def _analyze_volume(self, market_data: Dict[str, UnderlyingTickData]) -> Dict:
        """分析成交量数据"""
        try:
            if not market_data:
                return {'state': VolumeState.NORMAL, 'confidence': 0.5}
            
            volume_ratios = []
            volume_zscores = []
            
            for symbol, data in market_data.items():
                if hasattr(data, 'volume') and data.volume:
                    ratio = self._calculate_volume_ratio(symbol, data.volume)
                    zscore = self._calculate_volume_zscore(symbol, data.volume)
                    
                    if ratio is not None:
                        volume_ratios.append(ratio)
                    if zscore is not None:
                        volume_zscores.append(zscore)
            
            if not volume_ratios:
                return {'state': VolumeState.NORMAL, 'confidence': 0.5}
            
            # 计算平均比率
            avg_ratio = np.mean(volume_ratios)
            avg_zscore = np.mean(volume_zscores) if volume_zscores else 0
            
            # 确定成交量状态
            if avg_ratio >= self.config.volume_spike_threshold:
                state = VolumeState.SPIKE
                confidence = 0.9
            elif avg_ratio >= self.config.volume_high_threshold:
                state = VolumeState.HIGH
                confidence = 0.8
            elif avg_ratio < 0.7:
                state = VolumeState.LOW
                confidence = 0.7
            else:
                state = VolumeState.NORMAL
                confidence = 0.6
            
            return {
                'state': state,
                'avg_ratio': avg_ratio,
                'avg_zscore': avg_zscore,
                'confidence': confidence
            }
            
        except Exception as e:
            self.logger.error(f"成交量分析失败: {e}")
            return {'state': VolumeState.NORMAL, 'confidence': 0.5}
    
    def _analyze_technical_indicators(self, market_data: Dict[str, UnderlyingTickData]) -> Dict:
        """分析技术指标"""
        try:
            # 暂时返回基础分析，后续整合technical_indicators模块
            if not market_data:
                return {'momentum': 0.5, 'trend': 0.5, 'volatility': 0.5}
            
            momentum_scores = []
            trend_scores = []
            volatility_scores = []
            
            for symbol, data in market_data.items():
                # 基于价格历史计算简单指标
                price_history = self.price_history.get(symbol, deque())
                if len(price_history) > 10:
                    prices = list(price_history)
                    
                    # 动量评分（基于短期价格变化）
                    momentum = (prices[-1] - prices[-5]) / prices[-5] if len(prices) >= 5 else 0
                    momentum_scores.append(abs(momentum))
                    
                    # 趋势强度（基于价格方向一致性）
                    trend = self._calculate_trend_strength(prices)
                    trend_scores.append(trend)
                    
                    # 波动率评分（基于价格标准差）
                    volatility = np.std(prices[-20:]) / np.mean(prices[-20:]) if len(prices) >= 20 else 0
                    volatility_scores.append(volatility)
            
            return {
                'momentum': np.mean(momentum_scores) if momentum_scores else 0.5,
                'trend': np.mean(trend_scores) if trend_scores else 0.5,
                'volatility': np.mean(volatility_scores) if volatility_scores else 0.5
            }
            
        except Exception as e:
            self.logger.error(f"技术指标分析失败: {e}")
            return {'momentum': 0.5, 'trend': 0.5, 'volatility': 0.5}
    
    def _determine_market_state(self, vix_analysis: Dict, volume_analysis: Dict, 
                              technical_analysis: Dict) -> Tuple[MarketState, float]:
        """确定市场状态 - 多因子综合评分"""
        try:
            # 提取各项指标
            vix_level = vix_analysis.get('level', VIXLevel.NORMAL)
            vix_value = vix_analysis.get('value', 20.0)
            vix_zscore = vix_analysis.get('zscore', 0.0) or 0.0
            
            volume_state = volume_analysis.get('state', VolumeState.NORMAL)
            volume_ratio = volume_analysis.get('avg_ratio', 1.0) or 1.0
            volume_zscore = volume_analysis.get('avg_zscore', 0.0) or 0.0
            
            momentum = technical_analysis.get('momentum', 0.5)
            trend = technical_analysis.get('trend', 0.5)
            volatility = technical_analysis.get('volatility', 0.5)
            
            # 多因子评分系统 (总分100分)
            scores = {}
            
            # 1. VIX评分 (权重25%)
            vix_score = self._calculate_vix_score(vix_level, vix_value, vix_zscore)
            
            # 2. 成交量评分 (权重25%)
            volume_score = self._calculate_volume_score(volume_state, volume_ratio, volume_zscore)
            
            # 3. 技术指标评分 (权重30%)
            technical_score = self._calculate_technical_score(momentum, trend, volatility)
            
            # 4. 价格波动评分 (权重20%)
            price_volatility_score = self._calculate_price_volatility_score(volatility)
            
            # 综合评分
            anomaly_score = (vix_score['anomaly'] * 0.25 + 
                           volume_score['anomaly'] * 0.25 + 
                           technical_score['anomaly'] * 0.30 + 
                           price_volatility_score['anomaly'] * 0.20)
            
            volatile_score = (vix_score['volatile'] * 0.25 + 
                            volume_score['volatile'] * 0.25 + 
                            technical_score['volatile'] * 0.30 + 
                            price_volatility_score['volatile'] * 0.20)
            
            trending_score = (vix_score['trending'] * 0.15 + 
                            volume_score['trending'] * 0.15 + 
                            technical_score['trending'] * 0.50 + 
                            price_volatility_score['trending'] * 0.20)
            
            sideways_score = (vix_score['sideways'] * 0.15 + 
                            volume_score['sideways'] * 0.25 + 
                            technical_score['sideways'] * 0.40 + 
                            price_volatility_score['sideways'] * 0.20)
            
            normal_score = (vix_score['normal'] * 0.20 + 
                          volume_score['normal'] * 0.20 + 
                          technical_score['normal'] * 0.30 + 
                          price_volatility_score['normal'] * 0.30)
            
            # 选择最高分状态
            all_scores = {
                MarketState.ANOMALY: anomaly_score,
                MarketState.VOLATILE: volatile_score,
                MarketState.TRENDING: trending_score,
                MarketState.SIDEWAYS: sideways_score,
                MarketState.NORMAL: normal_score
            }
            
            best_state = max(all_scores, key=all_scores.get)
            best_score = all_scores[best_state]
            confidence = min(0.95, best_score / 100.0)
            
            # 记录评分详情供调试
            self.logger.debug(f"市场状态评分: {all_scores}")
            
            return best_state, confidence
            
        except Exception as e:
            self.logger.error(f"市场状态判断失败: {e}")
            return MarketState.UNCERTAIN, 0.3
    
    def _calculate_vix_score(self, vix_level: VIXLevel, vix_value: float, vix_zscore: float) -> Dict[str, float]:
        """计算VIX相关评分"""
        scores = {'anomaly': 0, 'volatile': 0, 'trending': 0, 'sideways': 0, 'normal': 0}
        
        # 基于VIX等级评分
        if vix_level == VIXLevel.EXTREME:
            scores['anomaly'] = 90
        elif vix_level == VIXLevel.HIGH:
            scores['anomaly'] = 70
            scores['volatile'] = 30
        elif vix_level == VIXLevel.ELEVATED:
            scores['volatile'] = 60
            scores['normal'] = 20
        elif vix_level == VIXLevel.NORMAL:
            scores['normal'] = 70
            scores['trending'] = 20
        else:  # LOW
            scores['sideways'] = 60
            scores['normal'] = 40
        
        # 基于Z-score调整
        if abs(vix_zscore) > 2:  # 异常偏离
            scores['anomaly'] += 20
        elif abs(vix_zscore) > 1:  # 显著偏离
            scores['volatile'] += 15
        
        return scores
    
    def _calculate_volume_score(self, volume_state: VolumeState, volume_ratio: float, volume_zscore: float) -> Dict[str, float]:
        """计算成交量相关评分"""
        scores = {'anomaly': 0, 'volatile': 0, 'trending': 0, 'sideways': 0, 'normal': 0}
        
        # 基于成交量状态评分
        if volume_state == VolumeState.SPIKE:
            scores['anomaly'] = 80
            scores['volatile'] = 20
        elif volume_state == VolumeState.HIGH:
            scores['volatile'] = 60
            scores['trending'] = 30
        elif volume_state == VolumeState.NORMAL:
            scores['normal'] = 60
            scores['trending'] = 20
        else:  # LOW
            scores['sideways'] = 70
            scores['normal'] = 30
        
        # 基于成交量比率调整
        if volume_ratio > 3:
            scores['anomaly'] += 15
        elif volume_ratio > 2:
            scores['volatile'] += 15
        elif volume_ratio < 0.5:
            scores['sideways'] += 15
        
        return scores
    
    def _calculate_technical_score(self, momentum: float, trend: float, volatility: float) -> Dict[str, float]:
        """计算技术指标相关评分"""
        scores = {'anomaly': 0, 'volatile': 0, 'trending': 0, 'sideways': 0, 'normal': 0}
        
        # 趋势评分
        if trend > 0.8:
            scores['trending'] = 80
        elif trend > 0.6:
            scores['trending'] = 60
            scores['normal'] = 20
        elif trend < 0.3:
            scores['sideways'] = 50
        else:
            scores['normal'] = 40
        
        # 动量评分
        if momentum > 0.7:
            scores['trending'] += 20
            scores['volatile'] += 15
        elif momentum > 0.5:
            scores['normal'] += 20
        elif momentum < 0.2:
            scores['sideways'] += 30
        
        # 波动率评分
        if volatility > 0.8:
            scores['anomaly'] += 25
            scores['volatile'] += 20
        elif volatility > 0.5:
            scores['volatile'] += 15
            scores['normal'] += 10
        elif volatility < 0.2:
            scores['sideways'] += 25
        else:
            scores['normal'] += 15
        
        return scores
    
    def _calculate_price_volatility_score(self, volatility: float) -> Dict[str, float]:
        """计算价格波动评分"""
        scores = {'anomaly': 0, 'volatile': 0, 'trending': 0, 'sideways': 0, 'normal': 0}
        
        if volatility > 0.9:
            scores['anomaly'] = 85
        elif volatility > 0.6:
            scores['volatile'] = 70
        elif volatility > 0.4:
            scores['volatile'] = 40
            scores['normal'] = 30
        elif volatility < 0.15:
            scores['sideways'] = 80
        else:
            scores['normal'] = 60
        
        return scores
    
    def _update_market_state(self, new_state: MarketStateData):
        """更新市场状态"""
        try:
            with self._lock:
                old_state = self.current_state
                
                # 状态转换平滑机制
                if self._should_change_state(old_state, new_state):
                    self.current_state = new_state
                    self.state_history.append(new_state)
                    self.last_state_change = new_state.timestamp
                    
                    # 触发状态变化回调
                    if old_state and old_state.state != new_state.state:
                        self._trigger_state_change_callbacks(old_state, new_state)
                        
                        self.logger.info(
                            f"市场状态变化: {old_state.state.value} → {new_state.state.value} "
                            f"(置信度: {new_state.confidence:.2f})"
                        )
                else:
                    # 更新当前状态的其他属性但不改变状态
                    if self.current_state:
                        self.current_state.timestamp = new_state.timestamp
                        self.current_state.confidence = max(self.current_state.confidence, new_state.confidence)
                
        except Exception as e:
            self.logger.error(f"市场状态更新失败: {e}")
    
    def _should_change_state(self, old_state: MarketStateData, new_state: MarketStateData) -> bool:
        """判断是否应该改变状态"""
        if not old_state:
            return True
        
        # 置信度足够高
        if new_state.confidence < self.config.state_change_threshold:
            return False
        
        # 状态确实不同
        if old_state.state == new_state.state:
            return False
        
        # 最小持续时间检查
        duration = (new_state.timestamp - self.last_state_change).total_seconds()
        if duration < self.config.min_state_duration:
            return False
        
        return True
    
    def _trigger_state_change_callbacks(self, old_state: MarketStateData, new_state: MarketStateData):
        """触发状态变化回调"""
        for callback in self.state_change_callbacks:
            try:
                callback(old_state, new_state)
            except Exception as e:
                self.logger.error(f"状态变化回调执行失败: {e}")
    
    def register_state_change_callback(self, callback: Callable[[MarketStateData, MarketStateData], None]):
        """注册状态变化回调"""
        self.state_change_callbacks.append(callback)
        self.logger.debug("注册状态变化回调成功")
    
    def get_current_state(self) -> MarketStateData:
        """获取当前市场状态"""
        with self._lock:
            return self.current_state
    
    def get_state_history(self, limit: int = 100) -> List[MarketStateData]:
        """获取状态历史"""
        with self._lock:
            return list(self.state_history)[-limit:]
    
    def update_market_data(self, symbol: str, data: UnderlyingTickData):
        """更新市场数据"""
        try:
            with self._lock:
                # 更新价格历史
                if symbol in self.price_history:
                    self.price_history[symbol].append(data.price)
                
                # 更新成交量历史
                if symbol in self.volume_history and hasattr(data, 'volume'):
                    self.volume_history[symbol].append({
                        'timestamp': datetime.now(),
                        'volume': data.volume
                    })
                
                # 清空缓存
                self._cache_timestamp = datetime.min
                
        except Exception as e:
            self.logger.error(f"市场数据更新失败: {e}")
    
    # 辅助方法
    def _get_vix_data(self) -> Optional[float]:
        """获取VIX数据（模拟实现）"""
        # TODO: 整合真实VIX API
        # 暂时返回模拟数据
        import random
        return random.uniform(15, 35)
    
    def _calculate_vix_change(self, current_vix: float) -> Optional[float]:
        """计算VIX变化"""
        if len(self.vix_history) < 2:
            return None
        
        previous_vix = self.vix_history[-1].get('value', current_vix)
        return current_vix - previous_vix
    
    def _calculate_vix_zscore(self, current_vix: float) -> Optional[float]:
        """计算VIX的Z-score"""
        if len(self.vix_history) < 10:
            return None
        
        values = [item.get('value', 0) for item in self.vix_history]
        mean_vix = np.mean(values)
        std_vix = np.std(values)
        
        if std_vix == 0:
            return 0
        
        return (current_vix - mean_vix) / std_vix
    
    def _calculate_volume_ratio(self, symbol: str, current_volume: int) -> Optional[float]:
        """计算成交量比率"""
        if symbol not in self.volume_history or len(self.volume_history[symbol]) < 5:
            return None
        
        volumes = [item['volume'] for item in self.volume_history[symbol]]
        avg_volume = np.mean(volumes)
        
        if avg_volume == 0:
            return None
        
        return current_volume / avg_volume
    
    def _calculate_volume_zscore(self, symbol: str, current_volume: int) -> Optional[float]:
        """计算成交量Z-score"""
        if symbol not in self.volume_history or len(self.volume_history[symbol]) < 10:
            return None
        
        volumes = [item['volume'] for item in self.volume_history[symbol]]
        mean_volume = np.mean(volumes)
        std_volume = np.std(volumes)
        
        if std_volume == 0:
            return 0
        
        return (current_volume - mean_volume) / std_volume
    
    def _calculate_trend_strength(self, prices: List[float]) -> float:
        """计算趋势强度"""
        if len(prices) < 5:
            return 0.5
        
        # 简单趋势强度：价格变化方向的一致性
        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        positive_changes = sum(1 for change in changes if change > 0)
        
        return positive_changes / len(changes)
    
    def _extract_prices(self, market_data: Dict[str, UnderlyingTickData]) -> Dict[str, float]:
        """提取价格数据"""
        return {symbol: data.price for symbol, data in market_data.items() if hasattr(data, 'price')}


def create_market_state_detector(config: MarketStateConfig = None, 
                                trading_config: TradingConfig = None) -> MarketStateDetector:
    """创建市场状态检测器实例"""
    return MarketStateDetector(config, trading_config)
