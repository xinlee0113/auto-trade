# API参考文档

## 概述

本文档详细描述了自动交易系统的API接口，包括期权分析、行情数据、配置管理等核心功能。

## 目录

- [BrokerTigerAPI](#brokerttigerapi)
- [OptionAnalyzer](#optionanalyzer)
- [OptionCalculator](#optioncalculator)
- [DataValidator](#datavalidator)
- [配置模型](#配置模型)
- [数据模型](#数据模型)

---

## BrokerTigerAPI

老虎证券API的主要封装类，提供期权分析和行情数据功能。

### 初始化

```python
from src.api.broker_tiger_api import BrokerTigerAPI

api = BrokerTigerAPI(props_path="config/tiger_openapi_config.properties")
```

**参数:**
- `props_path` (str, 可选): 配置文件路径，默认为相对路径

### 主要方法

#### get_qqq_optimal_0dte_options

获取QQQ最优末日期权。

```python
def get_qqq_optimal_0dte_options(
    self, 
    strategy: str = 'balanced', 
    top_n: int = 5
) -> dict:
```

**参数:**
- `strategy` (str): 策略类型，可选值：`'liquidity'`, `'balanced'`, `'value'`
- `top_n` (int): 返回最优期权数量，默认5个

**返回值:**
```python
{
    'calls': [OptionData, ...],      # Call期权列表
    'puts': [OptionData, ...],       # Put期权列表
    'strategy': str,                 # 使用的策略
    'current_price': float,          # QQQ当前价格
    'total_contracts': int,          # 总合约数
    'price_range': str,              # 筛选价格区间
    'timestamp': str,                # 分析时间戳
    'error': str or None            # 错误信息
}
```

**示例:**
```python
result = api.get_qqq_optimal_0dte_options(strategy='balanced', top_n=3)
if 'error' not in result:
    print(f"找到 {len(result['calls'])} 个最优Call期权")
    for call in result['calls']:
        print(f"执行价: ${call['strike']}, 评分: {call['score']:.1f}")
```

#### 行情监听方法

##### register_quote_depth_changed_listener

注册深度行情变化监听器。

```python
def register_quote_depth_changed_listener(
    self, 
    listener: Callable[[QuoteDepthData], None]
) -> None:
```

##### connect_push_client / disconnect_push_client

连接/断开推送客户端。

```python
def connect_push_client(self) -> None:
def disconnect_push_client(self) -> None:
```

---

## OptionAnalyzer

期权分析服务类，提供核心的期权评估功能。

### 初始化

```python
from src.services.option_analyzer import OptionAnalyzer
from src.config.option_config import OptionConfig

analyzer = OptionAnalyzer(config=OptionConfig())
```

### 主要方法

#### analyze_options

分析期权并返回最优选择。

```python
def analyze_options(
    self,
    option_chains: pd.DataFrame,
    current_price: float,
    strategy: OptionStrategy = OptionStrategy.BALANCED,
    top_n: int = 5,
    option_filter: OptionFilter = None
) -> OptionAnalysisResult:
```

**参数:**
- `option_chains` (pd.DataFrame): 期权链数据
- `current_price` (float): 标的当前价格
- `strategy` (OptionStrategy): 分析策略枚举
- `top_n` (int): 返回最优期权数量
- `option_filter` (OptionFilter, 可选): 筛选条件

**返回值:**
`OptionAnalysisResult` 对象，包含分析结果

---

## OptionCalculator

期权计算器，提供各种评分和计算功能。

### 初始化

```python
from src.utils.option_calculator import OptionCalculator
from src.config.option_config import OptionConfig

calculator = OptionCalculator(config=OptionConfig())
```

### 主要方法

#### calculate_option_score

计算期权综合评分。

```python
def calculate_option_score(
    self,
    option: OptionData,
    strategy: OptionStrategy,
    current_price: float
) -> float:
```

**参数:**
- `option` (OptionData): 期权数据
- `strategy` (OptionStrategy): 评估策略
- `current_price` (float): 标的当前价格

**返回值:**
综合评分 (0-100)

#### estimate_delta

估算期权Delta值。

```python
def estimate_delta(
    self,
    current_price: float,
    strike: float,
    right: str
) -> float:
```

**参数:**
- `current_price` (float): 标的当前价格
- `strike` (float): 执行价
- `right` (str): 期权类型 ('CALL' 或 'PUT')

**返回值:**
估算的Delta值

---

## DataValidator

数据验证器，提供输入数据的验证功能。

### 主要方法

#### validate_dataframe

验证DataFrame的有效性。

```python
def validate_dataframe(self, df: pd.DataFrame) -> bool:
```

#### validate_price

验证价格有效性。

```python
def validate_price(self, price: float) -> bool:
```

#### validate_strategy

验证策略有效性。

```python
def validate_strategy(self, strategy: str) -> bool:
```

---

## 配置模型

### OptionConfig

期权分析配置类。

```python
@dataclass
class OptionConfig:
    MAX_SYMBOLS_PER_REQUEST: int = 20
    MAX_OPTION_BRIEFS_PER_REQUEST: int = 30
    DEFAULT_PRICE_RANGE_PERCENT: float = 0.02
    MIN_VOLUME_THRESHOLD: int = 10
    MIN_OPEN_INTEREST_THRESHOLD: int = 100
    MAX_SPREAD_PERCENTAGE: float = 0.20
    STRATEGY_WEIGHTS: Dict[OptionStrategy, Dict[str, float]]
    DEFAULT_GAMMA: float = 0.1
    DEFAULT_THETA: float = -0.05
    DEFAULT_VEGA: float = 0.01
    DEFAULT_IMPLIED_VOL: float = 0.2
    DELTA_THRESHOLDS: Dict[str, float]
```

### OptionStrategy

策略枚举类。

```python
class OptionStrategy(Enum):
    LIQUIDITY = "liquidity"
    BALANCED = "balanced"
    VALUE = "value"
```

---

## 数据模型

### OptionData

期权数据模型。

```python
@dataclass
class OptionData:
    symbol: str
    strike: float
    right: str
    expiry: str
    latest_price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    volume: int = 0
    open_interest: int = 0
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    implied_vol: float = 0.0
    
    # 计算字段
    bid_ask_spread: float
    spread_percentage: float
    intrinsic_value: float
    time_value: float
    moneyness: float
    
    # 评分字段
    score: float = 0.0
    rank: int = 0
    score_details: Dict[str, float]
```

### OptionAnalysisResult

分析结果模型。

```python
@dataclass
class OptionAnalysisResult:
    calls: List[OptionData]
    puts: List[OptionData]
    strategy: str
    current_price: float
    total_contracts: int
    price_range: str
    timestamp: str
    message: Optional[str] = None
    error: Optional[str] = None
```

### OptionFilter

筛选条件模型。

```python
@dataclass
class OptionFilter:
    min_volume: Optional[int] = None
    min_open_interest: Optional[int] = None
    max_spread_percentage: Optional[float] = None
    price_range_percent: Optional[float] = None
    option_types: Optional[List[str]] = None
```

---

## 异常处理

### 自定义异常

#### OptionAnalysisException

期权分析专用异常。

```python
class OptionAnalysisException(Exception):
    def __init__(
        self, 
        message: str, 
        error_code: str = None, 
        details: Dict[str, Any] = None
    ):
```

#### DataValidationException

数据验证异常。

```python
class DataValidationException(OptionAnalysisException):
    def __init__(
        self, 
        message: str, 
        field_name: str = None, 
        field_value: Any = None
    ):
```

#### APIException

API调用异常。

```python
class APIException(OptionAnalysisException):
    def __init__(
        self, 
        message: str, 
        api_name: str = None, 
        status_code: int = None
    ):
```

---

## 缓存管理

### 缓存装饰器

使用缓存装饰器优化性能：

```python
from src.utils.cache_manager import cache_result

@cache_result(cache_name="option_analysis", ttl=300)
def expensive_calculation():
    # 耗时计算
    pass
```

### 缓存统计

```python
from src.utils.cache_manager import cache_manager

stats = cache_manager.get_all_stats()
print(f"缓存命中率: {stats['option_analysis']['hit_rate']:.1%}")
```

---

## 性能监控

### 性能装饰器

```python
from src.utils.cache_manager import monitor_performance

@monitor_performance
def monitored_function():
    # 被监控的函数
    pass
```

### 性能统计

```python
from src.utils.cache_manager import performance_monitor

stats = performance_monitor.get_all_stats()
for func_name, metrics in stats.items():
    print(f"{func_name}: 平均耗时 {metrics['avg_time']:.3f}s")
```

---

## 错误代码

| 错误代码 | 描述 |
|---------|------|
| `OPTION_ANALYSIS_ERROR` | 通用期权分析错误 |
| `DATA_VALIDATION_ERROR` | 数据验证失败 |
| `API_ERROR` | API调用错误 |
| `CONFIGURATION_ERROR` | 配置错误 |

---

## 最佳实践

### 1. 错误处理

总是检查返回结果中的错误字段：

```python
result = api.get_qqq_optimal_0dte_options()
if 'error' in result and result['error']:
    print(f"分析失败: {result['error']}")
    return

# 处理正常结果
for call in result['calls']:
    # 处理期权数据
    pass
```

### 2. 资源管理

使用上下文管理器确保资源正确释放：

```python
try:
    api.connect_push_client()
    # 处理实时数据
finally:
    api.disconnect_push_client()
```

### 3. 性能优化

- 使用适当的缓存TTL避免过期数据
- 合理设置筛选条件减少计算量
- 监控性能指标识别瓶颈

### 4. 配置管理

使用配置对象管理参数：

```python
from src.config.option_config import OptionConfig

config = OptionConfig()
config.MIN_VOLUME_THRESHOLD = 50  # 自定义阈值
analyzer = OptionAnalyzer(config)
```

---

## 版本兼容性

- Python 3.8+
- pandas 2.0+
- numpy 1.24+
- tigeropen 3.3.3+

---

## 更新日志

### v1.0.0 (2024-08-21)
- 初始版本发布
- 完整的期权分析功能
- 三种投资策略支持
- 模块化架构设计
- 100%测试覆盖率
