#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基础风险管理模块

实现0DTE期权高频交易的核心风险控制：
1. 实时止损管理（价格止损、时间止损、Delta止损）
2. 仓位管理（单笔限制、总仓位限制、集中度控制）
3. 风险监控（实时PnL、Greeks暴露、流动性风险）
4. 紧急风控（连接中断、异常波动、强制平仓）

Author: AI Assistant
Date: 2024-01-21
"""

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Callable
import threading
import time

from ..config.trading_config import TradingConfig, RiskLevel
from ..models.trading_models import (
    Position, TradingSignal, OptionTickData, UnderlyingTickData,
    MarketData
)
from ..utils.logger_config import get_logger

logger = get_logger(__name__)


class StopLossType(Enum):
    """止损类型"""
    PRICE = "price"          # 价格止损
    TIME = "time"            # 时间止损  
    DELTA = "delta"          # Delta止损
    PNL = "pnl"             # 盈亏止损
    IMPLIED_VOL = "iv"       # 隐含波动率止损


class RiskEvent(Enum):
    """风险事件类型"""
    STOP_LOSS_TRIGGERED = "stop_loss_triggered"
    POSITION_LIMIT_EXCEEDED = "position_limit_exceeded"
    CONCENTRATION_RISK = "concentration_risk"
    LIQUIDITY_RISK = "liquidity_risk"
    CONNECTION_LOST = "connection_lost"
    EXTREME_VOLATILITY = "extreme_volatility"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    EMERGENCY_HALT = "emergency_halt"


@dataclass
class StopLossRule:
    """止损规则"""
    type: StopLossType
    threshold: float                # 触发阈值
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    
    # 价格止损参数
    stop_price: Optional[float] = None
    
    # 时间止损参数  
    expiry_time: Optional[datetime] = None
    
    # Delta止损参数
    max_delta_exposure: Optional[float] = None
    
    # PnL止损参数
    max_loss_amount: Optional[float] = None
    max_loss_percentage: Optional[float] = None


@dataclass
class PositionLimits:
    """仓位限制"""
    max_single_position_value: float        # 单笔最大价值
    max_total_position_value: float         # 总仓位最大价值
    max_options_per_underlying: int         # 单标的最大期权数量
    max_concentration_percentage: float     # 最大集中度百分比
    max_daily_trades: int                   # 日内最大交易次数
    
    # Greeks限制
    max_portfolio_delta: float = 1000.0     # 最大组合Delta
    max_portfolio_gamma: float = 500.0      # 最大组合Gamma
    max_portfolio_theta: float = -200.0     # 最大组合Theta (负值)
    max_portfolio_vega: float = 1000.0      # 最大组合Vega


@dataclass
class RiskMetrics:
    """风险指标"""
    timestamp: datetime
    
    # PnL指标
    unrealized_pnl: float
    realized_pnl: float
    daily_pnl: float
    total_pnl: float
    
    # 仓位指标
    total_position_value: float
    position_count: int
    concentration_risk: float           # 最大集中度
    
    # Greeks指标
    portfolio_delta: float
    portfolio_gamma: float
    portfolio_theta: float
    portfolio_vega: float
    
    # 流动性指标
    avg_bid_ask_spread: float
    min_liquidity_score: float
    
    # 风险分数 (0-100, 100为最高风险)
    risk_score: float


@dataclass
class RiskAlert:
    """风险警报"""
    event_type: RiskEvent
    severity: str                       # "low", "medium", "high", "critical"
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    position_id: Optional[str] = None
    recommended_action: Optional[str] = None
    auto_executed: bool = False


class RiskManager:
    """基础风险管理器
    
    负责0DTE期权高频交易的核心风险控制
    """
    
    def __init__(self, config: TradingConfig):
        """初始化风险管理器"""
        self.config = config
        self.logger = get_logger(f"{__name__}.RiskManager")
        
        # 风险规则和限制
        self._initialize_risk_rules()
        self._initialize_position_limits()
        
        # 运行时状态
        self.positions: Dict[str, Position] = {}
        self.stop_loss_rules: Dict[str, List[StopLossRule]] = {}  # position_id -> rules
        self.risk_alerts: List[RiskAlert] = []
        self.daily_trades_count = 0
        self.daily_pnl = 0.0
        self.last_risk_check = datetime.now()
        
        # 回调函数
        self.risk_alert_callbacks: List[Callable[[RiskAlert], None]] = []
        self.emergency_stop_callback: Optional[Callable[[], None]] = None
        
        # 线程安全
        self._lock = threading.RLock()
        
        # 启动风险监控
        self._start_risk_monitoring()
        
        self.logger.info("基础风险管理器初始化完成")
    
    def _initialize_risk_rules(self):
        """初始化风险规则"""
        risk_level = self.config.risk_level
        
        if risk_level == RiskLevel.LOW:
            self.max_daily_loss_percentage = 0.02  # 2%
            self.max_position_loss_percentage = 0.05  # 5%
            self.default_time_stop_minutes = 30
        elif risk_level == RiskLevel.MEDIUM:
            self.max_daily_loss_percentage = 0.05  # 5%
            self.max_position_loss_percentage = 0.10  # 10%
            self.default_time_stop_minutes = 60
        elif risk_level == RiskLevel.HIGH:
            self.max_daily_loss_percentage = 0.08  # 8%
            self.max_position_loss_percentage = 0.12  # 12%
            self.default_time_stop_minutes = 75
        else:  # EXTREME
            self.max_daily_loss_percentage = 0.10  # 10%
            self.max_position_loss_percentage = 0.15  # 15%
            self.default_time_stop_minutes = 90
    
    def _initialize_position_limits(self):
        """初始化仓位限制"""
        max_position_value = self.config.max_position_value
        
        self.position_limits = PositionLimits(
            max_single_position_value=max_position_value * 0.1,    # 单笔10%
            max_total_position_value=max_position_value,
            max_options_per_underlying=20,                         # 单标的最多20个期权
            max_concentration_percentage=0.3,                      # 最大30%集中度
            max_daily_trades=100,                                  # 日内最多100笔交易
            max_portfolio_delta=max_position_value * 0.01,         # Delta暴露限制
            max_portfolio_gamma=max_position_value * 0.005,
            max_portfolio_theta=-max_position_value * 0.002,
            max_portfolio_vega=max_position_value * 0.01
        )
    
    def add_position(self, position: Position) -> bool:
        """添加仓位"""
        with self._lock:
            # 预检查仓位限制
            if not self._check_position_limits_before_add(position):
                return False
            
            # 添加仓位
            self.positions[position.position_id] = position
            
            # 设置默认止损规则
            self._setup_default_stop_loss(position)
            
            # 更新交易计数
            self.daily_trades_count += 1
            
            self.logger.info(f"添加仓位: {position.position_id}, 当前仓位数: {len(self.positions)}")
            return True
    
    def remove_position(self, position_id: str) -> Optional[Position]:
        """移除仓位"""
        with self._lock:
            position = self.positions.pop(position_id, None)
            if position:
                # 清除止损规则
                self.stop_loss_rules.pop(position_id, None)
                self.logger.info(f"移除仓位: {position_id}")
            return position
    
    def update_position(self, position_id: str, market_data: MarketData) -> List[RiskAlert]:
        """更新仓位并检查风险"""
        with self._lock:
            alerts = []
            
            if position_id not in self.positions:
                return alerts
            
            position = self.positions[position_id]
            
            # 更新仓位价值
            self._update_position_value(position, market_data)
            
            # 检查止损规则
            stop_loss_alerts = self._check_stop_loss_rules(position, market_data)
            alerts.extend(stop_loss_alerts)
            
            # 检查仓位风险
            position_alerts = self._check_position_risks(position)
            alerts.extend(position_alerts)
            
            return alerts
    
    def _check_position_limits_before_add(self, position: Position) -> bool:
        """添加仓位前检查限制"""
        # 检查单笔价值限制
        if position.current_value > self.position_limits.max_single_position_value:
            self._create_alert(
                RiskEvent.POSITION_LIMIT_EXCEEDED,
                "critical",
                f"单笔仓位价值超限: {position.current_value:.2f} > {self.position_limits.max_single_position_value:.2f}",
                position_id=position.position_id
            )
            return False
        
        # 检查总仓位限制
        total_value = sum(p.current_value for p in self.positions.values()) + position.current_value
        if total_value > self.position_limits.max_total_position_value:
            self._create_alert(
                RiskEvent.POSITION_LIMIT_EXCEEDED,
                "critical", 
                f"总仓位价值超限: {total_value:.2f} > {self.position_limits.max_total_position_value:.2f}",
                position_id=position.position_id
            )
            return False
        
        # 检查日内交易次数
        if self.daily_trades_count >= self.position_limits.max_daily_trades:
            self._create_alert(
                RiskEvent.POSITION_LIMIT_EXCEEDED,
                "high",
                f"日内交易次数超限: {self.daily_trades_count} >= {self.position_limits.max_daily_trades}",
                position_id=position.position_id
            )
            return False
        
        # 检查单标的期权数量
        underlying_count = sum(1 for p in self.positions.values() 
                             if hasattr(p, 'underlying') and p.underlying == getattr(position, 'underlying', None))
        if underlying_count >= self.position_limits.max_options_per_underlying:
            self._create_alert(
                RiskEvent.CONCENTRATION_RISK,
                "medium",
                f"单标的期权数量超限: {underlying_count} >= {self.position_limits.max_options_per_underlying}",
                position_id=position.position_id
            )
            return False
        
        return True
    
    def _setup_default_stop_loss(self, position: Position):
        """设置默认止损规则"""
        position_id = position.position_id
        rules = []
        
        # 价格止损 (5-15%损失)
        price_stop = StopLossRule(
            type=StopLossType.PRICE,
            threshold=self.max_position_loss_percentage,
            max_loss_percentage=self.max_position_loss_percentage
        )
        rules.append(price_stop)
        
        # 时间止损 (30-90分钟)
        time_stop = StopLossRule(
            type=StopLossType.TIME,
            threshold=self.default_time_stop_minutes,
            expiry_time=datetime.now() + timedelta(minutes=self.default_time_stop_minutes)
        )
        rules.append(time_stop)
        
        # Delta止损 (绝对值超过阈值)
        if hasattr(position, 'delta') and position.delta is not None:
            delta_stop = StopLossRule(
                type=StopLossType.DELTA,
                threshold=0.8,  # Delta绝对值超过0.8
                max_delta_exposure=0.8
            )
            rules.append(delta_stop)
        
        self.stop_loss_rules[position_id] = rules
        self.logger.debug(f"为仓位 {position_id} 设置了 {len(rules)} 个止损规则")
    
    def _check_stop_loss_rules(self, position: Position, market_data: MarketData) -> List[RiskAlert]:
        """检查止损规则"""
        alerts = []
        position_id = position.position_id
        
        if position_id not in self.stop_loss_rules:
            return alerts
        
        for rule in self.stop_loss_rules[position_id]:
            if not rule.enabled:
                continue
            
            triggered = False
            message = ""
            
            if rule.type == StopLossType.PRICE:
                # 价格止损检查
                if rule.max_loss_percentage:
                    loss_pct = (position.entry_price - position.current_price) / position.entry_price
                    if position.quantity < 0:  # 做空仓位
                        loss_pct = -loss_pct
                    
                    if loss_pct > rule.max_loss_percentage:
                        triggered = True
                        message = f"价格止损触发: 损失 {loss_pct:.2%} > {rule.max_loss_percentage:.2%}"
            
            elif rule.type == StopLossType.TIME:
                # 时间止损检查
                if rule.expiry_time and datetime.now() > rule.expiry_time:
                    triggered = True
                    message = f"时间止损触发: 持仓时间超过 {rule.threshold} 分钟"
            
            elif rule.type == StopLossType.DELTA:
                # Delta止损检查
                if hasattr(position, 'delta') and position.delta is not None:
                    if abs(position.delta) > rule.max_delta_exposure:
                        triggered = True
                        message = f"Delta止损触发: |{position.delta:.3f}| > {rule.max_delta_exposure:.3f}"
            
            if triggered:
                alert = self._create_alert(
                    RiskEvent.STOP_LOSS_TRIGGERED,
                    "high",
                    message,
                    position_id=position_id,
                    recommended_action="立即平仓"
                )
                alerts.append(alert)
                
                # 禁用已触发的规则避免重复触发
                rule.enabled = False
        
        return alerts
    
    def _check_position_risks(self, position: Position) -> List[RiskAlert]:
        """检查单个仓位风险"""
        alerts = []
        
        # 检查流动性风险
        if hasattr(position, 'bid_ask_spread') and position.bid_ask_spread is not None and position.bid_ask_spread > 0.05:  # 5%
            alerts.append(self._create_alert(
                RiskEvent.LIQUIDITY_RISK,
                "medium",
                f"流动性风险: 买卖价差 {position.bid_ask_spread:.2%} > 5%",
                position_id=position.position_id
            ))
        
        return alerts
    
    def check_portfolio_risks(self) -> List[RiskAlert]:
        """检查整体投资组合风险"""
        with self._lock:
            alerts = []
            
            # 计算组合指标
            metrics = self.calculate_risk_metrics()
            
            # 检查日损失限制
            daily_loss_limit = self.config.max_position_value * self.max_daily_loss_percentage
            if metrics.daily_pnl < -daily_loss_limit:
                alerts.append(self._create_alert(
                    RiskEvent.DAILY_LOSS_LIMIT,
                    "critical",
                    f"日损失超限: {metrics.daily_pnl:.2f} < -{daily_loss_limit:.2f}",
                    recommended_action="停止交易并平仓"
                ))
            
            # 检查Greeks暴露
            if abs(metrics.portfolio_delta) > self.position_limits.max_portfolio_delta:
                alerts.append(self._create_alert(
                    RiskEvent.CONCENTRATION_RISK,
                    "high",
                    f"组合Delta超限: {metrics.portfolio_delta:.2f}",
                    recommended_action="调整Delta中性"
                ))
            
            if abs(metrics.portfolio_gamma) > self.position_limits.max_portfolio_gamma:
                alerts.append(self._create_alert(
                    RiskEvent.CONCENTRATION_RISK,
                    "medium",
                    f"组合Gamma超限: {metrics.portfolio_gamma:.2f}"
                ))
            
            # 检查集中度风险
            if metrics.concentration_risk > self.position_limits.max_concentration_percentage:
                alerts.append(self._create_alert(
                    RiskEvent.CONCENTRATION_RISK,
                    "medium",
                    f"集中度风险: {metrics.concentration_risk:.2%} > {self.position_limits.max_concentration_percentage:.2%}"
                ))
            
            return alerts
    
    def calculate_risk_metrics(self) -> RiskMetrics:
        """计算风险指标"""
        with self._lock:
            # PnL计算
            unrealized_pnl = sum(p.unrealized_pnl for p in self.positions.values())
            total_position_value = sum(abs(p.current_value) for p in self.positions.values())
            
            # Greeks计算
            portfolio_delta = sum(getattr(p, 'delta', 0) or 0 for p in self.positions.values())
            portfolio_gamma = sum(getattr(p, 'gamma', 0) or 0 for p in self.positions.values())
            portfolio_theta = sum(getattr(p, 'theta', 0) or 0 for p in self.positions.values())
            portfolio_vega = sum(getattr(p, 'vega', 0) or 0 for p in self.positions.values())
            
            # 集中度计算
            if self.positions and total_position_value > 0:
                max_position_value = max(abs(p.current_value) for p in self.positions.values())
                concentration_risk = max_position_value / total_position_value
            else:
                concentration_risk = 0.0
            
            # 流动性指标
            spreads = [getattr(p, 'bid_ask_spread', 0) or 0 for p in self.positions.values() 
                      if hasattr(p, 'bid_ask_spread') and getattr(p, 'bid_ask_spread', None) is not None]
            avg_bid_ask_spread = sum(spreads) / len(spreads) if spreads else 0.0
            
            # 风险分数计算 (简化版)
            risk_score = min(100, max(0, (
                abs(unrealized_pnl) / max(total_position_value, 1) * 50 +
                concentration_risk * 30 +
                avg_bid_ask_spread * 100 * 20
            )))
            
            return RiskMetrics(
                timestamp=datetime.now(),
                unrealized_pnl=unrealized_pnl,
                realized_pnl=0.0,  # TODO: 从交易历史计算
                daily_pnl=self.daily_pnl,
                total_pnl=unrealized_pnl,
                total_position_value=total_position_value,
                position_count=len(self.positions),
                concentration_risk=concentration_risk,
                portfolio_delta=portfolio_delta,
                portfolio_gamma=portfolio_gamma,
                portfolio_theta=portfolio_theta,
                portfolio_vega=portfolio_vega,
                avg_bid_ask_spread=avg_bid_ask_spread,
                min_liquidity_score=1.0 - avg_bid_ask_spread,  # 简化计算
                risk_score=risk_score
            )
    
    def _update_position_value(self, position: Position, market_data: MarketData):
        """更新仓位价值"""
        if isinstance(market_data, OptionTickData):
            position.current_price = market_data.price
            position.current_value = position.quantity * market_data.price * 100  # 期权合约乘数
            position.unrealized_pnl = (position.current_price - position.entry_price) * position.quantity * 100
            
            # 更新Greeks
            if market_data.delta is not None:
                position.delta = market_data.delta * position.quantity
            if market_data.gamma is not None:
                position.gamma = market_data.gamma * position.quantity
            if market_data.theta is not None:
                position.theta = market_data.theta * position.quantity
            if market_data.vega is not None:
                position.vega = market_data.vega * position.quantity
    
    def _create_alert(self, event_type: RiskEvent, severity: str, message: str, 
                     position_id: Optional[str] = None, recommended_action: Optional[str] = None) -> RiskAlert:
        """创建风险警报"""
        alert = RiskAlert(
            event_type=event_type,
            severity=severity,
            message=message,
            position_id=position_id,
            recommended_action=recommended_action
        )
        
        self.risk_alerts.append(alert)
        self.logger.warning(f"风险警报 [{severity.upper()}]: {message}")
        
        # 触发回调
        for callback in self.risk_alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                self.logger.error(f"风险警报回调执行失败: {e}")
        
        # 严重风险自动处理
        if severity == "critical" and self.emergency_stop_callback:
            try:
                self.emergency_stop_callback()
                alert.auto_executed = True
            except Exception as e:
                self.logger.error(f"紧急停止回调执行失败: {e}")
        
        return alert
    
    def _start_risk_monitoring(self):
        """启动风险监控线程"""
        def monitor_loop():
            while True:
                try:
                    # 每5秒检查一次整体风险
                    alerts = self.check_portfolio_risks()
                    
                    # 清理过期警报 (保留24小时)
                    cutoff_time = datetime.now() - timedelta(hours=24)
                    self.risk_alerts = [a for a in self.risk_alerts if a.timestamp > cutoff_time]
                    
                    time.sleep(5)
                except Exception as e:
                    self.logger.error(f"风险监控线程异常: {e}")
                    time.sleep(10)
        
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()
        self.logger.info("风险监控线程已启动")
    
    def register_risk_alert_callback(self, callback: Callable[[RiskAlert], None]):
        """注册风险警报回调"""
        self.risk_alert_callbacks.append(callback)
    
    def register_emergency_stop_callback(self, callback: Callable[[], None]):
        """注册紧急停止回调"""
        self.emergency_stop_callback = callback
    
    def get_risk_summary(self) -> Dict:
        """获取风险摘要"""
        with self._lock:
            metrics = self.calculate_risk_metrics()
            recent_alerts = [a for a in self.risk_alerts if a.timestamp > datetime.now() - timedelta(hours=1)]
            
            return {
                "timestamp": datetime.now().isoformat(),
                "metrics": {
                    "unrealized_pnl": metrics.unrealized_pnl,
                    "daily_pnl": metrics.daily_pnl,
                    "total_position_value": metrics.total_position_value,
                    "position_count": metrics.position_count,
                    "risk_score": metrics.risk_score,
                    "portfolio_delta": metrics.portfolio_delta,
                    "portfolio_gamma": metrics.portfolio_gamma,
                    "concentration_risk": metrics.concentration_risk
                },
                "limits": {
                    "max_single_position": self.position_limits.max_single_position_value,
                    "max_total_position": self.position_limits.max_total_position_value,
                    "daily_trades": f"{self.daily_trades_count}/{self.position_limits.max_daily_trades}",
                    "daily_loss_limit": self.config.max_position_value * self.max_daily_loss_percentage
                },
                "alerts": {
                    "total": len(self.risk_alerts),
                    "recent_hour": len(recent_alerts),
                    "critical": len([a for a in recent_alerts if a.severity == "critical"]),
                    "high": len([a for a in recent_alerts if a.severity == "high"])
                }
            }
    
    def reset_daily_counters(self):
        """重置日计数器（每日开盘前调用）"""
        with self._lock:
            self.daily_trades_count = 0
            self.daily_pnl = 0.0
            self.logger.info("日计数器已重置")


def create_risk_manager(config: TradingConfig) -> RiskManager:
    """创建风险管理器实例"""
    return RiskManager(config)
