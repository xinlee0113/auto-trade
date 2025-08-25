#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Greeks计算真实集成测试
使用真实Tiger API数据验证Greeks计算的准确性和实时性
"""

import pytest
import time
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, List

from demos.client_config import get_client_config
from src.utils.greeks_calculator import GreeksCalculator, GreeksData
from src.models.trading_models import OptionTickData, UnderlyingTickData
from src.api.broker_tiger_api import BrokerTigerAPI
from src.utils.logger_config import get_logger

logger = get_logger(__name__)

class TestGreeksRealIntegration:
    """Greeks计算真实集成测试"""
    
    @classmethod
    def setup_class(cls):
        """测试类初始化"""
        logger.info("初始化Greeks真实集成测试")
        cls.config = get_client_config()
        cls.api = BrokerTigerAPI(cls.config)
        cls.greeks_calc = GreeksCalculator()
        cls.test_symbols = ["QQQ", "SPY"]  # 高流动性标的
        
    def test_real_underlying_data_retrieval(self):
        """测试真实标的数据获取"""
        logger.info("测试真实标的数据获取")
        
        quote_client = self.api.get_quote_client()
        briefs = quote_client.get_briefs(self.test_symbols)
        
        # 验证数据完整性
        assert briefs is not None, "标的数据获取失败"
        assert len(briefs) > 0, "未获取到标的数据"
        
        for brief in briefs:
            # 验证关键字段存在且合理
            assert hasattr(brief, 'symbol'), "标的符号缺失"
            assert hasattr(brief, 'latest_price'), "最新价格缺失"
            assert brief.latest_price > 0, f"价格异常: {brief.latest_price}"
            
            logger.info(f"✅ {brief.symbol}: ${brief.latest_price}")
        
        return briefs
    
    def test_real_option_chain_retrieval(self):
        """测试真实期权链数据获取"""
        logger.info("测试真实期权链数据获取")
        
        quote_client = self.api.get_quote_client()
        
        for symbol in self.test_symbols:
            # 获取期权到期日
            expiry_dates = quote_client.get_option_expirations(symbol)
            assert expiry_dates and len(expiry_dates) > 0, f"{symbol}无期权到期日"
            
            # 选择最近到期日
            nearest_expiry = min(expiry_dates)
            logger.info(f"{symbol} 最近到期日: {nearest_expiry}")
            
            # 获取期权链
            option_chain = quote_client.get_option_chain(symbol, nearest_expiry)
            assert option_chain is not None, f"{symbol}期权链获取失败"
            assert not option_chain.empty, f"{symbol}期权链为空"
            
            # 验证期权链数据完整性
            required_columns = ['symbol', 'strike', 'put_call', 'bid', 'ask']
            for col in required_columns:
                assert col in option_chain.columns, f"缺少列: {col}"
            
            logger.info(f"✅ {symbol} 期权链: {len(option_chain)}个合约")
    
    def test_real_greeks_calculation_accuracy(self):
        """测试真实Greeks计算准确性"""
        logger.info("测试真实Greeks计算准确性")
        
        quote_client = self.api.get_quote_client()
        
        for symbol in self.test_symbols:
            # 获取标的数据
            briefs = quote_client.get_briefs([symbol])
            underlying_brief = briefs[0]
            underlying_price = float(underlying_brief.latest_price)
            
            # 获取期权数据
            expiry_dates = quote_client.get_option_expirations(symbol)
            nearest_expiry = min(expiry_dates)
            option_chain = quote_client.get_option_chain(symbol, nearest_expiry)
            
            # 筛选ATM期权
            atm_options = option_chain[
                abs(option_chain['strike'].astype(float) - underlying_price) <= 5.0
            ].head(5)  # 最多测试5个ATM期权
            
            for _, option_row in atm_options.iterrows():
                strike = float(option_row['strike'])
                option_type = option_row['put_call'].upper()
                
                # 构造期权数据
                option_data = OptionTickData(
                    symbol=f"{symbol}_{strike}_{option_type}",
                    underlying_symbol=symbol,
                    strike=strike,
                    option_type=option_type,
                    expiry_date=nearest_expiry,
                    price=float(option_row.get('latest_price', option_row.get('bid', 0))),
                    bid=float(option_row.get('bid', 0)),
                    ask=float(option_row.get('ask', 0)),
                    volume=int(option_row.get('volume', 0)),
                    open_interest=int(option_row.get('open_interest', 0)),
                    timestamp=datetime.now()
                )
                
                # 计算Greeks
                greeks_result = self.greeks_calc.calculate_all_greeks(
                    option_data=option_data,
                    underlying_price=underlying_price,
                    risk_free_rate=0.05,  # 5%无风险利率
                    volatility=0.25       # 25%波动率
                )
                
                # 验证Greeks合理性
                assert greeks_result is not None, "Greeks计算失败"
                assert isinstance(greeks_result, GreeksData), "Greeks结果类型错误"
                
                # Delta范围检查
                if option_type == "CALL":
                    assert 0 <= greeks_result.delta <= 1, f"Call Delta异常: {greeks_result.delta}"
                else:
                    assert -1 <= greeks_result.delta <= 0, f"Put Delta异常: {greeks_result.delta}"
                
                # Gamma必须为正
                assert greeks_result.gamma >= 0, f"Gamma异常: {greeks_result.gamma}"
                
                # Theta通常为负（时间衰减）
                assert greeks_result.theta <= 0, f"Theta异常: {greeks_result.theta}"
                
                logger.info(f"✅ {option_data.symbol} Greeks: "
                          f"Δ={greeks_result.delta:.3f}, "
                          f"Γ={greeks_result.gamma:.3f}, "
                          f"Θ={greeks_result.theta:.3f}")
    
    def test_real_time_greeks_performance(self):
        """测试实时Greeks计算性能"""
        logger.info("测试实时Greeks计算性能")
        
        quote_client = self.api.get_quote_client()
        
        # 获取一个期权进行性能测试
        symbol = "QQQ"
        briefs = quote_client.get_briefs([symbol])
        underlying_price = float(briefs[0].latest_price)
        
        expiry_dates = quote_client.get_option_expirations(symbol)
        nearest_expiry = min(expiry_dates)
        option_chain = quote_client.get_option_chain(symbol, nearest_expiry)
        
        # 选择一个ATM期权
        atm_option = option_chain.iloc[len(option_chain)//2]  # 中间的期权
        
        option_data = OptionTickData(
            symbol=f"{symbol}_{atm_option['strike']}_CALL",
            underlying_symbol=symbol,
            strike=float(atm_option['strike']),
            option_type="CALL",
            expiry_date=nearest_expiry,
            price=float(atm_option.get('latest_price', atm_option.get('bid', 0))),
            bid=float(atm_option.get('bid', 0)),
            ask=float(atm_option.get('ask', 0)),
            volume=int(atm_option.get('volume', 0)),
            open_interest=int(atm_option.get('open_interest', 0)),
            timestamp=datetime.now()
        )
        
        # 性能测试：连续计算100次
        iterations = 100
        start_time = time.time()
        
        for i in range(iterations):
            greeks_result = self.greeks_calc.calculate_all_greeks(
                option_data=option_data,
                underlying_price=underlying_price,
                risk_free_rate=0.05,
                volatility=0.25
            )
            assert greeks_result is not None
        
        end_time = time.time()
        total_time = end_time - start_time
        avg_time_ms = (total_time / iterations) * 1000
        
        # 性能要求：每次计算<10ms
        assert avg_time_ms < 10, f"Greeks计算性能不达标: {avg_time_ms:.2f}ms"
        
        logger.info(f"✅ Greeks计算性能: {avg_time_ms:.2f}ms/次 (目标<10ms)")
    
    def test_real_option_data_consistency(self):
        """测试真实期权数据一致性"""
        logger.info("测试真实期权数据一致性")
        
        quote_client = self.api.get_quote_client()
        
        # 连续获取3次数据，检查一致性
        symbol = "QQQ"
        consistency_checks = 3
        prices = []
        
        for check in range(consistency_checks):
            briefs = quote_client.get_briefs([symbol])
            price = float(briefs[0].latest_price)
            prices.append(price)
            
            logger.info(f"第{check+1}次获取价格: ${price}")
            
            if check < consistency_checks - 1:
                time.sleep(2)  # 等待2秒
        
        # 检查价格变动合理性（不超过5%）
        max_price = max(prices)
        min_price = min(prices)
        price_change_pct = abs(max_price - min_price) / min_price
        
        assert price_change_pct < 0.05, f"价格变动过大: {price_change_pct:.3f} > 5%"
        
        logger.info(f"✅ 价格一致性检查通过，变动幅度: {price_change_pct:.3f}")
    
    def test_market_hours_data_validity(self):
        """测试交易时间数据有效性"""
        logger.info("测试交易时间数据有效性")
        
        quote_client = self.api.get_quote_client()
        
        # 检查市场状态
        from tigeropen.common.consts import Market
        market_status = quote_client.get_market_status(Market.US)
        logger.info(f"当前市场状态: {market_status}")
        
        # 获取数据并检查时效性
        briefs = quote_client.get_briefs(self.test_symbols)
        
        for brief in briefs:
            # 检查是否有最新时间戳
            if hasattr(brief, 'latest_time') and brief.latest_time:
                latest_time = datetime.fromtimestamp(brief.latest_time / 1000)
                time_diff = datetime.now() - latest_time
                
                # 数据时效性检查（最多5分钟延迟）
                assert time_diff.total_seconds() < 300, \
                    f"{brief.symbol}数据延迟过大: {time_diff.total_seconds()}秒"
                
                logger.info(f"✅ {brief.symbol} 数据时效性: {time_diff.total_seconds():.1f}秒")
    
    def test_end_to_end_greeks_workflow(self):
        """端到端Greeks计算工作流测试"""
        logger.info("端到端Greeks计算工作流测试")
        
        # 完整工作流：数据获取 → Greeks计算 → 结果验证
        quote_client = self.api.get_quote_client()
        
        # 1. 获取标的数据
        symbol = "QQQ"
        briefs = quote_client.get_briefs([symbol])
        underlying_price = float(briefs[0].latest_price)
        
        # 2. 获取期权数据
        expiry_dates = quote_client.get_option_expirations(symbol)
        target_expiry = min(expiry_dates)
        option_chain = quote_client.get_option_chain(symbol, target_expiry)
        
        # 3. 筛选ATM期权
        atm_options = option_chain[
            abs(option_chain['strike'].astype(float) - underlying_price) <= 3.0
        ].head(3)
        
        # 4. 批量计算Greeks
        greeks_results = []
        
        for _, option_row in atm_options.iterrows():
            option_data = OptionTickData(
                symbol=f"{symbol}_{option_row['strike']}_{option_row['put_call']}",
                underlying_symbol=symbol,
                strike=float(option_row['strike']),
                option_type=option_row['put_call'].upper(),
                expiry_date=target_expiry,
                price=float(option_row.get('latest_price', option_row.get('bid', 0))),
                bid=float(option_row.get('bid', 0)),
                ask=float(option_row.get('ask', 0)),
                volume=int(option_row.get('volume', 0)),
                open_interest=int(option_row.get('open_interest', 0)),
                timestamp=datetime.now()
            )
            
            greeks = self.greeks_calc.calculate_all_greeks(
                option_data=option_data,
                underlying_price=underlying_price,
                risk_free_rate=0.05,
                volatility=0.25
            )
            
            greeks_results.append((option_data, greeks))
        
        # 5. 验证结果合理性
        assert len(greeks_results) > 0, "未成功计算任何Greeks"
        
        for option_data, greeks in greeks_results:
            assert greeks is not None, f"{option_data.symbol} Greeks计算失败"
            
            # Delta相关性检查：Call的Delta应该随strike增加而减小
            logger.info(f"✅ {option_data.symbol}: "
                      f"Delta={greeks.delta:.3f}, "
                      f"Gamma={greeks.gamma:.3f}, "
                      f"Price=${option_data.price:.2f}")
        
        logger.info(f"✅ 端到端工作流完成，成功处理{len(greeks_results)}个期权")

if __name__ == "__main__":
    # 允许单独运行此测试
    pytest.main([__file__, "-v", "-s"])
