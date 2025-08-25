# 0DTE期权高频交易系统 - 严格分层工程结构图

## 🏗️ **严格分层架构结构**

```
auto_trade/
├── 📁 src/                              # 源代码目录 (严格分层架构)
│   ├── 📁 presentation/                 # 🎨 表示层 (Presentation Layer)
│   │   ├── 📄 __init__.py
│   │   ├── 📄 main_application.py       # 主应用程序 - 系统启动入口
│   │   └── 📄 command_line_interface.py # 命令行界面 - 参数处理
│   │
│   ├── 📁 application/                  # 🔄 应用服务层 (Application Service Layer)
│   │   ├── 📄 __init__.py
│   │   ├── 📄 trading_orchestrator.py   # 交易编排器 - 业务流程协调
│   │   └── 📄 system_controller.py      # 系统控制器 - 系统生命周期管理
│   │
│   ├── 📁 domain/                       # 🏢 领域服务层 (Domain Service Layer)
│   │   ├── 📄 __init__.py
│   │   ├── 📄 market_analysis_service.py     # 市场分析服务 - 核心市场分析业务
│   │   ├── 📄 option_trading_service.py      # 期权交易服务 - 核心期权交易业务
│   │   └── 📄 risk_management_service.py     # 风险管理服务 - 核心风险管理业务
│   │
│   ├── 📁 infrastructure/               # ⚙️  基础设施层 (Infrastructure Layer)
│   │   ├── 📄 __init__.py
│   │   ├── 📄 data_access_layer.py      # 数据访问层 - 数据访问抽象
│   │   ├── 📄 external_api_adapter.py   # 外部API适配器 - Tiger API和第三方API
│   │   └── 📄 cache_repository.py       # 缓存存储库 - 内存缓存和策略
│   │
│   ├── 📁 engines/                      # 🔬 计算引擎层 (Calculation Engine Layer)
│   │   ├── 📄 __init__.py
│   │   ├── 📄 greeks_calculation_engine.py   # Greeks计算引擎 - Black-Scholes模型
│   │   ├── 📄 technical_analysis_engine.py   # 技术分析引擎 - 技术指标计算
│   │   └── 📄 risk_calculation_engine.py     # 风险计算引擎 - VaR和风险模型
│   │
│   ├── 📁 models/                       # 📊 数据模型层 (Data Model Layer)
│   │   ├── 📄 __init__.py
│   │   └── 📄 trading_models.py         # 交易数据模型 - 领域实体和值对象
│   │
│   ├── 📁 config/                       # ⚙️  配置层 (Configuration Layer)
│   │   ├── 📄 __init__.py
│   │   ├── 📄 configuration_manager.py  # 配置管理器 - 系统配置管理
│   │   ├── 📄 constants_definition.py   # 常量定义 - 系统常量和业务参数
│   │   └── 📄 trading_config.py         # 交易配置 - 交易参数配置
│   │
│   └── 📁 utils/                        # 🛠️  工具层 (Utility Layer)
│       ├── 📄 __init__.py
│       ├── 📄 logger_config.py          # 日志配置 - 现有日志工具
│       ├── 📄 logging_utility.py        # 日志工具 - 日志记录和性能监控
│       ├── 📄 validation_utility.py     # 验证工具 - 数据验证和业务规则
│       ├── 📄 security_utility.py       # 安全工具 - 安全认证和数据加密
│       ├── 📄 parallel_api_manager.py   # 并行API管理器 - 现有并行处理
│       └── 📄 technical_indicators.py   # 技术指标计算 - 现有技术指标
│
├── 📁 test/                                  # 测试目录
│   ├── 📁 integration/                       # 集成测试
│   │   ├── 📄 __init__.py                    # 包初始化
│   │   ├── 📄 test_greeks_real_integration.py      # Greeks计算真实集成测试
│   │   ├── 📄 test_risk_management_real_integration.py  # 风险管理真实集成测试
│   │   ├── 📄 test_market_analysis_real_integration.py  # 市场分析真实集成测试
│   │   ├── 📄 test_option_analysis_real_integration.py  # 期权分析真实集成测试
│   │   └── 📄 test_end_to_end_trading_workflow.py      # 端到端交易流程测试
│   │
│   ├── 📁 api/                               # API层单元测试
│   │   ├── 📄 __init__.py                    # 包初始化
│   │   ├── 📄 test_broker_tiger_api.py       # Tiger API测试
│   │   └── 📄 test_qqq_options.py            # QQQ期权测试
│   │
│   ├── 📁 data/                              # 数据层单元测试
│   │   ├── 📄 __init__.py                    # 包初始化
│   │   └── 📄 test_real_time_market_data.py  # 实时数据测试
│   │
│   ├── 📁 services/                          # 服务层单元测试
│   │   ├── 📄 __init__.py                    # 包初始化
│   │   └── 📄 test_risk_manager.py           # 风险管理测试
│   │
│   └── 📁 utils/                             # 工具层单元测试
│       ├── 📄 __init__.py                    # 包初始化
│       ├── 📄 test_greeks_calculator.py      # Greeks计算测试
│       ├── 📄 test_technical_indicators.py   # 技术指标测试
│       └── 📄 test_api_rate_limiter.py       # API限流测试
│
├── 📁 docs/                                  # 文档目录
│   ├── 📁 architecture/                      # 架构设计文档
│   │   ├── 📄 system_architecture.puml       # 系统架构图(PlantUML)
│   │   ├── 📄 class_diagram.puml             # 类图设计(PlantUML)
│   │   └── 📄 project_structure.md           # 项目结构说明
│   │
│   ├── 📄 0DTE期权高频交易策略设计文档.md        # 策略设计文档
│   ├── 📄 QQQ末日期权最优策略分析.md             # QQQ策略分析
│   ├── 📄 开发规范与最佳实践.md                 # 开发规范
│   ├── 📄 代码优化总结.md                     # 优化总结
│   ├── 📄 项目实施计划.md                     # 实施计划
│   ├── 📄 api_reference.md                   # API参考
│   └── 📄 风险评估与免责声明.md                 # 风险声明
│
├── 📁 config/                                # 配置文件目录
│   └── 📄 tiger_openapi_config.properties    # Tiger API配置
│
├── 📁 demos/                                 # API示例(第三方提供)
│   ├── 📄 client_config.py                  # 客户端配置
│   ├── 📄 financial_demo.py                 # 金融数据示例
│   ├── 📄 nasdaq100.py                      # 纳斯达克100示例
│   ├── 📄 push_client_demo.py               # 推送客户端示例
│   ├── 📄 push_client_stomp_demo.py         # STOMP推送示例
│   ├── 📄 quote_client_demo.py              # 行情客户端示例
│   └── 📄 trade_client_demo.py              # 交易客户端示例
│
├── 📁 notebooks/                             # Jupyter笔记本
│   └── 📄 老虎证券真实交易API演示.ipynb         # API演示笔记本
│
├── 📁 logs/                                  # 日志目录
│   ├── 📄 trading_system_*.log              # 交易系统日志
│   └── 📄 option_analyzer_*.log             # 期权分析日志
│
├── 📄 main.py                                # 主程序入口
├── 📄 requirements.txt                       # 生产依赖
├── 📄 requirements-dev.txt                   # 开发依赖
├── 📄 Makefile                              # 构建脚本
├── 📄 pyproject.toml                        # 项目配置
├── 📄 README.md                             # 项目说明
├── 📄 LICENSE                               # 许可证
├── 📄 CHANGELOG.md                          # 变更日志
├── 📄 .gitignore                            # Git忽略规则
└── 📄 code_guard.py                         # 代码守护脚本
```

## 📊 架构层级映射

### 🏗️ 严格分层架构对应关系

| 架构层级 | 目录位置 | 核心职责 | 主要类 | 依赖方向 |
|----------|----------|----------|--------|----------|
| **表示层** | `/main.py`, `/src/presentation/` | 用户交互、系统启动 | MainApplication, CommandLineInterface | ↓ 应用服务层 |
| **应用服务层** | `/src/application/` | 业务流程编排、服务协调 | TradingOrchestrator, SystemController | ↓ 领域服务层 |
| **领域服务层** | `/src/domain/` | 核心业务逻辑、领域规则 | MarketAnalysisService, OptionTradingService, RiskManagementService | ↓ 基础设施层 + 计算引擎层 |
| **基础设施层** | `/src/infrastructure/` | 外部资源访问、技术实现 | DataAccessLayer, ExternalAPIAdapter, CacheRepository | ↓ 数据模型层 |
| **计算引擎层** | `/src/engines/` | 数学计算、算法实现 | GreeksCalculationEngine, TechnicalAnalysisEngine, RiskCalculationEngine | ↓ 数据模型层 |
| **数据模型层** | `/src/models/` | 数据结构定义、业务实体 | DomainModels, ValueObjects, Entities | 无依赖（最底层） |
| **配置层** | `/src/config/` | 配置管理、参数注入 | ConfigurationManager, ConstantsDefinition | → 横向支持 |
| **工具层** | `/src/utils/` | 通用工具、基础服务 | LoggingUtility, ValidationUtility, SecurityUtility | → 横向支持 |

### 🔗 严格分层依赖关系规则

```
                    严格向下单向依赖
                          ↓

┌─────────────────────────────────────────────────────────────┐
│                    表示层 (Presentation Layer)                │
│                      /main.py, /src/presentation/            │
└──────────────────────────┬──────────────────────────────────┘
                           ↓ 仅依赖
┌─────────────────────────────────────────────────────────────┐
│                应用服务层 (Application Service Layer)          │
│                        /src/application/                     │
└──────────────────────────┬──────────────────────────────────┘
                           ↓ 仅依赖
┌─────────────────────────────────────────────────────────────┐
│                  领域服务层 (Domain Service Layer)             │
│                        /src/domain/                          │
└─────────────┬─────────────────────────────┬─────────────────┘
              ↓ 依赖                        ↓ 依赖
┌──────────────────────────┐    ┌──────────────────────────────┐
│    基础设施层              │    │      计算引擎层                │
│ (Infrastructure Layer)    │    │ (Calculation Engine Layer)   │
│  /src/infrastructure/     │    │      /src/engines/           │
└─────────┬────────────────┘    └─────────┬────────────────────┘
          ↓ 仅依赖                        ↓ 仅依赖
┌─────────────────────────────────────────────────────────────┐
│                   数据模型层 (Data Model Layer)                │
│                        /src/models/                          │
│                    （最底层，无外部依赖）                        │
└─────────────────────────────────────────────────────────────┘

     横向支持（配置注入、工具支持）
          ↙          ↘
┌──────────────────┐    ┌──────────────────┐
│    配置层         │    │     工具层        │
│ /src/config/     │    │  /src/utils/     │
│ (Configuration)  │    │  (Utilities)     │
└──────────────────┘    └──────────────────┘
```

### 📏 分层原则与约束

#### ✅ **允许的依赖关系**
- **向下依赖**: 上层可以依赖下层
- **横向注入**: 配置层和工具层提供横向支持
- **接口依赖**: 依赖抽象接口，不依赖具体实现

#### ❌ **禁止的依赖关系**
- **向上依赖**: 下层绝不能依赖上层
- **跨层依赖**: 不能跨越中间层直接依赖
- **同层循环**: 同层级内部不能有循环依赖
- **具体依赖**: 不能直接依赖具体实现类

## 🎯 文件职责矩阵

| 文件路径 | 主要类 | 核心方法 | 架构层级 |
|----------|--------|----------|----------|
| `src/api/broker_tiger_api.py` | BrokerTigerAPI | get_quote_client(), safe_api_call() | API适配层 |
| `src/data/realtime_data_manager.py` | RealTimeDataManager | subscribe(), start_market_data_feed() | 数据管理层 |
| `src/services/market_analyzer.py` | MarketAnalyzer | analyze_overall_market(), detect_anomaly() | 业务服务层 |
| `src/services/option_analyzer.py` | OptionAnalyzer | select_optimal_options(), calculate_scores() | 业务服务层 |
| `src/services/risk_manager.py` | RiskManager | calculate_risk_metrics(), check_alerts() | 业务服务层 |
| `src/utils/greeks_calculator.py` | GreeksCalculator | calculate_all_greeks(), calculate_delta() | 计算引擎层 |
| `src/utils/technical_indicators.py` | TechnicalIndicators | calculate_ema(), generate_signals() | 计算引擎层 |
| `src/utils/parallel_api_manager.py` | ParallelAPIManager | execute_parallel_calls() | API适配层 |
| `src/models/trading_models.py` | MarketData, Position, RiskMetrics | __post_init__() | 数据模型层 |
| `src/models/option_models.py` | OptionData, GreeksData | __post_init__() | 数据模型层 |
| `src/config/trading_config.py` | TradingConfig, TradingConstants | - | 配置管理层 |

## ✅ 架构一致性检查点

1. **📁 目录结构一致性**: 实际目录必须与架构图完全匹配
2. **🏷️ 类名一致性**: 代码中的类名必须与类图完全一致
3. **🔗 依赖关系一致性**: 导入关系必须遵循架构设计的依赖方向
4. **📋 方法签名一致性**: 公共方法签名必须与类图设计一致
5. **🎯 职责分离一致性**: 每个类的职责必须与架构设计描述一致
6. **📦 包组织一致性**: 模块导入路径必须与目录结构一致

## 🚨 禁止的架构违规行为

❌ **跨层直接调用**: 业务层直接调用外部API
❌ **循环依赖**: 上层模块依赖下层模块
❌ **职责混乱**: 数据层包含业务逻辑
❌ **类名不一致**: 实现类名与设计类名不符
❌ **目录错放**: 文件放置在错误的架构层级
❌ **方法签名变更**: 未经设计更新就修改公共接口
