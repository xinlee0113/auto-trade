#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据验证工具
"""

import logging
from typing import List, Optional, Any
import pandas as pd

from ..config.option_config import OptionConstants

logger = logging.getLogger(__name__)


class DataValidator:
    """数据验证器"""
    
    def validate_dataframe(self, df: pd.DataFrame) -> bool:
        """
        验证DataFrame的有效性
        
        Args:
            df: 要验证的DataFrame
            
        Returns:
            bool: 验证是否通过
        """
        try:
            if df is None or df.empty:
                logger.warning("DataFrame为空")
                return False
            
            # 检查必需字段
            required_fields = ['symbol', 'strike', 'put_call']
            missing_fields = [field for field in required_fields if field not in df.columns]
            if missing_fields:
                logger.warning(f"缺少必需字段: {missing_fields}")
                return False
            
            # 检查数据类型
            if not self._validate_data_types(df):
                return False
            
            logger.info(f"DataFrame验证通过，包含 {len(df)} 行数据")
            return True
            
        except Exception as e:
            logger.error(f"DataFrame验证失败: {e}")
            return False
    
    def _validate_data_types(self, df: pd.DataFrame) -> bool:
        """验证数据类型"""
        try:
            # 验证symbol字段
            if not df['symbol'].dtype == 'object':
                logger.warning("symbol字段类型不正确")
                return False
            
            # 验证put_call字段值
            valid_rights = {OptionConstants.CALL, OptionConstants.PUT}
            invalid_rights = set(df['put_call'].unique()) - valid_rights
            if invalid_rights:
                logger.warning(f"无效的期权类型: {invalid_rights}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"数据类型验证失败: {e}")
            return False
    
    def validate_price(self, price: float) -> bool:
        """验证价格有效性"""
        return isinstance(price, (int, float)) and price > 0
    
    def validate_strategy(self, strategy: str) -> bool:
        """验证策略有效性"""
        from ..config.option_config import OptionStrategy
        valid_strategies = [s.value for s in OptionStrategy]
        return strategy in valid_strategies
    
    def validate_top_n(self, top_n: int) -> bool:
        """验证返回数量有效性"""
        return isinstance(top_n, int) and 1 <= top_n <= 20
    
    def sanitize_symbol_list(self, symbols: List[str], max_count: int) -> List[str]:
        """
        清理和限制symbol列表
        
        Args:
            symbols: 原始symbol列表
            max_count: 最大数量
            
        Returns:
            List[str]: 清理后的symbol列表
        """
        if not symbols:
            return []
        
        # 去重并限制数量
        unique_symbols = list(dict.fromkeys(symbols))  # 保持顺序的去重
        limited_symbols = unique_symbols[:max_count]
        
        if len(unique_symbols) > max_count:
            logger.warning(f"Symbol数量超限，从 {len(unique_symbols)} 缩减到 {max_count}")
        
        return limited_symbols
    
    def validate_option_data(self, option_data: dict) -> bool:
        """
        验证期权数据的完整性
        
        Args:
            option_data: 期权数据字典
            
        Returns:
            bool: 验证是否通过
        """
        try:
            required_fields = ['symbol', 'strike', 'right', 'latest_price']
            
            for field in required_fields:
                if field not in option_data:
                    logger.warning(f"期权数据缺少字段: {field}")
                    return False
                
                if option_data[field] is None:
                    logger.warning(f"期权数据字段为空: {field}")
                    return False
            
            # 验证数值字段
            numeric_fields = ['strike', 'latest_price', 'bid', 'ask', 'volume', 'open_interest']
            for field in numeric_fields:
                if field in option_data:
                    value = option_data[field]
                    if not isinstance(value, (int, float)) or value < 0:
                        logger.warning(f"期权数据字段值无效: {field}={value}")
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"期权数据验证失败: {e}")
            return False
