"""
配置层 (Configuration Layer)

职责：
- 配置管理服务
- 参数注入支持
- 环境配置分离
- 系统常量定义

特点：
- 横向支持设计
- 配置驱动架构
- 环境独立性

原则：
- 集中配置管理
- 类型安全配置
- 热更新支持
"""

from .configuration_manager import ConfigurationManager
from .constants_definition import ConstantsDefinition
from .trading_config import (
    TradingConfig,
    TradingConstants,
    DEFAULT_TRADING_CONFIG,
)

__all__ = [
    'ConfigurationManager',
    'ConstantsDefinition', 
    'TradingConfig',
    'TradingConstants',
    'DEFAULT_TRADING_CONFIG',
]
