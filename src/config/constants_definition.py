"""
常量定义 - 系统常量和业务参数定义
"""

class ConstantsDefinition:
    """
    常量定义类
    
    职责：
    - 业务常量定义
    - 计算参数设置
    - 枚举类型定义
    - 系统配置常量
    
    原则：
    - 集中管理常量
    - 类型安全定义
    - 业务语义清晰
    - 可维护性设计
    """
    
    # 交易常量
    TRADING_CONSTANTS = {
        'EMA_SHORT_PERIOD': 3,
        'EMA_LONG_PERIOD': 8,
        'MOMENTUM_PERIOD': 10,
        'VOLUME_PERIOD': 20,
        'VOLATILITY_THRESHOLD': 0.02,
        'MOMENTUM_THRESHOLD': 0.01,
        'VOLUME_SPIKE_THRESHOLD': 2.0,
    }
    
    # 风险阈值
    RISK_THRESHOLDS = {
        'MAX_POSITION_SIZE': 100000,
        'MAX_DAILY_LOSS': 5000,
        'MAX_PORTFOLIO_DELTA': 1000,
        'VAR_CONFIDENCE_LEVEL': 0.95,
        'CONCENTRATION_LIMIT': 0.3,
    }
    
    # API限制
    API_LIMITS = {
        'MAX_CALLS_PER_MINUTE': 600,
        'MAX_CALLS_PER_SECOND': 10,
        'REQUEST_TIMEOUT': 30,
        'RETRY_MAX_ATTEMPTS': 3,
        'RETRY_DELAY': 1.0,
    }
    
    # 计算参数
    CALCULATION_PARAMS = {
        'RISK_FREE_RATE': 0.05,
        'DAYS_PER_YEAR': 365,
        'TRADING_DAYS_PER_YEAR': 252,
        'BLACK_SCHOLES_ITERATIONS': 100,
        'NUMERICAL_PRECISION': 1e-6,
    }
