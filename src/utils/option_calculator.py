#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
期权计算工具
"""

import logging
from typing import Dict, Any
from ..config.option_config import OptionConfig, OptionStrategy, OptionConstants
from ..models.option_models import OptionData, ScoreBreakdown

logger = logging.getLogger(__name__)


class OptionCalculator:
    """期权计算器"""
    
    def __init__(self, config: OptionConfig):
        self.config = config
    
    def calculate_option_score(
        self, 
        option: OptionData, 
        strategy: OptionStrategy, 
        current_price: float
    ) -> float:
        """
        计算期权综合评分
        
        Args:
            option: 期权数据
            strategy: 评估策略
            current_price: 标的当前价格
            
        Returns:
            float: 综合评分 (0-100)
        """
        try:
            # 获取策略权重
            weights = self.config.STRATEGY_WEIGHTS.get(strategy, {})
            
            # 计算各维度评分
            liquidity_score = self._calculate_liquidity_score(option)
            spread_score = self._calculate_spread_score(option)
            greeks_score = self._calculate_greeks_score(option, current_price)
            value_score = self._calculate_value_score(option, current_price)
            
            # 加权计算综合评分
            total_score = (
                liquidity_score * weights.get('liquidity', 0) +
                spread_score * weights.get('spread', 0) +
                greeks_score * weights.get('greeks', 0) +
                value_score * weights.get('value', 0)
            )
            
            # 确保评分在有效范围内
            return max(OptionConstants.MIN_SCORE, 
                      min(OptionConstants.MAX_SCORE, total_score))
            
        except Exception as e:
            logger.warning(f"计算期权评分失败: {e}")
            return 0.0
    
    def _calculate_liquidity_score(self, option: OptionData) -> float:
        """计算流动性评分"""
        try:
            volume = option.volume
            open_interest = option.open_interest
            
            # 成交量评分 (权重0.6)
            volume_score = min(OptionConstants.MAX_SCORE, 
                              (volume / OptionConstants.VOLUME_BENCHMARK) * 100) if volume > 0 else 0
            
            # 未平仓评分 (权重0.4)  
            oi_score = min(OptionConstants.MAX_SCORE, 
                          (open_interest / OptionConstants.OPEN_INTEREST_BENCHMARK) * 100) if open_interest > 0 else 0
            
            return volume_score * 0.6 + oi_score * 0.4
            
        except Exception as e:
            logger.warning(f"计算流动性评分失败: {e}")
            return 0.0
    
    def _calculate_spread_score(self, option: OptionData) -> float:
        """计算买卖价差评分"""
        try:
            spread_percentage = option.spread_percentage
            # 价差越小评分越高
            return max(0, (1 - min(spread_percentage, 0.5)) * OptionConstants.MAX_SCORE)
        except Exception as e:
            logger.warning(f"计算价差评分失败: {e}")
            return 0.0
    
    def _calculate_greeks_score(self, option: OptionData, current_price: float) -> float:
        """计算希腊字母评分"""
        try:
            delta = abs(option.delta)
            gamma = option.gamma
            
            # Delta评分：接近0.5的Delta通常更优（ATM附近）
            delta_score = max(0, OptionConstants.MAX_SCORE - 
                             abs(delta - OptionConstants.IDEAL_DELTA) * 200)
            
            # Gamma评分：Gamma越高末日期权收益潜力越大
            gamma_score = min(OptionConstants.MAX_SCORE, 
                             gamma * OptionConstants.GAMMA_MULTIPLIER) if gamma > 0 else 0
            
            return delta_score * 0.5 + gamma_score * 0.5
            
        except Exception as e:
            logger.warning(f"计算希腊字母评分失败: {e}")
            return 0.0
    
    def _calculate_value_score(self, option: OptionData, current_price: float) -> float:
        """计算价值评分 - 专业级IV评分算法"""
        try:
            implied_vol = option.implied_vol
            moneyness = option.moneyness
            time_value = option.time_value
            
            # 🔥 专业级IV评分：基于QQQ期权特性的动态评估
            iv_score = self._calculate_professional_iv_score(implied_vol, moneyness)
            
            # 价值合理性评分：ATM附近期权通常更活跃
            moneyness_score = max(0, OptionConstants.MAX_SCORE - moneyness * 2000)
            
            # 时间价值评分：有适度时间价值但不过高
            tv_score = min(OptionConstants.MAX_SCORE, 
                          time_value * 100) if time_value > 0 else 0
            
            return iv_score * 0.4 + moneyness_score * 0.4 + tv_score * 0.2
            
        except Exception as e:
            logger.warning(f"计算价值评分失败: {e}")
            return 0.0
    
    def _calculate_professional_iv_score(self, implied_vol: float, moneyness: float) -> float:
        """专业级IV评分算法 - 基于波动率微笑曲线"""
        try:
            if implied_vol <= 0:
                return 0.0
            
            # 基于QQQ历史数据的动态IV基准 (考虑波动率微笑)
            # QQQ典型IV范围: 0.12-0.35，ATM通常0.18左右
            base_iv = 0.18 + moneyness * 0.1  # 简化的波动率微笑曲线
            
            # 计算IV偏离程度
            iv_deviation = abs(implied_vol - base_iv)
            
            # 非线性评分系统：适度偏离可接受，极端偏离严重惩罚
            if iv_deviation < 0.05:  # 5%以内 - 正常范围
                return OptionConstants.MAX_SCORE
            elif iv_deviation < 0.10:  # 5%-10% - 可接受范围
                # 线性衰减: 100 → 70
                return 100 - (iv_deviation - 0.05) * 600
            elif iv_deviation < 0.15:  # 10%-15% - 轻度惩罚
                # 加速衰减: 70 → 40
                return 70 - (iv_deviation - 0.10) * 600
            else:  # >15% - 严重惩罚
                # 重度惩罚: 40 → 10
                return max(10, 40 - (iv_deviation - 0.15) * 200)
                
        except Exception as e:
            logger.warning(f"专业IV评分计算失败: {e}")
            return 50.0  # 返回中性评分
    
    def get_score_breakdown(self, option: OptionData, strategy: OptionStrategy) -> ScoreBreakdown:
        """获取评分明细"""
        try:
            return ScoreBreakdown(
                liquidity=self._calculate_liquidity_score(option),
                spread=self._calculate_spread_score(option),
                greeks=self._calculate_greeks_score(option, 0),  # current_price不影响相对评分
                value=self._calculate_value_score(option, 0),
                strategy=strategy.value
            )
        except Exception as e:
            logger.warning(f"获取评分明细失败: {e}")
            return ScoreBreakdown(0, 0, 0, 0, strategy.value)
    
    def estimate_delta(self, current_price: float, strike: float, right: str) -> float:
        """
        简化的Delta估算方法
        基于期权的价值状态（ITM/ATM/OTM）估算Delta
        """
        try:
            moneyness = current_price / strike
            thresholds = self.config.DELTA_THRESHOLDS
            
            if right.upper() == OptionConstants.CALL:
                if moneyness > thresholds['deep_itm']:  # 深度ITM (S/K > 1.05)
                    return 0.8
                elif moneyness > thresholds['light_itm']:  # 浅度ITM (S/K > 1.02)
                    return 0.6
                elif moneyness >= thresholds['atm_lower']:  # ATM (0.98 <= S/K <= 1.02)
                    return 0.5
                elif moneyness >= thresholds['light_otm']:  # 浅度OTM (0.95 <= S/K < 0.98)
                    return 0.3
                else:  # 深度OTM (S/K < 0.95)
                    return 0.1
            else:  # PUT
                if moneyness < (2 - thresholds['deep_itm']):  # 深度ITM (S/K < 0.95)
                    return -0.8
                elif moneyness < (2 - thresholds['light_itm']):  # 浅度ITM (S/K < 0.98)
                    return -0.6
                elif moneyness <= thresholds['atm_upper']:  # ATM (0.98 <= S/K <= 1.02)
                    return -0.5
                elif moneyness <= thresholds['light_otm']:  # 浅度OTM (1.02 < S/K <= 1.05)
                    return -0.3
                else:  # 深度OTM (S/K > 1.05)
                    return -0.1
        except Exception as e:
            logger.warning(f"Delta估算失败: {e}")
            return 0.5 if right.upper() == OptionConstants.CALL else -0.5
