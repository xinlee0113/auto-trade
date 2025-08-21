#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
异常处理工具
"""

import logging
import functools
from typing import Callable, Any, Optional, Dict
from datetime import datetime


class OptionAnalysisException(Exception):
    """期权分析专用异常"""
    
    def __init__(self, message: str, error_code: str = None, details: Dict[str, Any] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "OPTION_ANALYSIS_ERROR"
        self.details = details or {}
        self.timestamp = datetime.now().isoformat()


class DataValidationException(OptionAnalysisException):
    """数据验证异常"""
    
    def __init__(self, message: str, field_name: str = None, field_value: Any = None):
        super().__init__(message, "DATA_VALIDATION_ERROR")
        self.field_name = field_name
        self.field_value = field_value


class APIException(OptionAnalysisException):
    """API调用异常"""
    
    def __init__(self, message: str, api_name: str = None, status_code: int = None):
        super().__init__(message, "API_ERROR")
        self.api_name = api_name
        self.status_code = status_code


class ConfigurationException(OptionAnalysisException):
    """配置异常"""
    
    def __init__(self, message: str, config_key: str = None):
        super().__init__(message, "CONFIGURATION_ERROR")
        self.config_key = config_key


def exception_handler(
    logger: logging.Logger,
    default_return: Any = None,
    reraise: bool = False,
    log_traceback: bool = True
):
    """
    异常处理装饰器
    
    Args:
        logger: 日志记录器
        default_return: 发生异常时的默认返回值
        reraise: 是否重新抛出异常
        log_traceback: 是否记录堆栈跟踪
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except OptionAnalysisException as e:
                # 自定义异常的特殊处理
                logger.error(
                    f"期权分析异常 in {func.__name__}: [{e.error_code}] {e.message}",
                    extra={'error_code': e.error_code, 'details': e.details}
                )
                if log_traceback:
                    logger.debug("异常详情:", exc_info=True)
                
                if reraise:
                    raise
                return default_return
                
            except Exception as e:
                # 通用异常处理
                logger.error(
                    f"未预期异常 in {func.__name__}: {str(e)}",
                    exc_info=log_traceback
                )
                
                if reraise:
                    raise
                return default_return
        
        return wrapper
    return decorator


def safe_execute(
    func: Callable,
    *args,
    logger: logging.Logger = None,
    default_return: Any = None,
    **kwargs
) -> Any:
    """
    安全执行函数，捕获和记录异常
    
    Args:
        func: 要执行的函数
        *args: 函数位置参数
        logger: 日志记录器
        default_return: 异常时的默认返回值
        **kwargs: 函数关键字参数
        
    Returns:
        Any: 函数执行结果或默认返回值
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if logger:
            logger.error(f"安全执行失败 {func.__name__}: {str(e)}", exc_info=True)
        return default_return


def validate_and_convert(
    value: Any,
    target_type: type,
    field_name: str = "unknown",
    allow_none: bool = False
) -> Any:
    """
    验证并转换数据类型
    
    Args:
        value: 要验证的值
        target_type: 目标类型
        field_name: 字段名称
        allow_none: 是否允许None值
        
    Returns:
        Any: 转换后的值
        
    Raises:
        DataValidationException: 验证失败时抛出
    """
    if value is None:
        if allow_none:
            return None
        else:
            raise DataValidationException(
                f"字段 {field_name} 不能为空",
                field_name=field_name,
                field_value=value
            )
    
    try:
        if isinstance(value, target_type):
            return value
        
        # 尝试类型转换
        if target_type == float:
            return float(value)
        elif target_type == int:
            return int(float(value))  # 先转float再转int，处理"1.0"这种字符串
        elif target_type == str:
            return str(value)
        elif target_type == bool:
            if isinstance(value, str):
                return value.lower() in ('true', '1', 'yes', 'on')
            return bool(value)
        else:
            return target_type(value)
            
    except (ValueError, TypeError) as e:
        raise DataValidationException(
            f"字段 {field_name} 类型转换失败: {str(e)}",
            field_name=field_name,
            field_value=value
        ) from e


class ErrorCollector:
    """错误收集器"""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
    
    def add_error(self, message: str, error_code: str = None, **details):
        """添加错误"""
        self.errors.append({
            'message': message,
            'error_code': error_code,
            'details': details,
            'timestamp': datetime.now().isoformat()
        })
    
    def add_warning(self, message: str, **details):
        """添加警告"""
        self.warnings.append({
            'message': message,
            'details': details,
            'timestamp': datetime.now().isoformat()
        })
    
    def has_errors(self) -> bool:
        """是否有错误"""
        return len(self.errors) > 0
    
    def has_warnings(self) -> bool:
        """是否有警告"""
        return len(self.warnings) > 0
    
    def get_summary(self) -> Dict[str, Any]:
        """获取错误汇总"""
        return {
            'error_count': len(self.errors),
            'warning_count': len(self.warnings),
            'errors': self.errors,
            'warnings': self.warnings
        }
    
    def clear(self):
        """清空错误和警告"""
        self.errors.clear()
        self.warnings.clear()
