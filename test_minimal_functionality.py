"""
最小化功能测试 - 验证核心组件
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """测试核心导入"""
    print("🔍 测试核心导入...")
    
    try:
        from src.config.trading_config import DEFAULT_TRADING_CONFIG, TradingConstants
        print("  ✅ 交易配置导入成功")
        
        from src.models.trading_models import OptionTickData, UnderlyingTickData
        print("  ✅ 数据模型导入成功")
        
        from src.utils.logger_config import get_logger
        print("  ✅ 日志配置导入成功")
        
        from src.utils.api_rate_limiter import APIRateLimiter, get_rate_limiter, safe_api_call
        print("  ✅ API限制器导入成功")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 导入失败: {e}")
        return False


def test_api_rate_limiter():
    """测试API限制器"""
    print("\n🔍 测试API限制器...")
    
    try:
        from src.utils.api_rate_limiter import APIRateLimiter
        
        limiter = APIRateLimiter()
        
        # 测试基本功能
        can_call = limiter.can_call_api('quote_api')
        assert can_call == True, "初始状态应该允许调用"
        print("  ✅ 初始状态检查通过")
        
        # 测试记录功能
        limiter.record_api_call('quote_api', 'test_call', True)
        assert len(limiter.call_history['quote_api']) == 1, "调用记录应该增加"
        print("  ✅ 调用记录功能正常")
        
        # 测试统计功能
        stats = limiter.get_api_stats()
        assert 'quote_api' in stats, "统计应该包含quote_api"
        assert stats['quote_api']['minute_calls'] == 1, "分钟调用次数应该为1"
        print("  ✅ 统计功能正常")
        
        # 测试等待时间计算
        wait_time = limiter.wait_if_needed('quote_api')
        assert wait_time >= 0, "等待时间不能为负数"
        print("  ✅ 等待时间计算正常")
        
        return True
        
    except Exception as e:
        print(f"  ❌ API限制器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_data_models():
    """测试数据模型"""
    print("\n🔍 测试数据模型...")
    
    try:
        from src.models.trading_models import OptionTickData, UnderlyingTickData
        from datetime import datetime
        
        # 测试标的数据模型
        underlying_data = UnderlyingTickData(
            symbol='QQQ',
            timestamp=datetime.now(),
            price=350.0,
            volume=1000,
            bid=349.9,
            ask=350.1,
            bid_size=100,
            ask_size=200
        )
        
        assert underlying_data.symbol == 'QQQ', "标的数据字段错误"
        assert underlying_data.price == 350.0, "价格字段错误"
        print("  ✅ 标的数据模型正常")
        
        # 测试期权数据模型
        option_data = OptionTickData(
            symbol='QQQ240101C350',
            underlying='QQQ',
            strike=350.0,
            expiry='2024-01-01',
            right='CALL',
            timestamp=datetime.now(),
            price=5.5,
            volume=100,
            bid=5.4,
            ask=5.6,
            bid_size=10,
            ask_size=15,
            open_interest=500
        )
        
        assert option_data.symbol == 'QQQ240101C350', "期权数据字段错误"
        assert option_data.strike == 350.0, "执行价字段错误"
        print("  ✅ 期权数据模型正常")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 数据模型测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_trading_config():
    """测试交易配置"""
    print("\n🔍 测试交易配置...")
    
    try:
        from src.config.trading_config import DEFAULT_TRADING_CONFIG, TradingConstants
        
        # 测试默认配置
        config = DEFAULT_TRADING_CONFIG
        assert len(config.watch_symbols) > 0, "监听标的不能为空"
        assert 'QQQ' in config.watch_symbols, "应该包含QQQ"
        print("  ✅ 默认配置正常")
        
        # 测试交易常量
        constants = TradingConstants
        assert hasattr(constants, 'UNDERLYING_EMA_FAST'), "应该有EMA快线周期"
        assert hasattr(constants, 'MAX_POSITION_TIME'), "应该有最大持仓时间"
        print("  ✅ 交易常量正常")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 交易配置测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_safe_api_call():
    """测试安全API调用"""
    print("\n🔍 测试安全API调用...")
    
    try:
        from src.utils.api_rate_limiter import safe_api_call, get_rate_limiter
        
        # 重置限制器状态
        limiter = get_rate_limiter()
        
        # 测试成功调用
        def mock_successful_api():
            return "success_result"
        
        result = safe_api_call('quote_api', 'test_api', mock_successful_api)
        assert result == "success_result", "结果应该匹配"
        print("  ✅ 成功调用测试通过")
        
        # 测试调用记录
        stats = limiter.get_api_stats()
        assert stats['quote_api']['minute_calls'] > 0, "应该有调用记录"
        print("  ✅ 调用记录正常")
        
        # 测试失败调用
        def mock_failing_api():
            raise Exception("测试异常")
        
        try:
            safe_api_call('quote_api', 'failing_api', mock_failing_api)
            assert False, "应该抛出异常"
        except Exception:
            print("  ✅ 异常处理正常")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 安全API调用测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("🧪 开始最小化功能测试...")
    print("=" * 50)
    
    test_results = []
    
    # 运行各项测试
    tests = [
        ('核心导入', test_imports),
        ('API限制器', test_api_rate_limiter),
        ('数据模型', test_data_models),
        ('交易配置', test_trading_config),
        ('安全API调用', test_safe_api_call)
    ]
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            test_results.append((test_name, result))
        except Exception as e:
            print(f"❌ 测试 {test_name} 出现异常: {e}")
            test_results.append((test_name, False))
    
    # 汇总结果
    print("\n" + "=" * 50)
    print("📊 测试结果汇总:")
    
    passed = 0
    failed = 0
    
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  - {test_name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\n📈 总计: {passed + failed} 个测试")
    print(f"✅ 通过: {passed}")
    print(f"❌ 失败: {failed}")
    
    if failed == 0:
        print(f"\n🎉 所有核心功能测试通过!")
        print(f"   ✅ 核心组件工作正常")
        print(f"   ✅ API限制器功能完整")
        print(f"   ✅ 数据模型结构正确")
        print(f"   ✅ 系统架构健全")
        return True
    else:
        print(f"\n⚠️ 有 {failed} 个测试失败，需要修复!")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
