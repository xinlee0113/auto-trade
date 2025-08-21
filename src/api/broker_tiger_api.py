import time
from typing import Callable, List, Optional
from tigeropen.common.util.order_utils import order_leg
from tigeropen.push.push_client import PushClient
from tigeropen.push.pb.QuoteDepthData_pb2 import QuoteDepthData
from tigeropen.push.pb.QuoteBasicData_pb2 import QuoteBasicData
from tigeropen.push.pb.QuoteBBOData_pb2 import QuoteBBOData
from tigeropen.quote.quote_client import QuoteClient
from tigeropen.tiger_open_config import TigerOpenClientConfig
from tigeropen.trade.trade_client import TradeClient


class BrokerTigerAPI:
    def __init__(self):
        try:
            import os
            # 读取配置文件路径
            config_path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'tiger_openapi_config.properties'))
            private_key_path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'private_key.pem'))

            # 检查配置文件是否存在
            if not os.path.exists(config_path):
                raise FileNotFoundError(f"配置文件不存在: {config_path}")

            # 导入必要的工具函数
            from tigeropen.common.util.signature_utils import read_private_key
            from tigeropen.common.consts import Language

            # 初始化客户端配置
            client_config = TigerOpenClientConfig(
                sandbox_debug=False,  # 生产环境
                props_path=config_path
            )
            
            # 尝试从private_key.pem文件读取私钥，如果文件不存在则从配置文件读取
            if os.path.exists(private_key_path):
                client_config.private_key = read_private_key(private_key_path)
                print("✅ 从private_key.pem文件读取私钥")
            else:
                # 从配置文件读取私钥
                import configparser
                config = configparser.ConfigParser()
                config.read(config_path)
                
                # 尝试读取pk8格式的私钥
                if config.has_option('DEFAULT', 'private_key_pk8'):
                    private_key_content = config.get('DEFAULT', 'private_key_pk8')
                    client_config.private_key = private_key_content
                    print("✅ 从配置文件读取pk8格式私钥")
                elif config.has_option('DEFAULT', 'private_key_pk1'):
                    private_key_content = config.get('DEFAULT', 'private_key_pk1')
                    client_config.private_key = private_key_content
                    print("✅ 从配置文件读取pk1格式私钥")
                else:
                    raise ValueError("配置文件中未找到私钥信息（private_key_pk8 或 private_key_pk1）")
            client_config.language = Language.zh_CN
            client_config.timeout = 60

            # 保存配置供后续使用
            self.client_config = client_config

            # 创建客户端实例
            self.trade_client = TradeClient(client_config)
            protocol, host, port = client_config.socket_host_port
            self.push_client = PushClient(host, port, use_ssl=(protocol == 'ssl'))
            
            # 初始化推送相关变量
            self.is_push_connected = False
            self.depth_quote_listeners = []
            self.quote_listeners = []
            self.bbo_listeners = []
            
            # 设置推送客户端回调
            self._setup_push_callbacks()
            
            print("✅ 客户端初始化完成")

            self.quote_client = QuoteClient(client_config)
            permissions = self.quote_client.grab_quote_permission()
            print(f"✅ 行情连接成功，权限信息: {permissions}")

            accounts = self.trade_client.get_managed_accounts()
            print(f"✅ 交易连接成功，账户数量: {len(accounts) if accounts else 0}")

        except Exception as e:
            print(f"❌ 客户端初始化失败: {e}")
            raise

    def get_account_profile(self, account_type=None):
        accounts = self.trade_client.get_managed_accounts()
        print(f"✅ 账户数量: {len(accounts) if accounts else 0}")
        select_account = None
        print("👤 账户信息:")
        if accounts:
            for account in accounts:
                print(f"  账户: {account}")
                if account.account_type == account_type:
                    select_account = account
        return select_account

    def get_assets(self, account_profile):
        # 获取资产信息
        # 使用账户字符串而不是AccountProfile对象
        assets = self.trade_client.get_assets(account=account_profile.account)
        print("💰 资产信息:")

        if assets:
            for asset in assets:
                # 从summary获取资产信息
                if hasattr(asset, 'summary') and asset.summary:
                    summary = asset.summary

                    # 显示基本信息
                    if hasattr(summary, 'currency'):
                        print(f"  货币: {summary.currency}")

                    # 显示资产数据
                    if hasattr(summary, 'net_liquidation'):
                        print(f"  总资产: ${summary.net_liquidation:,.2f}")
                    if hasattr(summary, 'cash'):
                        print(f"  现金: ${summary.cash:,.2f}")
                    if hasattr(summary, 'buying_power'):
                        print(f"  可用资金: ${summary.buying_power:,.2f}")
                    if hasattr(summary, 'gross_position_value'):
                        print(f"  持仓市值: ${summary.gross_position_value:,.2f}")
                    if hasattr(summary, 'unrealized_pnl'):
                        print(f"  未实现盈亏: ${summary.unrealized_pnl:,.2f}")
                    if hasattr(summary, 'realized_pnl'):
                        print(f"  已实现盈亏: ${summary.realized_pnl:,.2f}")
                    if hasattr(summary, 'available_funds'):
                        print(f"  可用资金: ${summary.available_funds:,.2f}")
                    if hasattr(summary, 'excess_liquidity'):
                        print(f"  超额流动性: ${summary.excess_liquidity:,.2f}")
                else:
                    print("  无法获取资产摘要信息")

                print("---")
        else:
            print("  未获取到资产信息")
        return assets

    def get_contacts(self, symbol):
        contract = self.trade_client.get_contracts(symbol)[0]
        print(f"✅ 合约信息: {contract}\n")
        from tigeropen.common.consts import Currency, SecurityType
        contract = self.trade_client.get_contract(symbol=symbol, sec_type=SecurityType.STK, currency=Currency.USD)
        print(contract)
        # get derivative option_basics of stock. include OPT, WAR, IOPT
        contracts = self.trade_client.get_derivative_contracts(symbol="QQQ", sec_type=SecurityType.OPT, expiry='20250820')
        print(f"✅ 期权合约信息: {contracts}")
        return contract

    def create_order(self, account, contract):
        # order = self.trade_client.create_order(account, contract, 'BUY', 'LMT', 100, limit_price=5.0)
        # self.trade_client.place_order(order)
        # print(f"✅ 创建订单: {json.dumps(order.to_dict(), indent=2, ensure_ascii=False, default=lambda o: o.__dict__)}\n")

        # new_order = self.trade_client.get_order(id=order.id)
        # assert order.order_id == new_order.order_id
        # print(f"✅ 获取订单信息: {new_order}\n")
        #
        # self.trade_client.modify_order(new_order, quantity=150)
        # new_order = self.trade_client.get_order(id=order.id)
        # print(f"✅ 修改订单信息: {new_order}\n")
        # assert new_order.quantity == 150
        #
        # self.trade_client.cancel_order(id=order.id)
        # new_order = self.trade_client.get_order(id=order.id)
        # assert new_order.status == OrderStatus.CANCELLED or new_order.status == OrderStatus.PENDING_CANCEL
        # print(f"✅ 取消订单信息: {new_order}\n")
        #
        # result = self.trade_client.preview_order(order)
        # print(f"✅ 预览订单信息: {result}")

        stop_loss_order_leg = order_leg('LOSS', 8.0, time_in_force='GTC')  # 附加止损
        profit_taker_order_leg = order_leg('PROFIT', 12.0, time_in_force='GTC')  # 附加止盈
        main_order = self.trade_client.create_order(account, contract, 'BUY', 'LMT', quantity=100, limit_price=10.0,
                                                    order_legs=[stop_loss_order_leg, profit_taker_order_leg])

        self.trade_client.place_order(main_order)
        print(main_order)

        # result = self.trade_client.preview_order(main_order)
        # print(f"✅ 预览订单信息: {result}")

        # 查询主订单所关联的附加订单
        order_legs = self.trade_client.get_open_orders(account, parent_id=main_order.order_id)
        print(order_legs)

    def _setup_push_callbacks(self):
        """设置推送客户端的回调方法"""
        # 深度行情回调
        self.push_client.quote_depth_changed = self._on_quote_depth_changed
        # 基本行情回调
        self.push_client.quote_changed = self._on_quote_changed
        # 最优报价回调
        self.push_client.quote_bbo_changed = self._on_quote_bbo_changed
        
        # 连接相关回调
        self.push_client.connect_callback = self._on_connect
        self.push_client.disconnect_callback = self._on_disconnect
        self.push_client.error_callback = self._on_error
        
        # 订阅相关回调
        self.push_client.subscribe_callback = self._on_subscribe
        self.push_client.unsubscribe_callback = self._on_unsubscribe
        self.push_client.query_subscribed_callback = self._on_query_subscribed
    
    def _on_quote_depth_changed(self, frame: QuoteDepthData):
        """深度行情变化回调分发"""
        try:
            # 分发给所有注册的监听器
            for listener in self.depth_quote_listeners:
                try:
                    listener(frame)
                except Exception as e:
                    print(f"❌ 深度行情监听器执行失败: {e}")
        except Exception as e:
            print(f"❌ 深度行情回调分发失败: {e}")
    
    def _on_quote_changed(self, frame: QuoteBasicData):
        """基本行情变化回调分发"""
        try:
            for listener in self.quote_listeners:
                try:
                    listener(frame)
                except Exception as e:
                    print(f"❌ 基本行情监听器执行失败: {e}")
        except Exception as e:
            print(f"❌ 基本行情回调分发失败: {e}")
    
    def _on_quote_bbo_changed(self, frame: QuoteBBOData):
        """最优报价变化回调分发"""
        try:
            for listener in self.bbo_listeners:
                try:
                    listener(frame)
                except Exception as e:
                    print(f"❌ 最优报价监听器执行失败: {e}")
        except Exception as e:
            print(f"❌ 最优报价回调分发失败: {e}")
    
    def _on_connect(self, frame):
        """连接建立回调"""
        self.is_push_connected = True
        print(f"✅ 推送连接已建立: {frame}")
    
    def _on_disconnect(self):
        """连接断开回调，实现自动重连"""
        self.is_push_connected = False
        print("⚠️ 推送连接断开，开始重连...")
        
        # 实现重连逻辑
        for attempt in range(1, 11):  # 最多重连10次
            try:
                print(f"🔄 第{attempt}次重连尝试...")
                self.push_client.connect(self.client_config.tiger_id, self.client_config.private_key)
                print("✅ 重连成功")
                return
            except Exception as e:
                print(f"❌ 第{attempt}次重连失败: {e}")
                time.sleep(min(attempt * 2, 30))  # 指数退避，最大30秒
        
        print("❌ 重连失败，请检查网络连接")
    
    def _on_error(self, frame):
        """错误回调"""
        print(f"❌ 推送客户端错误: {frame}")
    
    def _on_subscribe(self, frame):
        """订阅成功回调"""
        print(f"✅ 订阅成功: {frame}")
    
    def _on_unsubscribe(self, frame):
        """取消订阅回调"""
        print(f"✅ 取消订阅成功: {frame}")
    
    def _on_query_subscribed(self, data):
        """查询已订阅行情回调"""
        try:
            if isinstance(data, str):
                import json
                data = json.loads(data)
            
            print(f"📋 已订阅行情信息:")
            
            # 基本行情订阅信息
            if 'subscribed_symbols' in data:
                print(f"  基本行情: {data['subscribed_symbols']} (已用: {data.get('used', 0)}/{data.get('limit', 0)})")
            
            # 深度行情订阅信息
            if 'subscribed_quote_depth_symbols' in data:
                print(f"  深度行情: {data['subscribed_quote_depth_symbols']} (已用: {data.get('quote_depth_used', 0)}/{data.get('quote_depth_limit', 0)})")
            else:
                print(f"  深度行情: 无权限或未订阅")
            
            # 逐笔成交订阅信息
            if 'subscribed_trade_tick_symbols' in data:
                print(f"  逐笔成交: {data['subscribed_trade_tick_symbols']} (已用: {data.get('trade_tick_used', 0)}/{data.get('trade_tick_limit', 0)})")
            
            # K线订阅信息
            if 'kline_used' in data:
                print(f"  K线数据: 已用 {data.get('kline_used', 0)}/{data.get('kline_limit', 0)}")
            
        except Exception as e:
            print(f"❌ 解析订阅信息失败: {e}")
            print(f"   原始数据: {data}")
    
    def connect_push_client(self):
        """连接推送客户端"""
        try:
            if not self.is_push_connected:
                self.push_client.connect(self.client_config.tiger_id, self.client_config.private_key)
                print("✅ 推送客户端连接成功")
            else:
                print("ℹ️ 推送客户端已连接")
        except Exception as e:
            print(f"❌ 推送客户端连接失败: {e}")
            raise
    
    def disconnect_push_client(self):
        """断开推送客户端连接"""
        try:
            if self.is_push_connected:
                self.push_client.disconnect()
                self.is_push_connected = False
                print("✅ 推送客户端已断开")
            else:
                print("ℹ️ 推送客户端未连接")
        except Exception as e:
            print(f"❌ 推送客户端断开失败: {e}")
    
    def register_quote_depth_changed_listener(self, listener: Callable[[QuoteDepthData], None], symbols: List[str]):
        """
        注册深度行情变化监听器
        
        Args:
            listener: 深度行情变化回调函数，参数为QuoteDepthData
            symbols: 要订阅的股票代码列表
        """
        try:
            # 确保推送连接已建立
            self.connect_push_client()
            
            # 注册监听器
            if listener not in self.depth_quote_listeners:
                self.depth_quote_listeners.append(listener)
                print(f"✅ 深度行情监听器已注册，当前监听器数量: {len(self.depth_quote_listeners)}")
            
            # 订阅深度行情
            self.push_client.subscribe_depth_quote(symbols)
            print(f"✅ 已订阅深度行情: {symbols}")
            
        except Exception as e:
            print(f"❌ 注册深度行情监听器失败: {e}")
            raise
    
    def unregister_quote_depth_changed_listener(self, listener: Callable[[QuoteDepthData], None]):
        """
        取消注册深度行情变化监听器
        
        Args:
            listener: 要取消注册的监听器
        """
        try:
            if listener in self.depth_quote_listeners:
                self.depth_quote_listeners.remove(listener)
                print(f"✅ 深度行情监听器已取消注册，当前监听器数量: {len(self.depth_quote_listeners)}")
            else:
                print("⚠️ 监听器未找到")
        except Exception as e:
            print(f"❌ 取消注册深度行情监听器失败: {e}")
    
    def register_quote_changed_listener(self, listener: Callable[[QuoteBasicData], None], symbols: List[str]):
        """
        注册基本行情变化监听器
        
        Args:
            listener: 基本行情变化回调函数，参数为QuoteBasicData
            symbols: 要订阅的股票代码列表
        """
        try:
            self.connect_push_client()
            
            if listener not in self.quote_listeners:
                self.quote_listeners.append(listener)
                print(f"✅ 基本行情监听器已注册，当前监听器数量: {len(self.quote_listeners)}")
            
            self.push_client.subscribe_quote(symbols)
            print(f"✅ 已订阅基本行情: {symbols}")
            
        except Exception as e:
            print(f"❌ 注册基本行情监听器失败: {e}")
            raise
    
    def register_quote_bbo_changed_listener(self, listener: Callable[[QuoteBBOData], None], symbols: List[str]):
        """
        注册最优报价变化监听器
        
        Args:
            listener: 最优报价变化回调函数，参数为QuoteBBOData
            symbols: 要订阅的股票代码列表
        """
        try:
            self.connect_push_client()
            
            if listener not in self.bbo_listeners:
                self.bbo_listeners.append(listener)
                print(f"✅ 最优报价监听器已注册，当前监听器数量: {len(self.bbo_listeners)}")
            
            # 老虎证券的BBO数据通常通过基本行情订阅获得
            self.push_client.subscribe_quote(symbols)
            print(f"✅ 已订阅最优报价: {symbols}")
            
        except Exception as e:
            print(f"❌ 注册最优报价监听器失败: {e}")
            raise
    
    def query_subscribed_quotes(self):
        """查询已订阅的行情"""
        try:
            self.push_client.query_subscribed_quote()
            print("✅ 已发送查询已订阅行情请求")
        except Exception as e:
            print(f"❌ 查询已订阅行情失败: {e}")
    
    def get_qqq_optimal_0dte_options(self, strategy: str = 'balanced', top_n: int = 5) -> dict:
        """
        获取QQQ最优末日期权（重构版本）
        
        Args:
            strategy: 策略类型 ('liquidity', 'balanced', 'value')
            top_n: 返回最优期权数量
            
        Returns:
            dict: 包含Call和Put的最优期权列表
        """
        try:
            from datetime import datetime
            from ..services.option_analyzer import OptionAnalyzer
            from ..config.option_config import OptionStrategy, OPTION_CONFIG
            from ..models.option_models import OptionFilter
            from ..utils.data_validator import DataValidator
            
            print(f"🔍 开始获取QQQ末日期权，策略: {strategy}")
            
            # 数据验证
            validator = DataValidator()
            if not validator.validate_strategy(strategy):
                return {'calls': [], 'puts': [], 'error': f'无效的策略: {strategy}'}
            
            if not validator.validate_top_n(top_n):
                return {'calls': [], 'puts': [], 'error': f'无效的top_n值: {top_n}'}
            
            # 获取QQQ当前价格
            qqq_brief = self.quote_client.get_briefs(['QQQ'])
            if not qqq_brief or len(qqq_brief) == 0:
                return {'calls': [], 'puts': [], 'error': '无法获取QQQ当前价格'}
            
            current_price = qqq_brief[0].latest_price
            if not validator.validate_price(current_price):
                return {'calls': [], 'puts': [], 'error': f'无效的QQQ价格: {current_price}'}
            
            print(f"📊 QQQ当前价格: ${current_price:.2f}")
            
            # 获取今日到期的期权链
            today = datetime.now().strftime('%Y-%m-%d')
            print("🔍 获取今日到期期权链...")
            option_chains = self.quote_client.get_option_chain('QQQ', expiry=today)
            
            # 初始化分析器
            analyzer = OptionAnalyzer(OPTION_CONFIG)
            
            # 创建筛选条件
            option_filter = OptionFilter(
                min_volume=OPTION_CONFIG.MIN_VOLUME_THRESHOLD,
                min_open_interest=OPTION_CONFIG.MIN_OPEN_INTEREST_THRESHOLD,
                max_spread_percentage=OPTION_CONFIG.MAX_SPREAD_PERCENTAGE
            )
            
            # 执行分析
            strategy_enum = OptionStrategy(strategy)
            result = analyzer.analyze_options(
                option_chains=option_chains,
                current_price=current_price,
                strategy=strategy_enum,
                top_n=top_n,
                option_filter=option_filter
            )
            
            print(f"🎯 最优期权筛选完成: {len(result.calls)} Call, {len(result.puts)} Put")
            return result.to_dict()
            
        except Exception as e:
            print(f"❌ 获取QQQ最优末日期权失败: {e}")
            import traceback
            traceback.print_exc()
            return {'calls': [], 'puts': [], 'error': str(e)}
    
 
