#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
短线技术指标模块
专为0DTE期权高频交易设计的实时技术指标计算器

主要功能:
1. 超短期EMA指标 (EMA3/8)
2. 实时动量计算 (10s/30s/1m)
3. 成交量分析 (突增/大单/散度)
4. 微趋势检测
5. 信号强度评估
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import deque
import logging

from ..config.trading_config import TradingConstants
from ..utils.logger_config import get_logger

logger = get_logger(__name__)


@dataclass
class TechnicalSignal:
    """技术信号数据模型"""
    timestamp: datetime
    signal_type: str  # 'bullish', 'bearish', 'neutral'
    strength: float   # 信号强度 0-1
    confidence: float # 信号置信度 0-1
    source: str      # 信号来源指标
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MomentumData:
    """动量数据模型"""
    timestamp: datetime
    price: float
    momentum_10s: float = 0.0
    momentum_30s: float = 0.0
    momentum_1m: float = 0.0
    acceleration: float = 0.0
    consistency: bool = False
    direction: str = "neutral"  # "up", "down", "neutral"


@dataclass
class VolumeData:
    """成交量数据模型"""
    timestamp: datetime
    current_volume: int
    volume_ratio: float = 1.0        # 当前成交量 / 平均成交量
    volume_spike: bool = False       # 成交量突增
    large_trade_ratio: float = 0.0   # 大单比例
    aggressive_buys: float = 0.0     # 主动买入比例
    aggressive_sells: float = 0.0    # 主动卖出比例
    flow_pressure: str = "neutral"   # "buy", "sell", "neutral"


@dataclass
class EMAData:
    """EMA数据模型"""
    timestamp: datetime
    price: float
    ema3: float = 0.0
    ema8: float = 0.0
    cross_signal: str = "neutral"    # "bullish", "bearish", "neutral"
    cross_strength: float = 0.0      # 穿越强度
    slope_ema3: float = 0.0          # EMA3斜率
    slope_ema8: float = 0.0          # EMA8斜率
    divergence: float = 0.0          # EMA3-EMA8差值百分比


class RealTimeTechnicalIndicators:
    """实时技术指标计算器"""
    
    def __init__(self, config: TradingConstants = None):
        self.config = config or TradingConstants()
        
        # 数据存储队列 (时间窗口限制)
        self.price_data = deque(maxlen=300)      # 5分钟历史 (1秒一个点)
        self.volume_data = deque(maxlen=300)     # 5分钟成交量历史
        self.timestamp_data = deque(maxlen=300)  # 时间戳历史
        
        # EMA计算相关
        self.ema3_multiplier = 2 / (3 + 1)  # EMA3平滑因子
        self.ema8_multiplier = 2 / (8 + 1)  # EMA8平滑因子
        self.current_ema3 = None
        self.current_ema8 = None
        self.prev_ema3 = None
        self.prev_ema8 = None
        
        # 历史缓存
        self.momentum_history = deque(maxlen=100)
        self.volume_history = deque(maxlen=100)
        self.ema_history = deque(maxlen=100)
        self.signal_history = deque(maxlen=50)
        
        # 统计信息
        self.calculation_count = 0
        self.signal_count = 0
        self.last_update = None
        
        logger.info("实时技术指标计算器初始化完成")
    
    def update_market_data(self, price: float, volume: int, timestamp: datetime = None) -> bool:
        """
        更新市场数据
        
        Args:
            price: 当前价格
            volume: 当前成交量
            timestamp: 时间戳
            
        Returns:
            bool: 是否成功更新
        """
        try:
            if timestamp is None:
                timestamp = datetime.now()
            
            # 添加到数据队列
            self.price_data.append(price)
            self.volume_data.append(volume)
            self.timestamp_data.append(timestamp)
            
            self.last_update = timestamp
            
            # 如果数据足够，计算指标
            if len(self.price_data) >= 2:  # 至少需要2个数据点进行EMA计算
                self._calculate_all_indicators()
                self.calculation_count += 1
            
            return True
            
        except Exception as e:
            logger.error(f"更新市场数据失败: {e}")
            return False
    
    def _calculate_all_indicators(self):
        """计算所有技术指标"""
        try:
            current_time = self.timestamp_data[-1]
            current_price = self.price_data[-1]
            current_volume = self.volume_data[-1]
            
            # 计算EMA指标
            ema_data = self._calculate_ema(current_price, current_time)
            if ema_data:
                self.ema_history.append(ema_data)
            
            # 计算动量指标
            momentum_data = self._calculate_momentum(current_price, current_time)
            if momentum_data:
                self.momentum_history.append(momentum_data)
            
            # 计算成交量指标
            volume_data = self._calculate_volume_indicators(current_volume, current_time)
            if volume_data:
                self.volume_history.append(volume_data)
            
            # 生成综合信号
            self._generate_composite_signals(current_time)
            
        except Exception as e:
            logger.error(f"计算技术指标失败: {e}")
    
    def _calculate_ema(self, current_price: float, timestamp: datetime) -> Optional[EMAData]:
        """计算EMA指标"""
        try:
            # 初始化EMA
            if self.current_ema3 is None:
                self.current_ema3 = current_price
                self.current_ema8 = current_price
                # 第一次计算也创建EMA数据记录
                return EMAData(
                    timestamp=timestamp,
                    price=current_price,
                    ema3=self.current_ema3,
                    ema8=self.current_ema8,
                    cross_signal="neutral",
                    cross_strength=0.0,
                    slope_ema3=0.0,
                    slope_ema8=0.0,
                    divergence=0.0
                )
            
            # 保存前一期值
            self.prev_ema3 = self.current_ema3
            self.prev_ema8 = self.current_ema8
            
            # 计算新的EMA值
            self.current_ema3 = (current_price * self.ema3_multiplier) + (self.current_ema3 * (1 - self.ema3_multiplier))
            self.current_ema8 = (current_price * self.ema8_multiplier) + (self.current_ema8 * (1 - self.ema8_multiplier))
            
            # 计算斜率
            slope_ema3 = (self.current_ema3 - self.prev_ema3) / self.prev_ema3 if self.prev_ema3 > 0 else 0
            slope_ema8 = (self.current_ema8 - self.prev_ema8) / self.prev_ema8 if self.prev_ema8 > 0 else 0
            
            # 计算EMA差值百分比
            divergence = (self.current_ema3 - self.current_ema8) / self.current_ema8 if self.current_ema8 > 0 else 0
            
            # 判断穿越信号
            cross_signal = "neutral"
            cross_strength = 0.0
            
            if len(self.ema_history) > 0:
                prev_divergence = self.ema_history[-1].divergence
                
                # 金叉: EMA3从下方穿越EMA8
                if prev_divergence <= 0 and divergence > 0:
                    cross_signal = "bullish"
                    cross_strength = abs(divergence) * 100  # 转换为百分比
                
                # 死叉: EMA3从上方穿越EMA8
                elif prev_divergence >= 0 and divergence < 0:
                    cross_signal = "bearish"
                    cross_strength = abs(divergence) * 100
            
            return EMAData(
                timestamp=timestamp,
                price=current_price,
                ema3=self.current_ema3,
                ema8=self.current_ema8,
                cross_signal=cross_signal,
                cross_strength=cross_strength,
                slope_ema3=slope_ema3,
                slope_ema8=slope_ema8,
                divergence=divergence
            )
            
        except Exception as e:
            logger.error(f"EMA计算失败: {e}")
            return None
    
    def _calculate_momentum(self, current_price: float, timestamp: datetime) -> Optional[MomentumData]:
        """计算动量指标"""
        try:
            # 需要足够的历史数据
            if len(self.price_data) < 60:  # 至少1分钟数据
                return None
            
            prices = list(self.price_data)
            timestamps = list(self.timestamp_data)
            
            # 计算不同时间段的动量
            momentum_10s = self._get_momentum_for_period(prices, timestamps, timestamp, 10)
            momentum_30s = self._get_momentum_for_period(prices, timestamps, timestamp, 30)
            momentum_1m = self._get_momentum_for_period(prices, timestamps, timestamp, 60)
            
            # 计算加速度 (动量的变化率)
            acceleration = 0.0
            if len(self.momentum_history) > 0:
                prev_momentum = self.momentum_history[-1].momentum_10s
                acceleration = momentum_10s - prev_momentum
            
            # 判断动量一致性
            momentum_values = [momentum_10s, momentum_30s, momentum_1m]
            consistency = self._check_momentum_consistency(momentum_values)
            
            # 判断方向
            direction = "neutral"
            if all(m > 0.001 for m in momentum_values):  # 0.1%阈值
                direction = "up"
            elif all(m < -0.001 for m in momentum_values):
                direction = "down"
            
            return MomentumData(
                timestamp=timestamp,
                price=current_price,
                momentum_10s=momentum_10s,
                momentum_30s=momentum_30s,
                momentum_1m=momentum_1m,
                acceleration=acceleration,
                consistency=consistency,
                direction=direction
            )
            
        except Exception as e:
            logger.error(f"动量计算失败: {e}")
            return None
    
    def _get_momentum_for_period(self, prices: List[float], timestamps: List[datetime], 
                                current_time: datetime, seconds: int) -> float:
        """计算指定时间段的动量"""
        try:
            target_time = current_time - timedelta(seconds=seconds)
            current_price = prices[-1]
            
            # 找到最接近目标时间的价格
            for i in range(len(timestamps) - 1, -1, -1):
                if timestamps[i] <= target_time:
                    past_price = prices[i]
                    return (current_price - past_price) / past_price if past_price > 0 else 0.0
            
            # 如果没找到足够历史的数据，使用最早的数据
            if len(prices) > 1:
                past_price = prices[0]
                return (current_price - past_price) / past_price if past_price > 0 else 0.0
            
            return 0.0
            
        except Exception as e:
            logger.error(f"动量计算失败 ({seconds}s): {e}")
            return 0.0
    
    def _check_momentum_consistency(self, momentum_values: List[float]) -> bool:
        """检查动量一致性"""
        try:
            # 检查所有动量是否同方向且超过阈值
            if all(m > 0.001 for m in momentum_values):
                return True
            elif all(m < -0.001 for m in momentum_values):
                return True
            else:
                return False
        except:
            return False
    
    def _calculate_volume_indicators(self, current_volume: int, timestamp: datetime) -> Optional[VolumeData]:
        """计算成交量指标"""
        try:
            # 需要足够的历史数据
            if len(self.volume_data) < 30:
                return None
            
            volumes = list(self.volume_data)
            
            # 计算平均成交量 (过去5分钟)
            avg_volume = np.mean(volumes[-300:]) if len(volumes) >= 300 else np.mean(volumes)
            
            # 成交量比率
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
            
            # 成交量突增检测
            volume_spike = volume_ratio > 1.5
            
            # 大单比例分析 (简化版，实际需要逐笔数据)
            # 这里用成交量变化幅度作为代理指标
            large_trade_ratio = min(volume_ratio / 3.0, 1.0) if volume_ratio > 2.0 else 0.0
            
            # 买卖压力分析 (简化版，基于价格变化)
            aggressive_buys = 0.5  # 默认中性
            aggressive_sells = 0.5
            
            if len(self.price_data) >= 2:
                price_change = self.price_data[-1] - self.price_data[-2]
                if price_change > 0 and volume_spike:
                    aggressive_buys = 0.7  # 价格上涨 + 成交量增加 = 买压
                    aggressive_sells = 0.3
                elif price_change < 0 and volume_spike:
                    aggressive_buys = 0.3
                    aggressive_sells = 0.7  # 价格下跌 + 成交量增加 = 卖压
            
            # 资金流向判断
            flow_pressure = "neutral"
            if aggressive_buys > 0.6:
                flow_pressure = "buy"
            elif aggressive_sells > 0.6:
                flow_pressure = "sell"
            
            return VolumeData(
                timestamp=timestamp,
                current_volume=current_volume,
                volume_ratio=volume_ratio,
                volume_spike=volume_spike,
                large_trade_ratio=large_trade_ratio,
                aggressive_buys=aggressive_buys,
                aggressive_sells=aggressive_sells,
                flow_pressure=flow_pressure
            )
            
        except Exception as e:
            logger.error(f"成交量指标计算失败: {e}")
            return None
    
    def _generate_composite_signals(self, timestamp: datetime):
        """生成综合技术信号"""
        try:
            if not self.ema_history or not self.momentum_history or not self.volume_history:
                return
            
            latest_ema = self.ema_history[-1]
            latest_momentum = self.momentum_history[-1]
            latest_volume = self.volume_history[-1]
            
            signals = []
            
            # EMA穿越信号
            if latest_ema.cross_signal != "neutral":
                strength = min(latest_ema.cross_strength / 0.5, 1.0)  # 0.5%为满强度
                confidence = 0.7 if latest_volume.volume_spike else 0.5
                
                signals.append(TechnicalSignal(
                    timestamp=timestamp,
                    signal_type=latest_ema.cross_signal,
                    strength=strength,
                    confidence=confidence,
                    source="ema_cross",
                    details={
                        "ema3": latest_ema.ema3,
                        "ema8": latest_ema.ema8,
                        "cross_strength": latest_ema.cross_strength
                    }
                ))
            
            # 动量信号
            if latest_momentum.consistency and latest_momentum.direction != "neutral":
                strength = min(abs(latest_momentum.momentum_10s) / 0.005, 1.0)  # 0.5%为满强度
                confidence = 0.8 if latest_volume.flow_pressure != "neutral" else 0.6
                
                signal_type = "bullish" if latest_momentum.direction == "up" else "bearish"
                
                signals.append(TechnicalSignal(
                    timestamp=timestamp,
                    signal_type=signal_type,
                    strength=strength,
                    confidence=confidence,
                    source="momentum",
                    details={
                        "momentum_10s": latest_momentum.momentum_10s,
                        "momentum_30s": latest_momentum.momentum_30s,
                        "momentum_1m": latest_momentum.momentum_1m,
                        "acceleration": latest_momentum.acceleration
                    }
                ))
            
            # 成交量确认信号
            if latest_volume.volume_spike and latest_volume.flow_pressure != "neutral":
                strength = min(latest_volume.volume_ratio / 3.0, 1.0)  # 3倍为满强度
                confidence = 0.6
                
                signal_type = "bullish" if latest_volume.flow_pressure == "buy" else "bearish"
                
                signals.append(TechnicalSignal(
                    timestamp=timestamp,
                    signal_type=signal_type,
                    strength=strength,
                    confidence=confidence,
                    source="volume",
                    details={
                        "volume_ratio": latest_volume.volume_ratio,
                        "large_trade_ratio": latest_volume.large_trade_ratio,
                        "flow_pressure": latest_volume.flow_pressure
                    }
                ))
            
            # 保存信号
            for signal in signals:
                self.signal_history.append(signal)
                self.signal_count += 1
            
        except Exception as e:
            logger.error(f"生成综合信号失败: {e}")
    
    def get_latest_indicators(self) -> Dict[str, Any]:
        """获取最新的技术指标数据"""
        try:
            result = {
                "timestamp": self.last_update,
                "calculation_count": self.calculation_count,
                "signal_count": self.signal_count
            }
            
            if self.ema_history:
                latest_ema = self.ema_history[-1]
                result["ema"] = {
                    "ema3": latest_ema.ema3,
                    "ema8": latest_ema.ema8,
                    "cross_signal": latest_ema.cross_signal,
                    "cross_strength": latest_ema.cross_strength,
                    "divergence": latest_ema.divergence
                }
            
            if self.momentum_history:
                latest_momentum = self.momentum_history[-1]
                result["momentum"] = {
                    "momentum_10s": latest_momentum.momentum_10s,
                    "momentum_30s": latest_momentum.momentum_30s,
                    "momentum_1m": latest_momentum.momentum_1m,
                    "acceleration": latest_momentum.acceleration,
                    "consistency": latest_momentum.consistency,
                    "direction": latest_momentum.direction
                }
            
            if self.volume_history:
                latest_volume = self.volume_history[-1]
                result["volume"] = {
                    "volume_ratio": latest_volume.volume_ratio,
                    "volume_spike": latest_volume.volume_spike,
                    "large_trade_ratio": latest_volume.large_trade_ratio,
                    "flow_pressure": latest_volume.flow_pressure
                }
            
            if self.signal_history:
                latest_signals = list(self.signal_history)[-5:]  # 最近5个信号
                result["signals"] = [
                    {
                        "timestamp": signal.timestamp,
                        "signal_type": signal.signal_type,
                        "strength": signal.strength,
                        "confidence": signal.confidence,
                        "source": signal.source
                    }
                    for signal in latest_signals
                ]
            
            return result
            
        except Exception as e:
            logger.error(f"获取指标数据失败: {e}")
            return {}
    
    def get_trading_signal_strength(self) -> Tuple[str, float, float]:
        """
        获取当前交易信号强度
        
        Returns:
            Tuple[str, float, float]: (信号类型, 强度, 置信度)
        """
        try:
            if not self.signal_history:
                return "neutral", 0.0, 0.0
            
            # 分析最近的信号
            recent_signals = list(self.signal_history)[-10:]  # 最近10个信号
            
            bullish_signals = [s for s in recent_signals if s.signal_type == "bullish"]
            bearish_signals = [s for s in recent_signals if s.signal_type == "bearish"]
            
            # 计算加权强度
            bullish_strength = sum(s.strength * s.confidence for s in bullish_signals)
            bearish_strength = sum(s.strength * s.confidence for s in bearish_signals)
            
            if bullish_strength > bearish_strength and bullish_strength > 0.3:
                signal_type = "bullish"
                strength = min(bullish_strength, 1.0)
                confidence = np.mean([s.confidence for s in bullish_signals])
            elif bearish_strength > bullish_strength and bearish_strength > 0.3:
                signal_type = "bearish"
                strength = min(bearish_strength, 1.0)
                confidence = np.mean([s.confidence for s in bearish_signals])
            else:
                signal_type = "neutral"
                strength = 0.0
                confidence = 0.0
            
            return signal_type, strength, confidence
            
        except Exception as e:
            logger.error(f"获取交易信号强度失败: {e}")
            return "neutral", 0.0, 0.0
    
    def clear_history(self):
        """清理历史数据"""
        try:
            self.price_data.clear()
            self.volume_data.clear()
            self.timestamp_data.clear()
            self.momentum_history.clear()
            self.volume_history.clear()
            self.ema_history.clear()
            self.signal_history.clear()
            
            self.current_ema3 = None
            self.current_ema8 = None
            self.prev_ema3 = None
            self.prev_ema8 = None
            
            self.calculation_count = 0
            self.signal_count = 0
            
            logger.info("技术指标历史数据已清理")
            
        except Exception as e:
            logger.error(f"清理历史数据失败: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "calculation_count": self.calculation_count,
            "signal_count": self.signal_count,
            "data_points": len(self.price_data),
            "ema_history_count": len(self.ema_history),
            "momentum_history_count": len(self.momentum_history),
            "volume_history_count": len(self.volume_history),
            "signal_history_count": len(self.signal_history),
            "last_update": self.last_update.isoformat() if self.last_update else None
        }


# 便捷函数
def create_technical_indicators(config: TradingConstants = None) -> RealTimeTechnicalIndicators:
    """创建技术指标计算器实例"""
    return RealTimeTechnicalIndicators(config)


if __name__ == "__main__":
    # 基础功能测试
    print("🚀 短线技术指标模块测试")
    
    indicator = create_technical_indicators()
    
    # 模拟一些价格数据
    import time
    base_price = 100.0
    
    for i in range(100):
        # 模拟价格波动
        price = base_price + np.sin(i * 0.1) * 2 + np.random.normal(0, 0.5)
        volume = int(1000 + np.random.normal(0, 200))
        
        indicator.update_market_data(price, volume)
        
        if i % 20 == 0:  # 每20个数据点显示一次
            indicators = indicator.get_latest_indicators()
            signal_type, strength, confidence = indicator.get_trading_signal_strength()
            
            print(f"\n📊 数据点 {i}:")
            if "ema" in indicators:
                ema = indicators["ema"]
                print(f"  EMA3: {ema['ema3']:.3f}, EMA8: {ema['ema8']:.3f}")
                print(f"  穿越信号: {ema['cross_signal']}, 强度: {ema['cross_strength']:.4f}")
            
            if "momentum" in indicators:
                momentum = indicators["momentum"]
                print(f"  动量(10s): {momentum['momentum_10s']:.4f}")
                print(f"  方向: {momentum['direction']}, 一致性: {momentum['consistency']}")
            
            print(f"  交易信号: {signal_type}, 强度: {strength:.3f}, 置信度: {confidence:.3f}")
        
        time.sleep(0.01)  # 模拟实时数据
    
    print(f"\n📈 测试完成!")
    print(f"统计信息: {indicator.get_statistics()}")
