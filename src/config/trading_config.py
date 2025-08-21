"""
实时交易系统配置
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, List


class MarketState(Enum):
    """市场状态枚举"""
    TRENDING_UP = "trending_up"        # 上升趋势
    TRENDING_DOWN = "trending_down"    # 下降趋势
    SIDEWAYS = "sideways"              # 震荡市
    HIGH_VOLATILITY = "high_volatility"  # 高波动
    LOW_VOLATILITY = "low_volatility"    # 低波动
    BREAKOUT = "breakout"              # 突破
    REVERSAL = "reversal"              # 反转


class TradingStrategy(Enum):
    """0DTE期权高频交易策略枚举"""
    GAMMA_SCALPING = "gamma_scalping"        # Gamma剥头皮
    THETA_DECAY = "theta_decay"              # 时间价值衰减策略
    DELTA_NEUTRAL = "delta_neutral"          # Delta中性策略
    VOLATILITY_SPIKE = "volatility_spike"    # 波动率突增策略
    MOMENTUM_OPTIONS = "momentum_options"    # 期权动量策略
    BREAKOUT_STRADDLE = "breakout_straddle" # 突破跨式组合
    QUICK_ARBITRAGE = "quick_arbitrage"     # 快速套利
    IV_CRUSH = "iv_crush"                   # 隐含波动率挤压


class SignalType(Enum):
    """交易信号类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


@dataclass
class TradingConstants:
    """0DTE期权高频交易常量配置"""
    
    # 标的技术指标参数（用于期权定价和方向判断）
    UNDERLYING_EMA_FAST: int = 3          # 标的快速EMA周期
    UNDERLYING_EMA_SLOW: int = 8          # 标的慢速EMA周期
    UNDERLYING_RSI_PERIOD: int = 5        # 标的RSI周期
    VWAP_PERIOD: int = 20                 # VWAP周期
    
    # 期权特有参数
    MIN_TIME_TO_EXPIRY: int = 30          # 最小到期时间(分钟)
    MAX_TIME_TO_EXPIRY: int = 480         # 最大到期时间(分钟，8小时)
    MIN_IMPLIED_VOLATILITY: float = 0.1   # 最小隐含波动率 10%
    MAX_IMPLIED_VOLATILITY: float = 2.0   # 最大隐含波动率 200%
    MIN_DELTA: float = 0.05              # 最小Delta绝对值
    MAX_DELTA: float = 0.95              # 最大Delta绝对值
    
    # Gamma交易阈值
    MIN_GAMMA: float = 0.01              # 最小Gamma值
    GAMMA_SCALP_THRESHOLD: float = 0.02  # Gamma剥头皮阈值
    
    # 期权价格变化阈值
    OPTION_PRICE_CHANGE_THRESHOLD: float = 0.05  # 期权价格变化阈值 5%
    IV_CHANGE_THRESHOLD: float = 0.1     # 隐含波动率变化阈值 10%
    
    # 0DTE期权交易参数（针对高流动性标的优化）
    MAX_OPTION_SPREAD: float = 0.03      # 最大期权买卖价差(美元) - 更严格要求
    MIN_OPTION_VOLUME: int = 50          # 最小期权成交量 - 降低要求
    MIN_OPEN_INTEREST: int = 100         # 最小未平仓合约数
    
    # 快速进出交易参数（期权特化）
    QUICK_ENTRY_CONTRACTS: int = 1       # 快速入场合约数
    GAMMA_STOP_LOSS: float = 0.3         # Gamma交易止损比例 30%
    GAMMA_TAKE_PROFIT: float = 0.5       # Gamma交易止盈比例 50%
    THETA_STOP_LOSS: float = 0.2         # Theta交易止损比例 20%
    THETA_TAKE_PROFIT: float = 0.4       # Theta交易止盈比例 40%
    
    # 0DTE特殊风险控制
    MAX_DAILY_LOSS: float = 0.015        # 日最大亏损 1.5%
    MAX_CONCURRENT_OPTIONS: int = 3      # 最大同时期权持仓数
    MIN_TRADE_INTERVAL: int = 3          # 最小交易间隔(秒)
    MAX_POSITION_TIME: int = 180         # 最大持仓时间(秒) 3分钟
    EXPIRY_CUTOFF_TIME: int = 30         # 到期前停止交易时间(分钟)
    
    # 数据更新频率（期权需要更高频率）
    OPTION_TICK_INTERVAL: float = 0.25   # 期权Tick数据更新间隔(秒)
    GREEKS_UPDATE_INTERVAL: float = 1.0  # Greeks更新间隔(秒)
    RISK_CHECK_INTERVAL: float = 1.0     # 风险检查间隔(秒)
    IV_UPDATE_INTERVAL: float = 2.0      # 隐含波动率更新间隔(秒)


@dataclass
class TradingConfig:
    """交易配置类"""
    
    # 监听股票列表
    watch_symbols: List[str]
    
    # 策略权重配置
    strategy_weights: Dict[TradingStrategy, float]
    
    # 市场状态策略映射
    market_strategy_mapping: Dict[MarketState, List[TradingStrategy]]
    
    # 常量配置
    constants: TradingConstants
    
    # 风险配置
    risk_level: RiskLevel
    max_position_value: float
    
    # 数据更新频率
    data_update_interval: float = 1.0  # 秒


# 0DTE期权交易默认配置
DEFAULT_TRADING_CONFIG = TradingConfig(
    watch_symbols=["QQQ", "SPY", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META"],  # QQQ、SPY和纳斯达克七姐妹
    
    strategy_weights={
        TradingStrategy.GAMMA_SCALPING: 0.25,      # Gamma剥头皮 - 高频主策略
        TradingStrategy.THETA_DECAY: 0.2,          # 时间价值衰减
        TradingStrategy.VOLATILITY_SPIKE: 0.2,     # 波动率突增
        TradingStrategy.MOMENTUM_OPTIONS: 0.15,    # 期权动量
        TradingStrategy.DELTA_NEUTRAL: 0.1,        # Delta中性
        TradingStrategy.QUICK_ARBITRAGE: 0.1       # 快速套利
    },
    
    market_strategy_mapping={
        MarketState.TRENDING_UP: [TradingStrategy.MOMENTUM_OPTIONS, TradingStrategy.GAMMA_SCALPING],
        MarketState.TRENDING_DOWN: [TradingStrategy.MOMENTUM_OPTIONS, TradingStrategy.THETA_DECAY],
        MarketState.SIDEWAYS: [TradingStrategy.THETA_DECAY, TradingStrategy.DELTA_NEUTRAL],
        MarketState.HIGH_VOLATILITY: [TradingStrategy.VOLATILITY_SPIKE, TradingStrategy.GAMMA_SCALPING],
        MarketState.LOW_VOLATILITY: [TradingStrategy.THETA_DECAY, TradingStrategy.IV_CRUSH],
        MarketState.BREAKOUT: [TradingStrategy.MOMENTUM_OPTIONS, TradingStrategy.BREAKOUT_STRADDLE],
        MarketState.REVERSAL: [TradingStrategy.QUICK_ARBITRAGE, TradingStrategy.VOLATILITY_SPIKE]
    },
    
    constants=TradingConstants(),
    risk_level=RiskLevel.HIGH,  # 0DTE期权风险较高
    max_position_value=5000.0,  # 降低单次最大仓位
    data_update_interval=0.25   # 更高频的数据更新
)


# 市场状态描述
MARKET_STATE_DESCRIPTIONS = {
    MarketState.TRENDING_UP: "市场呈上升趋势，价格持续向上",
    MarketState.TRENDING_DOWN: "市场呈下降趋势，价格持续向下", 
    MarketState.SIDEWAYS: "市场横盘整理，价格在区间内波动",
    MarketState.HIGH_VOLATILITY: "市场高波动，价格变化剧烈",
    MarketState.LOW_VOLATILITY: "市场低波动，价格变化平缓",
    MarketState.BREAKOUT: "价格突破关键阻力或支撑位",
    MarketState.REVERSAL: "市场可能发生趋势反转"
}

# 0DTE期权策略描述
STRATEGY_DESCRIPTIONS = {
    TradingStrategy.GAMMA_SCALPING: "利用Gamma效应进行高频剥头皮交易",
    TradingStrategy.THETA_DECAY: "利用时间价值快速衰减获利",
    TradingStrategy.DELTA_NEUTRAL: "保持Delta中性，赚取Gamma和Theta",
    TradingStrategy.VOLATILITY_SPIKE: "捕获隐含波动率突然上升机会",
    TradingStrategy.MOMENTUM_OPTIONS: "跟随标的强劲动量买入期权",
    TradingStrategy.BREAKOUT_STRADDLE: "在关键突破点建立跨式组合",
    TradingStrategy.QUICK_ARBITRAGE: "快速捕获期权定价错误套利机会",
    TradingStrategy.IV_CRUSH: "利用隐含波动率挤压获利"
}
