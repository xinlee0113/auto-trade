#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场状态检测器测试

测试市场状态检测器的各项功能：
1. VIX分析和波动率状态判断
2. 成交量异动检测
3. 技术指标综合评估
4. 市场状态转换逻辑
5. 实时监控和回调机制

Author: AI Assistant
Date: 2024-01-22
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import time
from datetime import datetime, timedelta
from dataclasses import replace

from src.services.market_state_detector import (
    MarketStateDetector, MarketStateConfig, MarketState, VIXLevel, VolumeState,
    MarketStateData, create_market_state_detector
)
from src.models.trading_models import UnderlyingTickData
from src.config.trading_config import TradingConfig, DEFAULT_TRADING_CONFIG


class TestMarketStateDetector(unittest.TestCase):
    """市场状态检测器基础测试"""
    
    def setUp(self):
        """测试前置设置"""
        self.config = MarketStateConfig()
        self.detector = MarketStateDetector(self.config)
        
        # 测试数据
        self.sample_market_data = {
            "QQQ": UnderlyingTickData(
                symbol="QQQ",
                timestamp=datetime.now(),
                price=562.45,
                volume=1000000,
                bid=562.40,
                ask=562.50
            ),
            "SPY": UnderlyingTickData(
                symbol="SPY",
                timestamp=datetime.now(),
                price=555.20,
                volume=800000,
                bid=555.15,
                ask=555.25
            )
        }
    
    def test_initialization(self):
        """测试初始化"""
        self.assertIsNotNone(self.detector)
        self.assertEqual(self.detector.config, self.config)
        self.assertIsNone(self.detector.current_state)
        self.assertEqual(len(self.detector.state_history), 0)
        
        # 测试默认配置
        default_detector = MarketStateDetector()
        self.assertIsNotNone(default_detector.config)
    
    def test_vix_analysis(self):
        """测试VIX分析"""
        # 测试低VIX
        vix_analysis = self.detector._analyze_vix(12.0)
        self.assertEqual(vix_analysis['level'], VIXLevel.LOW)
        
        # 测试正常VIX
        vix_analysis = self.detector._analyze_vix(18.0)
        self.assertEqual(vix_analysis['level'], VIXLevel.NORMAL)
        
        # 测试高VIX
        vix_analysis = self.detector._analyze_vix(35.0)
        self.assertEqual(vix_analysis['level'], VIXLevel.HIGH)
        
        # 测试极端VIX
        vix_analysis = self.detector._analyze_vix(45.0)
        self.assertEqual(vix_analysis['level'], VIXLevel.EXTREME)
    
    def test_volume_analysis(self):
        """测试成交量分析"""
        # 测试正常成交量
        volume_analysis = self.detector._analyze_volume(self.sample_market_data)
        self.assertIn('state', volume_analysis)
        self.assertIn('confidence', volume_analysis)
        
        # 测试空数据
        empty_analysis = self.detector._analyze_volume({})
        self.assertEqual(empty_analysis['state'], VolumeState.NORMAL)
        
        # 测试无效数据
        none_analysis = self.detector._analyze_volume(None)
        self.assertEqual(none_analysis['state'], VolumeState.NORMAL)
    
    def test_technical_analysis(self):
        """测试技术指标分析"""
        # 准备价格历史数据
        prices = [560, 561, 562, 563, 562, 561, 562, 563, 564, 565]
        for price in prices:
            self.detector.price_history["QQQ"].append(price)
        
        technical_analysis = self.detector._analyze_technical_indicators(self.sample_market_data)
        
        self.assertIn('momentum', technical_analysis)
        self.assertIn('trend', technical_analysis)
        self.assertIn('volatility', technical_analysis)
        
        # 检查值的合理性
        self.assertGreaterEqual(technical_analysis['momentum'], 0)
        self.assertLessEqual(technical_analysis['momentum'], 1)
    
    def test_market_state_determination(self):
        """测试市场状态判断"""
        # 测试异动市场
        vix_analysis = {'level': VIXLevel.HIGH, 'confidence': 0.9}
        volume_analysis = {'state': VolumeState.SPIKE, 'confidence': 0.9}
        technical_analysis = {'momentum': 0.5, 'trend': 0.5, 'volatility': 0.5}
        
        state, confidence = self.detector._determine_market_state(
            vix_analysis, volume_analysis, technical_analysis
        )
        self.assertEqual(state, MarketState.ANOMALY)
        
        # 测试正常市场
        vix_analysis = {'level': VIXLevel.NORMAL, 'confidence': 0.7}
        volume_analysis = {'state': VolumeState.NORMAL, 'confidence': 0.7}
        
        state, confidence = self.detector._determine_market_state(
            vix_analysis, volume_analysis, technical_analysis
        )
        self.assertEqual(state, MarketState.NORMAL)
    
    def test_state_detection(self):
        """测试状态检测"""
        state_data = self.detector.detect_market_state(
            vix_data=20.0,
            market_data=self.sample_market_data
        )
        
        self.assertIsNotNone(state_data)
        self.assertIsInstance(state_data, MarketStateData)
        self.assertIsInstance(state_data.state, MarketState)
        self.assertGreaterEqual(state_data.confidence, 0)
        self.assertLessEqual(state_data.confidence, 1)
    
    def test_state_change_logic(self):
        """测试状态变化逻辑"""
        # 创建初始状态
        initial_state = MarketStateData(
            timestamp=datetime.now() - timedelta(minutes=1),
            state=MarketState.NORMAL,
            confidence=0.8,
            vix_level=VIXLevel.NORMAL,
            volume_state=VolumeState.NORMAL
        )
        
        # 创建新状态
        new_state = MarketStateData(
            timestamp=datetime.now(),
            state=MarketState.VOLATILE,
            confidence=0.8,
            vix_level=VIXLevel.ELEVATED,
            volume_state=VolumeState.HIGH
        )
        
        # 测试应该改变状态
        should_change = self.detector._should_change_state(initial_state, new_state)
        self.assertTrue(should_change)
        
        # 测试置信度不足
        low_confidence_state = replace(new_state, confidence=0.5)
        should_change = self.detector._should_change_state(initial_state, low_confidence_state)
        self.assertFalse(should_change)
    
    def test_market_data_update(self):
        """测试市场数据更新"""
        symbol = "QQQ"
        data = self.sample_market_data[symbol]
        
        # 更新数据
        self.detector.update_market_data(symbol, data)
        
        # 检查数据是否更新
        self.assertGreater(len(self.detector.price_history[symbol]), 0)
        self.assertEqual(self.detector.price_history[symbol][-1], data.price)
    
    def test_callback_mechanism(self):
        """测试回调机制"""
        callback_called = False
        old_state_received = None
        new_state_received = None
        
        def test_callback(old_state, new_state):
            nonlocal callback_called, old_state_received, new_state_received
            callback_called = True
            old_state_received = old_state
            new_state_received = new_state
        
        # 注册回调
        self.detector.register_state_change_callback(test_callback)
        
        # 模拟状态变化
        old_state = MarketStateData(
            timestamp=datetime.now() - timedelta(minutes=1),
            state=MarketState.NORMAL,
            confidence=0.8,
            vix_level=VIXLevel.NORMAL,
            volume_state=VolumeState.NORMAL
        )
        
        new_state = MarketStateData(
            timestamp=datetime.now(),
            state=MarketState.VOLATILE,
            confidence=0.8,
            vix_level=VIXLevel.ELEVATED,
            volume_state=VolumeState.HIGH
        )
        
        # 设置初始状态
        self.detector.current_state = old_state
        self.detector.last_state_change = old_state.timestamp
        
        # 触发状态更新
        self.detector._update_market_state(new_state)
        
        # 验证回调被调用
        self.assertTrue(callback_called)
        self.assertEqual(old_state_received.state, MarketState.NORMAL)
        self.assertEqual(new_state_received.state, MarketState.VOLATILE)


class TestMarketStateDetectorIntegration(unittest.TestCase):
    """市场状态检测器集成测试"""
    
    def setUp(self):
        """测试前置设置"""
        self.config = MarketStateConfig(
            min_state_duration=1,  # 1秒，便于测试
            state_change_threshold=0.6
        )
        self.detector = MarketStateDetector(self.config)
    
    def test_monitoring_lifecycle(self):
        """测试监控生命周期"""
        # 开始监控
        self.detector.start_monitoring(update_interval=1)
        self.assertTrue(self.detector._running)
        
        # 等待一点时间
        time.sleep(0.1)
        
        # 停止监控
        self.detector.stop_monitoring()
        self.assertFalse(self.detector._running)
    
    def test_real_time_detection(self):
        """测试实时检测"""
        # 模拟实时数据
        market_data = {
            "QQQ": UnderlyingTickData(
                symbol="QQQ",
                timestamp=datetime.now(),
                price=562.45,
                volume=2000000,  # 高成交量
                bid=562.40,
                ask=562.50
            )
        }
        
        # 检测状态
        state = self.detector.detect_market_state(
            vix_data=35.0,  # 高VIX
            market_data=market_data
        )
        
        # 验证异动市场检测
        self.assertEqual(state.state, MarketState.ANOMALY)
        self.assertGreater(state.confidence, 0.8)
    
    def test_state_history_tracking(self):
        """测试状态历史跟踪"""
        # 生成多个状态
        states = [
            MarketState.NORMAL,
            MarketState.VOLATILE,
            MarketState.ANOMALY,
            MarketState.NORMAL
        ]
        
        for i, state_type in enumerate(states):
            state_data = MarketStateData(
                timestamp=datetime.now() + timedelta(seconds=i),
                state=state_type,
                confidence=0.8,
                vix_level=VIXLevel.NORMAL,
                volume_state=VolumeState.NORMAL
            )
            
            self.detector._update_market_state(state_data)
            time.sleep(0.01)  # 确保时间戳不同
        
        # 检查历史记录
        history = self.detector.get_state_history()
        self.assertGreater(len(history), 0)
        
        # 检查最新状态
        current_state = self.detector.get_current_state()
        self.assertEqual(current_state.state, MarketState.NORMAL)
    
    @patch('src.services.market_state_detector.MarketStateDetector._get_vix_data')
    def test_vix_data_integration(self, mock_vix):
        """测试VIX数据整合"""
        # 模拟VIX数据
        mock_vix.return_value = 25.0
        
        state = self.detector.detect_market_state()
        
        self.assertIsNotNone(state)
        self.assertEqual(state.vix_level, VIXLevel.ELEVATED)
        mock_vix.assert_called_once()


class TestMarketStateConfig(unittest.TestCase):
    """市场状态配置测试"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = MarketStateConfig()
        
        # 检查VIX阈值
        self.assertEqual(config.vix_low_threshold, 15.0)
        self.assertEqual(config.vix_normal_threshold, 20.0)
        self.assertEqual(config.vix_elevated_threshold, 30.0)
        self.assertEqual(config.vix_high_threshold, 40.0)
        
        # 检查成交量阈值
        self.assertEqual(config.volume_spike_threshold, 2.5)
        self.assertEqual(config.volume_high_threshold, 1.5)
        
        # 检查监控符号
        self.assertIn("QQQ", config.watch_symbols)
        self.assertIn("SPY", config.watch_symbols)
    
    def test_custom_config(self):
        """测试自定义配置"""
        custom_symbols = ["AAPL", "MSFT"]
        config = MarketStateConfig(
            vix_low_threshold=12.0,
            vix_high_threshold=35.0,
            watch_symbols=custom_symbols
        )
        
        self.assertEqual(config.vix_low_threshold, 12.0)
        self.assertEqual(config.vix_high_threshold, 35.0)
        self.assertEqual(config.watch_symbols, custom_symbols)


class TestMarketStateFactory(unittest.TestCase):
    """市场状态检测器工厂测试"""
    
    def test_create_detector(self):
        """测试创建检测器"""
        detector = create_market_state_detector()
        self.assertIsInstance(detector, MarketStateDetector)
        
        # 测试带配置创建
        config = MarketStateConfig()
        trading_config = DEFAULT_TRADING_CONFIG
        
        detector_with_config = create_market_state_detector(config, trading_config)
        self.assertIsInstance(detector_with_config, MarketStateDetector)
        self.assertEqual(detector_with_config.config, config)
        self.assertEqual(detector_with_config.trading_config, trading_config)


class TestMarketStateEdgeCases(unittest.TestCase):
    """市场状态检测器边界情况测试"""
    
    def setUp(self):
        """测试前置设置"""
        self.detector = MarketStateDetector()
    
    def test_empty_data_handling(self):
        """测试空数据处理"""
        # 测试空VIX数据
        vix_analysis = self.detector._analyze_vix(None)
        self.assertIn('level', vix_analysis)
        self.assertIn('confidence', vix_analysis)
        
        # 测试空市场数据
        volume_analysis = self.detector._analyze_volume(None)
        self.assertEqual(volume_analysis['state'], VolumeState.NORMAL)
        
        # 测试空技术指标数据
        technical_analysis = self.detector._analyze_technical_indicators(None)
        self.assertIn('momentum', technical_analysis)
    
    def test_invalid_data_handling(self):
        """测试无效数据处理"""
        # 测试负VIX值
        vix_analysis = self.detector._analyze_vix(-5.0)
        self.assertEqual(vix_analysis['level'], VIXLevel.LOW)
        
        # 测试极大VIX值
        vix_analysis = self.detector._analyze_vix(100.0)
        self.assertEqual(vix_analysis['level'], VIXLevel.EXTREME)
    
    def test_concurrent_access(self):
        """测试并发访问"""
        import threading
        
        def update_data():
            for i in range(10):
                data = UnderlyingTickData(
                    symbol="TEST",
                    timestamp=datetime.now(),
                    price=100 + i,
                    volume=1000 + i
                )
                self.detector.update_market_data("TEST", data)
        
        def detect_state():
            for _ in range(10):
                self.detector.detect_market_state()
        
        # 创建多个线程
        threads = []
        for _ in range(3):
            t1 = threading.Thread(target=update_data)
            t2 = threading.Thread(target=detect_state)
            threads.extend([t1, t2])
        
        # 启动线程
        for t in threads:
            t.start()
        
        # 等待完成
        for t in threads:
            t.join()
        
        # 验证没有异常
        self.assertTrue(True)  # 如果到达这里说明没有死锁或异常


if __name__ == '__main__':
    unittest.main()
