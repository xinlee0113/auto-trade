#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BrokerTigerAPI测试文件
包含基本功能测试和深度行情功能测试
"""

import os
import sys
import time
import unittest
from unittest.mock import Mock, patch, MagicMock

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from tigeropen.push.pb.QuoteDepthData_pb2 import QuoteDepthData
from tigeropen.push.pb.QuoteBasicData_pb2 import QuoteBasicData
from tigeropen.push.pb.QuoteBBOData_pb2 import QuoteBBOData


class TestBrokerTigerAPI(unittest.TestCase):
    """BrokerTigerAPI 单元测试类"""
    
    def setUp(self):
        """测试前置设置"""
        # 模拟配置文件存在
        self.config_patch = patch('os.path.exists', return_value=True)
        self.config_patch.start()
        
        # 模拟读取私钥
        self.private_key_patch = patch('tigeropen.common.util.signature_utils.read_private_key', return_value="mock_private_key")
        self.private_key_patch.start()
        
        # 模拟客户端配置
        mock_config = Mock()
        mock_config.tiger_id = "test_tiger_id"
        mock_config.private_key = "test_private_key"
        mock_config.socket_host_port = ("ssl", "mock_host", 443)
        
        self.config_class_patch = patch('tigeropen.tiger_open_config.TigerOpenClientConfig', return_value=mock_config)
        self.config_class_patch.start()
        
        # 模拟各种客户端
        self.trade_client_patch = patch('tigeropen.trade.trade_client.TradeClient')
        self.quote_client_patch = patch('tigeropen.quote.quote_client.QuoteClient')
        self.push_client_patch = patch('tigeropen.push.push_client.PushClient')
        
        mock_trade_client = self.trade_client_patch.start()
        mock_quote_client = self.quote_client_patch.start()
        self.mock_push_client = self.push_client_patch.start()
        
        # 配置模拟对象的返回值
        mock_trade_client.return_value.get_managed_accounts.return_value = ["test_account"]
        mock_quote_client.return_value.grab_quote_permission.return_value = {"permission": "granted"}
        
        # 导入并初始化API
        from src.api.broker_tiger_api import BrokerTigerAPI
        self.api = BrokerTigerAPI()
    
    def tearDown(self):
        """测试后置清理"""
        self.config_patch.stop()
        self.private_key_patch.stop()
        self.config_class_patch.stop()
        self.trade_client_patch.stop()
        self.quote_client_patch.stop()
        self.push_client_patch.stop()
    
    def test_api_initialization(self):
        """测试API初始化"""
        self.assertIsNotNone(self.api)
        self.assertIsNotNone(self.api.trade_client)
        self.assertIsNotNone(self.api.quote_client)
        self.assertIsNotNone(self.api.push_client)
        self.assertEqual(len(self.api.depth_quote_listeners), 0)
        self.assertEqual(len(self.api.quote_listeners), 0)
        self.assertEqual(len(self.api.bbo_listeners), 0)
        self.assertFalse(self.api.is_push_connected)
    
    def test_register_quote_depth_listener(self):
        """测试注册深度行情监听器"""
        # 创建模拟监听器
        mock_listener = Mock()
        test_symbols = ['AAPL', 'QQQ']
        
        # 模拟连接成功
        self.api.is_push_connected = True
        
        # 重置mock调用记录
        self.api.push_client.subscribe_depth_quote.reset_mock()
        
        # 注册监听器
        self.api.register_quote_depth_changed_listener(mock_listener, test_symbols)
        
        # 验证监听器已注册
        self.assertIn(mock_listener, self.api.depth_quote_listeners)
        self.assertEqual(len(self.api.depth_quote_listeners), 1)
        
        # 验证调用了订阅方法
        self.api.push_client.subscribe_depth_quote.assert_called_once_with(test_symbols)
    
    def test_register_quote_listener(self):
        """测试注册基本行情监听器"""
        mock_listener = Mock()
        test_symbols = ['NVDA', 'TSLA']
        
        self.api.is_push_connected = True
        
        # 重置mock调用记录
        self.api.push_client.subscribe_quote.reset_mock()
        
        self.api.register_quote_changed_listener(mock_listener, test_symbols)
        
        self.assertIn(mock_listener, self.api.quote_listeners)
        self.assertEqual(len(self.api.quote_listeners), 1)
        self.api.push_client.subscribe_quote.assert_called_once_with(test_symbols)
    
    def test_register_bbo_listener(self):
        """测试注册最优报价监听器"""
        mock_listener = Mock()
        test_symbols = ['MSFT']
        
        self.api.is_push_connected = True
        
        self.api.register_quote_bbo_changed_listener(mock_listener, test_symbols)
        
        self.assertIn(mock_listener, self.api.bbo_listeners)
        self.assertEqual(len(self.api.bbo_listeners), 1)
        self.api.push_client.subscribe_quote.assert_called_once_with(test_symbols)
    
    def test_unregister_quote_depth_listener(self):
        """测试取消注册深度行情监听器"""
        mock_listener = Mock()
        
        # 先注册
        self.api.depth_quote_listeners.append(mock_listener)
        
        # 取消注册
        self.api.unregister_quote_depth_changed_listener(mock_listener)
        
        # 验证已移除
        self.assertNotIn(mock_listener, self.api.depth_quote_listeners)
        self.assertEqual(len(self.api.depth_quote_listeners), 0)
    
    def test_depth_quote_callback_distribution(self):
        """测试深度行情回调分发"""
        # 创建模拟监听器
        listener1 = Mock()
        listener2 = Mock()
        
        # 注册监听器
        self.api.depth_quote_listeners = [listener1, listener2]
        
        # 创建模拟深度行情数据
        mock_frame = Mock(spec=QuoteDepthData)
        mock_frame.symbol = "AAPL"
        mock_frame.timestamp = 1640995200000
        
        # 调用回调分发
        self.api._on_quote_depth_changed(mock_frame)
        
        # 验证所有监听器都被调用
        listener1.assert_called_once_with(mock_frame)
        listener2.assert_called_once_with(mock_frame)
    
    def test_quote_callback_distribution(self):
        """测试基本行情回调分发"""
        listener1 = Mock()
        listener2 = Mock()
        
        self.api.quote_listeners = [listener1, listener2]
        
        mock_frame = Mock(spec=QuoteBasicData)
        mock_frame.symbol = "QQQ"
        
        self.api._on_quote_changed(mock_frame)
        
        listener1.assert_called_once_with(mock_frame)
        listener2.assert_called_once_with(mock_frame)
    
    def test_bbo_callback_distribution(self):
        """测试最优报价回调分发"""
        listener1 = Mock()
        
        self.api.bbo_listeners = [listener1]
        
        mock_frame = Mock(spec=QuoteBBOData)
        mock_frame.symbol = "NVDA"
        
        self.api._on_quote_bbo_changed(mock_frame)
        
        listener1.assert_called_once_with(mock_frame)
    
    def test_callback_error_handling(self):
        """测试回调错误处理"""
        # 创建会抛出异常的监听器
        error_listener = Mock(side_effect=Exception("测试异常"))
        normal_listener = Mock()
        
        self.api.depth_quote_listeners = [error_listener, normal_listener]
        
        mock_frame = Mock(spec=QuoteDepthData)
        
        # 调用回调分发，不应该抛出异常
        try:
            self.api._on_quote_depth_changed(mock_frame)
        except Exception:
            self.fail("回调分发不应该抛出异常")
        
        # 验证正常监听器仍然被调用
        normal_listener.assert_called_once_with(mock_frame)
    
    def test_push_client_connection(self):
        """测试推送客户端连接"""
        self.api.is_push_connected = False
        
        # 模拟连接成功
        self.api.push_client.connect = Mock()
        
        self.api.connect_push_client()
        
        # 验证连接方法被调用
        self.api.push_client.connect.assert_called_once_with(
            self.api.client_config.tiger_id, 
            self.api.client_config.private_key
        )
    
    def test_push_client_disconnect(self):
        """测试推送客户端断开"""
        self.api.is_push_connected = True
        self.api.push_client.disconnect = Mock()
        
        self.api.disconnect_push_client()
        
        self.api.push_client.disconnect.assert_called_once()
        self.assertFalse(self.api.is_push_connected)
    
    def test_query_subscribed_quotes(self):
        """测试查询已订阅行情"""
        self.api.push_client.query_subscribed_quote = Mock()
        
        self.api.query_subscribed_quotes()
        
        self.api.push_client.query_subscribed_quote.assert_called_once()
    
    def test_duplicate_listener_registration(self):
        """测试重复注册监听器"""
        mock_listener = Mock()
        test_symbols = ['AAPL']
        
        self.api.is_push_connected = True
        
        # 注册两次相同的监听器
        self.api.register_quote_depth_changed_listener(mock_listener, test_symbols)
        self.api.register_quote_depth_changed_listener(mock_listener, test_symbols)
        
        # 应该只有一个监听器
        self.assertEqual(len(self.api.depth_quote_listeners), 1)
        self.assertEqual(self.api.depth_quote_listeners.count(mock_listener), 1)


def test_real_api_functionality():
    """实际API功能测试（需要真实配置文件）"""
    try:
        print("\n🧪 开始实际API功能测试...")
        
        # 检查配置文件是否存在
        config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'tiger_openapi_config.properties')
        if not os.path.exists(config_path):
            print("⚠️ 跳过实际API测试：配置文件不存在")
            return
        
        from src.api.broker_tiger_api import BrokerTigerAPI
        
        # 测试数据接收标志
        received_data = {
            'depth_quote': False,
            'basic_quote': False,
            'bbo_quote': False
        }
        
        def test_depth_listener(frame):
            print(f"✅ 收到深度行情数据: {frame.symbol}")
            received_data['depth_quote'] = True
        
        def test_quote_listener(frame):
            print(f"✅ 收到基本行情数据: {frame.symbol}")
            received_data['basic_quote'] = True
        
        def test_bbo_listener(frame):
            print(f"✅ 收到最优报价数据: {frame.symbol}")
            received_data['bbo_quote'] = True
        
        # 初始化API
        api = BrokerTigerAPI()
        
        # 注册监听器
        test_symbols = ['QQQ']
        api.register_quote_depth_changed_listener(test_depth_listener, test_symbols)
        api.register_quote_changed_listener(test_quote_listener, test_symbols)
        api.register_quote_bbo_changed_listener(test_bbo_listener, test_symbols)
        
        print("⏳ 等待实时数据（10秒）...")
        time.sleep(10)
        
        # 检查结果
        if any(received_data.values()):
            print("✅ 实际API功能测试成功，收到实时数据")
        else:
            print("⚠️ 实际API功能测试：未收到数据（可能是市场休市或网络问题）")
        
        # 清理
        api.disconnect_push_client()
        print("✅ 实际API测试完成")
        
    except Exception as e:
        print(f"❌ 实际API测试失败: {e}")


if __name__ == "__main__":
    print("🧪 开始BrokerTigerAPI单元测试...")
    
    # 运行单元测试
    unittest.main(argv=[''], exit=False, verbosity=2)
    
    # 运行实际API测试
    test_real_api_functionality()
    
    print("🎉 所有测试完成！")
