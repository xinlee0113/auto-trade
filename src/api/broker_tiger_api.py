from tigeropen.common.util.order_utils import order_leg
from tigeropen.push.push_client import PushClient
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

            if not os.path.exists(private_key_path):
                raise FileNotFoundError(f"私钥文件不存在: {private_key_path}")

            # 导入必要的工具函数
            from tigeropen.common.util.signature_utils import read_private_key
            from tigeropen.common.consts import Language

            # 初始化客户端配置
            client_config = TigerOpenClientConfig(
                sandbox_debug=False,  # 生产环境
                props_path=config_path
            )
            client_config.private_key = read_private_key(private_key_path)
            client_config.language = Language.zh_CN
            client_config.timeout = 60

            # 创建客户端实例
            self.trade_client = TradeClient(client_config)
            protocol, host, port = client_config.socket_host_port
            self.push_client = PushClient(host, port, use_ssl=(protocol == 'ssl'))
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
