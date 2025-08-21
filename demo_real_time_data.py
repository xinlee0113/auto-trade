"""
实时市场数据监听器演示
展示如何使用纯推送模式获取0DTE期权高频交易数据

注意：
- 此演示采用纯推送模式，避免API频率限制
- 所有数据通过订阅获取，无主动API调用
- 防止账号因频繁调用API而被冻结
"""

import time
import sys
import os
from datetime import datetime

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.data.real_time_market_data import (
    get_data_manager,
    initialize_market_data,
    shutdown_market_data
)
from src.utils.logger_config import setup_logging


def data_callback(data):
    """数据回调函数"""
    print(f"📊 收到数据: {data.symbol} - 价格: ${data.price:.2f} - 时间: {data.timestamp}")


def option_callback(option_data):
    """期权数据回调函数"""
    print(f"📈 期权数据: {option_data.symbol} - 价格: ${option_data.price:.2f} - Delta: {option_data.delta}")


def main():
    """主函数"""
    # 设置日志
    setup_logging()
    
    print("🚀 启动0DTE期权实时数据监听器演示")
    print("⚠️  注意：采用纯推送模式，避免API频率限制")
    
    try:
        # 初始化数据系统（需要配置文件路径）
        config_path = "config/tiger_openapi_config.properties"
        
        print("🔌 初始化数据连接...")
        if not initialize_market_data(config_path):
            print("❌ 数据系统初始化失败")
            return
        
        # 获取数据管理器
        data_manager = get_data_manager()
        
        # 添加数据回调
        data_manager.add_data_callback(data_callback)
        
        print("✅ 数据系统初始化成功")
        print("📡 开始接收实时数据...")
        print("📝 监听标的:", data_manager.config.watch_symbols)
        print("⏱️  数据更新频率:", data_manager.config.data_update_interval, "秒")
        print("\n--- 实时数据流 ---")
        
        # 运行监听
        start_time = datetime.now()
        while True:
            try:
                # 显示系统状态
                status = data_manager.get_system_status()
                current_time = datetime.now()
                running_time = (current_time - start_time).total_seconds()
                
                if int(running_time) % 30 == 0:  # 每30秒显示一次状态
                    print(f"\n📊 系统状态 (运行 {running_time:.0f} 秒):")
                    print(f"   连接状态: {'✅ 正常' if status.is_connected else '❌ 断开'}")
                    print(f"   数据延迟: {status.latency_ms:.0f} ms")
                    print(f"   错误计数: {status.error_count}")
                    print(f"   市场时段: {status.market_session}")
                
                # 显示最新价格
                for symbol in data_manager.config.watch_symbols:
                    latest_price = data_manager.underlying_listener.get_latest_price(symbol)
                    if latest_price:
                        market_data = data_manager.get_market_data(symbol)
                        if market_data:
                            spread = market_data.ask - market_data.bid
                            print(f"💰 {symbol}: ${latest_price:.2f} (价差: ${spread:.3f})")
                
                time.sleep(5)  # 每5秒更新一次显示
                
            except KeyboardInterrupt:
                print("\n⏹️  收到停止信号...")
                break
            except Exception as e:
                print(f"❌ 运行错误: {e}")
                time.sleep(1)
        
    except Exception as e:
        print(f"❌ 系统错误: {e}")
        
    finally:
        print("🔌 关闭数据连接...")
        shutdown_market_data()
        print("✅ 演示完成")


if __name__ == "__main__":
    print("=" * 60)
    print("🎯 0DTE期权高频交易 - 实时数据监听器")
    print("📡 纯推送模式 - 避免API频率限制")
    print("=" * 60)
    
    main()
