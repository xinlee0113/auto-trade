#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
短线技术指标模块演示
展示EMA3/8、动量、成交量指标的实时计算
"""

import sys
import os
import time
import numpy as np
from datetime import datetime, timedelta

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.utils.technical_indicators import create_technical_indicators
from src.config.trading_config import TradingConstants


def simulate_market_scenario():
    """模拟市场场景"""
    print("🚀 短线技术指标实时演示")
    print("=" * 80)
    
    # 创建技术指标计算器
    indicator = create_technical_indicators()
    
    # 模拟场景1：横盘整理
    print("\n📊 场景1: 市场横盘整理")
    print("-" * 50)
    
    base_price = 100.0
    for i in range(30):
        price = base_price + np.sin(i * 0.1) * 0.3 + np.random.normal(0, 0.1)
        volume = 1000 + int(np.random.normal(0, 50))
        timestamp = datetime.now() + timedelta(seconds=i)
        
        indicator.update_market_data(price, volume, timestamp)
        
        if i % 10 == 9:  # 每10秒显示一次
            show_indicators(indicator, f"横盘 {i+1}s")
    
    # 模拟场景2：突破上涨
    print("\n📈 场景2: 突破上涨")
    print("-" * 50)
    
    current_price = base_price
    for i in range(30, 60):
        current_price += 0.05 + np.random.normal(0, 0.02)  # 持续上涨
        volume = 1500 + int(np.random.normal(200, 100))  # 成交量增加
        timestamp = datetime.now() + timedelta(seconds=i)
        
        indicator.update_market_data(current_price, volume, timestamp)
        
        if i % 10 == 9:
            show_indicators(indicator, f"上涨 {i+1}s")
    
    # 模拟场景3：高位回调
    print("\n📉 场景3: 高位回调")
    print("-" * 50)
    
    for i in range(60, 90):
        current_price -= 0.03 + np.random.normal(0, 0.02)  # 回调下跌
        volume = 1200 + int(np.random.normal(100, 80))
        timestamp = datetime.now() + timedelta(seconds=i)
        
        indicator.update_market_data(current_price, volume, timestamp)
        
        if i % 10 == 9:
            show_indicators(indicator, f"回调 {i+1}s")
    
    # 最终统计
    print("\n📊 最终统计信息")
    print("=" * 80)
    
    stats = indicator.get_statistics()
    print(f"计算次数: {stats['calculation_count']}")
    print(f"数据点数: {stats['data_points']}")
    print(f"EMA历史: {stats['ema_history_count']}")
    print(f"动量历史: {stats['momentum_history_count']}")
    print(f"成交量历史: {stats['volume_history_count']}")
    print(f"信号历史: {stats['signal_history_count']}")
    
    # 最终交易信号
    signal_type, strength, confidence = indicator.get_trading_signal_strength()
    print(f"\n🎯 最终交易信号:")
    print(f"   信号类型: {signal_type}")
    print(f"   信号强度: {strength:.3f}")
    print(f"   信号置信度: {confidence:.3f}")
    
    return indicator


def show_indicators(indicator, stage):
    """显示技术指标状态"""
    indicators = indicator.get_latest_indicators()
    signal_type, strength, confidence = indicator.get_trading_signal_strength()
    
    print(f"\n🔍 {stage}:")
    
    # EMA指标
    if "ema" in indicators:
        ema = indicators["ema"]
        print(f"  📈 EMA3: {ema['ema3']:.3f} | EMA8: {ema['ema8']:.3f}")
        print(f"      穿越: {ema['cross_signal']} | 强度: {ema['cross_strength']:.4f}")
        print(f"      差值: {ema['divergence']:.4f}")
    
    # 动量指标
    if "momentum" in indicators:
        momentum = indicators["momentum"]
        print(f"  ⚡ 动量10s: {momentum['momentum_10s']:.4f}")
        print(f"      动量30s: {momentum['momentum_30s']:.4f}")
        print(f"      动量1m: {momentum['momentum_1m']:.4f}")
        print(f"      方向: {momentum['direction']} | 一致性: {momentum['consistency']}")
    
    # 成交量指标
    if "volume" in indicators:
        volume = indicators["volume"]
        print(f"  📊 成交量比: {volume['volume_ratio']:.2f}")
        print(f"      突增: {volume['volume_spike']}")
        print(f"      资金流向: {volume['flow_pressure']}")
    
    # 综合信号
    print(f"  🎯 交易信号: {signal_type} | 强度: {strength:.3f} | 置信度: {confidence:.3f}")


def test_ema_cross_scenario():
    """测试EMA穿越场景"""
    print("\n🔄 EMA穿越专项测试")
    print("=" * 80)
    
    indicator = create_technical_indicators()
    
    # 制造EMA死叉场景
    print("\n📉 制造EMA死叉场景")
    base_price = 100.0
    
    # 先上涨，让EMA3 > EMA8
    for i in range(20):
        price = base_price + i * 0.1
        indicator.update_market_data(price, 1000)
        time.sleep(0.01)
    
    print(f"上涨后 - EMA3: {indicator.current_ema3:.3f}, EMA8: {indicator.current_ema8:.3f}")
    
    # 然后快速下跌，制造死叉
    for i in range(20, 40):
        price = base_price + 2.0 - (i - 19) * 0.15  # 快速下跌
        indicator.update_market_data(price, 1500)
        
        if len(indicator.ema_history) > 0:
            latest_ema = indicator.ema_history[-1]
            if latest_ema.cross_signal == "bearish":
                print(f"🔄 检测到死叉! 时间点: {i}s")
                print(f"   EMA3: {latest_ema.ema3:.3f}")
                print(f"   EMA8: {latest_ema.ema8:.3f}")
                print(f"   穿越强度: {latest_ema.cross_strength:.4f}")
                break
        
        time.sleep(0.01)
    
    # 再制造金叉
    print("\n📈 制造EMA金叉场景")
    for i in range(40, 70):
        price = base_price - 1.0 + (i - 39) * 0.12  # 反弹上涨
        indicator.update_market_data(price, 1800)
        
        if len(indicator.ema_history) > 0:
            latest_ema = indicator.ema_history[-1]
            if latest_ema.cross_signal == "bullish":
                print(f"🔄 检测到金叉! 时间点: {i}s")
                print(f"   EMA3: {latest_ema.ema3:.3f}")
                print(f"   EMA8: {latest_ema.ema8:.3f}")
                print(f"   穿越强度: {latest_ema.cross_strength:.4f}")
                break
        
        time.sleep(0.01)


def test_volume_spike_detection():
    """测试成交量突增检测"""
    print("\n📊 成交量突增检测测试")
    print("=" * 80)
    
    indicator = create_technical_indicators()
    
    # 建立正常成交量基线
    print("建立成交量基线...")
    for i in range(50):
        price = 100.0 + np.random.normal(0, 0.1)
        volume = 1000 + int(np.random.normal(0, 50))
        indicator.update_market_data(price, volume)
        time.sleep(0.001)
    
    # 制造成交量突增
    print("\n制造成交量突增...")
    spike_volumes = [3000, 4000, 3500, 5000, 2800]  # 突增序列
    
    for i, spike_vol in enumerate(spike_volumes):
        price = 100.2 + i * 0.1  # 价格同时上涨
        indicator.update_market_data(price, spike_vol)
        
        if indicator.volume_history:
            latest_vol = indicator.volume_history[-1]
            print(f"  时间点{i+1}: 成交量{spike_vol} | 比率{latest_vol.volume_ratio:.2f} | 突增: {latest_vol.volume_spike}")
        
        time.sleep(0.01)
    
    # 检查信号生成
    signal_type, strength, confidence = indicator.get_trading_signal_strength()
    print(f"\n🎯 成交量突增后信号: {signal_type} | 强度: {strength:.3f}")


def test_momentum_consistency():
    """测试动量一致性"""
    print("\n⚡ 动量一致性测试")
    print("=" * 80)
    
    indicator = create_technical_indicators()
    
    # 制造一致的上涨动量
    print("制造一致上涨动量...")
    base_price = 100.0
    
    for i in range(80):
        # 确保各时间段都有正动量
        price = base_price + (i ** 1.05) * 0.01  # 轻微加速上涨
        volume = 1000 + int(np.random.normal(100, 50))
        timestamp = datetime.now() + timedelta(seconds=i)
        
        indicator.update_market_data(price, volume, timestamp)
        
        if i >= 60 and i % 10 == 0 and indicator.momentum_history:
            latest_momentum = indicator.momentum_history[-1]
            print(f"  {i}s: 10s动量: {latest_momentum.momentum_10s:.4f}")
            print(f"       30s动量: {latest_momentum.momentum_30s:.4f}")
            print(f"       1m动量:  {latest_momentum.momentum_1m:.4f}")
            print(f"       一致性: {latest_momentum.consistency} | 方向: {latest_momentum.direction}")
        
        time.sleep(0.005)
    
    # 最终动量检查
    if indicator.momentum_history:
        final_momentum = indicator.momentum_history[-1]
        print(f"\n🎯 最终动量状态:")
        print(f"   一致性: {final_momentum.consistency}")
        print(f"   方向: {final_momentum.direction}")
        print(f"   加速度: {final_momentum.acceleration:.4f}")


def main():
    """主演示函数"""
    print("🚀 短线技术指标模块演示")
    print("💡 专为0DTE期权高频交易设计")
    print("📊 包含EMA3/8、动量、成交量等核心指标")
    print("=" * 80)
    
    try:
        # 主要市场场景演示
        print("\n🎬 主要演示: 完整市场场景")
        indicator = simulate_market_scenario()
        
        # 等待用户确认
        input("\n按回车键继续EMA穿越测试...")
        
        # EMA穿越专项测试
        test_ema_cross_scenario()
        
        # 等待用户确认
        input("\n按回车键继续成交量突增测试...")
        
        # 成交量突增测试
        test_volume_spike_detection()
        
        # 等待用户确认
        input("\n按回车键继续动量一致性测试...")
        
        # 动量一致性测试
        test_momentum_consistency()
        
        print("\n🎉 技术指标演示完成!")
        print("=" * 80)
        
        print("✅ 演示成果:")
        print("  📈 EMA3/8指标计算正常")
        print("  ⚡ 多时间段动量分析")
        print("  📊 成交量突增检测")
        print("  🔄 EMA穿越信号识别")
        print("  🎯 综合交易信号生成")
        print("  📉 实时风险评估")
        
        print("\n🔧 技术特点:")
        print("  ⚡ 实时计算 (毫秒级)")
        print("  🎯 多层信号确认")
        print("  📊 动量一致性检查")
        print("  🔄 EMA金叉死叉检测")
        print("  📈 成交量异动识别")
        print("  🚨 综合风险评分")
        
        print("\n💡 适用场景:")
        print("  🏃 0DTE期权高频交易")
        print("  ⚡ 秒级交易决策")
        print("  📊 实时市场监控")
        print("  🎯 技术分析辅助")
        
    except KeyboardInterrupt:
        print("\n🛑 演示被用户中断")
    except Exception as e:
        print(f"\n❌ 演示过程出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
