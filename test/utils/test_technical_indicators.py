#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
短线技术指标模块测试
"""

import unittest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import sys
import os

# 添加项目路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.utils.technical_indicators import (
    RealTimeTechnicalIndicators,
    TechnicalSignal,
    MomentumData,
    VolumeData,
    EMAData,
    create_technical_indicators
)
from src.config.trading_config import TradingConstants


class TestTechnicalIndicators(unittest.TestCase):
    """技术指标测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.config = TradingConstants()
        self.indicator = RealTimeTechnicalIndicators(self.config)
        self.base_time = datetime.now()
        
    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.indicator)
        self.assertEqual(len(self.indicator.price_data), 0)
        self.assertEqual(len(self.indicator.volume_data), 0)
        self.assertEqual(self.indicator.calculation_count, 0)
        self.assertEqual(self.indicator.signal_count, 0)
        
    def test_update_market_data(self):
        """测试市场数据更新"""
        # 测试单个数据点
        result = self.indicator.update_market_data(100.0, 1000, self.base_time)
        self.assertTrue(result)
        self.assertEqual(len(self.indicator.price_data), 1)
        self.assertEqual(len(self.indicator.volume_data), 1)
        self.assertEqual(self.indicator.price_data[0], 100.0)
        self.assertEqual(self.indicator.volume_data[0], 1000)
        
        # 测试多个数据点
        for i in range(20):
            price = 100.0 + i * 0.1
            volume = 1000 + i * 10
            timestamp = self.base_time + timedelta(seconds=i)
            result = self.indicator.update_market_data(price, volume, timestamp)
            self.assertTrue(result)
        
        self.assertEqual(len(self.indicator.price_data), 21)
        self.assertGreater(self.indicator.calculation_count, 0)
        
    def test_ema_calculation(self):
        """测试EMA计算"""
        # 添加足够的数据点来计算EMA
        prices = [100.0, 101.0, 102.0, 101.5, 103.0, 102.0, 104.0, 103.5, 105.0, 104.0]
        
        for i, price in enumerate(prices):
            timestamp = self.base_time + timedelta(seconds=i)
            self.indicator.update_market_data(price, 1000, timestamp)
        
        # 检查EMA值
        self.assertIsNotNone(self.indicator.current_ema3)
        self.assertIsNotNone(self.indicator.current_ema8)
        self.assertGreater(len(self.indicator.ema_history), 0)
        
        # 检查EMA历史记录
        latest_ema = self.indicator.ema_history[-1]
        self.assertIsInstance(latest_ema, EMAData)
        self.assertGreater(latest_ema.ema3, 0)
        self.assertGreater(latest_ema.ema8, 0)
        
    def test_momentum_calculation(self):
        """测试动量计算"""
        # 生成上升趋势数据
        base_price = 100.0
        for i in range(70):  # 70秒数据，确保有足够历史
            price = base_price + i * 0.05  # 持续上升
            volume = 1000 + i * 5
            timestamp = self.base_time + timedelta(seconds=i)
            self.indicator.update_market_data(price, volume, timestamp)
        
        # 检查动量数据
        self.assertGreater(len(self.indicator.momentum_history), 0)
        
        latest_momentum = self.indicator.momentum_history[-1]
        self.assertIsInstance(latest_momentum, MomentumData)
        
        # 在上升趋势中，动量应该为正
        self.assertGreater(latest_momentum.momentum_10s, 0)
        self.assertGreater(latest_momentum.momentum_30s, 0)
        self.assertGreater(latest_momentum.momentum_1m, 0)
        self.assertEqual(latest_momentum.direction, "up")
        
    def test_volume_indicators(self):
        """测试成交量指标"""
        # 添加正常成交量数据
        for i in range(50):
            price = 100.0 + np.sin(i * 0.1)
            volume = 1000 + int(np.random.normal(0, 100))
            timestamp = self.base_time + timedelta(seconds=i)
            self.indicator.update_market_data(price, volume, timestamp)
        
        # 添加成交量突增数据
        spike_volume = 5000  # 5倍正常成交量
        self.indicator.update_market_data(100.5, spike_volume, 
                                        self.base_time + timedelta(seconds=50))
        
        # 检查成交量指标
        self.assertGreater(len(self.indicator.volume_history), 0)
        
        latest_volume = self.indicator.volume_history[-1]
        self.assertIsInstance(latest_volume, VolumeData)
        self.assertGreater(latest_volume.volume_ratio, 1.0)  # 应该检测到成交量突增
        
    def test_signal_generation(self):
        """测试信号生成"""
        # 生成有明显趋势的数据
        base_price = 100.0
        
        # 第一阶段：横盘
        for i in range(30):
            price = base_price + np.random.normal(0, 0.1)
            volume = 1000 + int(np.random.normal(0, 50))
            timestamp = self.base_time + timedelta(seconds=i)
            self.indicator.update_market_data(price, volume, timestamp)
        
        # 第二阶段：突破上涨
        for i in range(30, 60):
            price = base_price + (i - 29) * 0.1  # 线性上涨
            volume = 1500 + int(np.random.normal(0, 100))  # 成交量增加
            timestamp = self.base_time + timedelta(seconds=i)
            self.indicator.update_market_data(price, volume, timestamp)
        
        # 检查是否生成了信号
        self.assertGreater(len(self.indicator.signal_history), 0)
        
        # 检查信号质量
        signals = list(self.indicator.signal_history)
        bullish_signals = [s for s in signals if s.signal_type == "bullish"]
        self.assertGreater(len(bullish_signals), 0)  # 应该有看涨信号
        
    def test_trading_signal_strength(self):
        """测试交易信号强度"""
        # 生成强烈的上涨信号
        base_price = 100.0
        for i in range(80):
            price = base_price + i * 0.05  # 强劲上涨
            volume = 1000 + i * 20  # 成交量增加
            timestamp = self.base_time + timedelta(seconds=i)
            self.indicator.update_market_data(price, volume, timestamp)
        
        # 获取交易信号强度
        signal_type, strength, confidence = self.indicator.get_trading_signal_strength()
        
        self.assertIn(signal_type, ["bullish", "bearish", "neutral"])
        self.assertGreaterEqual(strength, 0.0)
        self.assertLessEqual(strength, 1.0)
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)
        
        # 在明显上涨趋势中，应该倾向于看涨
        if signal_type != "neutral":
            self.assertEqual(signal_type, "bullish")
            self.assertGreater(strength, 0.3)
            
    def test_get_latest_indicators(self):
        """测试获取最新指标"""
        # 添加数据
        for i in range(70):
            price = 100.0 + i * 0.02
            volume = 1000 + i * 10
            timestamp = self.base_time + timedelta(seconds=i)
            self.indicator.update_market_data(price, volume, timestamp)
        
        # 获取指标
        indicators = self.indicator.get_latest_indicators()
        
        self.assertIsInstance(indicators, dict)
        self.assertIn("timestamp", indicators)
        self.assertIn("calculation_count", indicators)
        self.assertIn("signal_count", indicators)
        
        if "ema" in indicators:
            ema = indicators["ema"]
            self.assertIn("ema3", ema)
            self.assertIn("ema8", ema)
            self.assertIn("cross_signal", ema)
            
        if "momentum" in indicators:
            momentum = indicators["momentum"]
            self.assertIn("momentum_10s", momentum)
            self.assertIn("momentum_30s", momentum)
            self.assertIn("momentum_1m", momentum)
            
        if "volume" in indicators:
            volume = indicators["volume"]
            self.assertIn("volume_ratio", volume)
            self.assertIn("volume_spike", volume)
            
    def test_ema_cross_detection(self):
        """测试EMA穿越检测"""
        # 生成EMA金叉场景
        base_price = 100.0
        
        # 第一阶段：下降趋势，EMA8 > EMA3
        for i in range(30):
            price = base_price - i * 0.1
            timestamp = self.base_time + timedelta(seconds=i)
            self.indicator.update_market_data(price, 1000, timestamp)
        
        # 第二阶段：反转上升，形成金叉
        for i in range(30, 60):
            price = base_price - 3.0 + (i - 30) * 0.15  # 快速反弹
            timestamp = self.base_time + timedelta(seconds=i)
            self.indicator.update_market_data(price, 1000, timestamp)
        
        # 检查是否检测到金叉
        cross_signals = [ema for ema in self.indicator.ema_history 
                        if ema.cross_signal == "bullish"]
        self.assertGreater(len(cross_signals), 0)
        
    def test_momentum_consistency(self):
        """测试动量一致性检测"""
        # 生成一致的上涨动量
        base_price = 100.0
        for i in range(80):
            # 确保各时间段动量都为正且超过阈值
            price = base_price + (i ** 1.1) * 0.01  # 加速上涨
            timestamp = self.base_time + timedelta(seconds=i)
            self.indicator.update_market_data(price, 1000, timestamp)
        
        # 检查最新动量一致性
        if self.indicator.momentum_history:
            latest_momentum = self.indicator.momentum_history[-1]
            self.assertTrue(latest_momentum.consistency)
            self.assertEqual(latest_momentum.direction, "up")
            
    def test_volume_spike_detection(self):
        """测试成交量突增检测"""
        # 建立正常成交量基线
        for i in range(40):
            price = 100.0 + np.random.normal(0, 0.1)
            volume = 1000 + int(np.random.normal(0, 50))
            timestamp = self.base_time + timedelta(seconds=i)
            self.indicator.update_market_data(price, volume, timestamp)
        
        # 插入成交量突增
        spike_volume = 3000  # 3倍基线成交量
        self.indicator.update_market_data(100.5, spike_volume, 
                                        self.base_time + timedelta(seconds=40))
        
        # 检查是否检测到成交量突增
        volume_spikes = [vol for vol in self.indicator.volume_history 
                        if vol.volume_spike]
        self.assertGreater(len(volume_spikes), 0)
        
    def test_clear_history(self):
        """测试清理历史数据"""
        # 添加一些数据
        for i in range(50):
            price = 100.0 + i * 0.1
            volume = 1000 + i * 10
            timestamp = self.base_time + timedelta(seconds=i)
            self.indicator.update_market_data(price, volume, timestamp)
        
        # 验证数据存在
        self.assertGreater(len(self.indicator.price_data), 0)
        self.assertGreater(len(self.indicator.volume_data), 0)
        self.assertGreater(self.indicator.calculation_count, 0)
        
        # 清理历史
        self.indicator.clear_history()
        
        # 验证数据已清理
        self.assertEqual(len(self.indicator.price_data), 0)
        self.assertEqual(len(self.indicator.volume_data), 0)
        self.assertEqual(len(self.indicator.ema_history), 0)
        self.assertEqual(len(self.indicator.momentum_history), 0)
        self.assertEqual(len(self.indicator.volume_history), 0)
        self.assertEqual(len(self.indicator.signal_history), 0)
        self.assertEqual(self.indicator.calculation_count, 0)
        self.assertEqual(self.indicator.signal_count, 0)
        
    def test_get_statistics(self):
        """测试统计信息"""
        # 添加数据
        for i in range(30):
            price = 100.0 + i * 0.1
            volume = 1000 + i * 10
            timestamp = self.base_time + timedelta(seconds=i)
            self.indicator.update_market_data(price, volume, timestamp)
        
        # 获取统计信息
        stats = self.indicator.get_statistics()
        
        self.assertIsInstance(stats, dict)
        self.assertIn("calculation_count", stats)
        self.assertIn("signal_count", stats)
        self.assertIn("data_points", stats)
        self.assertIn("ema_history_count", stats)
        self.assertIn("momentum_history_count", stats)
        self.assertIn("volume_history_count", stats)
        self.assertIn("signal_history_count", stats)
        self.assertIn("last_update", stats)
        
        self.assertEqual(stats["data_points"], 30)
        self.assertGreater(stats["calculation_count"], 0)
        
    def test_create_technical_indicators_function(self):
        """测试便捷创建函数"""
        indicator1 = create_technical_indicators()
        self.assertIsInstance(indicator1, RealTimeTechnicalIndicators)
        
        config = TradingConstants()
        indicator2 = create_technical_indicators(config)
        self.assertIsInstance(indicator2, RealTimeTechnicalIndicators)
        self.assertEqual(indicator2.config, config)
        
    def test_data_model_properties(self):
        """测试数据模型属性"""
        # 测试TechnicalSignal
        signal = TechnicalSignal(
            timestamp=self.base_time,
            signal_type="bullish",
            strength=0.8,
            confidence=0.7,
            source="ema_cross"
        )
        self.assertEqual(signal.signal_type, "bullish")
        self.assertEqual(signal.strength, 0.8)
        self.assertEqual(signal.confidence, 0.7)
        
        # 测试MomentumData
        momentum = MomentumData(
            timestamp=self.base_time,
            price=100.0,
            momentum_10s=0.01,
            momentum_30s=0.015,
            momentum_1m=0.02,
            direction="up"
        )
        self.assertEqual(momentum.direction, "up")
        self.assertEqual(momentum.momentum_10s, 0.01)
        
        # 测试VolumeData
        volume = VolumeData(
            timestamp=self.base_time,
            current_volume=1500,
            volume_ratio=1.5,
            volume_spike=True,
            flow_pressure="buy"
        )
        self.assertEqual(volume.flow_pressure, "buy")
        self.assertTrue(volume.volume_spike)
        
    def test_edge_cases(self):
        """测试边界情况"""
        # 测试空数据
        indicators = self.indicator.get_latest_indicators()
        self.assertIsInstance(indicators, dict)
        
        signal_type, strength, confidence = self.indicator.get_trading_signal_strength()
        self.assertEqual(signal_type, "neutral")
        self.assertEqual(strength, 0.0)
        self.assertEqual(confidence, 0.0)
        
        # 测试单个数据点
        self.indicator.update_market_data(100.0, 1000, self.base_time)
        indicators = self.indicator.get_latest_indicators()
        self.assertIn("calculation_count", indicators)
        
        # 测试异常价格数据
        self.indicator.update_market_data(0.0, 1000, self.base_time)  # 零价格
        self.indicator.update_market_data(-100.0, 1000, self.base_time)  # 负价格
        
        # 测试异常成交量数据
        self.indicator.update_market_data(100.0, 0, self.base_time)  # 零成交量
        self.indicator.update_market_data(100.0, -1000, self.base_time)  # 负成交量


class TestTechnicalIndicatorsIntegration(unittest.TestCase):
    """技术指标集成测试"""
    
    def setUp(self):
        """测试前准备"""
        self.indicator = create_technical_indicators()
        self.base_time = datetime.now()
        
    def test_full_trading_scenario(self):
        """测试完整交易场景"""
        # 模拟一个完整的交易日场景
        base_price = 100.0
        scenarios = [
            # 开盘横盘
            {"duration": 20, "trend": "flat", "volatility": 0.1},
            # 突破上涨
            {"duration": 30, "trend": "up", "volatility": 0.05},
            # 高位整理
            {"duration": 15, "trend": "flat", "volatility": 0.08},
            # 回调下跌
            {"duration": 25, "trend": "down", "volatility": 0.06},
            # 底部反弹
            {"duration": 20, "trend": "up", "volatility": 0.04}
        ]
        
        current_price = base_price
        total_seconds = 0
        
        for scenario in scenarios:
            for i in range(scenario["duration"]):
                # 根据趋势生成价格
                if scenario["trend"] == "up":
                    trend_component = i * 0.05
                elif scenario["trend"] == "down":
                    trend_component = -i * 0.03
                else:  # flat
                    trend_component = np.sin(i * 0.2) * 0.1
                
                # 添加波动性
                volatility_component = np.random.normal(0, scenario["volatility"])
                
                current_price = current_price + trend_component + volatility_component
                
                # 成交量根据趋势调整
                base_volume = 1000
                if scenario["trend"] != "flat":
                    volume = base_volume + int(np.random.normal(300, 100))
                else:
                    volume = base_volume + int(np.random.normal(0, 50))
                
                timestamp = self.base_time + timedelta(seconds=total_seconds + i)
                self.indicator.update_market_data(current_price, volume, timestamp)
            
            total_seconds += scenario["duration"]
        
        # 验证指标计算
        indicators = self.indicator.get_latest_indicators()
        self.assertIn("ema", indicators)
        self.assertIn("momentum", indicators)
        self.assertIn("volume", indicators)
        
        # 验证信号生成
        signal_type, strength, confidence = self.indicator.get_trading_signal_strength()
        self.assertIn(signal_type, ["bullish", "bearish", "neutral"])
        
        # 验证统计信息
        stats = self.indicator.get_statistics()
        self.assertGreater(stats["calculation_count"], 0)
        self.assertEqual(stats["data_points"], total_seconds)
        
    def test_real_time_performance(self):
        """测试实时性能"""
        import time
        
        # 测试连续数据更新的性能
        start_time = time.time()
        
        for i in range(200):  # 200个数据点
            price = 100.0 + np.sin(i * 0.1) * 2 + np.random.normal(0, 0.1)
            volume = 1000 + int(np.random.normal(0, 100))
            timestamp = self.base_time + timedelta(seconds=i)
            
            self.indicator.update_market_data(price, volume, timestamp)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # 验证性能要求 (应该能够处理高频数据)
        self.assertLess(duration, 2.0)  # 200个数据点应在2秒内完成
        
        # 验证计算结果
        indicators = self.indicator.get_latest_indicators()
        self.assertIsNotNone(indicators)
        
        stats = self.indicator.get_statistics()
        self.assertEqual(stats["data_points"], 200)


if __name__ == "__main__":
    print("🚀 开始技术指标模块测试...")
    
    # 创建测试套件
    test_suite = unittest.TestSuite()
    
    # 添加测试用例
    test_suite.addTest(unittest.makeSuite(TestTechnicalIndicators))
    test_suite.addTest(unittest.makeSuite(TestTechnicalIndicatorsIntegration))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # 输出测试结果
    if result.wasSuccessful():
        print("\n✅ 所有测试通过！")
        print(f"运行测试数: {result.testsRun}")
        print(f"失败: {len(result.failures)}")
        print(f"错误: {len(result.errors)}")
    else:
        print("\n❌ 测试失败！")
        print(f"运行测试数: {result.testsRun}")
        print(f"失败: {len(result.failures)}")
        print(f"错误: {len(result.errors)}")
        
        if result.failures:
            print("\n失败详情:")
            for test, traceback in result.failures:
                print(f"- {test}: {traceback}")
        
        if result.errors:
            print("\n错误详情:")
            for test, traceback in result.errors:
                print(f"- {test}: {traceback}")
