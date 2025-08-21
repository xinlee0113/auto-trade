"""
API频率限制器测试
确保API调用控制功能正常
"""

import unittest
import time
from datetime import datetime, timedelta
from unittest.mock import patch, Mock

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from src.utils.api_rate_limiter import (
    APIRateLimiter,
    APICallRecord,
    get_rate_limiter,
    safe_api_call
)


class TestAPICallRecord(unittest.TestCase):
    """API调用记录测试"""
    
    def test_record_creation(self):
        """测试记录创建"""
        timestamp = datetime.now()
        record = APICallRecord(
            timestamp=timestamp,
            api_name='get_quotes',
            success=True
        )
        
        self.assertEqual(record.timestamp, timestamp)
        self.assertEqual(record.api_name, 'get_quotes')
        self.assertTrue(record.success)


class TestAPIRateLimiter(unittest.TestCase):
    """API频率限制器测试"""
    
    def setUp(self):
        self.limiter = APIRateLimiter()
    
    def test_initialization(self):
        """测试初始化"""
        self.assertIn('quote_api', self.limiter.limits)
        self.assertIn('trade_api', self.limiter.limits)
        self.assertIn('account_api', self.limiter.limits)
        
        # 验证限制设置
        self.assertEqual(self.limiter.limits['quote_api']['per_second'], 8)
        self.assertEqual(self.limiter.limits['quote_api']['per_minute'], 500)
    
    def test_can_call_api_initial_state(self):
        """测试初始状态下可以调用API"""
        self.assertTrue(self.limiter.can_call_api('quote_api'))
        self.assertTrue(self.limiter.can_call_api('trade_api'))
        self.assertTrue(self.limiter.can_call_api('account_api'))
    
    def test_record_api_call(self):
        """测试API调用记录"""
        self.limiter.record_api_call('quote_api', 'get_quotes', True)
        
        # 验证记录存在
        self.assertEqual(len(self.limiter.call_history['quote_api']), 1)
        
        record = self.limiter.call_history['quote_api'][0]
        self.assertEqual(record.api_name, 'get_quotes')
        self.assertTrue(record.success)
    
    def test_per_second_limit(self):
        """测试每秒限制"""
        # 快速调用超过每秒限制
        for i in range(10):  # 超过quote_api的8次/秒限制
            self.limiter.record_api_call('quote_api', f'call_{i}', True)
        
        # 应该被限制
        self.assertFalse(self.limiter.can_call_api('quote_api'))
    
    def test_per_minute_limit(self):
        """测试每分钟限制"""
        # 模拟大量调用
        base_time = datetime.now() - timedelta(seconds=30)
        
        # 手动添加历史记录（模拟30秒前的调用）
        for i in range(450):  # 接近500次/分钟的限制
            record = APICallRecord(
                timestamp=base_time + timedelta(seconds=i/15),  # 分散在30秒内
                api_name=f'call_{i}',
                success=True
            )
            self.limiter.call_history['quote_api'].append(record)
        
        # 现在应该还能调用几次
        self.assertTrue(self.limiter.can_call_api('quote_api'))
        
        # 再添加更多调用，应该被限制
        for i in range(60):
            self.limiter.record_api_call('quote_api', f'recent_call_{i}', True)
        
        self.assertFalse(self.limiter.can_call_api('quote_api'))
    
    def test_wait_if_needed(self):
        """测试等待时间计算"""
        # 初始状态不需要等待
        wait_time = self.limiter.wait_if_needed('quote_api')
        self.assertEqual(wait_time, 0.0)
        
        # 超过限制后需要等待
        for i in range(10):
            self.limiter.record_api_call('quote_api', f'call_{i}', True)
        
        wait_time = self.limiter.wait_if_needed('quote_api')
        self.assertGreater(wait_time, 0.0)
        self.assertLessEqual(wait_time, 2.0)  # 应该在合理范围内
    
    def test_get_api_stats(self):
        """测试API统计"""
        # 添加一些调用记录
        for i in range(5):
            self.limiter.record_api_call('quote_api', f'call_{i}', True)
            self.limiter.record_api_call('trade_api', f'trade_{i}', i % 2 == 0)  # 交替成功/失败
        
        stats = self.limiter.get_api_stats()
        
        # 验证统计结构
        self.assertIn('quote_api', stats)
        self.assertIn('trade_api', stats)
        
        # 验证quote_api统计
        quote_stats = stats['quote_api']
        self.assertEqual(quote_stats['minute_calls'], 5)
        self.assertEqual(quote_stats['minute_limit'], 500)
        self.assertEqual(quote_stats['success_rate'], 100.0)
        
        # 验证trade_api统计（成功率应该是60%：3成功/5总数）
        trade_stats = stats['trade_api']
        self.assertEqual(trade_stats['minute_calls'], 5)
        self.assertEqual(trade_stats['success_rate'], 60.0)
    
    def test_unknown_api_type(self):
        """测试未知API类型"""
        # 未知API类型应该被允许
        self.assertTrue(self.limiter.can_call_api('unknown_api'))
        
        # 等待时间应该为0
        wait_time = self.limiter.wait_if_needed('unknown_api')
        self.assertEqual(wait_time, 0.0)


class TestGlobalRateLimiter(unittest.TestCase):
    """全局限制器测试"""
    
    def test_singleton_behavior(self):
        """测试单例行为"""
        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()
        
        # 应该是同一个实例
        self.assertIs(limiter1, limiter2)
    
    def test_persistent_state(self):
        """测试状态持久性"""
        limiter = get_rate_limiter()
        
        # 记录调用
        limiter.record_api_call('quote_api', 'test_call', True)
        
        # 获取另一个引用
        limiter2 = get_rate_limiter()
        
        # 状态应该保持
        self.assertEqual(len(limiter2.call_history['quote_api']), 1)


class TestSafeAPICall(unittest.TestCase):
    """安全API调用包装器测试"""
    
    def setUp(self):
        # 重置全局限制器状态
        global _rate_limiter
        from src.utils import api_rate_limiter
        api_rate_limiter._rate_limiter = None
    
    def test_successful_api_call(self):
        """测试成功的API调用"""
        def mock_api_function(param1, param2):
            return f"success_{param1}_{param2}"
        
        result = safe_api_call('quote_api', 'test_api', mock_api_function, 'arg1', 'arg2')
        
        self.assertEqual(result, "success_arg1_arg2")
    
    def test_failed_api_call(self):
        """测试失败的API调用"""
        def mock_failing_api():
            raise Exception("API调用失败")
        
        with self.assertRaises(Exception) as context:
            safe_api_call('quote_api', 'failing_api', mock_failing_api)
        
        self.assertIn("API调用失败", str(context.exception))
    
    @patch('src.utils.api_rate_limiter.time.sleep')
    def test_rate_limiting_wait(self, mock_sleep):
        """测试频率限制等待"""
        limiter = get_rate_limiter()
        
        # 先耗尽限额
        for i in range(10):
            limiter.record_api_call('quote_api', f'call_{i}', True)
        
        def mock_api():
            return "delayed_result"
        
        # 应该触发等待
        result = safe_api_call('quote_api', 'delayed_api', mock_api)
        
        # 验证sleep被调用
        mock_sleep.assert_called()
        self.assertEqual(result, "delayed_result")
    
    def test_api_call_recording(self):
        """测试API调用记录"""
        limiter = get_rate_limiter()
        initial_count = len(limiter.call_history['quote_api'])
        
        def mock_api():
            return "recorded_result"
        
        safe_api_call('quote_api', 'recorded_api', mock_api)
        
        # 验证记录增加
        final_count = len(limiter.call_history['quote_api'])
        self.assertEqual(final_count, initial_count + 1)
        
        # 验证记录内容
        last_record = limiter.call_history['quote_api'][-1]
        self.assertEqual(last_record.api_name, 'recorded_api')
        self.assertTrue(last_record.success)


class TestRealWorldScenarios(unittest.TestCase):
    """真实场景测试"""
    
    def setUp(self):
        self.limiter = APIRateLimiter()
    
    def test_high_frequency_trading_scenario(self):
        """测试高频交易场景"""
        # 模拟高频交易：30秒内多次调用
        start_time = datetime.now()
        successful_calls = 0
        blocked_calls = 0
        
        for i in range(50):  # 尝试50次调用
            if self.limiter.can_call_api('quote_api'):
                self.limiter.record_api_call('quote_api', f'hft_call_{i}', True)
                successful_calls += 1
            else:
                blocked_calls += 1
                # 在真实场景中，这里会等待
                time.sleep(0.1)  # 短暂等待
        
        # 验证限制有效
        self.assertGreater(blocked_calls, 0, "应该有一些调用被限制")
        self.assertLess(successful_calls, 50, "不应该所有调用都成功")
        
        # 验证统计
        stats = self.limiter.get_api_stats()
        self.assertGreater(stats['quote_api']['minute_calls'], 0)
    
    def test_mixed_api_usage(self):
        """测试混合API使用场景"""
        # 模拟同时使用多种API
        api_calls = [
            ('quote_api', 'get_quotes'),
            ('quote_api', 'get_option_chain'),
            ('trade_api', 'place_order'),
            ('account_api', 'get_balance'),
            ('quote_api', 'get_briefs'),
            ('trade_api', 'cancel_order')
        ]
        
        successful_calls = 0
        for api_type, api_name in api_calls:
            if self.limiter.can_call_api(api_type):
                self.limiter.record_api_call(api_type, api_name, True)
                successful_calls += 1
        
        # 所有API调用都应该成功（频率不高）
        self.assertEqual(successful_calls, len(api_calls))
        
        # 验证各API都有记录
        stats = self.limiter.get_api_stats()
        self.assertGreater(stats['quote_api']['minute_calls'], 0)
        self.assertGreater(stats['trade_api']['minute_calls'], 0)
        self.assertGreater(stats['account_api']['minute_calls'], 0)
    
    def test_error_recovery_scenario(self):
        """测试错误恢复场景"""
        # 模拟API调用失败和恢复
        for i in range(5):
            success = i % 2 == 0  # 交替成功/失败
            self.limiter.record_api_call('quote_api', f'recovery_call_{i}', success)
        
        stats = self.limiter.get_api_stats()
        
        # 成功率应该是60%（3成功/5总数）
        self.assertEqual(stats['quote_api']['success_rate'], 60.0)
        
        # 即使有失败，也应该能继续调用
        self.assertTrue(self.limiter.can_call_api('quote_api'))


if __name__ == '__main__':
    # 运行所有测试
    print("🧪 开始API频率限制器测试...")
    print("=" * 60)
    
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试类
    test_classes = [
        TestAPICallRecord,
        TestAPIRateLimiter,
        TestGlobalRateLimiter,
        TestSafeAPICall,
        TestRealWorldScenarios
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
        print("\n🎉 所有测试通过! API频率限制器功能正常可用!")
    else:
        print("\n⚠️ 部分测试未通过，需要修复问题!")
        exit(1)
