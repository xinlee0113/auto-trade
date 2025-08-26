#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
期权分析服务
"""

import logging
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import pandas as pd

from ..config.option_config import OptionConfig, OptionStrategy, OptionConstants
from ..models.option_models import OptionData, OptionAnalysisResult, ScoreBreakdown, OptionFilter
from ..utils.option_calculator import OptionCalculator
from ..utils.data_validator import DataValidator
from ..utils.exception_handler import exception_handler, OptionAnalysisException, DataValidationException
from ..utils.cache_manager import cache_result, monitor_performance
from ..utils.logger_config import setup_option_logger

logger = setup_option_logger()


class OptionAnalyzer:
    """期权分析器"""
    
    def __init__(self, config: Optional[OptionConfig] = None):
        self.config = config or OptionConfig()
        self.calculator = OptionCalculator(self.config)
        self.validator = DataValidator()
    
    @monitor_performance
    @exception_handler(logger, default_return=None)
    def analyze_options(
        self, 
        option_chains: pd.DataFrame,
        current_price: float,
        strategy: OptionStrategy = OptionStrategy.BALANCED,
        top_n: int = 5,
        option_filter: Optional[OptionFilter] = None
    ) -> OptionAnalysisResult:
        """
        分析期权并返回最优选择
        
        Args:
            option_chains: 期权链数据
            current_price: 标的当前价格
            strategy: 分析策略
            top_n: 返回最优期权数量
            option_filter: 筛选条件
            
        Returns:
            OptionAnalysisResult: 分析结果
        """
        try:
            logger.info(f"开始期权分析，策略: {strategy.value}, 当前价格: ${current_price:.2f}")
            
            # 数据验证
            if not self.validator.validate_dataframe(option_chains):
                raise DataValidationException("期权链数据验证失败")
            
            # 数据预处理
            processed_data = self._preprocess_data(option_chains, current_price)
            if not processed_data:
                return OptionAnalysisResult(
                    calls=[], puts=[], strategy=strategy.value,
                    current_price=current_price, total_contracts=0,
                    price_range="", timestamp=datetime.now().isoformat(),
                    message="没有找到符合条件的期权"
                )
            
            # 应用筛选条件
            if option_filter:
                processed_data = option_filter.apply(processed_data)
            
            # 分离Call和Put
            calls, puts = self._separate_options(processed_data)
            
            # 评分和排序
            optimal_calls = self._evaluate_and_rank(calls, strategy, current_price, top_n)
            optimal_puts = self._evaluate_and_rank(puts, strategy, current_price, top_n)
            
            # 计算价格区间
            price_range = self._calculate_price_range(current_price)
            
            logger.info(f"分析完成: {len(optimal_calls)} Call, {len(optimal_puts)} Put")
            
            return OptionAnalysisResult(
                calls=optimal_calls,
                puts=optimal_puts,
                strategy=strategy.value,
                current_price=current_price,
                total_contracts=len(processed_data),
                price_range=price_range,
                timestamp=datetime.now().isoformat()
            )
            
        except Exception as e:
            logger.error(f"期权分析失败: {e}", exc_info=True)
            return OptionAnalysisResult(
                calls=[], puts=[], strategy=strategy.value,
                current_price=current_price, total_contracts=0,
                price_range="", timestamp=datetime.now().isoformat(),
                error=str(e)
            )
    
    def _preprocess_data(self, option_chains: pd.DataFrame, current_price: float) -> List[OptionData]:
        """预处理期权数据"""
        try:
            # 转换strike为数值类型
            option_chains['strike'] = pd.to_numeric(option_chains['strike'], errors='coerce')
            
            # 筛选价格区间
            price_range = current_price * self.config.DEFAULT_PRICE_RANGE_PERCENT
            min_strike = current_price - price_range
            max_strike = current_price + price_range
            
            filtered_chains = option_chains[
                (option_chains['strike'] >= min_strike) & 
                (option_chains['strike'] <= max_strike)
            ].dropna(subset=['strike'])
            
            logger.info(f"价格区间筛选: ${min_strike:.2f} - ${max_strike:.2f}, "
                       f"筛选后: {len(filtered_chains)} 个期权")
            
            # 转换为OptionData对象
            options_data = []
            for _, row in filtered_chains.iterrows():
                try:
                    option_data = self._row_to_option_data(row, current_price)
                    if option_data:
                        options_data.append(option_data)
                except Exception as e:
                    logger.warning(f"处理期权数据失败: {e}")
                    continue
            
            return options_data
            
        except Exception as e:
            logger.error(f"数据预处理失败: {e}")
            return []
    
    def _row_to_option_data(self, row: pd.Series, current_price: float) -> Optional[OptionData]:
        """将DataFrame行转换为OptionData对象"""
        try:
            # 使用字段映射获取数据
            field_map = OptionConstants.FIELD_MAPPINGS
            
            # 🔥 专业价格获取逻辑：交易员级别的价格层级
            raw_latest_price = float(row.get(field_map['latest_price'], 0))
            bid_price = float(row.get(field_map['bid'], 0))
            ask_price = float(row.get(field_map['ask'], 0))
            
            # 专业级价格优先级: Last Trade > Mid Price > Ask (保守估计)
            if raw_latest_price > 0:
                effective_latest_price = raw_latest_price  # 优先使用真实成交价
            elif bid_price > 0 and ask_price > 0:
                effective_latest_price = (bid_price + ask_price) / 2  # Mid Price
            elif ask_price > 0:
                effective_latest_price = ask_price  # 保守估计
            else:
                effective_latest_price = 0  # 无有效价格
            
            option_data = OptionData(
                symbol=row.get('symbol', ''),
                strike=float(row.get('strike', 0)),
                right=row.get(field_map['right'], ''),
                expiry=row.get('expiry', ''),
                latest_price=effective_latest_price,
                bid=bid_price,
                ask=ask_price,
                volume=int(row.get(field_map['volume'], 0)),
                open_interest=int(row.get(field_map['open_interest'], 0)),
                # 🔥 修复Greeks逻辑缺陷：0是合法值，只有缺失才估算
                delta=self._get_safe_greeks_value(
                    row, field_map['delta'], 
                    lambda: self.calculator.estimate_delta(current_price, float(row.get('strike', 0)), row.get(field_map['right'], ''))
                ),
                gamma=self._get_safe_greeks_value(row, field_map['gamma'], lambda: self.config.DEFAULT_GAMMA),
                theta=self._get_safe_greeks_value(row, field_map['theta'], lambda: self.config.DEFAULT_THETA),
                vega=self._get_safe_greeks_value(row, field_map['vega'], lambda: self.config.DEFAULT_VEGA),
                implied_vol=float(row.get(field_map['implied_vol'], 0)) or self.config.DEFAULT_IMPLIED_VOL
            )
            
            # 计算衍生字段
            option_data.calculate_intrinsic_value(current_price)
            option_data.calculate_moneyness(current_price)
            
            # 🔥 专业级数据验证和0DTE风险检测
            if not self._validate_option_data(option_data, current_price):
                logger.warning(f"期权数据验证失败: {option_data.symbol}")
                return None
            
            return option_data
            
        except Exception as e:
            logger.warning(f"转换期权数据失败: {e}")
            return None
    
    def _separate_options(self, options_data: List[OptionData]) -> Tuple[List[OptionData], List[OptionData]]:
        """分离Call和Put期权"""
        calls = [opt for opt in options_data if opt.right.upper() == OptionConstants.CALL]
        puts = [opt for opt in options_data if opt.right.upper() == OptionConstants.PUT]
        return calls, puts
    
    def _evaluate_and_rank(
        self, 
        options: List[OptionData], 
        strategy: OptionStrategy,
        current_price: float,
        top_n: int
    ) -> List[OptionData]:
        """评估期权并排序"""
        if not options:
            return []
        
        try:
            # 计算评分
            for option in options:
                option.score = self.calculator.calculate_option_score(option, strategy, current_price)
                option.score_details = self.calculator.get_score_breakdown(option, strategy).to_dict()
            
            # 按评分排序
            sorted_options = sorted(options, key=lambda x: x.score, reverse=True)
            
            # 添加排名
            for i, option in enumerate(sorted_options[:top_n]):
                option.rank = i + 1
            
            return sorted_options[:top_n]
            
        except Exception as e:
            logger.error(f"期权评估失败: {e}")
            return options[:top_n]
    
    def _get_safe_greeks_value(self, row: pd.Series, field_name: str, default_func) -> float:
        """安全获取Greeks值：区分缺失数据和0值"""
        try:
            # 检查字段是否存在且不为NaN
            if field_name in row and pd.notna(row[field_name]):
                value = float(row[field_name])
                # 0是合法的Greeks值，直接返回
                return value
            else:
                # 字段缺失或为NaN时才使用默认值
                return default_func()
        except (ValueError, TypeError):
            return default_func()
    
    def _validate_option_data(self, option: OptionData, current_price: float) -> bool:
        """专业级期权数据验证"""
        try:
            # 基础数据验证
            if option.strike <= 0 or option.latest_price < 0:
                return False
            
            # Greeks合理性检验
            if not self._validate_greeks_sanity(option, current_price):
                return False
            
            # 价差合理性检验  
            if option.bid > 0 and option.ask > 0:
                if option.ask <= option.bid:  # 买卖价倒挂
                    return False
                if (option.ask - option.bid) / option.ask > 0.5:  # 价差过大(>50%)
                    logger.warning(f"期权价差过大: {option.symbol}, 价差比例: {(option.ask - option.bid) / option.ask:.2%}")
            
            # 🔥 0DTE特殊风险检测
            if self._is_high_gamma_risk(option, current_price):
                logger.warning(f"检测到高Gamma风险: {option.symbol}, Gamma: {option.gamma:.3f}")
            
            return True
            
        except Exception as e:
            logger.error(f"期权数据验证异常: {e}")
            return False
    
    def _validate_greeks_sanity(self, option: OptionData, current_price: float) -> bool:
        """Greeks数据合理性检验"""
        try:
            # Delta范围检验
            if option.right.upper() == 'CALL':
                if not (0 <= option.delta <= 1):
                    logger.warning(f"Call Delta异常: {option.symbol}, Delta: {option.delta}")
                    return False
            else:  # PUT
                if not (-1 <= option.delta <= 0):
                    logger.warning(f"Put Delta异常: {option.symbol}, Delta: {option.delta}")
                    return False
            
            # Gamma合理性(总是非负)
            if option.gamma < 0:
                logger.warning(f"Gamma为负值: {option.symbol}, Gamma: {option.gamma}")
                return False
            
            # 🔥 修复Theta验证逻辑：Call和Put分别验证
            if option.right.upper() == 'CALL':
                # Call期权Theta应该总是负值
                if option.theta > 0:
                    logger.warning(f"Call Theta异常为正: {option.symbol}, Theta: {option.theta}")
                    return False
            else:  # PUT
                # Put期权可能有正Theta (深度ITM时)
                if option.theta > 0.1:  # 允许轻微正值
                    logger.warning(f"Put Theta异常偏高: {option.symbol}, Theta: {option.theta}")
            
            # IV合理性检验(0.05-2.0之间) - 但对0DTE期权放宽限制
            if not (0.01 <= option.implied_vol <= 5.0):  # 0DTE可能出现极端IV
                logger.warning(f"IV异常: {option.symbol}, IV: {option.implied_vol}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Greeks验证异常: {e}")
            return False
    
    def _is_high_gamma_risk(self, option: OptionData, current_price: float) -> bool:
        """检测0DTE高Gamma风险"""
        try:
            # 🔥 基于QQQ期权实证数据的Gamma风险阈值
            moneyness = abs(option.strike - current_price) / current_price
            
            # 基于QQQ期权历史数据的动态阈值
            # ATM期权Gamma通常0.01-0.05，0DTE时可达0.2+
            atm_threshold = 0.05   # ATM Gamma基准
            extreme_threshold = 0.15  # 极端Gamma阈值
            
            # ATM附近(±1%)的Pin Risk检测
            if moneyness <= 0.01 and option.gamma > atm_threshold:
                return True
            
            # 任何期权Gamma超过极端阈值
            if option.gamma > extreme_threshold:
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Gamma风险检测异常: {e}")
            return False

    def _calculate_price_range(self, current_price: float) -> str:
        """计算价格区间字符串"""
        price_range = current_price * self.config.DEFAULT_PRICE_RANGE_PERCENT
        min_strike = current_price - price_range
        max_strike = current_price + price_range
        return f"${min_strike:.2f} - ${max_strike:.2f}"
