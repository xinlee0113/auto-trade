#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
日志配置
"""

import logging
import logging.handlers
import os
from datetime import datetime
from typing import Optional


class LoggerConfig:
    """日志配置器"""
    
    @staticmethod
    def setup_logger(
        name: str,
        level: int = logging.INFO,
        log_file: Optional[str] = None,
        max_bytes: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5
    ) -> logging.Logger:
        """
        设置日志记录器
        
        Args:
            name: 日志记录器名称
            level: 日志级别
            log_file: 日志文件路径（可选）
            max_bytes: 单个日志文件最大字节数
            backup_count: 备份文件数量
            
        Returns:
            logging.Logger: 配置好的日志记录器
        """
        logger = logging.getLogger(name)
        
        # 避免重复添加处理器
        if logger.handlers:
            return logger
        
        logger.setLevel(level)
        
        # 创建格式化器
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # 文件处理器（如果指定了日志文件）
        if log_file:
            # 确保日志目录存在
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            
            # 使用轮转文件处理器
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        
        return logger
    
    @staticmethod
    def get_default_log_file(module_name: str) -> str:
        """
        获取默认日志文件路径
        
        Args:
            module_name: 模块名称
            
        Returns:
            str: 日志文件路径
        """
        log_dir = os.path.join(os.getcwd(), 'logs')
        timestamp = datetime.now().strftime('%Y%m%d')
        return os.path.join(log_dir, f'{module_name}_{timestamp}.log')


def setup_option_logger() -> logging.Logger:
    """设置期权分析专用日志记录器"""
    log_file = LoggerConfig.get_default_log_file('option_analyzer')
    return LoggerConfig.setup_logger(
        name='option_analyzer',
        level=logging.INFO,
        log_file=log_file
    )


def setup_api_logger() -> logging.Logger:
    """设置API专用日志记录器"""
    log_file = LoggerConfig.get_default_log_file('broker_api')
    return LoggerConfig.setup_logger(
        name='broker_api',
        level=logging.INFO,
        log_file=log_file
    )
