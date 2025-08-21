#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
QQQ最优末日期权获取演示程序（优化版本）
展示如何使用重构后的BrokerTigerAPI获取和分析最优期权
"""

import time
import logging
from datetime import datetime
from typing import Dict, Any, List

from src.api.broker_tiger_api import BrokerTigerAPI
from src.utils.logger_config import LoggerConfig
from src.utils.cache_manager import cache_manager, performance_monitor
from src.utils.exception_handler import OptionAnalysisException


# 设置日志
logger = LoggerConfig.setup_logger(
    name='demo_qqq_options',
    level=logging.INFO,
    log_file=LoggerConfig.get_default_log_file('demo_qqq_options')
)


class QQQOptionsDemo:
    """QQQ期权演示类"""
    
    def __init__(self):
        """初始化演示"""
        self.api = None
        self.results = {}
    
    def initialize_api(self) -> bool:
        """初始化API连接"""
        try:
            logger.info("🔧 初始化老虎证券API...")
            self.api = BrokerTigerAPI()
            logger.info("✅ API初始化成功")
            return True
        except Exception as e:
            logger.error(f"❌ API初始化失败: {e}")
            return False
    
    def analyze_strategies(self, strategies: List[str], top_n: int = 3) -> Dict[str, Any]:
        """分析多种策略"""
        results = {}
        
        for strategy in strategies:
            logger.info(f"🔍 正在分析 {strategy} 策略...")
            
            try:
                # 解释策略
                self._explain_strategy(strategy)
                
                # 获取最优期权
                result = self.api.get_qqq_optimal_0dte_options(
                    strategy=strategy,
                    top_n=top_n
                )
                
                results[strategy] = result
                
                # 打印分析结果
                self._print_analysis_result(result, strategy)
                
                # 只为平衡策略提供投资建议
                if strategy == 'balanced' and 'error' not in result:
                    self._print_investment_suggestions(result)
                
                # 策略间隔
                time.sleep(1)  # 避免API调用过频
                
            except Exception as e:
                logger.error(f"❌ {strategy}策略分析失败: {e}")
                results[strategy] = {'error': str(e)}
        
        return results
    
    def _explain_strategy(self, strategy: str):
        """解释策略特点"""
        explanations = {
            'liquidity': {
                'name': '流动性优先策略',
                'description': '重点关注成交量和未平仓合约，最小化交易成本',
                'best_for': '大资金量交易，需要快速进出场',
                'weights': '流动性50% + 价差30% + 希腊字母10% + 价值10%'
            },
            'balanced': {
                'name': '平衡策略',
                'description': '综合考虑各项指标，寻求风险收益平衡',
                'best_for': '一般投资者，追求稳健收益',
                'weights': '各项指标均等权重25%'
            },
            'value': {
                'name': '价值导向策略',
                'description': '重点关注期权定价合理性，寻找价值洼地',
                'best_for': '专业投资者，基于量化分析',
                'weights': '价值40% + 希腊字母30% + 流动性20% + 价差10%'
            }
        }
        
        info = explanations.get(strategy, {})
        logger.info(f"💡 {info.get('name', strategy)}:")
        logger.info(f"   策略描述: {info.get('description', '未知策略')}")
        logger.info(f"   适用场景: {info.get('best_for', '通用')}")
        logger.info(f"   权重配置: {info.get('weights', '未知')}")
    
    def _print_analysis_result(self, result: Dict[str, Any], strategy_name: str):
        """打印期权分析结果"""
        print(f"\n{'='*60}")
        print(f"📊 {strategy_name}策略分析结果")
        print(f"{'='*60}")
        
        if 'error' in result and result['error']:
            print(f"❌ 错误: {result['error']}")
            return
        
        if 'message' in result and result['message']:
            print(f"ℹ️ 信息: {result['message']}")
            return
        
        # 基本信息
        print(f"🎯 基本信息:")
        print(f"   QQQ当前价格: ${result['current_price']:.2f}")
        print(f"   总期权合约: {result['total_contracts']} 个")
        print(f"   筛选价格区间: {result['price_range']}")
        print(f"   分析时间: {result['timestamp']}")
        
        # Call期权分析
        self._print_option_details(result.get('calls', []), "📈 最优Call期权 (看涨)")
        
        # Put期权分析
        self._print_option_details(result.get('puts', []), "📉 最优Put期权 (看跌)")
    
    def _print_option_details(self, options: List[Dict], title: str):
        """打印期权详细信息"""
        print(f"\n{title}:")
        
        if not options:
            print("   无符合条件的期权")
            return
        
        for i, option in enumerate(options):
            print(f"   第{i+1}名: {option.get('symbol', 'N/A')}")
            print(f"      执行价: ${option.get('strike', 0):.2f}")
            print(f"      期权价: ${option.get('latest_price', 0):.3f}")
            print(f"      综合评分: {option.get('score', 0):.1f}/100")
            print(f"      成交量: {option.get('volume', 0):,}")
            print(f"      未平仓: {option.get('open_interest', 0):,}")
            print(f"      买卖价差: ${option.get('bid_ask_spread', 0):.3f} ({option.get('spread_percentage', 0)*100:.1f}%)")
            print(f"      Delta: {option.get('delta', 0):.3f}")
            print(f"      Gamma: {option.get('gamma', 0):.4f}")
            print(f"      隐含波动率: {option.get('implied_vol', 0)*100:.1f}%")
            print(f"      内在价值: ${option.get('intrinsic_value', 0):.3f}")
            print(f"      时间价值: ${option.get('time_value', 0):.3f}")
            
            if 'score_details' in option:
                details = option['score_details']
                print(f"      评分明细: 流动性={details.get('liquidity', 0):.1f}, "
                      f"价差={details.get('spread', 0):.1f}, "
                      f"希腊字母={details.get('greeks', 0):.1f}, "
                      f"价值={details.get('value', 0):.1f}")
            print()
    
    def _print_investment_suggestions(self, result: Dict[str, Any]):
        """打印投资建议"""
        print(f"\n💰 投资建议:")
        
        if not result.get('calls') and not result.get('puts'):
            print("   当前无合适的末日期权投资机会")
            return
        
        current_price = result.get('current_price', 0)
        
        # 分析Call期权
        if result.get('calls'):
            best_call = result['calls'][0]
            call_strike = best_call['strike']
            call_delta = best_call['delta']
            call_gamma = best_call['gamma']
            
            print(f"   📈 看涨投资 (Call期权):")
            print(f"      推荐合约: {best_call['symbol']}")
            print(f"      投资逻辑: QQQ需上涨至${call_strike:.2f}以上获利")
            print(f"      风险评估: Delta={call_delta:.3f}, 每$1涨幅期权约涨${call_delta:.3f}")
            print(f"      加速效应: Gamma={call_gamma:.4f}, 接近执行价时收益加速")
            
            if call_delta > 0.6:
                print(f"      ⚠️ 高Delta警告: 期权价格变动幅度较大")
            elif call_delta < 0.2:
                print(f"      ⚠️ 低Delta警告: 需要大幅上涨才能获利")
        
        # 分析Put期权
        if result.get('puts'):
            best_put = result['puts'][0]
            put_strike = best_put['strike']
            put_delta = abs(best_put['delta'])
            put_gamma = best_put['gamma']
            
            print(f"   📉 看跌投资 (Put期权):")
            print(f"      推荐合约: {best_put['symbol']}")
            print(f"      投资逻辑: QQQ需下跌至${put_strike:.2f}以下获利")
            print(f"      风险评估: Delta={put_delta:.3f}, 每$1跌幅期权约涨${put_delta:.3f}")
            print(f"      加速效应: Gamma={put_gamma:.4f}, 接近执行价时收益加速")
            
            if put_delta > 0.6:
                print(f"      ⚠️ 高Delta警告: 期权价格变动幅度较大")
            elif put_delta < 0.2:
                print(f"      ⚠️ 低Delta警告: 需要大幅下跌才能获利")
        
        # 通用风险提示
        print(f"\n⚠️ 末日期权风险提示:")
        print(f"   1. 时间衰减极快: 临近收盘价值快速归零")
        print(f"   2. 流动性风险: 临近到期可能难以平仓")
        print(f"   3. 杠杆风险: 高杠杆放大盈亏")
        print(f"   4. 执行风险: ITM期权可能被自动执行")
        print(f"   5. 建议仓位: 不超过总资金的2-5%")
    
    def print_performance_stats(self):
        """打印性能统计"""
        print(f"\n📊 性能统计:")
        
        # 缓存统计
        cache_stats = cache_manager.get_all_stats()
        if cache_stats:
            print("缓存统计:")
            for name, stats in cache_stats.items():
                print(f"  {name}: 命中率={stats['hit_rate']:.1%}, "
                      f"大小={stats['size']}/{stats['max_size']}")
        
        # 性能统计
        perf_stats = performance_monitor.get_all_stats()
        if perf_stats:
            print("执行时间统计:")
            for func_name, stats in perf_stats.items():
                if stats:
                    print(f"  {func_name}: 平均={stats['avg_time']:.3f}s, "
                          f"最大={stats['max_time']:.3f}s, "
                          f"调用次数={stats['count']}")
    
    def run_demo(self):
        """运行演示"""
        print("🚀 QQQ最优末日期权分析系统（优化版本）")
        print("="*60)
        
        try:
            # 初始化API
            if not self.initialize_api():
                return
            
            # 测试不同策略
            strategies = ['liquidity', 'balanced', 'value']
            
            # 分析策略
            self.results = self.analyze_strategies(strategies, top_n=3)
            
            # 打印性能统计
            self.print_performance_stats()
            
            print(f"\n✅ 分析完成！")
            print(f"📊 建议定期运行此分析以获取最新数据")
            
        except Exception as e:
            logger.error(f"❌ 程序运行出错: {e}", exc_info=True)
            print(f"❌ 程序运行出错: {e}")


def main():
    """主程序"""
    demo = QQQOptionsDemo()
    demo.run_demo()


if __name__ == "__main__":
    main()
