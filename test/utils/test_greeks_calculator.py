"""
Greeks计算器测试
确保期权风险指标计算的准确性和可靠性
"""

import unittest
import math
from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from src.utils.greeks_calculator import (
    GreeksCalculator, 
    PortfolioGreeksManager,
    GreeksResult,
    OptionType
)
from src.models.trading_models import OptionTickData, UnderlyingTickData


class TestGreeksCalculator(unittest.TestCase):
    """Greeks计算器基础测试"""
    
    def setUp(self):
        self.calculator = GreeksCalculator()
        
        # 创建测试数据
        self.underlying_data = UnderlyingTickData(
            symbol='QQQ',
            timestamp=datetime.now(),
            price=350.0,
            volume=1000000,
            bid=349.95,
            ask=350.05
        )
        
        # ATM看涨期权
        today = datetime.now().date()
        self.call_option = OptionTickData(
            symbol='QQQ240101C350',
            underlying='QQQ',
            strike=350.0,
            expiry=today.strftime('%Y-%m-%d'),
            right='CALL',
            timestamp=datetime.now(),
            price=2.5,
            volume=5000,
            bid=2.45,
            ask=2.55,
            open_interest=10000
        )
        
        # ATM看跌期权
        self.put_option = OptionTickData(
            symbol='QQQ240101P350',
            underlying='QQQ',
            strike=350.0,
            expiry=today.strftime('%Y-%m-%d'),
            right='PUT',
            timestamp=datetime.now(),
            price=2.3,
            volume=4000,
            bid=2.25,
            ask=2.35,
            open_interest=8000
        )
        
        # OTM期权
        self.otm_call = OptionTickData(
            symbol='QQQ240101C355',
            underlying='QQQ',
            strike=355.0,  # 更接近ATM，确保有时间价值
            expiry=today.strftime('%Y-%m-%d'),
            right='CALL',
            timestamp=datetime.now(),
            price=1.2,    # 合理的价格
            volume=2000,
            bid=1.15,
            ask=1.25,
            open_interest=5000
        )
    
    def test_time_to_expiry_calculation(self):
        """测试到期时间计算"""
        # 今日到期(0DTE)
        today = datetime.now().date().strftime('%Y-%m-%d')
        time_today = self.calculator._calculate_time_to_expiry(today)
        
        # 应该是非常小的正数
        self.assertGreater(time_today, 0)
        self.assertLess(time_today, 1/365)
        print(f"  ✅ 0DTE到期时间: {time_today:.6f}年")
        
        # 明日到期
        tomorrow = (datetime.now().date() + timedelta(days=1)).strftime('%Y-%m-%d')
        time_tomorrow = self.calculator._calculate_time_to_expiry(tomorrow)
        
        self.assertGreater(time_tomorrow, time_today)
        self.assertAlmostEqual(time_tomorrow, 1/365, places=3)
        print(f"  ✅ 1DTE到期时间: {time_tomorrow:.6f}年")
    
    def test_d1_d2_calculation(self):
        """测试d1和d2计算"""
        S, K, T, r, q, sigma = 350.0, 350.0, 0.0274, 0.05, 0.0, 0.3
        
        d1, d2 = self.calculator._calculate_d1_d2(S, K, T, r, q, sigma)
        
        # ATM期权，d1应该略大于0
        self.assertGreater(d1, 0)
        self.assertLess(d2, d1)
        
        print(f"  ✅ d1={d1:.4f}, d2={d2:.4f}")
    
    def test_delta_calculation(self):
        """测试Delta计算"""
        # 计算ATM看涨期权Delta
        result = self.calculator.calculate_greeks(self.call_option, self.underlying_data)
        
        # ATM看涨期权Delta应该接近0.5
        self.assertGreater(result.delta, 0.3)
        self.assertLess(result.delta, 0.7)
        print(f"  ✅ ATM看涨Delta: {result.delta:.4f}")
        
        # 计算ATM看跌期权Delta
        put_result = self.calculator.calculate_greeks(self.put_option, self.underlying_data)
        
        # ATM看跌期权Delta应该接近-0.5
        self.assertLess(put_result.delta, -0.3)
        self.assertGreater(put_result.delta, -0.7)
        print(f"  ✅ ATM看跌Delta: {put_result.delta:.4f}")
        
        # 计算OTM看涨期权Delta
        otm_result = self.calculator.calculate_greeks(self.otm_call, self.underlying_data)
        
        # OTM看涨期权Delta应该小于ATM
        self.assertLess(otm_result.delta, result.delta)
        self.assertGreater(otm_result.delta, 0)
        print(f"  ✅ OTM看涨Delta: {otm_result.delta:.4f}")
    
    def test_gamma_calculation(self):
        """测试Gamma计算"""
        result = self.calculator.calculate_greeks(self.call_option, self.underlying_data)
        
        # Gamma应该为正数
        self.assertGreater(result.gamma, 0)
        
        # 0DTE期权Gamma应该相对较高
        self.assertGreater(result.gamma, 0.001)  # 实际值取决于具体情况
        
        print(f"  ✅ ATM Gamma: {result.gamma:.6f}")
        
        # 验证看涨和看跌期权Gamma相等
        put_result = self.calculator.calculate_greeks(self.put_option, self.underlying_data)
        
        # Gamma对看涨和看跌期权应该相等
        self.assertAlmostEqual(result.gamma, put_result.gamma, places=6)
        print(f"  ✅ Put-Call Gamma相等: {abs(result.gamma - put_result.gamma):.6f}")
    
    def test_theta_calculation(self):
        """测试Theta计算"""
        result = self.calculator.calculate_greeks(self.call_option, self.underlying_data)
        
        # 对于0DTE期权，Theta应该是负数且绝对值较大
        self.assertLess(result.theta, 0)
        
        # 0DTE期权Theta衰减应该很快
        self.assertLess(result.theta, -0.1)  # 每日损失超过0.1
        
        print(f"  ✅ ATM Theta: {result.theta:.4f}")
        print(f"  ✅ 时间衰减率: {result.time_decay_rate:.6f}/分钟")
        
        # 验证Theta燃烧率
        self.assertGreater(result.theta_burn_rate, 0)
        print(f"  ✅ Theta燃烧率: {result.theta_burn_rate:.2%}")
    
    def test_vega_calculation(self):
        """测试Vega计算"""
        result = self.calculator.calculate_greeks(self.call_option, self.underlying_data)
        
        # Vega应该为正数
        self.assertGreater(result.vega, 0)
        
        # 对于0DTE期权，Vega通常较小
        print(f"  ✅ ATM Vega: {result.vega:.4f}")
    
    def test_implied_volatility_calculation(self):
        """测试隐含波动率计算"""
        result = self.calculator.calculate_greeks(self.call_option, self.underlying_data)
        
        # 隐含波动率应该在合理范围内
        self.assertGreater(result.implied_volatility, 0.1)  # 10%以上
        self.assertLess(result.implied_volatility, 3.0)     # 300%以下
        
        print(f"  ✅ 隐含波动率: {result.implied_volatility:.2%}")
    
    def test_risk_assessment(self):
        """测试风险评估"""
        result = self.calculator.calculate_greeks(self.call_option, self.underlying_data)
        
        # 风险等级应该是有效值
        valid_levels = ["LOW", "MEDIUM", "HIGH", "EXTREME"]
        self.assertIn(result.risk_level, valid_levels)
        
        # 风险评分应该在0-100之间
        self.assertGreaterEqual(result.risk_score, 0)
        self.assertLessEqual(result.risk_score, 100)
        
        print(f"  ✅ 风险等级: {result.risk_level}")
        print(f"  ✅ 风险评分: {result.risk_score:.1f}")
    
    def test_0dte_special_indicators(self):
        """测试0DTE特有指标"""
        result = self.calculator.calculate_greeks(self.call_option, self.underlying_data)
        
        # Gamma敞口
        self.assertGreater(result.gamma_exposure, 0)
        print(f"  ✅ Gamma敞口: {result.gamma_exposure:.4f}")
        
        # 时间衰减率（每分钟）
        self.assertGreater(result.time_decay_rate, 0)
        print(f"  ✅ 每分钟衰减: ${result.time_decay_rate:.4f}")
        
        # Theta燃烧率
        self.assertGreater(result.theta_burn_rate, 0)
        print(f"  ✅ Theta燃烧率: {result.theta_burn_rate:.2%}")
    
    def test_cache_functionality(self):
        """测试缓存功能"""
        # 第一次计算
        result1 = self.calculator.calculate_greeks(self.call_option, self.underlying_data)
        
        # 验证缓存
        cached_greeks = self.calculator.get_cached_greeks(self.call_option.symbol)
        self.assertIsNotNone(cached_greeks)
        self.assertEqual(cached_greeks.delta, result1.delta)
        
        cached_vol = self.calculator.get_cached_volatility(self.call_option.symbol)
        self.assertIsNotNone(cached_vol)
        self.assertEqual(cached_vol, result1.implied_volatility)
        
        print(f"  ✅ 缓存功能正常")
        
        # 清空缓存
        self.calculator.clear_cache()
        self.assertIsNone(self.calculator.get_cached_greeks(self.call_option.symbol))
        print(f"  ✅ 缓存清理功能正常")
    
    def test_error_handling(self):
        """测试错误处理"""
        # 无效的期权数据
        invalid_option = OptionTickData(
            symbol='INVALID',
            underlying='QQQ',
            strike=0,  # 无效执行价
            expiry='2024-01-01',
            right='CALL',
            timestamp=datetime.now(),
            price=0,   # 无效价格
            volume=0,
            bid=0,
            ask=0,
            open_interest=0
        )
        
        # 应该返回零值Greeks而不是抛出异常
        result = self.calculator.calculate_greeks(invalid_option, self.underlying_data)
        
        self.assertEqual(result.delta, 0.0)
        self.assertEqual(result.gamma, 0.0)
        self.assertEqual(result.theta, 0.0)
        self.assertEqual(result.risk_level, "UNKNOWN")
        
        print(f"  ✅ 错误处理正常")


class TestPortfolioGreeksManager(unittest.TestCase):
    """投资组合Greeks管理器测试"""
    
    def setUp(self):
        self.manager = PortfolioGreeksManager()
        
        # 创建测试数据
        self.underlying_data = UnderlyingTickData(
            symbol='QQQ',
            timestamp=datetime.now(),
            price=350.0,
            volume=1000000,
            bid=349.95,
            ask=350.05
        )
        
        today = datetime.now().date().strftime('%Y-%m-%d')
        
        self.call_option1 = OptionTickData(
            symbol='QQQ240101C350',
            underlying='QQQ',
            strike=350.0,
            expiry=today,
            right='CALL',
            timestamp=datetime.now(),
            price=2.5,
            volume=5000,
            bid=2.45,
            ask=2.55,
            open_interest=10000
        )
        
        self.put_option1 = OptionTickData(
            symbol='QQQ240101P350',
            underlying='QQQ', 
            strike=350.0,
            expiry=today,
            right='PUT',
            timestamp=datetime.now(),
            price=2.3,
            volume=4000,
            bid=2.25,
            ask=2.35,
            open_interest=8000
        )
    
    def test_position_management(self):
        """测试持仓管理"""
        # 添加持仓
        self.manager.update_position('QQQ240101C350', 10)
        self.manager.update_position('QQQ240101P350', -5)
        
        self.assertEqual(self.manager.positions['QQQ240101C350'], 10)
        self.assertEqual(self.manager.positions['QQQ240101P350'], -5)
        print(f"  ✅ 持仓添加: {self.manager.positions}")
        
        # 清零持仓
        self.manager.update_position('QQQ240101C350', 0)
        self.assertNotIn('QQQ240101C350', self.manager.positions)
        print(f"  ✅ 持仓清零功能正常")
    
    def test_portfolio_greeks_calculation(self):
        """测试投资组合Greeks计算"""
        # 设置持仓
        self.manager.update_position('QQQ240101C350', 10)   # 多头10张看涨
        self.manager.update_position('QQQ240101P350', -5)   # 空头5张看跌
        
        # 计算投资组合Greeks
        option_data_list = [self.call_option1, self.put_option1]
        underlying_data_list = [self.underlying_data]
        
        portfolio_greeks = self.manager.calculate_portfolio_greeks(
            option_data_list, underlying_data_list
        )
        
        self.assertIsNotNone(portfolio_greeks)
        self.assertEqual(portfolio_greeks.symbol, "PORTFOLIO")
        
        # 验证Greeks合理性
        self.assertNotEqual(portfolio_greeks.delta, 0)
        self.assertNotEqual(portfolio_greeks.gamma, 0)
        self.assertNotEqual(portfolio_greeks.theta, 0)
        
        print(f"  ✅ 投资组合Delta: {portfolio_greeks.delta:.4f}")
        print(f"  ✅ 投资组合Gamma: {portfolio_greeks.gamma:.4f}")
        print(f"  ✅ 投资组合Theta: {portfolio_greeks.theta:.4f}")
    
    def test_risk_metrics(self):
        """测试风险指标"""
        # 设置持仓
        self.manager.update_position('QQQ240101C350', 10)
        
        # 计算投资组合Greeks
        option_data_list = [self.call_option1]
        underlying_data_list = [self.underlying_data]
        
        portfolio_greeks = self.manager.calculate_portfolio_greeks(
            option_data_list, underlying_data_list
        )
        
        # 获取风险指标
        risk_metrics = self.manager.get_portfolio_risk_metrics()
        
        self.assertIn('total_delta', risk_metrics)
        self.assertIn('total_gamma', risk_metrics)
        self.assertIn('daily_theta', risk_metrics)
        self.assertIn('delta_neutrality', risk_metrics)
        self.assertIn('gamma_risk', risk_metrics)
        
        print(f"  ✅ 风险指标: {risk_metrics}")
    
    def test_empty_portfolio(self):
        """测试空投资组合"""
        # 无持仓时应该返回None
        portfolio_greeks = self.manager.calculate_portfolio_greeks([], [])
        self.assertIsNone(portfolio_greeks)
        
        # 风险指标应该为空
        risk_metrics = self.manager.get_portfolio_risk_metrics()
        self.assertEqual(risk_metrics, {})
        
        print(f"  ✅ 空投资组合处理正常")


class TestGreeksValidation(unittest.TestCase):
    """Greeks计算验证测试"""
    
    def setUp(self):
        self.calculator = GreeksCalculator()
    
    def test_put_call_parity(self):
        """测试看涨看跌期权平价关系"""
        # 创建相同执行价的看涨和看跌期权
        underlying_data = UnderlyingTickData(
            symbol='QQQ',
            timestamp=datetime.now(),
            price=350.0,
            volume=1000000,
            bid=349.95,
            ask=350.05
        )
        
        today = datetime.now().date().strftime('%Y-%m-%d')
        
        call_option = OptionTickData(
            symbol='QQQ240101C350',
            underlying='QQQ',
            strike=350.0,
            expiry=today,
            right='CALL',
            timestamp=datetime.now(),
            price=2.5,
            volume=5000,
            bid=2.45,
            ask=2.55,
            open_interest=10000
        )
        
        put_option = OptionTickData(
            symbol='QQQ240101P350',
            underlying='QQQ',
            strike=350.0,
            expiry=today,
            right='PUT',
            timestamp=datetime.now(),
            price=2.3,
            volume=4000,
            bid=2.25,
            ask=2.35,
            open_interest=8000
        )
        
        # 计算Greeks
        call_greeks = self.calculator.calculate_greeks(call_option, underlying_data)
        put_greeks = self.calculator.calculate_greeks(put_option, underlying_data)
        
        # 验证Put-Call平价关系
        # Delta: call_delta - put_delta ≈ 1
        delta_diff = call_greeks.delta - put_greeks.delta
        self.assertAlmostEqual(delta_diff, 1.0, places=1)
        print(f"  ✅ Delta平价: {delta_diff:.4f} ≈ 1.0")
        
        # Gamma: 相同执行价的看涨看跌期权Gamma相等
        self.assertAlmostEqual(call_greeks.gamma, put_greeks.gamma, places=4)
        print(f"  ✅ Gamma相等: Call={call_greeks.gamma:.6f}, Put={put_greeks.gamma:.6f}")
        
        # Vega: 相同执行价的看涨看跌期权Vega相等
        self.assertAlmostEqual(call_greeks.vega, put_greeks.vega, places=4)
        print(f"  ✅ Vega相等: Call={call_greeks.vega:.4f}, Put={put_greeks.vega:.4f}")
    
    def test_boundary_conditions(self):
        """测试边界条件"""
        # 深度实值期权
        underlying_data = UnderlyingTickData(
            symbol='QQQ',
            timestamp=datetime.now(),
            price=400.0,  # 远高于执行价
            volume=1000000,
            bid=399.95,
            ask=400.05
        )
        
        today = datetime.now().date().strftime('%Y-%m-%d')
        
        deep_itm_call = OptionTickData(
            symbol='QQQ240101C350',
            underlying='QQQ',
            strike=350.0,
            expiry=today,
            right='CALL',
            timestamp=datetime.now(),
            price=50.0,  # 深度实值
            volume=1000,
            bid=49.5,
            ask=50.5,
            open_interest=1000
        )
        
        greeks = self.calculator.calculate_greeks(deep_itm_call, underlying_data)
        
        # 深度实值看涨期权Delta应该接近1
        self.assertGreater(greeks.delta, 0.9)
        print(f"  ✅ 深度实值Delta: {greeks.delta:.4f}")
        
        # Gamma应该很小
        self.assertLess(greeks.gamma, 0.01)
        print(f"  ✅ 深度实值Gamma: {greeks.gamma:.6f}")


if __name__ == '__main__':
    print("🧪 开始Greeks计算器测试...")
    print("=" * 60)
    
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试类
    test_classes = [
        TestGreeksCalculator,
        TestPortfolioGreeksManager,
        TestGreeksValidation
    ]
    
    for test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 输出测试结果
    print("\n" + "=" * 60)
    print(f"🧪 测试完成!")
    print(f"✅ 成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"❌ 失败: {len(result.failures)}")
    print(f"🚨 错误: {len(result.errors)}")
    
    if result.failures:
        print("\n❌ 失败的测试:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback}")
    
    if result.errors:
        print("\n🚨 错误的测试:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback}")
    
    # 判断测试是否通过
    if len(result.failures) == 0 and len(result.errors) == 0:
        print("\n🎉 所有测试通过! Greeks计算器功能正常可用!")
    else:
        print("\n⚠️ 部分测试未通过，需要修复问题!")
        exit(1)
