#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
重构后的QQQ末日期权功能测试文件
测试新的模块化架构
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import pandas as pd

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.services.option_analyzer import OptionAnalyzer
from src.utils.option_calculator import OptionCalculator
from src.utils.data_validator import DataValidator
from src.config.option_config import OptionConfig, OptionStrategy
from src.models.option_models import OptionData, OptionFilter


class TestOptionCalculator(unittest.TestCase):
    """期权计算器测试类"""
    
    def setUp(self):
        """测试前置设置"""
        self.config = OptionConfig()
        self.calculator = OptionCalculator(self.config)
    
    def test_calculate_liquidity_score(self):
        """测试流动性评分计算"""
        print("   测试流动性评分计算...")
        
        # 高流动性期权
        high_liquidity_option = OptionData(
            symbol="QQQ240821C00565000",
            strike=565.0,
            right="CALL",
            expiry="2024-08-21",
            volume=10000,
            open_interest=5000
        )
        
        # 低流动性期权
        low_liquidity_option = OptionData(
            symbol="QQQ240821C00570000",
            strike=570.0,
            right="CALL",
            expiry="2024-08-21",
            volume=10,
            open_interest=50
        )
        
        high_score = self.calculator._calculate_liquidity_score(high_liquidity_option)
        low_score = self.calculator._calculate_liquidity_score(low_liquidity_option)
        
        self.assertGreater(high_score, low_score)
        self.assertGreaterEqual(high_score, 0)
        self.assertLessEqual(high_score, 100)
    
    def test_calculate_spread_score(self):
        """测试价差评分计算"""
        print("   测试价差评分计算...")
        
        # 窄价差期权
        tight_spread_option = OptionData(
            symbol="QQQ240821C00565000",
            strike=565.0,
            right="CALL",
            expiry="2024-08-21",
            latest_price=2.0,
            bid=1.95,
            ask=2.05
        )
        
        # 宽价差期权
        wide_spread_option = OptionData(
            symbol="QQQ240821C00570000",
            strike=570.0,
            right="CALL",
            expiry="2024-08-21",
            latest_price=1.0,
            bid=0.8,
            ask=1.2
        )
        
        tight_score = self.calculator._calculate_spread_score(tight_spread_option)
        wide_score = self.calculator._calculate_spread_score(wide_spread_option)
        
        self.assertGreater(tight_score, wide_score)
        self.assertGreaterEqual(tight_score, 0)
        self.assertLessEqual(tight_score, 100)
    
    def test_calculate_greeks_score(self):
        """测试希腊字母评分计算"""
        print("   测试希腊字母评分计算...")
        
        # ATM期权（理想Delta）
        atm_option = OptionData(
            symbol="QQQ240821C00565000",
            strike=565.0,
            right="CALL",
            expiry="2024-08-21",
            delta=0.5,
            gamma=0.05
        )
        
        # OTM期权
        otm_option = OptionData(
            symbol="QQQ240821C00580000",
            strike=580.0,
            right="CALL",
            expiry="2024-08-21",
            delta=0.1,
            gamma=0.02
        )
        
        atm_score = self.calculator._calculate_greeks_score(atm_option, 565.0)
        otm_score = self.calculator._calculate_greeks_score(otm_option, 565.0)
        
        self.assertGreater(atm_score, otm_score)
        self.assertGreaterEqual(atm_score, 0)
        self.assertLessEqual(atm_score, 100)
    
    def test_delta_estimation(self):
        """测试Delta估算功能"""
        print("   测试Delta估算功能...")
        
        current_price = 565.0
        
        # 测试Call期权 (使用更大的价格差异)
        itm_call_delta = self.calculator.estimate_delta(current_price, 535.0, "CALL")  # 深度ITM: 565/535=1.056
        atm_call_delta = self.calculator.estimate_delta(current_price, 565.0, "CALL")  # ATM: 565/565=1.0
        otm_call_delta = self.calculator.estimate_delta(current_price, 595.0, "CALL")  # 深度OTM: 565/595=0.95
        
        self.assertGreater(itm_call_delta, atm_call_delta)
        self.assertGreater(atm_call_delta, otm_call_delta)
        
        # 测试Put期权 (使用更大的价格差异)
        itm_put_delta = self.calculator.estimate_delta(current_price, 595.0, "PUT")  # 深度ITM: 565/595=0.95
        atm_put_delta = self.calculator.estimate_delta(current_price, 565.0, "PUT")  # ATM: 565/565=1.0
        otm_put_delta = self.calculator.estimate_delta(current_price, 535.0, "PUT")  # 深度OTM: 565/535=1.056
        
        self.assertLess(itm_put_delta, atm_put_delta)
        self.assertLess(atm_put_delta, otm_put_delta)


class TestDataValidator(unittest.TestCase):
    """数据验证器测试类"""
    
    def setUp(self):
        """测试前置设置"""
        self.validator = DataValidator()
    
    def test_validate_dataframe(self):
        """测试DataFrame验证"""
        print("   测试DataFrame验证...")
        
        # 有效DataFrame
        valid_df = pd.DataFrame({
            'symbol': ['QQQ240821C00565000', 'QQQ240821P00565000'],
            'strike': [565.0, 565.0],
            'put_call': ['CALL', 'PUT']
        })
        
        # 无效DataFrame（缺少必需字段）
        invalid_df = pd.DataFrame({
            'symbol': ['QQQ240821C00565000'],
            'strike': [565.0]
            # 缺少put_call字段
        })
        
        # 空DataFrame
        empty_df = pd.DataFrame()
        
        self.assertTrue(self.validator.validate_dataframe(valid_df))
        self.assertFalse(self.validator.validate_dataframe(invalid_df))
        self.assertFalse(self.validator.validate_dataframe(empty_df))
        self.assertFalse(self.validator.validate_dataframe(None))
    
    def test_validate_price(self):
        """测试价格验证"""
        print("   测试价格验证...")
        
        self.assertTrue(self.validator.validate_price(565.50))
        self.assertTrue(self.validator.validate_price(100))
        self.assertFalse(self.validator.validate_price(0))
        self.assertFalse(self.validator.validate_price(-10.5))
        self.assertFalse(self.validator.validate_price("invalid"))
    
    def test_validate_strategy(self):
        """测试策略验证"""
        print("   测试策略验证...")
        
        self.assertTrue(self.validator.validate_strategy("liquidity"))
        self.assertTrue(self.validator.validate_strategy("balanced"))
        self.assertTrue(self.validator.validate_strategy("value"))
        self.assertFalse(self.validator.validate_strategy("invalid"))
        self.assertFalse(self.validator.validate_strategy(""))
        self.assertFalse(self.validator.validate_strategy(None))


class TestOptionAnalyzer(unittest.TestCase):
    """期权分析器测试类"""
    
    def setUp(self):
        """测试前置设置"""
        self.analyzer = OptionAnalyzer()
    
    def test_analyze_options_with_empty_data(self):
        """测试空数据分析"""
        print("   测试空数据分析...")
        
        empty_df = pd.DataFrame()
        result = self.analyzer.analyze_options(
            option_chains=empty_df,
            current_price=565.0,
            strategy=OptionStrategy.BALANCED,
            top_n=3
        )
        
        # 应该返回包含错误的结果，而不是None
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.error)
    
    def test_analyze_options_with_valid_data(self):
        """测试有效数据分析"""
        print("   测试有效数据分析...")
        
        # 创建模拟数据
        test_data = pd.DataFrame({
            'symbol': ['QQQ240821C00565000', 'QQQ240821P00565000', 'QQQ240821C00570000'],
            'strike': [565.0, 565.0, 570.0],
            'put_call': ['CALL', 'PUT', 'CALL'],
            'expiry': ['2024-08-21', '2024-08-21', '2024-08-21'],
            'latest_price': [2.5, 2.0, 1.5],
            'bid_price': [2.4, 1.9, 1.4],
            'ask_price': [2.6, 2.1, 1.6],
            'volume': [1000, 800, 600],
            'open_interest': [500, 400, 300]
        })
        
        result = self.analyzer.analyze_options(
            option_chains=test_data,
            current_price=565.0,
            strategy=OptionStrategy.BALANCED,
            top_n=2
        )
        
        self.assertIsNotNone(result)
        self.assertLessEqual(len(result.calls), 2)
        self.assertLessEqual(len(result.puts), 2)
        self.assertEqual(result.strategy, "balanced")
        self.assertEqual(result.current_price, 565.0)


class TestOptionFilter(unittest.TestCase):
    """期权筛选器测试类"""
    
    def setUp(self):
        """测试前置设置"""
        # 创建测试期权数据，手动设置spread_percentage
        option1 = OptionData(
            symbol="QQQ240821C00565000",
            strike=565.0,
            right="CALL",
            expiry="2024-08-21",
            volume=1000,
            open_interest=500,
            latest_price=2.0,
            bid=1.95,
            ask=2.05
        )
        
        option2 = OptionData(
            symbol="QQQ240821P00565000",
            strike=565.0,
            right="PUT",
            expiry="2024-08-21",
            volume=50,
            open_interest=25,
            latest_price=1.0,
            bid=0.875,
            ask=1.125
        )
        
        option3 = OptionData(
            symbol="QQQ240821C00570000",
            strike=570.0,
            right="CALL",
            expiry="2024-08-21",
            volume=800,
            open_interest=300,
            latest_price=1.5,
            bid=1.425,
            ask=1.575
        )
        
        self.test_options = [option1, option2, option3]
    
    def test_volume_filter(self):
        """测试成交量筛选"""
        print("   测试成交量筛选...")
        
        volume_filter = OptionFilter(min_volume=100)
        filtered = volume_filter.apply(self.test_options)
        
        self.assertEqual(len(filtered), 2)  # 只有两个期权满足成交量>=100
        for option in filtered:
            self.assertGreaterEqual(option.volume, 100)
    
    def test_spread_filter(self):
        """测试价差筛选"""
        print("   测试价差筛选...")
        
        spread_filter = OptionFilter(max_spread_percentage=0.15)
        filtered = spread_filter.apply(self.test_options)
        
        self.assertEqual(len(filtered), 2)  # 只有两个期权满足价差<=15%
        for option in filtered:
            self.assertLessEqual(option.spread_percentage, 0.15)
    
    def test_option_type_filter(self):
        """测试期权类型筛选"""
        print("   测试期权类型筛选...")
        
        call_filter = OptionFilter(option_types=["CALL"])
        filtered = call_filter.apply(self.test_options)
        
        self.assertEqual(len(filtered), 2)  # 只有两个CALL期权
        for option in filtered:
            self.assertEqual(option.right.upper(), "CALL")


class TestIntegration(unittest.TestCase):
    """集成测试类"""
    
    def test_end_to_end_workflow(self):
        """测试端到端工作流"""
        print("   测试端到端工作流...")
        
        # 创建测试组件
        analyzer = OptionAnalyzer()
        
        # 创建模拟数据
        test_data = pd.DataFrame({
            'symbol': ['QQQ240821C00565000', 'QQQ240821P00565000'],
            'strike': [565.0, 565.0],
            'put_call': ['CALL', 'PUT'],
            'expiry': ['2024-08-21', '2024-08-21'],
            'latest_price': [2.5, 2.0],
            'bid_price': [2.4, 1.9],
            'ask_price': [2.6, 2.1],
            'volume': [1000, 800],
            'open_interest': [500, 400]
        })
        
        # 创建筛选条件
        option_filter = OptionFilter(
            min_volume=100,
            max_spread_percentage=0.20
        )
        
        # 执行分析
        result = analyzer.analyze_options(
            option_chains=test_data,
            current_price=565.0,
            strategy=OptionStrategy.BALANCED,
            top_n=1,
            option_filter=option_filter
        )
        
        # 验证结果
        self.assertIsNotNone(result)
        self.assertIsInstance(result.calls, list)
        self.assertIsInstance(result.puts, list)
        self.assertTrue(len(result.calls) <= 1)
        self.assertTrue(len(result.puts) <= 1)


def run_tests():
    """运行所有测试"""
    print("🧪 开始运行重构后的QQQ期权功能测试...\n")
    
    # 创建测试套件
    test_classes = [
        TestOptionCalculator,
        TestDataValidator,
        TestOptionAnalyzer,
        TestOptionFilter,
        TestIntegration
    ]
    
    total_tests = 0
    total_errors = 0
    
    for test_class in test_classes:
        print(f"{'='*50}")
        print(f"运行 {test_class.__name__}")
        print(f"{'='*50}")
        
        suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        total_tests += result.testsRun
        total_errors += len(result.errors) + len(result.failures)
        
        print()
    
    print(f"{'='*50}")
    print(f"测试总结")
    print(f"{'='*50}")
    print(f"总测试数: {total_tests}")
    print(f"失败/错误数: {total_errors}")
    print(f"成功率: {((total_tests - total_errors) / total_tests * 100):.1f}%")
    
    if total_errors == 0:
        print("🎉 所有测试通过！")
    else:
        print(f"⚠️ 有 {total_errors} 个测试失败")
    
    return total_errors == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
