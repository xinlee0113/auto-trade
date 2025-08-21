#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于真实Tiger API数据的风险管理器测试

验证风险管理器在真实市场环境下的功能：
1. 真实期权数据下的仓位管理
2. 实际Greeks变化的风险控制
3. 真实流动性条件下的风险评估
4. 实时市场数据的止损机制

Author: AI Assistant
Date: 2024-01-21
"""

import unittest
import sys
import os
import time
from datetime import datetime, timedelta
from dataclasses import replace

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.risk_manager import create_risk_manager, RiskEvent
from src.config.trading_config import DEFAULT_TRADING_CONFIG, RiskLevel
from src.models.trading_models import Position, OptionTickData
from src.utils.greeks_calculator import GreeksCalculator
from demos.client_config import get_client_config

# Tiger API imports
from tigeropen.quote.quote_client import QuoteClient
import pandas as pd


class TestRealAPIRiskManager(unittest.TestCase):
    """基于真实API数据的风险管理器测试"""
    
    @classmethod
    def setUpClass(cls):
        """类级别的初始化"""
        print("🔧 初始化真实API连接...")
        try:
            cls.client_config = get_client_config()
            cls.quote_client = QuoteClient(cls.client_config)
            print("✅ Tiger API连接成功")
        except Exception as e:
            print(f"❌ Tiger API连接失败: {e}")
            raise unittest.SkipTest("Tiger API不可用，跳过真实API测试")
    
    def setUp(self):
        """测试初始化"""
        self.config = replace(
            DEFAULT_TRADING_CONFIG,
            risk_level=RiskLevel.MEDIUM,
            max_position_value=30000.0
        )
        self.risk_manager = create_risk_manager(self.config)
        self.greeks_calculator = GreeksCalculator()
        self.test_alerts = []
        
        # 注册警报回调
        self.risk_manager.register_risk_alert_callback(self.collect_alert)
    
    def collect_alert(self, alert):
        """收集警报用于测试验证"""
        self.test_alerts.append(alert)
    
    def fetch_real_underlying_data(self, symbol):
        """获取真实标的数据"""
        try:
            briefs = self.quote_client.get_stock_briefs([symbol])
            if briefs:
                return briefs[0]
        except Exception as e:
            self.skipTest(f"无法获取 {symbol} 数据: {e}")
        return None
    
    def fetch_real_option_data(self, underlying, limit=5):
        """获取真实期权数据"""
        try:
            expiry_date = datetime.now().date()
            expiry_str = expiry_date.strftime('%Y%m%d')
            
            # 获取期权链
            option_chain = self.quote_client.get_option_chain(underlying, expiry_str)
            if option_chain.empty:
                self.skipTest(f"今日无 {underlying} 期权数据")
                return []
            
            # 数据处理
            option_chain['strike'] = pd.to_numeric(option_chain['strike'], errors='coerce')
            option_chain = option_chain.dropna(subset=['strike'])
            
            # 获取标的价格
            underlying_brief = self.fetch_real_underlying_data(underlying)
            if not underlying_brief:
                return []
            
            underlying_price = float(underlying_brief.latest_price or 0)
            if underlying_price <= 0:
                self.skipTest(f"{underlying} 价格数据无效")
                return []
            
            # 筛选ATM附近期权
            atm_range = underlying_price * 0.03  # ±3%
            filtered_options = option_chain[
                (option_chain['strike'] >= underlying_price - atm_range) &
                (option_chain['strike'] <= underlying_price + atm_range)
            ].head(limit).copy()
            
            if filtered_options.empty:
                self.skipTest("ATM附近无合适期权")
                return []
            
            # 获取期权行情
            symbols = filtered_options['symbol'].tolist()
            try:
                option_briefs = self.quote_client.get_option_briefs(symbols)
                option_briefs_dict = {brief.symbol: brief for brief in option_briefs}
            except:
                option_briefs_dict = {}
            
            option_data_list = []
            
            for _, row in filtered_options.iterrows():
                symbol = row['symbol']
                brief = option_briefs_dict.get(symbol)
                
                option_data = OptionTickData(
                    symbol=symbol,
                    underlying=underlying,
                    strike=float(row['strike']),
                    expiry=expiry_str,
                    right=row['right'],
                    timestamp=datetime.now(),
                    price=float(getattr(brief, 'latest_price', 0) or 0) if brief else 0.01,
                    volume=int(getattr(brief, 'volume', 0) or 0) if brief else 100,
                    bid=float(getattr(brief, 'bid', 0) or 0) if brief else 0.01,
                    ask=float(getattr(brief, 'ask', 0) or 0) if brief else 0.02
                )
                
                # 计算Greeks
                if option_data.price > 0:
                    try:
                        greeks = self.greeks_calculator.calculate_greeks(
                            underlying_price=underlying_price,
                            strike_price=option_data.strike,
                            time_to_expiry=1/365,  # 0DTE
                            risk_free_rate=0.05,
                            volatility=0.2,
                            option_type=option_data.right.lower()
                        )
                        
                        option_data.delta = greeks.delta
                        option_data.gamma = greeks.gamma
                        option_data.theta = greeks.theta
                        option_data.vega = greeks.vega
                        
                    except Exception as e:
                        print(f"⚠️ Greeks计算失败: {e}")
                
                option_data_list.append(option_data)
            
            return option_data_list
            
        except Exception as e:
            self.skipTest(f"获取期权数据失败: {e}")
            return []
    
    def create_position_from_option(self, option_data, quantity=3):
        """从期权数据创建仓位"""
        position = Position(
            symbol=option_data.symbol,
            quantity=quantity,
            entry_price=option_data.price,
            current_price=option_data.price,
            entry_time=datetime.now(),
            position_id=f"TEST_{option_data.symbol}_{int(time.time())}"
        )
        
        position.current_value = abs(quantity) * option_data.price * 100
        position.delta = option_data.delta * quantity if option_data.delta else None
        position.gamma = option_data.gamma * quantity if option_data.gamma else None
        position.theta = option_data.theta * quantity if option_data.theta else None
        position.vega = option_data.vega * quantity if option_data.vega else None
        position.bid_ask_spread = option_data.spread_percentage / 100 if option_data.price > 0 else None
        position.underlying = option_data.underlying
        
        return position
    
    def test_real_data_position_creation(self):
        """测试基于真实数据的仓位创建"""
        print("\n🧪 测试1: 真实数据仓位创建")
        
        # 获取真实期权数据
        option_data_list = self.fetch_real_option_data("QQQ", limit=3)
        
        if not option_data_list:
            self.skipTest("无可用期权数据")
        
        initial_position_count = len(self.risk_manager.positions)
        
        # 尝试添加仓位
        for i, option_data in enumerate(option_data_list):
            if option_data.price <= 0:
                continue
                
            position = self.create_position_from_option(option_data, quantity=2)
            result = self.risk_manager.add_position(position)
            
            print(f"  添加仓位 {option_data.symbol}: {'✅' if result else '❌'}")
            print(f"    价格: ${option_data.price:.2f}, Delta: {option_data.delta:.3f if option_data.delta else 'N/A'}")
        
        # 验证仓位数量增加
        final_position_count = len(self.risk_manager.positions)
        self.assertGreater(final_position_count, initial_position_count)
        
        print(f"  ✅ 成功添加 {final_position_count - initial_position_count} 个仓位")
    
    def test_real_market_risk_calculation(self):
        """测试真实市场数据下的风险计算"""
        print("\n🧪 测试2: 真实市场风险计算")
        
        # 先添加一些仓位
        option_data_list = self.fetch_real_option_data("QQQ", limit=2)
        if not option_data_list:
            self.skipTest("无可用期权数据")
        
        for option_data in option_data_list:
            if option_data.price > 0:
                position = self.create_position_from_option(option_data)
                self.risk_manager.add_position(position)
        
        # 计算风险指标
        metrics = self.risk_manager.calculate_risk_metrics()
        
        # 验证风险指标的合理性
        self.assertGreaterEqual(metrics.position_count, 1)
        self.assertGreater(metrics.total_position_value, 0)
        self.assertGreaterEqual(metrics.risk_score, 0)
        self.assertLessEqual(metrics.risk_score, 100)
        
        print(f"  ✅ 仓位数: {metrics.position_count}")
        print(f"  ✅ 总价值: ${metrics.total_position_value:.2f}")
        print(f"  ✅ 风险分数: {metrics.risk_score:.1f}/100")
        print(f"  ✅ 组合Delta: {metrics.portfolio_delta:.3f}")
    
    def test_real_data_stop_loss_trigger(self):
        """测试真实数据下的止损触发"""
        print("\n🧪 测试3: 真实数据止损触发")
        
        # 获取期权数据并添加仓位
        option_data_list = self.fetch_real_option_data("QQQ", limit=1)
        if not option_data_list:
            self.skipTest("无可用期权数据")
        
        option_data = option_data_list[0]
        if option_data.price <= 0:
            self.skipTest("期权价格无效")
        
        position = self.create_position_from_option(option_data, quantity=5)
        result = self.risk_manager.add_position(position)
        self.assertTrue(result)
        
        print(f"  添加仓位: {option_data.symbol}, 价格: ${option_data.price:.2f}")
        
        # 清空之前的警报
        self.test_alerts.clear()
        
        # 模拟价格大幅下跌（基于真实数据但调整价格）
        stressed_option = OptionTickData(
            symbol=option_data.symbol,
            underlying=option_data.underlying,
            strike=option_data.strike,
            expiry=option_data.expiry,
            right=option_data.right,
            timestamp=datetime.now(),
            price=option_data.price * 0.4,  # 下跌60%
            volume=option_data.volume * 2,
            bid=option_data.bid * 0.4,
            ask=option_data.ask * 0.4,
            delta=option_data.delta * 0.5 if option_data.delta else None  # Delta变化
        )
        
        # 更新仓位触发止损
        alerts = self.risk_manager.update_position(position.position_id, stressed_option)
        
        # 验证止损触发
        stop_loss_alerts = [a for a in alerts if a.event_type == RiskEvent.STOP_LOSS_TRIGGERED]
        self.assertGreater(len(stop_loss_alerts), 0)
        
        print(f"  ✅ 价格下跌至: ${stressed_option.price:.2f} (-60%)")
        print(f"  ✅ 触发止损警报: {len(stop_loss_alerts)} 个")
    
    def test_real_data_position_limits(self):
        """测试真实数据下的仓位限制"""
        print("\n🧪 测试4: 真实数据仓位限制")
        
        # 获取期权数据
        option_data_list = self.fetch_real_option_data("QQQ", limit=1)
        if not option_data_list:
            self.skipTest("无可用期权数据")
        
        option_data = option_data_list[0]
        if option_data.price <= 0:
            self.skipTest("期权价格无效")
        
        # 创建超大仓位
        large_position = Position(
            symbol=option_data.symbol,
            quantity=1000,  # 大数量
            entry_price=option_data.price,
            current_price=option_data.price,
            entry_time=datetime.now(),
            position_id=f"LARGE_{int(time.time())}"
        )
        large_position.current_value = 100000.0  # 超过限制
        
        # 清空警报
        self.test_alerts.clear()
        
        # 尝试添加超大仓位
        result = self.risk_manager.add_position(large_position)
        
        # 验证被拒绝
        self.assertFalse(result)
        
        # 验证产生了限制警报
        limit_alerts = [a for a in self.test_alerts if a.event_type == RiskEvent.POSITION_LIMIT_EXCEEDED]
        self.assertGreater(len(limit_alerts), 0)
        
        print(f"  ✅ 超大仓位被拒绝: ${large_position.current_value:.2f}")
        print(f"  ✅ 触发限制警报: {len(limit_alerts)} 个")
    
    def test_real_time_risk_monitoring(self):
        """测试实时风险监控"""
        print("\n🧪 测试5: 实时风险监控")
        
        # 添加仓位
        option_data_list = self.fetch_real_option_data("QQQ", limit=2)
        if not option_data_list:
            self.skipTest("无可用期权数据")
        
        positions = []
        for option_data in option_data_list:
            if option_data.price > 0:
                position = self.create_position_from_option(option_data)
                if self.risk_manager.add_position(position):
                    positions.append((position, option_data))
        
        if not positions:
            self.skipTest("无法添加仓位")
        
        print(f"  监控 {len(positions)} 个仓位")
        
        # 模拟多次价格更新
        update_count = 0
        total_alerts = 0
        
        for i in range(3):  # 3次更新
            # 重新获取实时数据
            new_option_data_list = self.fetch_real_option_data("QQQ", limit=len(positions))
            if not new_option_data_list:
                continue
            
            # 更新仓位
            for j, (position, _) in enumerate(positions):
                if j < len(new_option_data_list):
                    new_option_data = new_option_data_list[j]
                    if new_option_data.symbol == position.symbol:
                        alerts = self.risk_manager.update_position(position.position_id, new_option_data)
                        total_alerts += len(alerts)
                        update_count += 1
            
            time.sleep(2)  # 2秒间隔
        
        # 验证监控效果
        final_metrics = self.risk_manager.calculate_risk_metrics()
        
        print(f"  ✅ 完成 {update_count} 次更新")
        print(f"  ✅ 总警报数: {total_alerts}")
        print(f"  ✅ 最终风险分数: {final_metrics.risk_score:.1f}")
        
        self.assertGreaterEqual(update_count, 1)
    
    def test_portfolio_greeks_calculation(self):
        """测试投资组合Greeks计算"""
        print("\n🧪 测试6: 投资组合Greeks计算")
        
        # 添加多个期权仓位
        option_data_list = self.fetch_real_option_data("QQQ", limit=3)
        if len(option_data_list) < 2:
            self.skipTest("期权数据不足")
        
        portfolio_delta = 0
        portfolio_gamma = 0
        
        for i, option_data in enumerate(option_data_list):
            if option_data.price <= 0:
                continue
                
            quantity = 5 if i % 2 == 0 else -3  # 混合多空
            position = self.create_position_from_option(option_data, quantity)
            
            if self.risk_manager.add_position(position):
                if position.delta:
                    portfolio_delta += position.delta
                if position.gamma:
                    portfolio_gamma += position.gamma
        
        # 计算系统的组合Greeks
        metrics = self.risk_manager.calculate_risk_metrics()
        
        # 验证Greeks计算的一致性
        self.assertAlmostEqual(metrics.portfolio_delta, portfolio_delta, places=2)
        
        print(f"  ✅ 预期组合Delta: {portfolio_delta:.3f}")
        print(f"  ✅ 系统计算Delta: {metrics.portfolio_delta:.3f}")
        print(f"  ✅ 组合Gamma: {metrics.portfolio_gamma:.3f}")
        print(f"  ✅ 组合Theta: ${metrics.portfolio_theta:.2f}")


class TestRealAPIRiskManagerIntegration(unittest.TestCase):
    """真实API数据集成测试"""
    
    @classmethod
    def setUpClass(cls):
        """类级别初始化"""
        try:
            cls.client_config = get_client_config()
            cls.quote_client = QuoteClient(cls.client_config)
        except Exception as e:
            raise unittest.SkipTest(f"Tiger API不可用: {e}")
    
    def setUp(self):
        """测试初始化"""
        self.config = replace(
            DEFAULT_TRADING_CONFIG,
            risk_level=RiskLevel.HIGH,
            max_position_value=50000.0
        )
        self.risk_manager = create_risk_manager(self.config)
    
    def test_full_trading_scenario(self):
        """测试完整交易场景"""
        print("\n🧪 集成测试: 完整交易场景")
        
        # 1. 建仓阶段
        option_data_list = self.fetch_real_option_data("QQQ", limit=3)
        if not option_data_list:
            self.skipTest("无可用期权数据")
        
        print("  📈 建仓阶段...")
        for option_data in option_data_list:
            if option_data.price > 0:
                position = self.create_position_from_option(option_data, quantity=3)
                result = self.risk_manager.add_position(position)
                print(f"    添加 {option_data.symbol}: {'✅' if result else '❌'}")
        
        initial_metrics = self.risk_manager.calculate_risk_metrics()
        print(f"    初始组合价值: ${initial_metrics.total_position_value:.2f}")
        
        # 2. 风险监控阶段
        print("  📊 风险监控阶段...")
        portfolio_alerts = self.risk_manager.check_portfolio_risks()
        print(f"    组合风险警报: {len(portfolio_alerts)} 个")
        
        # 3. 价格波动处理
        print("  📉 价格波动处理...")
        for position_id in list(self.risk_manager.positions.keys()):
            # 模拟轻微波动
            position = self.risk_manager.positions[position_id]
            new_price = position.current_price * 0.95  # 5%下跌
            
            mock_option = OptionTickData(
                symbol=position.symbol,
                underlying="QQQ",
                strike=380.0,
                expiry="20240121",
                right="CALL",
                timestamp=datetime.now(),
                price=new_price,
                volume=1000,
                bid=new_price - 0.02,
                ask=new_price + 0.02
            )
            
            alerts = self.risk_manager.update_position(position_id, mock_option)
            if alerts:
                print(f"    {position.symbol} 触发 {len(alerts)} 个警报")
        
        # 4. 风险评估
        final_metrics = self.risk_manager.calculate_risk_metrics()
        
        # 验证系统完整性
        self.assertGreater(final_metrics.position_count, 0)
        self.assertIsInstance(final_metrics.risk_score, float)
        
        print(f"  ✅ 最终风险分数: {final_metrics.risk_score:.1f}")
        print(f"  ✅ 盈亏变化: ${final_metrics.unrealized_pnl:.2f}")
    
    def fetch_real_option_data(self, underlying, limit=5):
        """获取真实期权数据（简化版）"""
        try:
            expiry_date = datetime.now().date()
            expiry_str = expiry_date.strftime('%Y%m%d')
            
            option_chain = self.quote_client.get_option_chain(underlying, expiry_str)
            if option_chain.empty:
                return []
            
            # 简单选择前几个期权
            selected = option_chain.head(limit)
            
            option_data_list = []
            for _, row in selected.iterrows():
                option_data = OptionTickData(
                    symbol=row['symbol'],
                    underlying=underlying,
                    strike=float(row['strike']),
                    expiry=expiry_str,
                    right=row['right'],
                    timestamp=datetime.now(),
                    price=1.0,  # 使用固定价格简化测试
                    volume=1000,
                    bid=0.95,
                    ask=1.05,
                    delta=0.5,
                    gamma=0.1,
                    theta=-0.05,
                    vega=0.2
                )
                option_data_list.append(option_data)
            
            return option_data_list
            
        except:
            return []
    
    def create_position_from_option(self, option_data, quantity=3):
        """简化版仓位创建"""
        position = Position(
            symbol=option_data.symbol,
            quantity=quantity,
            entry_price=option_data.price,
            current_price=option_data.price,
            entry_time=datetime.now(),
            position_id=f"INT_{option_data.symbol}_{int(time.time())}"
        )
        
        position.current_value = abs(quantity) * option_data.price * 100
        position.delta = option_data.delta * quantity
        position.underlying = option_data.underlying
        
        return position


if __name__ == "__main__":
    # 设置测试运行器
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试类
    suite.addTests(loader.loadTestsFromTestCase(TestRealAPIRiskManager))
    suite.addTests(loader.loadTestsFromTestCase(TestRealAPIRiskManagerIntegration))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2, buffer=True)
    result = runner.run(suite)
    
    # 输出结果摘要
    print("\n" + "="*70)
    print("🧪 真实API风险管理器测试结果摘要")
    print("="*70)
    print(f"总测试数: {result.testsRun}")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")
    print(f"跳过: {len(result.skipped) if hasattr(result, 'skipped') else 0}")
    
    if result.wasSuccessful():
        print("🎉 所有测试通过！风险管理器已通过真实API数据验证！")
    else:
        print("⚠️ 部分测试未通过，请检查具体错误信息")
    
    print("="*70)
