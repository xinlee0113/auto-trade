# This is a sample Python script.
import time
from tigeropen.push.pb.QuoteDepthData_pb2 import QuoteDepthData
from tigeropen.push.pb.QuoteBasicData_pb2 import QuoteBasicData
from tigeropen.push.pb.QuoteBBOData_pb2 import QuoteBBOData

from src.api.broker_tiger_api import BrokerTigerAPI


def on_quote_depth_changed(frame: QuoteDepthData):
    """深度行情变化回调函数"""
    print(f'📊 深度行情变化: {frame.symbol}')
    print(f'   时间戳: {frame.timestamp}')
    
    # 打印买盘信息（前5档）
    if hasattr(frame, 'bid') and frame.bid:
        print("   买盘:")
        for i in range(min(5, len(frame.bid.price))):
            print(f"     档位{i+1}: 价格=${frame.bid.price[i]:.2f}, 数量={frame.bid.volume[i]}, 订单数={frame.bid.orderCount[i]}")
    
    # 打印卖盘信息（前5档）
    if hasattr(frame, 'ask') and frame.ask:
        print("   卖盘:")
        for i in range(min(5, len(frame.ask.price))):
            print(f"     档位{i+1}: 价格=${frame.ask.price[i]:.2f}, 数量={frame.ask.volume[i]}, 订单数={frame.ask.orderCount[i]}")
    
    print("-" * 50)


def on_quote_changed(frame: QuoteBasicData):
    """基本行情变化回调函数"""
    print(f'📈 基本行情变化: {frame.symbol}')
    print(f'   最新价: ${frame.latestPrice:.2f}')
    print(f'   涨跌幅: {((frame.latestPrice - frame.preClose) / frame.preClose * 100):.2f}%')
    print(f'   成交量: {frame.volume:,}')
    print(f'   时间: {frame.latestTime}')
    print("-" * 30)


def on_quote_bbo_changed(frame: QuoteBBOData):
    """最优报价变化回调函数"""
    print(f'💰 最优报价变化: {frame.symbol}')
    print(f'   买价: ${frame.bidPrice:.2f} (数量: {frame.bidSize:,})')
    print(f'   卖价: ${frame.askPrice:.2f} (数量: {frame.askSize:,})')
    print("-" * 30)


print("=== main.py 脚本开始执行 ===")

if __name__ == '__main__':
    print("=== 进入主程序逻辑 ===")
    try:
        print("🚀 启动老虎证券实时行情监听...")
        
        # 初始化API客户端
        tiger_api = BrokerTigerAPI()
        
        # 定义要监听的股票代码
        # 美股代码（基本行情权限）
        us_symbols = ['QQQ', 'AAPL', 'NVDA']
        # 港股代码（Lv2权限，支持深度行情）
        hk_symbols = ['00700', '00981', '03690']
        
        # 注册深度行情监听器（港股有Lv2权限）
        print(f"📊 注册深度行情监听器，监听港股: {hk_symbols}")
        tiger_api.register_quote_depth_changed_listener(
            listener=on_quote_depth_changed,
            symbols=hk_symbols
        )
        
        # 注册基本行情监听器（美股+港股）
        all_symbols = us_symbols + hk_symbols
        print(f"📈 注册基本行情监听器，监听股票: {all_symbols}")
        tiger_api.register_quote_changed_listener(
            listener=on_quote_changed,
            symbols=all_symbols
        )
        
        # 注册最优报价监听器（美股+港股）
        print(f"💰 注册最优报价监听器，监听股票: {all_symbols}")
        tiger_api.register_quote_bbo_changed_listener(
            listener=on_quote_bbo_changed,
            symbols=all_symbols
        )
        
        # 查询已订阅的行情
        tiger_api.query_subscribed_quotes()
        
        print("✅ 行情监听已启动，等待实时数据...")
        print("按 Ctrl+C 停止监听")
        
        # 保持程序运行，监听实时数据
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 用户中断，正在停止监听...")
        
    except Exception as e:
        print(f"❌ 程序运行出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理资源
        try:
            tiger_api.disconnect_push_client()
            print("✅ 推送连接已断开")
        except:
            pass
        print("👋 程序已退出")
