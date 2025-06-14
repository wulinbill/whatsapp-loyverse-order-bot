"""统一日志配置模块"""
import logging
import sys
from typing import Optional


def setup_logging(level: str = "INFO") -> None:
    """配置全局日志格式和级别"""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """获取指定名称的 logger 实例
    
    Args:
        name: logger 名称，通常传入 __name__
        level: 可选的日志级别，如果不指定则使用全局配置
        
    Returns:
        配置好的 logger 实例
    """
    logger = logging.getLogger(name)
    
    if level:
        logger.setLevel(getattr(logging, level.upper()))
    
    return logger


# 初始化全局日志配置
setup_logging()
