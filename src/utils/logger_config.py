"""
日志配置模块
为0DTE期权高频交易系统提供统一的日志管理
"""

import logging
import os
from datetime import datetime
from typing import Optional


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    获取配置好的日志记录器
    
    Args:
        name: 日志记录器名称
        level: 日志级别
        
    Returns:
        配置好的日志记录器
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        # 创建日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        
        # 文件处理器
        logs_dir = "logs"
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir)
            
        today = datetime.now().strftime('%Y%m%d')
        log_file = os.path.join(logs_dir, f"trading_system_{today}.log")
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        
        # 添加处理器
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        logger.setLevel(level)
        
        # 防止重复日志
        logger.propagate = False
    
    return logger


def setup_logging(level: int = logging.INFO):
    """
    设置全局日志配置
    
    Args:
        level: 全局日志级别
    """
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )