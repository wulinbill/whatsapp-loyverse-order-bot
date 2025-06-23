#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kong Food Restaurant WhatsApp订餐机器人
使用Claude AI的智能对话系统
"""

import logging
import os
import sys
from datetime import datetime

# 配置日志系统
def setup_logging():
    """配置应用日志系统"""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # 创建日志格式
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # 配置根日志记录器
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            # 如果需要文件日志，可以添加FileHandler
            # logging.FileHandler('/var/log/kong-food-bot.log')
        ]
    )
    
    # 设置外部库的日志级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("twilio").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)
    
    # 应用启动日志
    logger = logging.getLogger(__name__)
    logger.info("🍜 Kong Food Restaurant Bot initialized")
    logger.info(f"🤖 Log level set to {log_level}")
    logger.info(f"🕐 Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# 初始化日志
setup_logging()

# 版本信息
__version__ = "2.0.0"
__author__ = "Kong Food Restaurant"
__description__ = "WhatsApp AI ordering bot powered by Claude"

# 导出主要组件
from .app import create_app
from .claude_client import ClaudeClient
from .agent import handle_message

__all__ = [
    'create_app',
    'ClaudeClient', 
    'handle_message',
    '__version__',
    '__author__',
    '__description__'
]
