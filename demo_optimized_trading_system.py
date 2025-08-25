#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优化交易系统演示

展示正确的优化策略:
1. 实时推送 + 智能轮询 + 差异化缓存
2. 明确分离整体市场和个股分析
3. 真正的并行API调用，而非减少调用
4. 性能监控和优化效果展示

Author: AI Assistant
Date: 2024-01-22
"""

import sys
import os
import time
from datetime import datetime
from typing import Dict, Any

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath('.')))

from demos.client_config import get_client_config
from tigeropen.quote.quote_client import QuoteClient
from tigeropen.push.push_client import PushClient

from src.data.realtime_data_manager import create_optimized_data_manager, DataSubscription, DataType
from src.services.market_analyzer import MarketAnalyzer
from src.utils.parallel_api_manager import ParallelAPIManager, execute_optimized_tiger_calls
from src.config.trading_config import DEFAULT_TRADING_CONFIG


class OptimizedTradingSystemDemo:
    """优化交易系统演示"""
    
    def __init__(self):
        """初始化演示系统"""
        print("🚀 优化交易系统演示")
        print("=" * 60)
        
        # 1. 初始化API客户端
        print("🔗 初始化Tiger API连接...")
        client_config = get_client_config()
        self.quote_client = QuoteClient(client_config)
        # self.push_client = PushClient(client_config)  # 推送客户端需要额外配置
        self.push_client = None  # 暂时不使用推送
        
        # 2. 配置
        self.config = DEFAULT_TRADING_CONFIG
        self.watch_symbols = ['QQQ', 'SPY', 'AAPL']  # 简化测试
        
        # 3. 初始化核心组件
        self.data_manager = create_optimized_data_manager(
            quote_client=self.quote_client,
            push_client=self.push_client,
            watch_symbols=self.watch_symbols
        )
        
        self.market_analyzer = MarketAnalyzer()
        self.api_manager = ParallelAPIManager(max_workers=4)
        
        print("✅ 系统初始化完成")
        print(f"📊 监控标的: {', '.join(self.watch_symbols)}")
    
    def demo_api_optimization_comparison(self):
        """演示API优化效果对比"""
        print("\n" + "="*60)
        print("📊 API优化效果对比演示")
        print("="*60)
        
        # 1. 传统串行调用
        print("\n1️⃣ 传统串行API调用:")
        start_time = time.time()
        
        try:
            # 模拟传统调用方式
            briefs = self.quote_client.get_briefs(self.watch_symbols)
            vix_data = self.quote_client.get_briefs(['VIX'])
            trade_ticks = self.quote_client.get_trade_ticks([self.watch_symbols[0]])
            from tigeropen.common.consts import Market
            market_status = self.quote_client.get_market_status(Market.US)
            
            serial_time = (time.time() - start_time) * 1000
            print(f"   ⏱️ 串行调用耗时: {serial_time:.1f}ms")
            print(f"   📞 API调用次数: 4次")
            print(f"   📦 获取数据: 价格×{len(self.watch_symbols)}, VIX×1, 成交量×1, 状态×1")
            
        except Exception as e:
            print(f"   ❌ 串行调用失败: {e}")
            serial_time = 999999
        
        # 2. 优化并行调用
        print("\n2️⃣ 优化并行API调用:")
        start_time = time.time()
        
        try:
            result = execute_optimized_tiger_calls(
                quote_client=self.quote_client,
                symbols=self.watch_symbols,
                manager=self.api_manager
            )
            
            parallel_time = (time.time() - start_time) * 1000
            print(f"   ⚡ 并行调用耗时: {parallel_time:.1f}ms")
            print(f"   📞 API调用次数: 4次 (并行执行)")
            print(f"   📦 获取相同数据 + 智能缓存")
            print(f"   🎯 成功率: {result['success']}")
            
            if result['performance']:
                perf = result['performance']
                print(f"   📈 缓存命中率: {perf.get('cache_hit_rate', 0)*100:.1f}%")
                print(f"   🔄 成功率: {perf.get('success_rate', 0)*100:.1f}%")
            
        except Exception as e:
            print(f"   ❌ 并行调用失败: {e}")
            parallel_time = 999999
            result = None
        
        # 3. 性能对比
        print("\n📈 性能对比结果:")
        if serial_time < 999999 and parallel_time < 999999:
            improvement = ((serial_time - parallel_time) / serial_time) * 100
            print(f"   🏃 延迟对比: {serial_time:.1f}ms → {parallel_time:.1f}ms")
            print(f"   🚀 性能提升: {improvement:.1f}%")
            print(f"   🎯 目标达成: {'✅' if parallel_time < 50 else '❌'} (目标<50ms)")
        else:
            print("   ⚠️ 无法比较，存在调用失败")
        
        return result
    
    def demo_market_analysis_separation(self, api_result: Dict[str, Any]):
        """演示市场分析的正确分离"""
        print("\n" + "="*60)
        print("🔍 市场分析层次分离演示")
        print("="*60)
        
        if not api_result or not api_result['success']:
            print("❌ 无法进行分析，API数据获取失败")
            return
        
        try:
            # 1. 准备数据
            print("\n📊 数据准备:")
            
            # VIX数据
            vix_value = 16.5  # 默认值
            if api_result['vix']:
                vix_value = getattr(api_result['vix'], 'latest_price', None) or \
                           getattr(api_result['vix'], 'prev_close', None) or 16.5
            print(f"   🌊 VIX数据: {vix_value:.2f}")
            
            # 市场状态
            market_status = {'is_trading': True, 'status': '交易中'}
            if api_result['market_status']:
                status_info = api_result['market_status']
                market_status = {
                    'is_trading': getattr(status_info, 'trading_status', '') == 'TRADING',
                    'status': getattr(status_info, 'status', '未知')
                }
            print(f"   📈 市场状态: {market_status['status']}")
            
            # 个股数据
            symbol_data = {}
            if api_result['prices']:
                from src.models.trading_models import UnderlyingTickData
                for brief in api_result['prices']:
                    symbol = brief.symbol
                    if symbol in self.watch_symbols:
                        symbol_data[symbol] = UnderlyingTickData(
                            symbol=symbol,
                            timestamp=datetime.now(),
                            price=getattr(brief, 'latest_price', 0.0) or 0.0,
                            volume=0,  # 成交量需要单独获取
                            bid=getattr(brief, 'bid_price', 0.0) or 0.0,
                            ask=getattr(brief, 'ask_price', 0.0) or 0.0
                        )
            print(f"   📊 个股数据: {len(symbol_data)}个标的")
            
            # 2. 分层分析
            print("\n🔍 分层分析结果:")
            
            market_analysis, symbol_analyses = self.market_analyzer.analyze_market_and_symbols(
                vix_value=vix_value,
                market_status=market_status,
                symbol_data=symbol_data
            )
            
            # 整体市场分析
            print(f"\n🌍 整体市场分析:")
            print(f"   📊 市场状态: {market_analysis.state.value}")
            print(f"   🌊 风险评分: {market_analysis.risk_score:.2f}")
            print(f"   ✅ 交易建议: {'建议交易' if market_analysis.trading_recommended else '暂停交易'}")
            print(f"   💭 分析原因: {market_analysis.reason}")
            print(f"   🎯 置信度: {market_analysis.confidence:.2f}")
            
            # 个股分析
            print(f"\n📈 个股趋势分析:")
            for symbol, analysis in symbol_analyses.items():
                print(f"   📊 {symbol}:")
                print(f"      📈 趋势状态: {analysis.trend_state.value}")
                print(f"      📊 成交量状态: {analysis.volume_state.value}")
                print(f"      🚀 动量评分: {analysis.momentum_score:.2f}")
                print(f"      🌊 波动率: {analysis.volatility_score:.2f}")
                print(f"      🎯 置信度: {analysis.confidence:.2f}")
                if analysis.signals:
                    print(f"      🚨 交易信号: {', '.join(analysis.signals)}")
            
            # 3. 综合交易建议
            print(f"\n🎯 综合交易建议:")
            recommendation = self.market_analyzer.get_trading_recommendation(
                market_analysis, symbol_analyses
            )
            
            print(f"   ✅ 总体建议: {'建议交易' if recommendation['recommended'] else '暂停交易'}")
            print(f"   💭 建议原因: {recommendation['reason']}")
            print(f"   🌍 市场环境: {recommendation['market_state']}")
            
            if recommendation['symbol_opportunities']:
                print(f"   🎯 交易机会:")
                for opp in recommendation['symbol_opportunities']:
                    print(f"      📊 {opp['symbol']}: {opp['trend']} - {', '.join(opp['signals'])}")
            else:
                print(f"   📊 暂无明显交易机会")
            
        except Exception as e:
            print(f"❌ 市场分析失败: {e}")
            import traceback
            traceback.print_exc()
    
    def demo_data_management_strategy(self):
        """演示数据管理策略"""
        print("\n" + "="*60)
        print("📡 数据管理策略演示")
        print("="*60)
        
        print("\n🏗️ 数据获取架构:")
        print("   1️⃣ 实时推送数据 (WebSocket):")
        print("      📊 个股价格: 实时推送，0秒缓存")
        print("      📈 成交量: 实时推送，0秒缓存")
        print("      💰 买卖价差: 实时推送，0秒缓存")
        print("      🎯 用途: 交易信号生成")
        
        print("\n   2️⃣ 智能轮询数据 (API + 缓存):")
        print("      🌊 VIX数据: 15秒轮询，15秒缓存")
        print("      📊 市场状态: 5分钟轮询，5分钟缓存")
        print("      🎯 用途: 整体市场风险评估")
        
        print("\n   3️⃣ 并行API调用:")
        print("      🚀 关键数据: 2秒超时，1次重试")
        print("      📊 重要数据: 3秒超时，2次重试")
        print("      🌊 一般数据: 5秒超时，2次重试")
        print("      📈 次要数据: 10秒超时，1次重试")
        
        # 模拟数据管理效果
        print("\n📊 数据管理效果模拟:")
        
        # 缓存效果演示
        cache_scenarios = [
            ("首次调用", 0, 0),
            ("15秒内", 80, 15),
            ("5分钟内", 90, 5),
            ("长期运行", 95, 2)
        ]
        
        for scenario, cache_hit_rate, api_calls in cache_scenarios:
            estimated_time = api_calls * 12 + (100 - cache_hit_rate) * 0.5
            print(f"   📈 {scenario}: 缓存命中率{cache_hit_rate}%, API调用{api_calls}次, 预估延迟{estimated_time:.1f}ms")
    
    def run_complete_demo(self):
        """运行完整演示"""
        print("\n🎬 开始完整优化系统演示")
        print("⏱️ 预计演示时间: 2-3分钟")
        
        try:
            # 1. API优化对比
            api_result = self.demo_api_optimization_comparison()
            
            # 2. 市场分析分离
            self.demo_market_analysis_separation(api_result)
            
            # 3. 数据管理策略
            self.demo_data_management_strategy()
            
            # 4. 总结
            print("\n" + "="*60)
            print("🎉 优化系统演示总结")
            print("="*60)
            
            print("\n✅ 关键优化点:")
            print("   1️⃣ 明确数据分类: 整体市场 vs 个股趋势")
            print("   2️⃣ 差异化获取策略: 推送 + 轮询 + 缓存")
            print("   3️⃣ 真正并行调用: 保持数据完整性")
            print("   4️⃣ 智能错误处理: 分级重试和超时")
            print("   5️⃣ 性能监控: 实时统计和优化")
            
            print("\n🎯 性能指标:")
            if hasattr(self, 'api_manager'):
                stats = self.api_manager.get_performance_stats()
                print(f"   ⚡ 平均延迟: {stats.get('avg_time', 0)*1000:.1f}ms")
                print(f"   📈 成功率: {stats.get('success_rate', 0)*100:.1f}%")
                print(f"   💾 缓存命中率: {stats.get('cache_hit_rate', 0)*100:.1f}%")
            
            print("\n💡 下一步工作:")
            print("   📡 集成WebSocket推送")
            print("   🔧 实盘测试和调优")
            print("   📊 完善性能监控")
            print("   🎯 策略信号优化")
            
        except Exception as e:
            print(f"\n❌ 演示过程中出现错误: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            # 清理资源
            if hasattr(self, 'api_manager'):
                self.api_manager.shutdown()
            print("\n🔚 演示结束，资源已清理")


def main():
    """主函数"""
    try:
        demo = OptimizedTradingSystemDemo()
        demo.run_complete_demo()
        
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断演示")
    except Exception as e:
        print(f"\n❌ 演示失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
