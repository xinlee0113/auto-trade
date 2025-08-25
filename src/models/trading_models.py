"""
实时交易系统数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from decimal import Decimal

from ..config.trading_config import MarketState, TradingStrategy, SignalType, RiskLevel


@dataclass
class MarketData:
    """市场数据模型"""
    symbol: str
    timestamp: datetime
    price: float
    volume: int
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    
    # 技术指标数据
    ma_short: Optional[float] = None
    ma_long: Optional[float] = None
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    bollinger_upper: Optional[float] = None
    bollinger_lower: Optional[float] = None
    volatility: Optional[float] = None
    
    # 计算属性
    @property
    def spread(self) -> float:
        """买卖价差"""
        return self.ask - self.bid
    
    @property
    def spread_percentage(self) -> float:
        """买卖价差百分比"""
        return (self.spread / self.price) * 100 if self.price > 0 else 0.0


@dataclass
class UnderlyingTickData:
    """标的资产Tick数据模型"""
    symbol: str
    timestamp: datetime
    price: float
    volume: int
    bid: float
    ask: float
    bid_size: int = 0
    ask_size: int = 0
    
    @property
    def spread(self) -> float:
        """买卖价差"""
        return self.ask - self.bid


@dataclass
class OptionTickData:
    """期权Tick数据模型"""
    symbol: str
    underlying: str
    strike: float
    expiry: str
    right: str  # 'CALL' or 'PUT'
    timestamp: datetime
    price: float
    volume: int
    bid: float
    ask: float
    bid_size: int = 0
    ask_size: int = 0
    open_interest: int = 0
    
    # 期权Greeks (可选，计算得出)
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    implied_volatility: Optional[float] = None
    
    @property
    def spread(self) -> float:
        """买卖价差"""
        return self.ask - self.bid
    
    @property
    def spread_percentage(self) -> float:
        """买卖价差百分比"""
        return (self.spread / self.price * 100) if self.price > 0 else 0.0
    
    @property
    def is_call(self) -> bool:
        """是否为看涨期权"""
        return self.right.upper() == 'CALL'
    
    @property
    def is_put(self) -> bool:
        """是否为看跌期权"""
        return self.right.upper() == 'PUT'


@dataclass
class TradeExecution:
    """交易执行结果"""
    order_id: str
    symbol: str
    side: str  # 'BUY' or 'SELL'
    quantity: int
    executed_price: float
    executed_time: datetime
    execution_status: str  # 'FILLED', 'PARTIAL', 'REJECTED'
    commission: float = 0.0
    error_message: Optional[str] = None


@dataclass
class PnLMetrics:
    """盈亏指标"""
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    daily_pnl: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    sharpe_ratio: Optional[float] = None


@dataclass
class MarketAnalysis:
    """市场分析结果"""
    symbol: str
    timestamp: datetime
    current_state: MarketState
    confidence: float  # 0-1之间，表示判断的置信度
    
    # 技术指标分析
    trend_direction: str  # "up", "down", "sideways"
    trend_strength: float  # 0-1之间
    volatility_level: float  # 波动率水平
    volume_analysis: str  # "normal", "high", "low"
    
    # 支撑阻力位
    support_level: Optional[float] = None
    resistance_level: Optional[float] = None
    
    # 分析原因
    analysis_reasons: List[str] = field(default_factory=list)


@dataclass
class TradingSignal:
    """交易信号模型"""
    symbol: str
    timestamp: datetime
    signal_type: SignalType
    strategy: TradingStrategy
    price: float
    confidence: float  # 0-1之间，信号强度
    
    # 交易参数
    suggested_quantity: int
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    
    # 信号原因
    reasons: List[str] = field(default_factory=list)
    
    # 风险评估
    risk_level: RiskLevel = RiskLevel.MEDIUM
    risk_reward_ratio: Optional[float] = None


@dataclass
class Position:
    """持仓模型"""
    symbol: str
    quantity: int
    entry_price: float
    entry_time: datetime
    strategy: TradingStrategy = None  # 允许为None以兼容风险管理器
    
    # 新增字段支持风险管理
    position_id: str = ""
    position_type: str = "LONG"  # "LONG" or "SHORT"
    
    # 风险管理
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    
    # 当前状态
    current_price: float = 0.0
    current_value: float = 0.0
    unrealized_pnl: float = 0.0
    
    # Greeks (for options)
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    
    # 市场数据
    bid_ask_spread: Optional[float] = None
    underlying: Optional[str] = None
    
    def __post_init__(self):
        """初始化后处理"""
        if not self.position_id:
            # 自动生成ID
            import uuid
            self.position_id = f"POS_{uuid.uuid4().hex[:8].upper()}"
        
        if self.current_value == 0.0:
            # 自动计算价值
            self.current_value = abs(self.quantity) * self.current_price
    
    def update_current_price(self, price: float):
        """更新当前价格和未实现盈亏"""
        self.current_price = price
        self.unrealized_pnl = (price - self.entry_price) * self.quantity
    
    @property
    def pnl_percentage(self) -> float:
        """盈亏百分比"""
        if self.entry_price > 0:
            return ((self.current_price - self.entry_price) / self.entry_price) * 100
        return 0.0


@dataclass
class Trade:
    """交易记录模型"""
    trade_id: str
    symbol: str
    side: str  # "buy" or "sell"
    quantity: int
    price: float
    timestamp: datetime
    strategy: TradingStrategy
    
    # 交易原因
    entry_reasons: List[str] = field(default_factory=list)
    exit_reasons: List[str] = field(default_factory=list)
    
    # 关联订单
    related_position_id: Optional[str] = None
    
    # 费用
    commission: float = 0.0
    
    @property
    def total_value(self) -> float:
        """交易总价值"""
        return self.quantity * self.price


@dataclass
class RiskMetrics:
    """风险指标模型"""
    timestamp: datetime
    
    # 持仓风险
    total_exposure: float  # 总敞口
    position_concentration: Dict[str, float]  # 持仓集中度
    
    # 盈亏风险
    unrealized_pnl: float
    daily_pnl: float
    max_drawdown: float
    
    # 风险限制
    risk_utilization: float  # 风险额度使用率
    leverage: float  # 杠杆倍数
    
    # 风险评级
    overall_risk_level: RiskLevel


@dataclass
class TradingPerformance:
    """交易绩效模型"""
    start_date: datetime
    end_date: datetime
    
    # 基础统计
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    
    # 盈亏统计
    total_pnl: float
    average_win: float
    average_loss: float
    profit_factor: float  # 盈利因子
    
    # 风险调整收益
    sharpe_ratio: Optional[float] = None
    max_drawdown: float = 0.0
    
    # 交易效率
    average_trade_duration: float = 0.0  # 平均持仓时间(小时)


@dataclass
class AlertMessage:
    """告警消息模型"""
    timestamp: datetime
    alert_type: str  # "signal", "risk", "system", "performance"
    severity: str  # "info", "warning", "error", "critical"
    symbol: Optional[str]
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GreeksData:
    """期权Greeks数据模型"""
    symbol: str
    timestamp: datetime
    underlying_price: float
    
    # Greeks指标
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    
    # 隐含波动率
    implied_volatility: float
    
    # 时间价值相关
    time_to_expiry: float  # 剩余时间（年）
    intrinsic_value: float  # 内在价值
    time_value: float  # 时间价值
    
    # 风险指标
    delta_exposure: float = 0.0  # Delta敞口
    gamma_exposure: float = 0.0  # Gamma敞口
    vega_exposure: float = 0.0   # Vega敞口
    theta_decay: float = 0.0     # 时间衰减


@dataclass
class SystemStatus:
    """系统状态模型"""
    timestamp: datetime
    is_trading_active: bool
    market_session: str  # "pre_market", "regular", "after_hours", "closed"
    
    # 连接状态
    market_data_connected: bool
    trading_api_connected: bool
    
    # 系统健康
    cpu_usage: float
    memory_usage: float
    latency_ms: float
    
    # 交易统计
    active_positions: int
    daily_trade_count: int
    daily_pnl: float
    
    # 错误统计
    error_count: int
    last_error: Optional[str] = None
