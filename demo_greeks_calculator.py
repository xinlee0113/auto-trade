"""
Greeks计算器演示
展示0DTE期权Greeks实时计算功能
"""

import sys
import os
from datetime import datetime, date, timedelta

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.utils.greeks_calculator import GreeksCalculator, PortfolioGreeksManager
from src.models.trading_models import OptionTickData, UnderlyingTickData


def create_sample_data():
    """创建示例数据"""
    # QQQ标的数据
    underlying = UnderlyingTickData(
        symbol='QQQ',
        timestamp=datetime.now(),
        price=350.0,
        volume=2500000,
        bid=349.98,
        ask=350.02,
        bid_size=1000,
        ask_size=1200
    )
    
    # 今日到期日期
    today = datetime.now().date().strftime('%Y-%m-%d')
    
    # 创建不同类型的期权
    options = []
    
    # ATM看涨期权
    options.append(OptionTickData(
        symbol='QQQ240101C350',
        underlying='QQQ',
        strike=350.0,
        expiry=today,
        right='CALL',
        timestamp=datetime.now(),
        price=3.5,
        volume=8000,
        bid=3.45,
        ask=3.55,
        bid_size=50,
        ask_size=60,
        open_interest=15000
    ))
    
    # ATM看跌期权
    options.append(OptionTickData(
        symbol='QQQ240101P350',
        underlying='QQQ',
        strike=350.0,
        expiry=today,
        right='PUT',
        timestamp=datetime.now(),
        price=3.2,
        volume=6500,
        bid=3.15,
        ask=3.25,
        bid_size=45,
        ask_size=55,
        open_interest=12000
    ))
    
    # OTM看涨期权
    options.append(OptionTickData(
        symbol='QQQ240101C355',
        underlying='QQQ',
        strike=355.0,
        expiry=today,
        right='CALL',
        timestamp=datetime.now(),
        price=1.2,
        volume=12000,
        bid=1.15,
        ask=1.25,
        bid_size=100,
        ask_size=120,
        open_interest=25000
    ))
    
    # ITM看涨期权
    options.append(OptionTickData(
        symbol='QQQ240101C345',
        underlying='QQQ',
        strike=345.0,
        expiry=today,
        right='CALL',
        timestamp=datetime.now(),
        price=6.8,
        volume=5000,
        bid=6.75,
        ask=6.85,
        bid_size=30,
        ask_size=35,
        open_interest=8000
    ))
    
    return underlying, options


def demonstrate_single_option_greeks():
    """演示单个期权Greeks计算"""
    print("\n" + "="*60)
    print("📊 单个期权Greeks计算演示")
    print("="*60)
    
    calculator = GreeksCalculator()
    underlying, options = create_sample_data()
    
    print(f"📈 标的价格: ${underlying.price:.2f}")
    print(f"⏰ 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    for option in options:
        print(f"🎯 分析期权: {option.symbol}")
        print(f"   执行价: ${option.strike:.0f} {option.right}")
        print(f"   市场价: ${option.price:.2f}")
        print(f"   成交量: {option.volume:,}")
        print(f"   未平仓: {option.open_interest:,}")
        
        # 计算Greeks
        result = calculator.calculate_greeks(option, underlying)
        
        # 显示计算结果
        print(f"   ┌─ Greeks指标 ─────────────────")
        print(f"   │ Delta:  {result.delta:8.4f}  (方向敏感度)")
        print(f"   │ Gamma:  {result.gamma:8.6f}  (加速度)")
        print(f"   │ Theta:  {result.theta:8.4f}  (时间衰减/日)")
        print(f"   │ Vega:   {result.vega:8.4f}  (波动率敏感度)")
        print(f"   │ Rho:    {result.rho:8.4f}  (利率敏感度)")
        print(f"   └─────────────────────────────")
        
        print(f"   ┌─ 0DTE特有指标 ───────────────")
        print(f"   │ 隐含波动率: {result.implied_volatility:6.1%}")
        print(f"   │ 时间衰减率: ${result.time_decay_rate:6.4f}/分钟")
        print(f"   │ Gamma敞口:  {result.gamma_exposure:8.4f}")
        print(f"   │ Theta燃烧:  {result.theta_burn_rate:6.2%}/日")
        print(f"   │ 风险等级:   {result.risk_level:>8s}")
        print(f"   │ 风险评分:   {result.risk_score:8.1f}/100")
        print(f"   └─────────────────────────────")
        print()


def demonstrate_portfolio_greeks():
    """演示投资组合Greeks计算"""
    print("\n" + "="*60)
    print("📊 投资组合Greeks计算演示")
    print("="*60)
    
    manager = PortfolioGreeksManager()
    underlying, options = create_sample_data()
    
    # 设置投资组合持仓
    positions = {
        'QQQ240101C350': 10,   # 多头10张ATM看涨
        'QQQ240101P350': -5,   # 空头5张ATM看跌
        'QQQ240101C355': 20,   # 多头20张OTM看涨
        'QQQ240101C345': -8    # 空头8张ITM看涨
    }
    
    print("📋 投资组合构成:")
    for symbol, quantity in positions.items():
        manager.update_position(symbol, quantity)
        direction = "多头" if quantity > 0 else "空头"
        print(f"   {symbol}: {direction} {abs(quantity):2d}张")
    print()
    
    # 计算投资组合Greeks
    portfolio_result = manager.calculate_portfolio_greeks(options, [underlying])
    
    if portfolio_result:
        print("🎯 投资组合Greeks汇总:")
        print(f"   ┌─ 总体风险指标 ───────────────")
        print(f"   │ 总Delta:    {portfolio_result.delta:8.2f}")
        print(f"   │ 总Gamma:    {portfolio_result.gamma:8.4f}")
        print(f"   │ 总Theta:    {portfolio_result.theta:8.2f}")
        print(f"   │ 总Vega:     {portfolio_result.vega:8.2f}")
        print(f"   │ 总Rho:      {portfolio_result.rho:8.2f}")
        print(f"   └─────────────────────────────")
        
        print(f"   ┌─ 组合特征 ───────────────────")
        print(f"   │ 总价值:     ${portfolio_result.option_price:8.2f}")
        print(f"   │ 每日衰减:   ${abs(portfolio_result.theta):8.2f}")
        print(f"   │ 每分钟衰减: ${portfolio_result.time_decay_rate:8.4f}")
        print(f"   │ Gamma敞口:  {portfolio_result.gamma_exposure:8.2f}")
        print(f"   └─────────────────────────────")
        
        # 获取详细风险指标
        risk_metrics = manager.get_portfolio_risk_metrics()
        
        print(f"   ┌─ 风险评估 ───────────────────")
        print(f"   │ Delta中性度: {risk_metrics.get('delta_neutrality', 0):8.2f}")
        print(f"   │ Gamma风险:   {risk_metrics.get('gamma_risk', 0):8.2f}")
        print(f"   │ Theta燃烧:   ${risk_metrics.get('theta_burn', 0):8.2f}")
        print(f"   │ 波动率敏感: {risk_metrics.get('volatility_sensitivity', 0):8.2f}")
        print(f"   └─────────────────────────────")
    else:
        print("❌ 投资组合Greeks计算失败")


def demonstrate_risk_scenarios():
    """演示风险情境分析"""
    print("\n" + "="*60)
    print("📊 风险情境分析演示")
    print("="*60)
    
    calculator = GreeksCalculator()
    underlying, options = create_sample_data()
    
    # 选择ATM看涨期权进行分析
    option = options[0]  # ATM看涨
    base_result = calculator.calculate_greeks(option, underlying)
    
    print(f"🎯 基础情境 (QQQ = ${underlying.price:.2f}):")
    print(f"   期权价格: ${option.price:.2f}")
    print(f"   Delta: {base_result.delta:.4f}")
    print(f"   Gamma: {base_result.gamma:.6f}")
    print(f"   Theta: {base_result.theta:.4f}")
    print()
    
    # 价格变动情境
    price_scenarios = [340, 345, 355, 360]
    
    print("📈 价格变动情境分析:")
    print("   价格变动 | 预期Delta | 预期Gamma | 预期收益")
    print("   ---------|-----------|-----------|----------")
    
    for new_price in price_scenarios:
        # 创建新的标的数据
        new_underlying = UnderlyingTickData(
            symbol=underlying.symbol,
            timestamp=underlying.timestamp,
            price=new_price,
            volume=underlying.volume,
            bid=new_price - 0.02,
            ask=new_price + 0.02
        )
        
        # 使用Delta和Gamma估算期权价格变化
        price_change = new_price - underlying.price
        estimated_option_change = (base_result.delta * price_change + 
                                 0.5 * base_result.gamma * price_change ** 2)
        estimated_option_price = option.price + estimated_option_change
        
        # 创建新的期权数据进行验证
        new_option = OptionTickData(
            symbol=option.symbol,
            underlying=option.underlying,
            strike=option.strike,
            expiry=option.expiry,
            right=option.right,
            timestamp=option.timestamp,
            price=max(0.01, estimated_option_price),  # 确保价格为正
            volume=option.volume,
            bid=max(0.01, estimated_option_price - 0.05),
            ask=estimated_option_price + 0.05
        )
        
        new_result = calculator.calculate_greeks(new_option, new_underlying)
        
        pnl = estimated_option_change
        pnl_pct = (pnl / option.price) * 100
        
        print(f"   ${new_price:3.0f} ({price_change:+4.0f}) | "
              f"{new_result.delta:9.4f} | "
              f"{new_result.gamma:9.6f} | "
              f"${pnl:+6.2f} ({pnl_pct:+5.1f}%)")
    
    print()
    
    # 时间衰减情境
    print("⏰ 时间衰减分析:")
    print(f"   当前Theta: {base_result.theta:.4f} (每日)")
    print(f"   每小时衰减: ${base_result.theta/24:.4f}")
    print(f"   每分钟衰减: ${base_result.time_decay_rate:.4f}")
    print(f"   剩余1小时预期损失: ${base_result.theta/24:.4f}")
    print(f"   剩余30分钟预期损失: ${base_result.time_decay_rate * 30:.4f}")


def main():
    """主函数"""
    print("🚀 Greeks计算器功能演示")
    print("🎯 专注于0DTE期权高频交易Greeks计算")
    print(f"📅 演示日期: {datetime.now().strftime('%Y年%m月%d日')}")
    
    try:
        # 演示1: 单个期权Greeks计算
        demonstrate_single_option_greeks()
        
        # 演示2: 投资组合Greeks计算
        demonstrate_portfolio_greeks()
        
        # 演示3: 风险情境分析
        demonstrate_risk_scenarios()
        
        print("\n" + "="*60)
        print("🎉 Greeks计算器演示完成!")
        print("✅ 核心功能:")
        print("   - Black-Scholes期权定价模型")
        print("   - 实时Greeks计算 (Delta, Gamma, Theta, Vega, Rho)")
        print("   - 隐含波动率反推计算")
        print("   - 0DTE期权特有指标")
        print("   - 投资组合Greeks汇总")
        print("   - 风险等级评估")
        print("   - 实时风险情境分析")
        print("="*60)
        
    except Exception as e:
        print(f"❌ 演示过程出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
