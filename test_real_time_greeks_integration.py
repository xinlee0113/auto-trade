"""
真实数据Greeks计算集成测试
验证Greeks计算器与实时数据的集成功能
"""

import sys
import os
import time
from datetime import datetime

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from demos.client_config import get_client_config
from src.data.real_time_market_data import RealTimeMarketDataManager
from src.utils.greeks_calculator import GreeksCalculator
from src.config.trading_config import DEFAULT_TRADING_CONFIG


def test_api_connectivity():
    """测试API连接性"""
    print("🔍 测试1: API连接性检查")
    
    try:
        client_config = get_client_config()
        print("  ✅ 配置加载成功")
        
        data_manager = RealTimeMarketDataManager(
            config=client_config,
            trading_config=DEFAULT_TRADING_CONFIG
        )
        print("  ✅ 数据管理器创建成功")
        
        return True, data_manager
        
    except Exception as e:
        print(f"  ❌ API连接测试失败: {e}")
        return False, None


def test_greeks_calculator_with_real_data(data_manager):
    """测试Greeks计算器与真实数据集成"""
    print("\n🔍 测试2: Greeks计算器与真实数据集成")
    
    calculator = GreeksCalculator()
    received_data = {'underlying': [], 'options': []}
    greeks_results = []
    
    def on_underlying_data(data):
        received_data['underlying'].append(data)
        print(f"  📊 接收标的数据: {data.symbol} = ${data.price:.2f}")
    
    def on_option_data(data):
        received_data['options'].append(data)
        print(f"  📈 接收期权数据: {data.symbol} = ${data.price:.2f}")
        
        # 寻找对应的标的数据
        underlying_data = None
        for underlying in received_data['underlying']:
            if underlying.symbol == data.underlying:
                underlying_data = underlying
                break
        
        if underlying_data:
            try:
                # 计算Greeks
                greeks = calculator.calculate_greeks(data, underlying_data)
                greeks_results.append(greeks)
                
                print(f"  🎯 Greeks计算成功: {data.symbol}")
                print(f"     Delta: {greeks.delta:.4f}, Gamma: {greeks.gamma:.6f}")
                print(f"     Theta: {greeks.theta:.4f}, 隐含波动率: {greeks.implied_volatility:.1%}")
                
            except Exception as e:
                print(f"  ⚠️ Greeks计算失败: {e}")
    
    # 注册回调
    data_manager.register_underlying_callback(on_underlying_data)
    data_manager.register_option_callback(on_option_data)
    
    try:
        # 启动数据流
        print("  🚀 启动数据流...")
        data_manager.start_data_stream()
        
        # 等待数据接收
        print("  ⏳ 等待数据接收 (120秒)...")
        start_time = time.time()
        
        while time.time() - start_time < 120:  # 等待2分钟
            time.sleep(5)
            
            # 显示进度
            elapsed = time.time() - start_time
            print(f"  📊 进度: {elapsed:.0f}/120秒 - "
                  f"标的: {len(received_data['underlying'])}, "
                  f"期权: {len(received_data['options'])}, "
                  f"Greeks: {len(greeks_results)}")
            
            # 如果已经有数据，可以提前结束
            if len(greeks_results) >= 3:
                print("  ✅ 已获取足够数据，提前结束测试")
                break
        
        # 分析结果
        print(f"\n  📊 数据接收结果:")
        print(f"     标的数据: {len(received_data['underlying'])} 条")
        print(f"     期权数据: {len(received_data['options'])} 条")
        print(f"     Greeks计算: {len(greeks_results)} 个")
        
        if len(greeks_results) > 0:
            print(f"  ✅ 集成测试成功")
            
            # 显示样例结果
            print(f"\n  📈 Greeks计算样例:")
            for i, greeks in enumerate(greeks_results[:3]):
                print(f"     {i+1}. {greeks.symbol}:")
                print(f"        Delta: {greeks.delta:.4f}")
                print(f"        Gamma: {greeks.gamma:.6f}")
                print(f"        Theta: {greeks.theta:.4f}")
                print(f"        隐含波动率: {greeks.implied_volatility:.1%}")
                print(f"        风险等级: {greeks.risk_level}")
            
            return True, greeks_results
        else:
            print(f"  ⚠️ 未获取到Greeks计算结果")
            return False, []
    
    except Exception as e:
        print(f"  ❌ 集成测试失败: {e}")
        return False, []
    
    finally:
        try:
            data_manager.stop_data_stream()
            print("  ✅ 数据流已停止")
        except:
            pass


def test_greeks_accuracy_validation(greeks_results):
    """测试Greeks计算精度验证"""
    print("\n🔍 测试3: Greeks计算精度验证")
    
    if not greeks_results:
        print("  ⚠️ 无Greeks结果可验证")
        return False
    
    accuracy_tests = []
    
    for greeks in greeks_results:
        print(f"\n  📊 验证 {greeks.symbol}:")
        
        # 检查Delta范围
        delta_valid = -1.0 <= greeks.delta <= 1.0
        print(f"     Delta范围检查: {greeks.delta:.4f} ∈ [-1,1] = {delta_valid}")
        accuracy_tests.append(delta_valid)
        
        # 检查Gamma非负
        gamma_valid = greeks.gamma >= 0
        print(f"     Gamma非负检查: {greeks.gamma:.6f} ≥ 0 = {gamma_valid}")
        accuracy_tests.append(gamma_valid)
        
        # 检查隐含波动率合理性
        iv_valid = 0.01 <= greeks.implied_volatility <= 5.0
        print(f"     波动率合理性: {greeks.implied_volatility:.1%} ∈ [1%,500%] = {iv_valid}")
        accuracy_tests.append(iv_valid)
        
        # 检查风险等级
        risk_valid = greeks.risk_level in ['LOW', 'MEDIUM', 'HIGH', 'EXTREME']
        print(f"     风险等级有效性: {greeks.risk_level} = {risk_valid}")
        accuracy_tests.append(risk_valid)
        
        # 检查0DTE特征（如果是当日到期）
        if greeks.time_to_expiry < 1/365:  # 小于1天
            theta_valid = greeks.theta < -0.01  # 0DTE期权应该有显著Theta衰减
            print(f"     0DTE Theta检查: {greeks.theta:.4f} < -0.01 = {theta_valid}")
            accuracy_tests.append(theta_valid)
        else:
            print(f"     非0DTE期权，跳过Theta检查")
    
    passed = sum(accuracy_tests)
    total = len(accuracy_tests)
    accuracy = passed / total * 100 if total > 0 else 0
    
    print(f"\n  📊 精度验证结果: {passed}/{total} ({accuracy:.1f}%)")
    
    if accuracy >= 80:
        print(f"  ✅ Greeks计算精度验证通过")
        return True
    else:
        print(f"  ⚠️ Greeks计算精度需要改进")
        return False


def test_performance_metrics():
    """测试性能指标"""
    print("\n🔍 测试4: 性能指标测试")
    
    calculator = GreeksCalculator()
    
    # 创建测试数据
    from src.models.trading_models import OptionTickData, UnderlyingTickData
    
    underlying = UnderlyingTickData(
        symbol='QQQ',
        timestamp=datetime.now(),
        price=350.0,
        volume=1000000,
        bid=349.98,
        ask=350.02
    )
    
    option = OptionTickData(
        symbol='QQQ240101C350',
        underlying='QQQ',
        strike=350.0,
        expiry=datetime.now().date().strftime('%Y-%m-%d'),
        right='CALL',
        timestamp=datetime.now(),
        price=3.5,
        volume=5000,
        bid=3.45,
        ask=3.55,
        open_interest=10000
    )
    
    # 性能测试
    calculation_times = []
    
    for i in range(100):
        start_time = time.time()
        greeks = calculator.calculate_greeks(option, underlying)
        end_time = time.time()
        
        calculation_time = (end_time - start_time) * 1000  # 毫秒
        calculation_times.append(calculation_time)
    
    avg_time = sum(calculation_times) / len(calculation_times)
    max_time = max(calculation_times)
    min_time = min(calculation_times)
    
    print(f"  📊 Greeks计算性能 (100次测试):")
    print(f"     平均时间: {avg_time:.2f}ms")
    print(f"     最大时间: {max_time:.2f}ms")
    print(f"     最小时间: {min_time:.2f}ms")
    
    # 性能要求：平均计算时间 < 10ms
    performance_ok = avg_time < 10.0
    
    if performance_ok:
        print(f"  ✅ 性能测试通过 (目标: <10ms)")
        return True
    else:
        print(f"  ⚠️ 性能需要优化 (目标: <10ms)")
        return False


def main():
    """主测试函数"""
    print("🧪 真实数据Greeks计算集成测试")
    print("🎯 验证Greeks计算器与Tiger API的集成")
    print(f"📅 测试日期: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}")
    print("=" * 80)
    
    test_results = []
    
    # 测试1: API连接性
    api_ok, data_manager = test_api_connectivity()
    test_results.append(('API连接性', api_ok))
    
    if not api_ok:
        print("\n❌ API连接失败，跳过后续测试")
        print("💡 请检查网络连接和API配置")
        return
    
    # 测试2: 数据集成
    integration_ok, greeks_results = test_greeks_calculator_with_real_data(data_manager)
    test_results.append(('数据集成', integration_ok))
    
    # 测试3: 精度验证
    if integration_ok:
        accuracy_ok = test_greeks_accuracy_validation(greeks_results)
        test_results.append(('计算精度', accuracy_ok))
    else:
        test_results.append(('计算精度', False))
    
    # 测试4: 性能测试
    performance_ok = test_performance_metrics()
    test_results.append(('计算性能', performance_ok))
    
    # 汇总结果
    print("\n" + "=" * 80)
    print("📊 集成测试结果汇总")
    print("=" * 80)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {test_name:<15}: {status}")
        if result:
            passed += 1
    
    print(f"\n📈 总体结果: {passed}/{total} ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 所有集成测试通过！")
        print("✅ Greeks计算器可以正常使用真实API数据")
        print("✅ 计算精度和性能符合要求")
        print("✅ 系统集成功能完整")
    elif passed >= total * 0.75:
        print("⚠️ 大部分测试通过，部分功能需要优化")
    else:
        print("❌ 多项测试失败，需要检查系统配置")
    
    print("\n💡 真实数据Greeks计算功能:")
    print("   - 使用 demo_real_time_greeks.py 进行实时演示")
    print("   - 集成Tiger API实时期权数据")
    print("   - 动态计算Greeks指标")
    print("   - 投资组合风险分析")


if __name__ == "__main__":
    main()
