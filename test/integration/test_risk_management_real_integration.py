#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
风险管理真实集成测试
使用真实Tiger API数据验证风险管理系统的有效性
"""

import pytest
import time
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from dataclasses import replace

from demos.client_config import get_client_config
from src.services.risk_manager import RiskManager
from src.models.trading_models import Position, RiskMetrics
from src.config.trading_config import TradingConfig, RiskLevel, DEFAULT_TRADING_CONFIG
from src.api.broker_tiger_api import BrokerTigerAPI
from src.utils.logger_config import get_logger

logger = get_logger(__name__)

class TestRiskManagementRealIntegration:
    """风险管理真实集成测试"""
    
    @classmethod
    def setup_class(cls):
        """测试类初始化"""
        logger.info("初始化风险管理真实集成测试")
        cls.config = get_client_config()
        cls.api = BrokerTigerAPI(cls.config)
        
        # 使用保守的风险配置
        cls.trading_config = replace(
            DEFAULT_TRADING_CONFIG,
            risk_level=RiskLevel.MEDIUM,
            max_position_value=50000.0  # 降低用于测试
        )
        cls.risk_manager = RiskManager(cls.trading_config)
        cls.test_symbols = ["QQQ", "SPY"]
    
    def test_real_position_data_creation(self):
        """测试使用真实API数据创建持仓"""
        logger.info("测试使用真实API数据创建持仓")
        
        quote_client = self.api.get_quote_client()
        
        # 获取真实期权数据
        symbol = "QQQ"
        briefs = quote_client.get_briefs([symbol])
        underlying_price = float(briefs[0].latest_price)
        
        expiry_dates = quote_client.get_option_expirations(symbol)
        nearest_expiry = min(expiry_dates)
        option_chain = quote_client.get_option_chain(symbol, nearest_expiry)
        
        # 筛选ATM期权
        atm_options = option_chain[
            abs(option_chain['strike'].astype(float) - underlying_price) <= 5.0
        ].head(3)
        
        positions = []
        
        for idx, (_, option_row) in enumerate(atm_options.iterrows()):
            option_price = float(option_row.get('latest_price', option_row.get('bid', 0)))
            if option_price <= 0:
                continue
                
            position = Position(
                position_id=f"TEST_POS_{idx}",
                symbol=f"{symbol}_{option_row['strike']}_{option_row['put_call']}",
                position_type="LONG",
                quantity=10,  # 10张合约
                entry_price=option_price,
                current_price=option_price,
                market_value=option_price * 10 * 100,  # 期权乘数100
                unrealized_pnl=0.0,
                delta=0.5,  # 临时值，实际应该计算
                gamma=0.02,
                theta=-0.05,
                vega=0.1,
                bid_ask_spread=float(option_row.get('ask', 0)) - float(option_row.get('bid', 0)),
                underlying=symbol,
                timestamp=datetime.now()
            )
            
            positions.append(position)
            logger.info(f"✅ 创建持仓: {position.symbol}, 价值: ${position.market_value:,.2f}")
        
        assert len(positions) > 0, "未能创建任何持仓"
        return positions
    
    def test_real_time_risk_calculation(self):
        """测试实时风险计算"""
        logger.info("测试实时风险计算")
        
        # 创建真实持仓
        positions = self.test_real_position_data_creation()
        
        # 添加持仓到风险管理器
        for position in positions:
            self.risk_manager.add_position(position)
        
        # 计算风险指标
        risk_metrics = self.risk_manager.calculate_risk_metrics()
        
        # 验证风险指标合理性
        assert risk_metrics is not None, "风险指标计算失败"
        assert isinstance(risk_metrics, RiskMetrics), "风险指标类型错误"
        
        assert risk_metrics.total_value >= 0, f"总价值异常: {risk_metrics.total_value}"
        assert risk_metrics.max_single_position_loss <= 0, "单笔止损应为负值"
        
        # 验证风险限制
        total_value = sum(pos.market_value for pos in positions)
        assert total_value <= self.trading_config.max_position_value, \
            f"总持仓超限: {total_value} > {self.trading_config.max_position_value}"
        
        logger.info(f"✅ 风险指标计算完成:")
        logger.info(f"   总价值: ${risk_metrics.total_value:,.2f}")
        logger.info(f"   总Delta: {risk_metrics.portfolio_delta:.3f}")
        logger.info(f"   总Gamma: {risk_metrics.portfolio_gamma:.3f}")
        logger.info(f"   VaR: ${risk_metrics.value_at_risk:,.2f}")
        
        return risk_metrics
    
    def test_real_position_monitoring(self):
        """测试真实持仓监控"""
        logger.info("测试真实持仓监控")
        
        quote_client = self.api.get_quote_client()
        
        # 创建持仓
        positions = self.test_real_position_data_creation()
        
        for position in positions:
            self.risk_manager.add_position(position)
        
        # 模拟价格更新监控
        monitoring_cycles = 3
        
        for cycle in range(monitoring_cycles):
            logger.info(f"监控周期 {cycle + 1}/{monitoring_cycles}")
            
            # 获取最新价格
            symbol = "QQQ"
            briefs = quote_client.get_briefs([symbol])
            current_underlying = float(briefs[0].latest_price)
            
            # 获取最新期权价格
            expiry_dates = quote_client.get_option_expirations(symbol)
            nearest_expiry = min(expiry_dates)
            option_chain = quote_client.get_option_chain(symbol, nearest_expiry)
            
            # 更新持仓价格
            updated_positions = []
            
            for position in self.risk_manager.positions.values():
                # 从期权链中找到对应期权的最新价格
                strike_str = position.symbol.split('_')[1]
                option_type = position.symbol.split('_')[2]
                
                matching_options = option_chain[
                    (option_chain['strike'].astype(str) == strike_str) &
                    (option_chain['put_call'].str.upper() == option_type)
                ]
                
                if not matching_options.empty:
                    new_price = float(matching_options.iloc[0].get('latest_price', 
                                    matching_options.iloc[0].get('bid', position.current_price)))
                    
                    # 更新持仓
                    updated_position = replace(
                        position,
                        current_price=new_price,
                        market_value=new_price * position.quantity * 100,
                        unrealized_pnl=(new_price - position.entry_price) * position.quantity * 100,
                        timestamp=datetime.now()
                    )
                    
                    self.risk_manager.update_position(updated_position)
                    updated_positions.append(updated_position)
                    
                    price_change_pct = (new_price - position.entry_price) / position.entry_price * 100
                    logger.info(f"   {position.symbol}: ${position.entry_price:.2f} → ${new_price:.2f} "
                              f"({price_change_pct:+.2f}%)")
            
            # 检查风险警报
            risk_alerts = self.risk_manager.check_risk_alerts()
            if risk_alerts:
                logger.warning(f"⚠️ 风险警报: {len(risk_alerts)}个")
                for alert in risk_alerts[:3]:  # 只显示前3个
                    logger.warning(f"   {alert.alert_type}: {alert.message}")
            
            # 计算更新后的风险指标
            updated_metrics = self.risk_manager.calculate_risk_metrics()
            logger.info(f"   更新风险: 总价值=${updated_metrics.total_value:,.2f}, "
                      f"总PnL=${sum(pos.unrealized_pnl for pos in updated_positions):,.2f}")
            
            if cycle < monitoring_cycles - 1:
                time.sleep(3)  # 等待3秒获取新数据
        
        logger.info("✅ 真实持仓监控测试完成")
    
    def test_risk_limits_enforcement(self):
        """测试风险限制执行"""
        logger.info("测试风险限制执行")
        
        quote_client = self.api.get_quote_client()
        
        # 获取真实期权数据
        symbol = "QQQ"
        briefs = quote_client.get_briefs([symbol])
        underlying_price = float(briefs[0].latest_price)
        
        expiry_dates = quote_client.get_option_expirations(symbol)
        nearest_expiry = min(expiry_dates)
        option_chain = quote_client.get_option_chain(symbol, nearest_expiry)
        
        # 创建一个大持仓来测试限制
        expensive_option = option_chain.iloc[0]
        option_price = float(expensive_option.get('latest_price', expensive_option.get('ask', 100)))
        
        large_position = Position(
            position_id="TEST_LARGE_POS",
            symbol=f"{symbol}_{expensive_option['strike']}_CALL",
            position_type="LONG",
            quantity=100,  # 大量持仓
            entry_price=option_price,
            current_price=option_price,
            market_value=option_price * 100 * 100,  # 可能超过限制
            unrealized_pnl=0.0,
            delta=0.5,
            gamma=0.02,
            theta=-0.05,
            vega=0.1,
            bid_ask_spread=5.0,
            underlying=symbol,
            timestamp=datetime.now()
        )
        
        # 尝试添加持仓，应该触发风险检查
        can_add = self.risk_manager.can_add_position(large_position)
        
        if large_position.market_value > self.trading_config.max_position_value:
            assert not can_add, "应该拒绝超限持仓"
            logger.info(f"✅ 正确拒绝超限持仓: ${large_position.market_value:,.2f} > "
                      f"${self.trading_config.max_position_value:,.2f}")
        else:
            assert can_add, "合理持仓应该被接受"
            logger.info(f"✅ 正确接受合理持仓: ${large_position.market_value:,.2f}")
    
    def test_portfolio_greeks_aggregation(self):
        """测试投资组合Greeks聚合"""
        logger.info("测试投资组合Greeks聚合")
        
        # 创建多个真实持仓
        positions = self.test_real_position_data_creation()
        
        for position in positions:
            self.risk_manager.add_position(position)
        
        # 计算投资组合Greeks
        risk_metrics = self.risk_manager.calculate_risk_metrics()
        
        # 验证Greeks聚合
        total_delta = sum(pos.delta * pos.quantity for pos in positions)
        total_gamma = sum(pos.gamma * pos.quantity for pos in positions)
        total_theta = sum(pos.theta * pos.quantity for pos in positions)
        total_vega = sum(pos.vega * pos.quantity for pos in positions)
        
        # 允许小的舍入误差
        assert abs(risk_metrics.portfolio_delta - total_delta) < 0.01, \
            f"Delta聚合错误: {risk_metrics.portfolio_delta} vs {total_delta}"
        
        assert abs(risk_metrics.portfolio_gamma - total_gamma) < 0.01, \
            f"Gamma聚合错误: {risk_metrics.portfolio_gamma} vs {total_gamma}"
        
        logger.info(f"✅ 投资组合Greeks验证:")
        logger.info(f"   总Delta: {risk_metrics.portfolio_delta:.3f}")
        logger.info(f"   总Gamma: {risk_metrics.portfolio_gamma:.3f}")
        logger.info(f"   总Theta: {risk_metrics.portfolio_theta:.3f}")
        logger.info(f"   总Vega: {risk_metrics.portfolio_vega:.3f}")
    
    def test_real_time_stop_loss_trigger(self):
        """测试实时止损触发"""
        logger.info("测试实时止损触发")
        
        quote_client = self.api.get_quote_client()
        
        # 创建一个持仓
        symbol = "QQQ"
        briefs = quote_client.get_briefs([symbol])
        underlying_price = float(briefs[0].latest_price)
        
        expiry_dates = quote_client.get_option_expirations(symbol)
        nearest_expiry = min(expiry_dates)
        option_chain = quote_client.get_option_chain(symbol, nearest_expiry)
        
        option_row = option_chain.iloc[0]
        option_price = float(option_row.get('latest_price', option_row.get('bid', 0)))
        
        position = Position(
            position_id="TEST_STOP_LOSS",
            symbol=f"{symbol}_{option_row['strike']}_CALL",
            position_type="LONG",
            quantity=10,
            entry_price=option_price,
            current_price=option_price,
            market_value=option_price * 10 * 100,
            unrealized_pnl=0.0,
            delta=0.5,
            gamma=0.02,
            theta=-0.05,
            vega=0.1,
            bid_ask_spread=2.0,
            underlying=symbol,
            timestamp=datetime.now()
        )
        
        self.risk_manager.add_position(position)
        
        # 模拟价格下跌触发止损
        simulated_loss_price = option_price * 0.85  # 15%损失
        
        updated_position = replace(
            position,
            current_price=simulated_loss_price,
            market_value=simulated_loss_price * 10 * 100,
            unrealized_pnl=(simulated_loss_price - option_price) * 10 * 100,
            timestamp=datetime.now()
        )
        
        self.risk_manager.update_position(updated_position)
        
        # 检查是否触发止损警报
        risk_alerts = self.risk_manager.check_risk_alerts()
        
        # 应该有止损相关的警报
        stop_loss_alerts = [alert for alert in risk_alerts 
                           if "止损" in alert.message or "loss" in alert.message.lower()]
        
        if abs(simulated_loss_price - option_price) / option_price > 0.1:  # 超过10%损失
            assert len(stop_loss_alerts) > 0, "应该触发止损警报"
            logger.info(f"✅ 正确触发止损警报: 损失{((simulated_loss_price - option_price) / option_price * 100):+.1f}%")
        else:
            logger.info(f"✅ 损失未达到止损阈值: {((simulated_loss_price - option_price) / option_price * 100):+.1f}%")
    
    def test_end_to_end_risk_workflow(self):
        """端到端风险管理工作流测试"""
        logger.info("端到端风险管理工作流测试")
        
        # 完整工作流：创建持仓 → 监控风险 → 更新价格 → 检查警报 → 执行操作
        
        # 1. 创建真实持仓组合
        positions = self.test_real_position_data_creation()
        
        initial_portfolio_value = 0
        for position in positions:
            self.risk_manager.add_position(position)
            initial_portfolio_value += position.market_value
        
        # 2. 初始风险评估
        initial_metrics = self.risk_manager.calculate_risk_metrics()
        logger.info(f"初始投资组合价值: ${initial_metrics.total_value:,.2f}")
        
        # 3. 模拟市场变动（获取真实价格更新）
        quote_client = self.api.get_quote_client()
        time.sleep(2)  # 等待价格可能的微小变动
        
        # 获取更新后的价格
        symbol = "QQQ"
        briefs = quote_client.get_briefs([symbol])
        current_underlying = float(briefs[0].latest_price)
        
        # 4. 更新所有持仓价格并重新计算风险
        updated_portfolio_value = 0
        
        for position_id, position in list(self.risk_manager.positions.items()):
            # 简单模拟：假设期权价格与标的有轻微相关性
            price_change_factor = 1.0 + (hash(position.symbol) % 100 - 50) / 10000  # ±0.5%随机变动
            new_price = position.entry_price * price_change_factor
            
            updated_position = replace(
                position,
                current_price=new_price,
                market_value=new_price * position.quantity * 100,
                unrealized_pnl=(new_price - position.entry_price) * position.quantity * 100,
                timestamp=datetime.now()
            )
            
            self.risk_manager.update_position(updated_position)
            updated_portfolio_value += updated_position.market_value
        
        # 5. 最终风险评估
        final_metrics = self.risk_manager.calculate_risk_metrics()
        total_pnl = final_metrics.total_value - initial_metrics.total_value
        
        # 6. 检查风险警报
        final_alerts = self.risk_manager.check_risk_alerts()
        
        # 7. 验证工作流完整性
        assert final_metrics.total_value > 0, "最终投资组合价值异常"
        assert len(self.risk_manager.positions) == len(positions), "持仓数量不匹配"
        
        logger.info(f"✅ 端到端风险管理工作流完成:")
        logger.info(f"   初始价值: ${initial_metrics.total_value:,.2f}")
        logger.info(f"   最终价值: ${final_metrics.total_value:,.2f}")
        logger.info(f"   总PnL: ${total_pnl:+,.2f}")
        logger.info(f"   风险警报: {len(final_alerts)}个")
        
        # 清理测试数据
        self.risk_manager.positions.clear()
    
    def teardown_method(self):
        """每个测试方法后的清理"""
        self.risk_manager.positions.clear()

if __name__ == "__main__":
    # 允许单独运行此测试
    pytest.main([__file__, "-v", "-s"])
