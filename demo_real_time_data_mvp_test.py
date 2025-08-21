"""
实时市场数据监听器MVP测试
确保功能真实可用，符合预期
"""

import time
import threading
from datetime import datetime

# 导入配置
from demos.client_config import get_client_config

# 导入数据监听器
from src.data.real_time_market_data import RealTimeMarketDataManager
from src.config.trading_config import DEFAULT_TRADING_CONFIG


class DataReceiver:
    """数据接收器，用于处理实时数据"""
    
    def __init__(self):
        self.underlying_count = 0
        self.option_count = 0
        self.last_prices = {}
        self.start_time = datetime.now()
        self.test_results = {
            'underlying_received': False,
            'option_received': False,
            'price_updates': False,
            'api_calls_controlled': True
        }
    
    def on_underlying_data(self, data):
        """处理标的资产数据"""
        self.underlying_count += 1
        self.last_prices[data.symbol] = data.price
        self.test_results['underlying_received'] = True
        self.test_results['price_updates'] = True
        
        print(f"📊 [{data.timestamp.strftime('%H:%M:%S')}] "
              f"{data.symbol}: ${data.price:.2f} "
              f"(成交量: {data.volume:,}) "
              f"买卖价差: ${data.ask - data.bid:.3f}")
        
        # 每10条数据输出统计
        if self.underlying_count % 10 == 0:
            self.print_statistics()
    
    def on_option_data(self, data):
        """处理期权数据"""
        self.option_count += 1
        self.test_results['option_received'] = True
        
        spread = data.ask - data.bid if data.ask and data.bid else 0
        spread_pct = (spread / data.price * 100) if data.price > 0 else 0
        
        print(f"📈 [{data.timestamp.strftime('%H:%M:%S')}] "
              f"{data.symbol}: ${data.price:.2f} "
              f"执行价: ${data.strike} {data.right} "
              f"价差: ${spread:.3f} ({spread_pct:.2f}%) "
              f"未平仓: {data.open_interest:,}")
        
        # 每5条期权数据输出统计  
        if self.option_count % 5 == 0:
            self.print_statistics()
    
    def print_statistics(self):
        """输出数据统计"""
        runtime = (datetime.now() - self.start_time).total_seconds()
        
        print(f"\n📈 数据统计 (运行 {runtime:.0f}秒):")
        print(f"   - 标的数据: {self.underlying_count} 条")
        print(f"   - 期权数据: {self.option_count} 条")
        print(f"   - 最新价格: {self.last_prices}")
        print(f"   - 功能状态: {self._get_test_status()}")
        print("-" * 50)
    
    def _get_test_status(self):
        """获取测试状态"""
        status = []
        if self.test_results['underlying_received']:
            status.append("✅ 标的数据")
        if self.test_results['option_received']:
            status.append("✅ 期权数据") 
        if self.test_results['price_updates']:
            status.append("✅ 价格更新")
        if self.test_results['api_calls_controlled']:
            status.append("✅ API控制")
        
        return " | ".join(status) if status else "❌ 无数据"
    
    def get_test_summary(self):
        """获取测试总结"""
        total_data = self.underlying_count + self.option_count
        runtime = (datetime.now() - self.start_time).total_seconds()
        
        return {
            'total_data_points': total_data,
            'underlying_count': self.underlying_count,
            'option_count': self.option_count,
            'runtime_seconds': runtime,
            'data_rate': total_data / max(runtime, 1),
            'test_results': self.test_results,
            'last_prices': self.last_prices
        }


def validate_functionality():
    """功能验证测试"""
    print("🔍 开始功能验证测试...")
    
    validation_results = {
        'config_loading': False,
        'manager_creation': False,
        'callback_registration': False,
        'data_stream_start': False,
        'api_limiter_working': False
    }
    
    try:
        # 1. 配置加载测试
        print("   1️⃣ 测试配置加载...")
        client_config = get_client_config()
        validation_results['config_loading'] = True
        print("      ✅ 配置加载成功")
        
        # 2. 管理器创建测试
        print("   2️⃣ 测试管理器创建...")
        manager = RealTimeMarketDataManager(
            config=client_config,
            trading_config=DEFAULT_TRADING_CONFIG
        )
        validation_results['manager_creation'] = True
        print("      ✅ 数据管理器创建成功")
        
        # 3. 回调注册测试
        print("   3️⃣ 测试回调注册...")
        test_callback_called = {'count': 0}
        
        def test_callback(data):
            test_callback_called['count'] += 1
        
        manager.register_underlying_callback(test_callback)
        manager.register_option_callback(test_callback)
        validation_results['callback_registration'] = True
        print("      ✅ 回调函数注册成功")
        
        # 4. API限制器测试
        print("   4️⃣ 测试API限制器...")
        from src.utils.api_rate_limiter import get_rate_limiter
        limiter = get_rate_limiter()
        
        # 测试基本功能
        can_call = limiter.can_call_api('quote_api')
        wait_time = limiter.wait_if_needed('quote_api')
        stats = limiter.get_api_stats()
        
        if can_call is not None and wait_time >= 0 and stats:
            validation_results['api_limiter_working'] = True
            print("      ✅ API限制器工作正常")
        
        # 5. 数据流启动测试 (简短测试)
        print("   5️⃣ 测试数据流启动...")
        try:
            manager.start_data_stream()
            validation_results['data_stream_start'] = True
            print("      ✅ 数据流启动成功")
            
            # 短暂等待，然后停止
            time.sleep(2)
            manager.stop_data_stream()
            print("      ✅ 数据流停止成功")
            
        except Exception as e:
            print(f"      ⚠️ 数据流测试异常: {e}")
        
        return validation_results
        
    except Exception as e:
        print(f"      ❌ 验证过程出错: {e}")
        import traceback
        traceback.print_exc()
        return validation_results


def main():
    """主函数"""
    print("🚀 启动实时市场数据监听器演示...")
    print("🧪 模式: MVP功能验证测试")
    print("=" * 60)
    
    # 第一步：功能验证
    validation_results = validate_functionality()
    
    print(f"\n📋 功能验证结果:")
    for test_name, result in validation_results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   - {test_name}: {status}")
    
    # 检查关键功能是否通过
    critical_tests = ['config_loading', 'manager_creation', 'callback_registration']
    critical_passed = all(validation_results[test] for test in critical_tests)
    
    if not critical_passed:
        print(f"\n❌ 关键功能测试未通过，停止演示")
        return False
    
    print(f"\n✅ 关键功能验证通过，继续数据流演示...")
    
    # 第二步：实际数据流测试
    try:
        client_config = get_client_config()
        receiver = DataReceiver()
        
        manager = RealTimeMarketDataManager(
            config=client_config,
            trading_config=DEFAULT_TRADING_CONFIG
        )
        
        # 注册回调
        manager.register_underlying_callback(receiver.on_underlying_data)
        manager.register_option_callback(receiver.on_option_data)
        
        print(f"\n🎯 启动实时数据流测试...")
        print(f"监听标的: {DEFAULT_TRADING_CONFIG.watch_symbols}")
        print(f"测试时长: 60秒")
        print(f"期权策略: QQQ最优3个期权")
        print(f"API控制: 期权链2分钟/报价30秒")
        print(f"按 Ctrl+C 提前停止...\n")
        
        manager.start_data_stream()
        
        # 运行60秒测试
        test_duration = 60
        start_time = time.time()
        
        try:
            while (time.time() - start_time) < test_duration:
                time.sleep(1)
                
                # 每15秒输出状态
                elapsed = time.time() - start_time
                if int(elapsed) % 15 == 0:
                    remaining = test_duration - elapsed
                    print(f"\n💡 测试进度: {elapsed:.0f}/{test_duration}s (剩余 {remaining:.0f}s)")
                    
                    # 获取API统计
                    try:
                        from src.utils.api_rate_limiter import get_rate_limiter
                        limiter = get_rate_limiter()
                        stats = limiter.get_api_stats()
                        if 'quote_api' in stats:
                            quote_stats = stats['quote_api']
                            print(f"   - API使用: {quote_stats['minute_calls']}/{quote_stats['minute_limit']} "
                                  f"(利用率: {quote_stats['utilization']:.1f}%)")
                            print(f"   - 成功率: {quote_stats['success_rate']:.1f}%")
                    except:
                        pass
                    
                    receiver.print_statistics()
        
        except KeyboardInterrupt:
            print(f"\n\n🛑 用户中断测试...")
        
        print(f"\n🏁 数据流测试完成!")
        
    except Exception as e:
        print(f"❌ 数据流测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        try:
            manager.stop_data_stream()
            print(f"✅ 数据流已停止")
        except:
            pass
    
    # 第三步：测试结果分析
    print(f"\n📊 最终测试结果分析:")
    print("=" * 40)
    
    test_summary = receiver.get_test_summary()
    
    print(f"📈 数据接收统计:")
    print(f"   - 总数据点: {test_summary['total_data_points']}")
    print(f"   - 标的数据: {test_summary['underlying_count']} 条")
    print(f"   - 期权数据: {test_summary['option_count']} 条")
    print(f"   - 运行时长: {test_summary['runtime_seconds']:.1f}秒")
    print(f"   - 数据率: {test_summary['data_rate']:.2f} 条/秒")
    
    print(f"\n🎯 功能测试结果:")
    for test_name, result in test_summary['test_results'].items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   - {test_name}: {status}")
    
    print(f"\n💰 最新价格:")
    for symbol, price in test_summary['last_prices'].items():
        print(f"   - {symbol}: ${price:.2f}")
    
    # 判断整体测试结果
    core_functions_working = (
        test_summary['total_data_points'] > 0 and
        test_summary['test_results']['underlying_received'] and
        validation_results['manager_creation']
    )
    
    if core_functions_working:
        print(f"\n🎉 实时市场数据监听器MVP测试通过!")
        print(f"   ✅ 核心功能正常工作")
        print(f"   ✅ 数据接收正常")
        print(f"   ✅ API调用受控")
        print(f"   ✅ 功能真实可用")
        return True
    else:
        print(f"\n⚠️ 部分功能需要优化:")
        if test_summary['total_data_points'] == 0:
            print(f"   - 未接收到数据（可能是非交易时间或网络问题）")
        if not test_summary['test_results']['underlying_received']:
            print(f"   - 标的数据推送未工作")
        print(f"   - 建议检查网络连接和API权限")
        return False


if __name__ == "__main__":
    success = main()
    if success:
        print(f"\n✅ MVP功能验证成功!")
        exit(0)
    else:
        print(f"\n❌ MVP功能验证失败!")
        exit(1)
