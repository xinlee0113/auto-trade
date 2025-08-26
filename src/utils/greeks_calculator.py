"""
Greeks实时计算器
用于0DTE期权高频交易的实时风险指标计算

支持的Greeks:
- Delta: 期权价格对标的价格变化的敏感度
- Gamma: Delta对标的价格变化的敏感度  
- Theta: 期权价格对时间衰减的敏感度
- Vega: 期权价格对隐含波动率变化的敏感度
- Rho: 期权价格对无风险利率变化的敏感度

针对0DTE期权特点:
- 高Gamma、高Theta特性
- 时间价值快速衰减
- 对标的价格变化极其敏感
"""

import math
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum

from ..models.trading_models import OptionTickData, UnderlyingTickData
from ..config.trading_config import TradingConstants
from ..utils.logger_config import get_logger

logger = get_logger(__name__)


class OptionType(Enum):
    """期权类型"""
    CALL = "CALL"
    PUT = "PUT"


@dataclass
class GreeksResult:
    """Greeks计算结果"""
    symbol: str
    timestamp: datetime
    underlying_price: float
    option_price: float
    strike: float
    time_to_expiry: float  # 年化时间
    risk_free_rate: float
    implied_volatility: float
    
    # Greeks值
    delta: float
    gamma: float
    theta: float  # 每日theta
    vega: float   # 每1%波动率变化
    rho: float    # 每1%利率变化
    
    # 0DTE特有指标
    time_decay_rate: float      # 每分钟时间衰减
    gamma_exposure: float       # Gamma敞口
    theta_burn_rate: float      # Theta燃烧率
    
    # 风险评级
    risk_level: str             # "LOW", "MEDIUM", "HIGH", "EXTREME"
    risk_score: float           # 0-100风险评分


class GreeksCalculator:
    """Greeks实时计算器"""
    
    def __init__(self):
        """初始化计算器"""
        self.constants = TradingConstants
        
        # 🔥 修复无风险利率：使用当前市场利率
        self.risk_free_rate = 0.045  # 4.5% 当前美国10年期国债利率(应动态获取)
        self.dividend_yield = 0.0075  # QQQ股息率约0.75%
        
        # 🔥 修复0DTE期权参数：更精确的时间处理
        self.min_time_to_expiry = 1/(365*24*60*60)  # 最小1秒（年化）- 更精确
        self.max_volatility = 10.0          # 提升至1000% (0DTE可能极端)
        self.min_volatility = 0.005         # 降至0.5% (更宽容)
        
        # 缓存
        self.volatility_cache: Dict[str, float] = {}
        self.greeks_cache: Dict[str, GreeksResult] = {}
        
        logger.info("Greeks实时计算器初始化完成")
    
    def calculate_greeks(
        self, 
        option_data: OptionTickData, 
        underlying_data: UnderlyingTickData,
        implied_vol: Optional[float] = None
    ) -> GreeksResult:
        """
        计算期权Greeks
        
        Args:
            option_data: 期权数据
            underlying_data: 标的数据
            implied_vol: 隐含波动率（可选，自动计算）
            
        Returns:
            GreeksResult: Greeks计算结果
        """
        try:
            # 基础参数
            S = underlying_data.price  # 标的价格
            K = option_data.strike     # 执行价
            T = self._calculate_time_to_expiry(option_data.expiry)  # 到期时间
            r = self.risk_free_rate    # 无风险利率
            q = self.dividend_yield    # 股息率
            option_price = option_data.price
            
            # 计算或使用提供的隐含波动率
            if implied_vol is None:
                sigma = self._calculate_implied_volatility(
                    S, K, T, r, q, option_price, 
                    option_data.right == 'CALL', option_data
                )
            else:
                sigma = implied_vol
            
            # 验证参数
            if T <= 0 or sigma <= 0 or S <= 0 or option_price <= 0:
                logger.warning(f"无效参数: S={S}, K={K}, T={T}, σ={sigma}, 期权价格={option_price}")
                return self._create_zero_greeks(option_data, underlying_data)
            
            # 计算标准正态分布相关值
            d1, d2 = self._calculate_d1_d2(S, K, T, r, q, sigma)
            
            # 计算Greeks
            is_call = (option_data.right.upper() == 'CALL')
            delta = self._calculate_delta(d1, T, q, is_call)
            gamma = self._calculate_gamma(S, d1, T, q, sigma)
            theta = self._calculate_theta(S, K, T, r, q, sigma, d1, d2, is_call)
            vega = self._calculate_vega(S, d1, T, q)
            rho = self._calculate_rho(K, T, r, d2, is_call)
            
            # 🔥 修复0DTE特有指标计算
            time_decay_rate = abs(theta) / (24 * 60)  # 每分钟theta衰减
            
            # 修复Gamma敞口公式：泰勒展开二阶项
            price_change = S * 0.01  # 1%价格变动
            gamma_exposure = 0.5 * gamma * (price_change ** 2)  # 正确的Gamma敞口公式
            
            theta_burn_rate = abs(theta) / option_price if option_price > 0 else 0  # theta燃烧率
            
            # 风险评估
            risk_level, risk_score = self._assess_risk(delta, gamma, theta, T, option_price)
            
            result = GreeksResult(
                symbol=option_data.symbol,
                timestamp=datetime.now(),
                underlying_price=S,
                option_price=option_price,
                strike=K,
                time_to_expiry=T,
                risk_free_rate=r,
                implied_volatility=sigma,
                delta=delta,
                gamma=gamma,
                theta=theta,
                vega=vega,
                rho=rho,
                time_decay_rate=time_decay_rate,
                gamma_exposure=gamma_exposure,
                theta_burn_rate=theta_burn_rate,
                risk_level=risk_level,
                risk_score=risk_score
            )
            
            # 缓存结果
            self.greeks_cache[option_data.symbol] = result
            self.volatility_cache[option_data.symbol] = sigma
            
            logger.debug(f"Greeks计算完成: {option_data.symbol} "
                        f"Delta={delta:.4f} Gamma={gamma:.4f} Theta={theta:.4f}")
            
            return result
            
        except Exception as e:
            logger.error(f"Greeks计算错误: {e}")
            return self._create_zero_greeks(option_data, underlying_data)
    
    def _calculate_time_to_expiry(self, expiry_str: str) -> float:
        """计算到期时间（年化）"""
        try:
            # 解析到期日期
            expiry_date = datetime.strptime(expiry_str, '%Y-%m-%d').date()
            today = datetime.now().date()
            
            # 计算剩余天数
            days_to_expiry = (expiry_date - today).days
            
            # 对于0DTE期权，计算到收盘的小时数
            if days_to_expiry == 0:
                from datetime import timezone, timedelta
                
                # 🔥 修复时区问题：使用美东时间
                est_tz = timezone(timedelta(hours=-5))  # EST时区
                now_est = datetime.now(est_tz)
                
                # 美股收盘时间 4:00 PM EST
                market_close_est = datetime.combine(today, time(16, 0)).replace(tzinfo=est_tz)
                
                if now_est >= market_close_est:
                    # 已过收盘时间，设为最小值
                    return self.min_time_to_expiry
                
                # 计算到收盘的小时数，转换为年化
                hours_to_expiry = (market_close_est - now_est).total_seconds() / 3600
                return max(hours_to_expiry / (365 * 24), self.min_time_to_expiry)
            
            # 非0DTE期权，使用天数
            return max(days_to_expiry / 365.0, self.min_time_to_expiry)
            
        except Exception as e:
            logger.warning(f"计算到期时间失败: {e}")
            return self.min_time_to_expiry
    
    def _calculate_d1_d2(self, S: float, K: float, T: float, r: float, q: float, sigma: float) -> Tuple[float, float]:
        """计算Black-Scholes公式中的d1和d2"""
        try:
            d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
            d2 = d1 - sigma * math.sqrt(T)
            return d1, d2
        except (ValueError, ZeroDivisionError) as e:
            logger.warning(f"计算d1/d2失败: {e}")
            return 0.0, 0.0
    
    def _calculate_delta(self, d1: float, T: float, q: float, is_call: bool) -> float:
        """计算Delta"""
        try:
            norm_d1 = self._norm_cdf(d1)
            discount_factor = math.exp(-q * T)
            
            if is_call:
                return discount_factor * norm_d1
            else:
                return discount_factor * (norm_d1 - 1.0)
                
        except Exception as e:
            logger.warning(f"计算Delta失败: {e}")
            return 0.0
    
    def _calculate_gamma(self, S: float, d1: float, T: float, q: float, sigma: float) -> float:
        """计算Gamma"""
        try:
            norm_pdf_d1 = self._norm_pdf(d1)
            discount_factor = math.exp(-q * T)
            denominator = S * sigma * math.sqrt(T)
            
            if denominator == 0:
                return 0.0
                
            return (discount_factor * norm_pdf_d1) / denominator
            
        except Exception as e:
            logger.warning(f"计算Gamma失败: {e}")
            return 0.0
    
    def _calculate_theta(self, S: float, K: float, T: float, r: float, q: float, 
                        sigma: float, d1: float, d2: float, is_call: bool) -> float:
        """计算Theta（每日）"""
        try:
            norm_pdf_d1 = self._norm_pdf(d1)
            norm_cdf_d2 = self._norm_cdf(d2)
            
            # 🔥 修复Theta计算公式错误
            # 第一项: 时间衰减项 (Call和Put相同)
            term1 = -S * norm_pdf_d1 * sigma * math.exp(-q * T) / (2 * math.sqrt(T))
            
            if is_call:
                # Call期权的Theta
                term2 = q * S * self._norm_cdf(d1) * math.exp(-q * T)
                term3 = -r * K * math.exp(-r * T) * self._norm_cdf(d2)
                theta = term1 + term2 + term3
            else:
                # Put期权的Theta (修复符号错误)
                term2 = -q * S * self._norm_cdf(-d1) * math.exp(-q * T)
                term3 = r * K * math.exp(-r * T) * self._norm_cdf(-d2)
                theta = term1 + term2 + term3
            
            # 转换为每日Theta
            return theta / 365.0
            
        except Exception as e:
            logger.warning(f"计算Theta失败: {e}")
            return 0.0
    
    def _calculate_vega(self, S: float, d1: float, T: float, q: float) -> float:
        """计算Vega（每1%隐含波动率变化）"""
        try:
            norm_pdf_d1 = self._norm_pdf(d1)
            return S * math.exp(-q * T) * norm_pdf_d1 * math.sqrt(T) / 100.0
            
        except Exception as e:
            logger.warning(f"计算Vega失败: {e}")
            return 0.0
    
    def _calculate_rho(self, K: float, T: float, r: float, d2: float, is_call: bool) -> float:
        """计算Rho（每1%利率变化）"""
        try:
            norm_cdf_d2 = self._norm_cdf(d2)
            discount_factor = math.exp(-r * T)
            
            if is_call:
                rho = K * T * discount_factor * norm_cdf_d2
            else:
                rho = -K * T * discount_factor * self._norm_cdf(-d2)
            
            # 转换为每1%利率变化
            return rho / 100.0
            
        except Exception as e:
            logger.warning(f"计算Rho失败: {e}")
            return 0.0
    
    def _calculate_implied_volatility(self, S: float, K: float, T: float, r: float, q: float, 
                                    market_price: float, is_call: bool, option_data=None) -> float:
        """使用Newton-Raphson方法计算隐含波动率"""
        try:
            # 初始猜测值
            sigma = 0.3  # 30%
            
            # 🔥 修复0DTE缓存策略：使用实时ATM期权IV作为初始值
            if T < 1/365:  # 0DTE期权
                underlying_symbol = option_data.symbol.split('_')[0] if hasattr(option_data, 'symbol') else 'DEFAULT'
                
                # 尝试获取实时ATM期权IV作为更准确的初始值
                atm_iv = self._get_atm_implied_volatility(underlying_symbol, S)
                if atm_iv and atm_iv > 0:
                    sigma = atm_iv
                    logger.info(f"使用实时ATM-IV初始值: {sigma:.3f}")
                else:
                    # fallback到缓存的历史值
                    sigma = self.volatility_cache.get(f"underlying_{underlying_symbol}", 0.5)
                    logger.info(f"使用缓存IV初始值: {sigma:.3f}")
            
            # 🔥 优化迭代次数：0DTE期权使用更少迭代提升性能
            max_iterations = 20 if T < 1/365 else 50  # 0DTE用20次，其他用50次
            tolerance = 1e-6
            
            for i in range(max_iterations):
                # 计算理论价格和Vega
                d1, d2 = self._calculate_d1_d2(S, K, T, r, q, sigma)
                theoretical_price = self._black_scholes_price(S, K, T, r, q, sigma, is_call)
                
                # 🔥 修复0DTE隐含波动率计算问题
                vega_raw = S * math.exp(-q * T) * self._norm_pdf(d1) * math.sqrt(T)
                
                # 0DTE期权Vega极小，使用数值求导
                if T < 1/365 or vega_raw < 1e-8:
                    # 数值求导计算Vega (1bp波动率变化)
                    sigma_up = sigma + 0.0001
                    sigma_down = sigma - 0.0001
                    price_up = self._black_scholes_price(S, K, T, r, q, sigma_up, is_call)
                    price_down = self._black_scholes_price(S, K, T, r, q, sigma_down, is_call)
                    vega_raw = (price_up - price_down) / 0.0002
                
                if abs(vega_raw) < 1e-10:  # 防止除零
                    break
                
                # Newton-Raphson迭代
                price_diff = theoretical_price - market_price
                if abs(price_diff) < tolerance:
                    break
                
                sigma_new = sigma - price_diff / vega_raw
                
                # 限制波动率范围
                sigma_new = max(self.min_volatility, min(self.max_volatility, sigma_new))
                
                if abs(sigma_new - sigma) < tolerance:
                    break
                
                sigma = sigma_new
            
            # 🔥 修复强制限制问题：只在异常情况下限制
            # 对于0DTE期权，只有在计算失败时才使用默认范围
            if T < 1/365 and (sigma <= 0 or sigma > 10.0):  # 只限制明显异常值
                logger.warning(f"0DTE期权IV异常: {sigma:.4f}, 使用默认值")
                sigma = 0.5  # 50%默认值
            
            return sigma
            
        except Exception as e:
            logger.warning(f"计算隐含波动率失败: {e}")
            # 返回默认值
            return 0.5 if T < 1/365 else 0.3
    
    def _black_scholes_price(self, S: float, K: float, T: float, r: float, q: float, 
                           sigma: float, is_call: bool) -> float:
        """Black-Scholes期权定价"""
        try:
            d1, d2 = self._calculate_d1_d2(S, K, T, r, q, sigma)
            
            if is_call:
                price = (S * math.exp(-q * T) * self._norm_cdf(d1) - 
                        K * math.exp(-r * T) * self._norm_cdf(d2))
            else:
                price = (K * math.exp(-r * T) * self._norm_cdf(-d2) - 
                        S * math.exp(-q * T) * self._norm_cdf(-d1))
            
            return max(0.0, price)
            
        except Exception as e:
            logger.warning(f"Black-Scholes计算失败: {e}")
            return 0.0
    
    def _norm_cdf(self, x: float) -> float:
        """标准正态分布累积分布函数"""
        try:
            return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
        except:
            return 0.5 if x >= 0 else 0.0
    
    def _norm_pdf(self, x: float) -> float:
        """标准正态分布概率密度函数"""
        try:
            return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)
        except:
            return 0.0
    
    def _assess_risk(self, delta: float, gamma: float, theta: float, 
                    time_to_expiry: float, option_price: float) -> Tuple[str, float]:
        """评估期权风险等级"""
        try:
            risk_score = 0.0
            
            # 🔥 专业级风险评估算法重构
            
            # Delta风险（方向性风险）- 非线性评估
            delta_risk = abs(delta) ** 1.5 * 25  # 凸性风险特征
            risk_score += min(delta_risk, 25)
            
            # Gamma风险（凸性风险）- 基于实证数据的系数
            # QQQ期权Gamma通常0-0.1范围，0.05为中等风险
            gamma_normalized = gamma / 0.05  # 标准化到0.05基准
            gamma_risk = min(gamma_normalized * 20, 30)  
            risk_score += gamma_risk
            
            # Theta风险（时间衰减风险）- 相对价值损失
            if option_price > 0:
                theta_burn_rate = abs(theta) / option_price  # 每日损失比例
                theta_risk = min(theta_burn_rate * 200, 25)  # 10%日损失=20分
            else:
                theta_risk = 25
            risk_score += theta_risk
            
            # 时间风险（0DTE指数衰减）
            if time_to_expiry < 1/365:  # 小于1天
                # 0DTE最后几小时风险指数增长
                hours_remaining = time_to_expiry * 365 * 24
                if hours_remaining < 1:  # 最后1小时
                    time_risk = 20
                elif hours_remaining < 3:  # 最后3小时
                    time_risk = 15
                elif hours_remaining < 6:  # 最后6小时
                    time_risk = 10
                else:
                    time_risk = 5
                risk_score += time_risk
            
            # 确定风险等级
            if risk_score >= 80:
                risk_level = "EXTREME"
            elif risk_score >= 60:
                risk_level = "HIGH" 
            elif risk_score >= 40:
                risk_level = "MEDIUM"
            else:
                risk_level = "LOW"
            
            return risk_level, min(100.0, risk_score)
            
        except Exception as e:
            logger.warning(f"风险评估失败: {e}")
            return "MEDIUM", 50.0
    
    def _create_zero_greeks(self, option_data: OptionTickData, 
                          underlying_data: UnderlyingTickData) -> GreeksResult:
        """创建零值Greeks结果（用于错误情况）"""
        return GreeksResult(
            symbol=option_data.symbol,
            timestamp=datetime.now(),
            underlying_price=underlying_data.price,
            option_price=option_data.price,
            strike=option_data.strike,
            time_to_expiry=0.0,
            risk_free_rate=self.risk_free_rate,
            implied_volatility=0.0,
            delta=0.0,
            gamma=0.0,
            theta=0.0,
            vega=0.0,
            rho=0.0,
            time_decay_rate=0.0,
            gamma_exposure=0.0,
            theta_burn_rate=0.0,
            risk_level="UNKNOWN",
            risk_score=0.0
        )
    
    def get_cached_greeks(self, symbol: str) -> Optional[GreeksResult]:
        """获取缓存的Greeks结果"""
        return self.greeks_cache.get(symbol)
    
    def get_cached_volatility(self, symbol: str) -> Optional[float]:
        """获取缓存的隐含波动率"""
        return self.volatility_cache.get(symbol)
    
    def clear_cache(self):
        """清空缓存"""
        self.greeks_cache.clear()
        self.volatility_cache.clear()
        logger.info("Greeks缓存已清空")


class PortfolioGreeksManager:
    """投资组合Greeks管理器"""
    
    def __init__(self):
        self.calculator = GreeksCalculator()
        self.positions: Dict[str, int] = {}  # symbol -> quantity
        self.portfolio_greeks: Optional[GreeksResult] = None
        
        logger.info("投资组合Greeks管理器初始化完成")
    
    def update_position(self, symbol: str, quantity: int):
        """更新持仓数量"""
        if quantity == 0:
            self.positions.pop(symbol, None)
        else:
            self.positions[symbol] = quantity
        
        logger.debug(f"更新持仓: {symbol} = {quantity}")
    
    def calculate_portfolio_greeks(self, option_data_list: List[OptionTickData], 
                                 underlying_data_list: List[UnderlyingTickData]) -> Optional[GreeksResult]:
        """计算投资组合总Greeks"""
        try:
            if not self.positions:
                return None
            
            # 创建数据映射
            option_map = {data.symbol: data for data in option_data_list}
            underlying_map = {data.symbol: data for data in underlying_data_list}
            
            # 累计Greeks
            total_delta = 0.0
            total_gamma = 0.0
            total_theta = 0.0
            total_vega = 0.0
            total_rho = 0.0
            total_value = 0.0
            
            valid_positions = 0
            
            for symbol, quantity in self.positions.items():
                if symbol not in option_map:
                    continue
                
                option_data = option_map[symbol]
                
                # 找到对应的标的数据
                underlying_data = None
                for underlying in underlying_data_list:
                    if underlying.symbol == option_data.underlying:
                        underlying_data = underlying
                        break
                
                if underlying_data is None:
                    continue
                
                # 计算单个期权的Greeks
                greeks = self.calculator.calculate_greeks(option_data, underlying_data)
                
                # 按持仓数量加权累计
                total_delta += greeks.delta * quantity
                total_gamma += greeks.gamma * quantity
                total_theta += greeks.theta * quantity
                total_vega += greeks.vega * quantity
                total_rho += greeks.rho * quantity
                total_value += option_data.price * quantity
                
                valid_positions += 1
            
            if valid_positions == 0:
                return None
            
            # 创建投资组合Greeks结果
            portfolio_greeks = GreeksResult(
                symbol="PORTFOLIO",
                timestamp=datetime.now(),
                underlying_price=0.0,  # 投资组合无单一标的价格
                option_price=total_value,
                strike=0.0,
                time_to_expiry=0.0,
                risk_free_rate=self.calculator.risk_free_rate,
                implied_volatility=0.0,
                delta=total_delta,
                gamma=total_gamma,
                theta=total_theta,
                vega=total_vega,
                rho=total_rho,
                time_decay_rate=abs(total_theta) / (24 * 60),
                gamma_exposure=total_gamma * 10000,  # 假设标的价格变动100点
                theta_burn_rate=abs(total_theta) / total_value if total_value > 0 else 0,
                risk_level="MEDIUM",  # 需要进一步评估
                risk_score=50.0
            )
            
            self.portfolio_greeks = portfolio_greeks
            
            logger.info(f"投资组合Greeks计算完成: "
                       f"Delta={total_delta:.2f} Gamma={total_gamma:.4f} Theta={total_theta:.2f}")
            
            return portfolio_greeks
            
        except Exception as e:
            logger.error(f"投资组合Greeks计算失败: {e}")
            return None
    
    def _get_atm_implied_volatility(self, underlying_symbol: str, spot_price: float) -> Optional[float]:
        """获取ATM期权的实时隐含波动率作为更准确的初始值"""
        try:
            # 这里需要外部API接口支持，暂时返回None使用fallback
            # 实际实现中可以调用Tiger API获取ATM期权的IV
            
            # 示例实现逻辑（需要API支持）:
            # 1. 找到最接近spot_price的执行价
            # 2. 获取该执行价Call/Put期权的IV
            # 3. 取平均值作为ATM-IV
            
            # TODO: 集成实际的ATM-IV获取逻辑
            logger.debug(f"尝试获取{underlying_symbol}@{spot_price:.2f}的ATM-IV")
            
            return None  # 暂时返回None，使用历史缓存
            
        except Exception as e:
            logger.warning(f"获取ATM-IV失败: {e}")
            return None
    
    def get_portfolio_risk_metrics(self) -> Dict[str, float]:
        """获取投资组合风险指标"""
        if self.portfolio_greeks is None:
            return {}
        
        greeks = self.portfolio_greeks
        
        return {
            'total_delta': greeks.delta,
            'total_gamma': greeks.gamma,
            'daily_theta': greeks.theta,
            'total_vega': greeks.vega,
            'delta_neutrality': abs(greeks.delta),  # 越小越好
            'gamma_risk': greeks.gamma * 10000,     # 标的变动100点的影响
            'theta_burn': abs(greeks.theta),        # 每日时间价值损失
            'volatility_sensitivity': abs(greeks.vega),  # 波动率敏感度
            'portfolio_value': greeks.option_price
        }
