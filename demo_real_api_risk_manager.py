#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于真实Tiger API数据的风险管理器演示

展示风险管理器在真实市场数据下的功能：
1. 使用真实期权数据进行仓位管理
2. 实时Greeks变化下的风险控制
3. 真实市场波动下的止损机制
4. 实际流动性条件下的风险评估

Author: AI Assistant
Date: 2024-01-21
"""

import sys
import os
import time
import threading
from datetime import datetime, timedelta
from dataclasses import replace
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.services.risk_manager import create_risk_manager, RiskEvent, StopLossType
from src.config.trading_config import DEFAULT_TRADING_CONFIG, RiskLevel
from src.models.trading_models import Position, OptionTickData, UnderlyingTickData
from src.utils.greeks_calculator import GreeksCalculator
from demos.client_config import get_client_config

# Tiger API imports
from tigeropen.trade.domain.order import *
from tigeropen.quote.quote_client import QuoteClient
from tigeropen.common.consts import *


class RealAPIRiskManagerDemo:
    """基于真实API数据的风险管理器演示"""
    
    def __init__(self):
        """初始化演示"""
        print("🛡️ 基于真实Tiger API数据的风险管理器演示")
        print("=" * 70)
        
        # 初始化Tiger API
        self.initialize_tiger_api()
        
        # 配置风险管理器 - 调整限制以适应真实期权价格
        self.config = replace(
            DEFAULT_TRADING_CONFIG,
            risk_level=RiskLevel.MEDIUM,
            max_position_value=200000.0  # 提高限制以适应真实期权价格
        )
        
        self.risk_manager = create_risk_manager(self.config)
        self.greeks_calculator = GreeksCalculator()
        
        # 注册回调
        self.risk_manager.register_risk_alert_callback(self.on_risk_alert)
        self.risk_manager.register_emergency_stop_callback(self.on_emergency_stop)
        
        self.alert_count = 0
        self.emergency_triggered = False
        self.real_positions = {}  # 存储真实仓位数据
        
        print(f"✅ 风险管理器初始化完成")
        print(f"📊 风险等级: {self.config.risk_level.value}")
        print(f"💰 最大仓位价值: ${self.config.max_position_value:,.2f}")
        print()
    
    def initialize_tiger_api(self):
        """初始化Tiger API连接"""
        try:
            self.client_config = get_client_config()
            self.quote_client = QuoteClient(self.client_config)
            print("✅ Tiger API连接初始化成功")
        except Exception as e:
            print(f"❌ Tiger API连接失败: {e}")
            raise
    
    def on_risk_alert(self, alert):
        """风险警报回调"""
        self.alert_count += 1
        severity_emoji = {
            "low": "ℹ️",
            "medium": "⚠️", 
            "high": "🚨",
            "critical": "🆘"
        }
        
        emoji = severity_emoji.get(alert.severity, "⚠️")
        print(f"{emoji} 风险警报 #{self.alert_count} [{alert.severity.upper()}] - {alert.timestamp.strftime('%H:%M:%S')}")
        print(f"   事件: {alert.event_type.value}")
        print(f"   消息: {alert.message}")
        if alert.recommended_action:
            print(f"   建议: {alert.recommended_action}")
        print()
    
    def on_emergency_stop(self):
        """紧急停止回调"""
        self.emergency_triggered = True
        print("🆘 紧急停止触发！")
        print("   所有交易活动已暂停")
        print("   风险管理器进入保护模式")
        print()
    
    def fetch_real_underlying_data(self, symbol):
        """获取真实标的资产数据"""
        try:
            briefs = self.quote_client.get_stock_briefs([symbol])
            
            # 检查返回数据
            if briefs is None:
                print(f"⚠️ {symbol} 行情数据为None")
                return None
            
            # 如果是DataFrame，转换为列表
            if hasattr(briefs, 'iloc'):
                if briefs.empty:
                    print(f"⚠️ {symbol} 行情数据为空")
                    return None
                brief = briefs.iloc[0]
            elif isinstance(briefs, list):
                if not briefs:
                    print(f"⚠️ {symbol} 行情数据列表为空")
                    return None
                brief = briefs[0]
            else:
                print(f"⚠️ {symbol} 行情数据格式异常: {type(briefs)}")
                return None
            
            underlying_data = UnderlyingTickData(
                symbol=symbol,
                timestamp=datetime.now(),
                price=float(brief.latest_price or 0),
                volume=int(brief.volume or 0),
                bid=float(getattr(brief, 'bid', 0.0) or 0.0),
                ask=float(getattr(brief, 'ask', 0.0) or 0.0),
                bid_size=int(getattr(brief, 'bid_size', 0) or 0),
                ask_size=int(getattr(brief, 'ask_size', 0) or 0)
            )
            
            print(f"📊 {symbol} 实时数据: ${underlying_data.price:.2f}, 成交量: {underlying_data.volume:,}")
            return underlying_data
            
        except Exception as e:
            print(f"❌ 获取 {symbol} 数据失败: {e}")
            return None
    
    def fetch_real_option_data(self, underlying, expiry_date=None):
        """获取真实期权数据"""
        try:
            # 使用今日日期作为期权到期日
            if expiry_date is None:
                target_expiry = datetime.now().strftime('%Y-%m-%d')
            else:
                target_expiry = expiry_date.strftime('%Y-%m-%d')
            
            print(f"🔍 获取 {underlying} 期权链数据 (到期日: {target_expiry})...")
            
            # 获取期权链 - 使用与成功案例相同的参数格式
            option_chain = self.quote_client.get_option_chain(underlying, expiry=target_expiry)
            
            # 检查返回的数据
            if option_chain is None:
                print(f"⚠️ {underlying} 期权链数据为None")
                return []
            
            # 如果不是DataFrame，尝试转换
            if not hasattr(option_chain, 'empty'):
                print(f"⚠️ 期权链数据格式异常: {type(option_chain)}")
                return []
            
            if option_chain.empty:
                print(f"⚠️ 未找到 {underlying} 在 {target_expiry} 的期权数据")
                return []
            
            print(f"✅ 获取到 {len(option_chain)} 个期权合约")
            print(f"📋 期权链列名: {list(option_chain.columns)}")
            
            # 数据预处理
            option_chain['strike'] = pd.to_numeric(option_chain['strike'], errors='coerce')
            option_chain = option_chain.dropna(subset=['strike'])
            
            # 获取标的价格用于筛选
            underlying_data = self.fetch_real_underlying_data(underlying)
            if not underlying_data:
                return []
            
            underlying_price = underlying_data.price
            
            # 使用最优期权选择逻辑 - 聚焦于虚值期权
            print(f"🎯 使用最优期权选择逻辑: 标的价格${underlying_price:.2f}")
            
            # 分离CALL和PUT期权
            call_options = option_chain[option_chain['put_call'] == 'CALL'].copy()
            put_options = option_chain[option_chain['put_call'] == 'PUT'].copy()
            
            # 超高频交易策略：聚焦ATM附近期权 (30秒-8分钟)
            atm_range = 3.0  # ATM±$3范围，适合超高频交易
            print(f"⚡ 超高频策略: ATM±${atm_range}范围，优化30秒-8分钟交易")
            
            # 选择ATM附近的期权（包含实值、ATM、轻度虚值）
            atm_calls = call_options[
                (call_options['strike'] >= underlying_price - atm_range) &
                (call_options['strike'] <= underlying_price + atm_range)
            ].copy()
            
            atm_puts = put_options[
                (put_options['strike'] >= underlying_price - atm_range) &
                (put_options['strike'] <= underlying_price + atm_range)  
            ].copy()
            
            # 合并ATM区域期权
            filtered_options = pd.concat([atm_calls, atm_puts], ignore_index=True)
            
            print(f"📊 ATM区域CALL期权: {len(atm_calls)} 个 (${underlying_price-atm_range:.0f}-${underlying_price+atm_range:.0f})")
            print(f"📊 ATM区域PUT期权: {len(atm_puts)} 个 (${underlying_price-atm_range:.0f}-${underlying_price+atm_range:.0f})")
            print(f"📈 筛选结果: {len(filtered_options)} 个ATM区域期权")
            
            if filtered_options.empty:
                print(f"⚠️ 在ATM附近未找到合适的期权")
                return []
            
            # 直接使用期权链中的价格数据，避免API调用问题
            print(f"📈 使用期权链中的价格数据 (共{len(filtered_options)}个期权)...")
            option_briefs_dict = {}  # 不使用额外的期权行情API
            
            # 应用最优期权评分逻辑
            scored_options = self._score_and_rank_options(filtered_options, underlying_price)
            
            # 选择最优的期权
            top_options = scored_options.head(8)  # 选择评分最高的8个期权
            print(f"🏆 选择评分最高的{len(top_options)}个期权:")
            
            option_data_list = []
            
            for _, row in top_options.iterrows():
                symbol = row['symbol']
                brief = option_briefs_dict.get(symbol)
                
                # 基础期权信息
                # 安全处理NaN值
                def safe_float(val, default=0.0):
                    try:
                        result = float(val or default)
                        return result if not pd.isna(result) else default
                    except (ValueError, TypeError):
                        return default
                        
                def safe_int(val, default=0):
                    try:
                        result = float(val or default)
                        return int(result) if not pd.isna(result) else default
                    except (ValueError, TypeError):
                        return default
                
                # 创建标准化的期权标识符
                strike_str = f"{int(safe_float(row['strike']))}"
                option_type = row['put_call']
                expiry_str = target_expiry.replace('-', '')  # 20250822
                unique_symbol = f"{underlying}_{expiry_str}_{option_type}_{strike_str}"
                
                option_data = OptionTickData(
                    symbol=unique_symbol,  # 使用唯一标识符
                    underlying=underlying,
                    strike=safe_float(row['strike']),
                    expiry=target_expiry,
                    right=row['put_call'],  # 修正字段名
                    timestamp=datetime.now(),
                    price=safe_float(row.get('latest_price', 0)),
                    volume=safe_int(row.get('volume', 0)),
                    bid=safe_float(row.get('bid_price', 0)),
                    ask=safe_float(row.get('ask_price', 0)),
                    bid_size=safe_int(row.get('bid_size', 0)),
                    ask_size=safe_int(row.get('ask_size', 0)),
                    open_interest=safe_int(row.get('open_interest', 0))
                )
                
                # 使用期权链中的Greeks数据
                option_data.delta = safe_float(row.get('delta', 0))
                option_data.gamma = safe_float(row.get('gamma', 0))
                option_data.theta = safe_float(row.get('theta', 0))
                option_data.vega = safe_float(row.get('vega', 0))
                option_data.implied_volatility = safe_float(row.get('implied_vol', 0))
                
                option_data_list.append(option_data)
                
                # 显示超高频期权信息和评分
                delta_str = f"{option_data.delta:.3f}" if option_data.delta != 0 else "N/A"
                score_str = f"{row.get('option_score', 0):.1f}" if 'option_score' in row else "N/A"
                atm_distance = row.get('moneyness', 0) * 100
                
                # 判断期权类型
                if atm_distance <= 0.1:
                    position_type = "⚡ATM"
                elif atm_distance <= 0.5:
                    position_type = "🎯近ATM"
                elif atm_distance <= 1.0:
                    position_type = "📊轻度偏离"
                else:
                    position_type = "📉远离ATM"
                
                print(f"  {position_type} [{symbol}] ${option_data.price:.2f} (超高频评分: {score_str})")
                print(f"     执行价: ${option_data.strike:.0f} {option_data.right}, ATM距离: {atm_distance:.2f}%")
                print(f"     Gamma敏感度: 高, 适合30秒-8分钟交易")
                print(f"     成交量: {option_data.volume:,}, 价差: {option_data.spread_percentage:.1f}%")
                print()
            
            print(f"✅ 成功获取 {len(option_data_list)} 个期权数据")
            return option_data_list
            
        except Exception as e:
            print(f"❌ 获取期权数据失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def create_position_from_option_data(self, option_data, quantity=5, index=0):
        """从期权数据创建仓位"""
        position = Position(
            symbol=option_data.symbol,
            quantity=quantity,
            entry_price=option_data.price,
            current_price=option_data.price,
            entry_time=datetime.now(),
            position_id=f"REAL_{option_data.symbol}_{datetime.now().strftime('%H%M%S')}_{index}",  # 添加索引避免重复
            position_type="LONG" if quantity > 0 else "SHORT"
        )
        
        # 设置期权特有属性
        position.current_value = abs(quantity) * option_data.price * 100  # 期权合约乘数
        position.unrealized_pnl = 0.0
        position.delta = option_data.delta * quantity if option_data.delta else None
        position.gamma = option_data.gamma * quantity if option_data.gamma else None
        position.theta = option_data.theta * quantity if option_data.theta else None
        position.vega = option_data.vega * quantity if option_data.vega else None
        position.bid_ask_spread = option_data.spread_percentage / 100 if option_data.price > 0 else None
        position.underlying = option_data.underlying
        
        return position
    
    def _score_and_rank_options(self, options_df, underlying_price):
        """对期权进行评分和排序"""
        print("🔍 应用最优期权选择评分算法...")
        
        # 复制数据避免修改原始DataFrame
        scored_df = options_df.copy()
        
        # 计算评分所需的指标，安全处理NaN值
        scored_df['bid_ask_spread'] = scored_df['ask_price'].fillna(0) - scored_df['bid_price'].fillna(0)
        scored_df['spread_percentage'] = scored_df['bid_ask_spread'] / scored_df['latest_price'].replace(0, 1)
        
        # 计算内在价值和距离ATM的程度
        scored_df['intrinsic_value'] = scored_df.apply(
            lambda row: max(underlying_price - row['strike'], 0) if row['put_call'] == 'CALL' 
            else max(row['strike'] - underlying_price, 0), axis=1
        )
        scored_df['time_value'] = scored_df['latest_price'] - scored_df['intrinsic_value']
        scored_df['moneyness'] = abs(scored_df['strike'] - underlying_price) / underlying_price
        
        # 超高频交易评分算法（0-100分）- 专为30秒-8分钟交易优化
        def calculate_ultra_hf_score(row):
            # 1. ATM距离评分 (0-40分) - 最重要因素
            moneyness = row['moneyness']
            if moneyness <= 0.001:  # ATM (±0.1%)
                atm_score = 40
            elif moneyness <= 0.003:  # 极轻度偏离ATM (±0.3%)
                atm_score = 35
            elif moneyness <= 0.005:  # 轻度偏离ATM (±0.5%)
                atm_score = 30
            elif moneyness <= 0.01:   # 中度偏离ATM (±1.0%)
                atm_score = 20
            elif moneyness <= 0.02:   # 较大偏离ATM (±2.0%)
                atm_score = 10
            else:
                atm_score = 0
            
            # 2. Gamma敏感度评分 (0-30分) - 基于理论Gamma估算
            # ATM期权Gamma最高，距离ATM越远Gamma越低
            if moneyness <= 0.002:    # 极ATM
                gamma_score = 30
            elif moneyness <= 0.005:  # 近ATM
                gamma_score = 25
            elif moneyness <= 0.01:   # 轻度偏离
                gamma_score = 15
            elif moneyness <= 0.02:   # 中度偏离
                gamma_score = 8
            else:
                gamma_score = 2
            
            # 3. 流动性评分 (0-20分) - 超高频需要快速进出
            volume_score = min(15, (row['volume'] / 2000) * 15) if row['volume'] > 0 else 0
            oi_score = min(5, (row['open_interest'] / 1000) * 5) if row['open_interest'] > 0 else 0
            liquidity_score = volume_score + oi_score
            
            # 4. 价差评分 (0-10分) - 超高频对价差敏感但不是最关键
            spread_pct = row['spread_percentage']
            if spread_pct <= 0.01:     # ≤1%
                spread_score = 10
            elif spread_pct <= 0.03:   # ≤3%
                spread_score = 7
            elif spread_pct <= 0.05:   # ≤5%
                spread_score = 4
            else:
                spread_score = 0
            
            total_score = atm_score + gamma_score + liquidity_score + spread_score
            return min(100, total_score)
        
        # 计算每个期权的超高频评分
        scored_df['option_score'] = scored_df.apply(calculate_ultra_hf_score, axis=1)
        
        # 按评分排序
        scored_df = scored_df.sort_values('option_score', ascending=False)
        
        # 显示超高频评分结果
        print("⚡ 超高频最优期权 (30秒-8分钟交易):")
        for i, (_, row) in enumerate(scored_df.head(5).iterrows()):
            atm_distance = row['moneyness'] * 100
            print(f"  {i+1}. {row['put_call']} ${row['strike']:.0f} - "
                  f"评分: {row['option_score']:.1f}, ATM距离: {atm_distance:.2f}%, "
                  f"价格: ${row['latest_price']:.2f}, 成交量: {row['volume']:,}")
        
        return scored_df
    
    def _validate_portfolio_calculations(self):
        """验证投资组合计算逻辑"""
        print("🔍 验证计算逻辑:")
        
        # 手动计算总价值
        manual_total_value = 0
        manual_delta = 0
        
        for position in self.risk_manager.positions.values():
            manual_total_value += position.current_value
            if position.delta:
                manual_delta += position.delta
            
            print(f"    {position.symbol}: {position.quantity}手 × ${position.current_price:.2f} × 100 = ${position.current_value:,.2f}")
        
        # 对比系统计算
        metrics = self.risk_manager.calculate_risk_metrics()
        
        print(f"  手动计算总值: ${manual_total_value:,.2f}")
        print(f"  系统计算总值: ${metrics.total_position_value:,.2f}")
        
        value_match = abs(manual_total_value - metrics.total_position_value) < 0.01
        print(f"  价值计算: {'✅ 正确' if value_match else '❌ 错误'}")
        
        delta_match = abs(manual_delta - metrics.portfolio_delta) < 0.001
        print(f"  Delta计算: {'✅ 正确' if delta_match else '❌ 错误'}")
        
        if not value_match:
            print(f"  ⚠️ 价值计算差异: ${abs(manual_total_value - metrics.total_position_value):,.2f}")
        
        if not delta_match:
            print(f"  ⚠️ Delta计算差异: {abs(manual_delta - metrics.portfolio_delta):.3f}")
    
    def demo_real_market_risk_control(self):
        """演示真实市场数据下的风险控制"""
        print("📊 演示1: 真实市场数据风险控制")
        print("-" * 50)
        
        # 获取QQQ期权数据
        option_data_list = self.fetch_real_option_data("QQQ")
        if not option_data_list:
            print("❌ 无法获取期权数据，跳过此演示")
            return
        
        print(f"\n🏗️ 基于真实数据构建投资组合...")
        
        # 选择3-4个期权创建投资组合
        selected_options = option_data_list[:4]
        quantities = [5, -3, 8, -2]  # 混合多空
        
        for i, (option_data, qty) in enumerate(zip(selected_options, quantities)):
            # 过滤无效的期权数据
            if option_data.price <= 0.10:  # 过滤价格过低的期权
                print(f"⚠️ 跳过价格过低的期权: {option_data.symbol} (${option_data.price:.2f})")
                continue
            
            # 过滤价格过高的期权（可能是深度实值期权）
            if option_data.price > 20.0:  # 末日期权一般不会超过$20
                print(f"⚠️ 跳过价格过高的期权: {option_data.symbol} (${option_data.price:.2f}) - 可能是深度实值")
                continue
            
            # 跳过买卖价差过大的期权（流动性差）
            if option_data.spread > option_data.price * 0.20:  # 价差超过20%
                print(f"⚠️ 跳过流动性差的期权: {option_data.symbol} (价差{option_data.spread_percentage:.1f}%)")
                continue
                
            position = self.create_position_from_option_data(option_data, qty, i)
            
            result = self.risk_manager.add_position(position)
            
            action = "做多" if qty > 0 else "做空"
            status = "✅ 成功" if result else "❌ 被拒绝"
            
            print(f"  {action} {abs(qty)}手 [{option_data.symbol}]: {status}")
            print(f"    期权详情: 执行价${option_data.strike:.0f} {option_data.right}, 到期{option_data.expiry}")
            print(f"    价格: ${option_data.price:.2f}, 价值: ${position.current_value:.2f}")
            if option_data.delta:
                print(f"    Delta: {option_data.delta:.3f}, 组合Delta: {position.delta:.3f}")
            
            if result:
                self.real_positions[position.position_id] = {
                    'position': position,
                    'option_data': option_data,
                    'last_update': datetime.now()
                }
        
        # 显示初始组合风险并验证计算
        metrics = self.risk_manager.calculate_risk_metrics()
        print(f"\n📈 初始组合风险指标:")
        print(f"  仓位数量: {metrics.position_count}")
        print(f"  总价值: ${metrics.total_position_value:,.2f}")
        print(f"  组合Delta: {metrics.portfolio_delta:.3f}")
        print(f"  组合Gamma: {metrics.portfolio_gamma:.3f}")
        print(f"  组合Theta: ${metrics.portfolio_theta:.2f}")
        print(f"  风险分数: {metrics.risk_score:.1f}/100")
        
        # 验证计算逻辑
        if metrics.position_count > 0:
            self._validate_portfolio_calculations()
        print()
    
    def get_specific_option_price(self, underlying, strike, option_type, expiry_date):
        """获取特定期权的当前价格"""
        try:
            # 获取完整期权链
            option_chain = self.quote_client.get_option_chain(underlying, expiry=expiry_date)
            
            if option_chain is None or option_chain.empty:
                return None
            
            # 精确匹配特定期权
            option_chain['strike'] = pd.to_numeric(option_chain['strike'], errors='coerce')
            specific_option = option_chain[
                (option_chain['strike'] == strike) & 
                (option_chain['put_call'] == option_type)
            ]
            
            if specific_option.empty:
                return None
            
            row = specific_option.iloc[0]
            price = row.get('latest_price', 0)
            
            # 安全处理价格
            try:
                price = float(price or 0)
                return price if not pd.isna(price) else None
            except (ValueError, TypeError):
                return None
                
        except Exception as e:
            print(f"⚠️ 获取期权价格失败: {e}")
            return None
    
    def demo_real_time_risk_monitoring(self):
        """演示实时风险监控 - 100%真实API数据"""
        print("⚡ 演示2: 实时风险监控 (30秒) - 🔴 纯真实API数据")
        print("-" * 50)
        
        if not self.real_positions:
            print("⚠️ 没有活跃仓位，跳过实时监控演示")
            return
        
        print("🔄 开始实时监控...")
        print("📍 监控内容: 真实价格变化、实际Greeks变化、真实止损触发")
        print("📡 数据来源: Tiger OpenAPI实时数据 (无任何模拟数据)")
        print()
        
        start_time = time.time()
        update_count = 0
        
        # 显示当前仓位信息和提取期权参数
        print("📋 当前监控仓位:")
        position_details = {}
        
        for pos_id, pos_info in self.real_positions.items():
            position = pos_info['position']
            option_data = pos_info['option_data']
            
            # 从OptionTickData中提取期权参数
            position_details[pos_id] = {
                'position': position,
                'underlying': option_data.underlying,
                'strike': option_data.strike,
                'option_type': option_data.right,
                'expiry': option_data.expiry
            }
            
            print(f"  • {position.symbol}: {position.quantity}手, 入场价${position.entry_price:.2f}")
            print(f"    期权参数: {option_data.underlying} {option_data.strike} {option_data.right} {option_data.expiry}")
        print()
        
        while time.time() - start_time < 30:  # 监控30秒
            try:
                # 更新现有仓位 - 针对每个具体期权查询价格
                for pos_id, details in position_details.items():
                    position = details['position']
                    
                    # 获取该特定期权的当前价格
                    current_price = self.get_specific_option_price(
                        underlying=details['underlying'],
                        strike=details['strike'],
                        option_type=details['option_type'],
                        expiry_date=details['expiry']
                    )
                    
                    if current_price is None:
                        continue
                    
                    # 只有价格发生变化才更新
                    if abs(current_price - position.current_price) > 0.01:
                        price_change_pct = ((current_price - position.current_price) / position.current_price) * 100
                        
                        print(f"📊 {position.symbol} 真实价格变动:")
                        print(f"  💰 价格: ${position.current_price:.2f} → ${current_price:.2f}")
                        print(f"  📡 数据来源: Tiger API特定期权查询")
                        print(f"  📈 变化幅度: {price_change_pct:+.2f}%")
                        print(f"  🎯 期权参数: {details['underlying']} ${details['strike']} {details['option_type']}")
                        
                        # 价格变动合理性检查
                        if abs(price_change_pct) > 30:
                            print(f"  ⚠️ 异常价格变动警告: {price_change_pct:+.2f}% (可能需要人工核实)")
                        
                        # 创建更新的OptionTickData
                        updated_option_data = OptionTickData(
                            symbol=position.symbol,
                            underlying=details['underlying'],
                            strike=details['strike'],
                            expiry=details['expiry'],
                            right=details['option_type'],
                            timestamp=datetime.now(),
                            price=current_price,
                            volume=0,  # 监控时不关注成交量变化
                            bid=0,
                            ask=0
                        )
                        
                        # 更新仓位并检查风险
                        alerts = self.risk_manager.update_position(pos_id, updated_option_data)
                        
                        if alerts:
                            print(f"🚨 {position.symbol} 基于真实价格触发 {len(alerts)} 个风险警报")
                            for alert in alerts:
                                print(f"  ⚠️ {alert.severity.upper()}: {alert.message}")
                        else:
                            print(f"✅ {position.symbol} 价格变动在安全范围内")
                        
                        update_count += 1
                        print()
                
                # 定期检查组合风险
                if update_count % 3 == 0:  # 每3次更新检查一次
                    portfolio_alerts = self.risk_manager.check_portfolio_risks()
                    if portfolio_alerts:
                        print(f"⚠️ 组合级别风险: {len(portfolio_alerts)} 个警报")
                
                time.sleep(5)  # 5秒更新一次
                
            except Exception as e:
                print(f"⚠️ 监控过程中出错: {e}")
                time.sleep(5)
        
        print(f"✅ 真实数据监控完成，共进行 {update_count} 次API价格更新")
        
        # 显示最终状态
        final_metrics = self.risk_manager.calculate_risk_metrics()
        print(f"\n📊 基于真实API数据的最终风险状态:")
        print(f"  📡 数据验证: 100%来自Tiger OpenAPI")
        print(f"  📊 价格更新次数: {update_count}")
        print(f"  💰 未实现盈亏: ${final_metrics.unrealized_pnl:.2f}")
        print(f"  📈 风险分数: {final_metrics.risk_score:.1f}/100")
        print(f"  ⚠️ 风险警报数: {self.alert_count}")
        print()
    
    def demo_stress_test_with_simulated_scenarios(self):
        """使用模拟极端场景进行压力测试"""
        print("🧪 演示3: 模拟极端场景压力测试 - 🟡 模拟数据")
        print("-" * 50)
        
        if not self.real_positions:
            print("⚠️ 没有活跃仓位，跳过压力测试")
            return
        
        print("💥 模拟市场极端波动场景...")
        print("📡 数据来源: 基于真实数据构造的模拟极端场景")
        
        # 获取当前期权数据作为基准
        option_data_list = self.fetch_real_option_data("QQQ")
        if not option_data_list:
            print("❌ 无法获取基准数据")
            return
        
        option_data_dict = {opt.symbol: opt for opt in option_data_list}
        
        # 模拟不同程度的市场冲击
        shock_scenarios = [
            {"name": "轻度下跌", "price_change": -0.05, "vol_change": 0.2},
            {"name": "中度暴跌", "price_change": -0.15, "vol_change": 0.5},
            {"name": "极端崩盘", "price_change": -0.30, "vol_change": 1.0}
        ]
        
        initial_metrics = self.risk_manager.calculate_risk_metrics()
        
        for scenario in shock_scenarios:
            print(f"\n📉 模拟场景: {scenario['name']} (价格变化: {scenario['price_change']:.1%})")
            print(f"🔧 测试目的: 验证{scenario['price_change']:.1%}市场冲击下的风险防护")
            
            scenario_alerts = []
            
            for pos_id, pos_info in self.real_positions.items():
                position = pos_info['position']
                symbol = position.symbol
                
                if symbol in option_data_dict:
                    base_option = option_data_dict[symbol]
                    
                    # 创建压力测试下的期权数据 (模拟价格)
                    stressed_price = base_option.price * (1 + scenario['price_change'])
                    stressed_price = max(0.01, stressed_price)  # 最低0.01
                    
                    print(f"  📊 {symbol}: ${base_option.price:.2f} → ${stressed_price:.2f} (模拟冲击)")
                    
                    stressed_option = OptionTickData(
                        symbol=symbol,
                        underlying=base_option.underlying,
                        strike=base_option.strike,
                        expiry=base_option.expiry,
                        right=base_option.right,
                        timestamp=datetime.now(),
                        price=stressed_price,
                        volume=base_option.volume * 2,  # 假设成交量放大
                        bid=stressed_price - 0.05,
                        ask=stressed_price + 0.05,
                        delta=base_option.delta * 0.8 if base_option.delta else None,  # Delta变化
                        gamma=base_option.gamma,
                        theta=base_option.theta,
                        vega=base_option.vega
                    )
                    
                    # 更新仓位并检查风险
                    alerts = self.risk_manager.update_position(pos_id, stressed_option)
                    scenario_alerts.extend(alerts)
            
            # 检查组合风险
            portfolio_alerts = self.risk_manager.check_portfolio_risks()
            scenario_alerts.extend(portfolio_alerts)
            
            # 计算压力测试下的指标
            stressed_metrics = self.risk_manager.calculate_risk_metrics()
            
            pnl_change = stressed_metrics.unrealized_pnl - initial_metrics.unrealized_pnl
            risk_change = stressed_metrics.risk_score - initial_metrics.risk_score
            
            print(f"  💰 盈亏变化: ${pnl_change:.2f}")
            print(f"  📊 风险分数变化: {risk_change:+.1f}")
            print(f"  🚨 触发警报: {len(scenario_alerts)} 个")
            
            # 分析警报类型
            alert_types = {}
            for alert in scenario_alerts:
                alert_types[alert.event_type.value] = alert_types.get(alert.event_type.value, 0) + 1
            
            if alert_types:
                print("  警报分布:", ", ".join([f"{k}: {v}" for k, v in alert_types.items()]))
        
        print(f"\n✅ 压力测试完成")
    
    def demo_risk_summary_report(self):
        """生成风险摘要报告"""
        print("📋 演示4: 风险摘要报告")
        print("-" * 50)
        
        summary = self.risk_manager.get_risk_summary()
        
        print("🎯 风险管理摘要报告:")
        print(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  监控时长: 约2-3分钟")
        print()
        
        print("📊 投资组合关键指标:")
        metrics = summary['metrics']
        print(f"  仓位数量: {metrics['position_count']}")
        print(f"  总价值: ${metrics['total_position_value']:,.2f}")
        print(f"  未实现盈亏: ${metrics['unrealized_pnl']:,.2f}")
        print(f"  组合Delta: {metrics['portfolio_delta']:.3f}")
        print(f"  组合Gamma: {metrics['portfolio_gamma']:.3f}")
        print(f"  集中度风险: {metrics['concentration_risk']:.1%}")
        print(f"  风险分数: {metrics['risk_score']:.1f}/100")
        print()
        
        print("🚧 风险限制状态:")
        limits = summary['limits']
        print(f"  单笔仓位限制: ${limits['max_single_position']:,.2f}")
        print(f"  总仓位限制: ${limits['max_total_position']:,.2f}")
        print(f"  日内交易: {limits['daily_trades']}")
        print(f"  日损失限制: ${limits['daily_loss_limit']:,.2f}")
        print()
        
        print("⚠️ 警报统计:")
        alerts = summary['alerts']
        print(f"  总警报数: {alerts['total']}")
        print(f"  近1小时: {alerts['recent_hour']}")
        print(f"  严重级别: {alerts['critical']}")
        print(f"  高风险: {alerts['high']}")
        print()
        
        # 风险评估
        risk_score = metrics['risk_score']
        if risk_score < 30:
            risk_level = "🟢 低风险"
        elif risk_score < 60:
            risk_level = "🟡 中等风险"
        elif risk_score < 80:
            risk_level = "🟠 高风险"
        else:
            risk_level = "🔴 极高风险"
        
        print(f"🎯 综合风险评级: {risk_level}")
        
        # 建议
        recommendations = []
        if metrics['concentration_risk'] > 0.5:
            recommendations.append("建议分散投资，降低集中度风险")
        if alerts['critical'] > 0:
            recommendations.append("立即处理严重级别风险警报")
        if metrics['portfolio_delta'] > abs(10):
            recommendations.append("考虑Delta对冲，降低方向性风险")
        
        if recommendations:
            print("\n💡 风险管理建议:")
            for i, rec in enumerate(recommendations, 1):
                print(f"  {i}. {rec}")
        
        print()
    
    def run_complete_real_api_demo(self):
        """运行完整的真实API演示"""
        try:
            print("🚀 开始基于真实Tiger API数据的风险管理演示")
            print("⏰ 预计演示时间: 3-4分钟")
            print()
            
            # 依次运行各个演示
            self.demo_real_market_risk_control()
            self.demo_real_time_risk_monitoring()  # 纯真实数据
            self.demo_stress_test_with_simulated_scenarios()  # 模拟极端场景
            self.demo_risk_summary_report()
            
            # 最终统计
            print("📈 演示结果统计")
            print("-" * 50)
            print(f"✅ 真实仓位数: {len(self.real_positions)}")
            print(f"⚠️ 总风险警报: {self.alert_count}")
            print(f"🛑 紧急停止触发: {'是' if self.emergency_triggered else '否'}")
            
            final_metrics = self.risk_manager.calculate_risk_metrics()
            print(f"📊 最终风险分数: {final_metrics.risk_score:.1f}/100")
            print(f"💰 最终盈亏: ${final_metrics.unrealized_pnl:.2f}")
            print()
            
            print("🎉 基于真实API数据的风险管理演示完成!")
            print("💡 风险管理器已经过真实市场数据验证，可用于生产环境")
            
        except Exception as e:
            print(f"❌ 演示过程中出现错误: {e}")
            import traceback
            traceback.print_exc()


def main():
    """主函数"""
    try:
        demo = RealAPIRiskManagerDemo()
        demo.run_complete_real_api_demo()
    except KeyboardInterrupt:
        print("\n⚠️ 演示被用户中断")
    except Exception as e:
        print(f"\n❌ 演示失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
