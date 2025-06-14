"""LangChain 工具封装模块"""
import asyncio
import json
from typing import Any, Dict, Union, Optional
from loyverse_api import get_menu_items, create_order
from gpt_parser import parse_order, validate_order_json, get_menu_item_names
from utils.logger import get_logger

logger = get_logger(__name__)


def _run_async(coro):
    """在线程安全的方式下运行异步协程
    
    LangChain agent 在常规线程中执行，因此需要创建事件循环来调用异步函数
    
    Args:
        coro: 要执行的协程
        
    Returns:
        协程的执行结果
        
    Raises:
        RuntimeError: 协程执行失败
    """
    try:
        # 首先尝试直接运行
        return asyncio.run(coro)
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            # 检测到现有事件循环，在新线程中创建新循环
            logger.debug("检测到现有事件循环，在新线程中创建新循环")
            import concurrent.futures
            import threading
            
            def run_in_thread():
                new_loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(new_loop)
                    return new_loop.run_until_complete(coro)
                finally:
                    new_loop.close()
                    asyncio.set_event_loop(None)
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                return future.result(timeout=60)  # 60秒超时
        else:
            raise


def tool_parse_order(message: str) -> str:
    """LangChain 工具：解析客户订单消息为 JSON 格式
    
    Args:
        message: 客户的自然语言订单消息
        
    Returns:
        JSON 格式的订单字符串，或错误信息
    """
    if not message or not isinstance(message, str):
        error_msg = "订单消息不能为空"
        logger.warning(error_msg)
        return json.dumps({"error": error_msg}, ensure_ascii=False)
    
    message = message.strip()
    if not message:
        error_msg = "订单消息不能为空"
        logger.warning(error_msg)
        return json.dumps({"error": error_msg}, ensure_ascii=False)
    
    logger.info("解析订单消息: %s", message[:100])
    
    try:
        # 获取菜单数据
        menu_data: Dict[str, Any] = _run_async(get_menu_items())
        menu_names = get_menu_item_names(menu_data)
        
        if not menu_names:
            error_msg = "无法获取菜单数据或菜单为空"
            logger.error(error_msg)
            return json.dumps({"error": error_msg}, ensure_ascii=False)
        
        # 调用 GPT 解析
        order_json = parse_order(message, menu_names)
        
        # 验证解析结果
        validate_order_json(order_json)
        
        logger.info("订单解析成功")
        return order_json
        
    except Exception as e:
        error_msg = f"订单解析失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return json.dumps({"error": error_msg}, ensure_ascii=False)


def tool_submit_order(order_json: Union[str, Dict[str, Any]]) -> str:
    """LangChain 工具：提交订单到 Loyverse POS
    
    Args:
        order_json: JSON 格式的订单字符串或字典
        
    Returns:
        JSON 格式的提交结果字符串
    """
    logger.info("提交订单到 Loyverse POS")
    
    try:
        # 解析订单数据
        if isinstance(order_json, str):
            try:
                order_data = json.loads(order_json)
            except json.JSONDecodeError as e:
                error_msg = f"订单 JSON 格式无效: {e}"
                logger.error(error_msg)
                return json.dumps({"error": error_msg}, ensure_ascii=False)
        elif isinstance(order_json, dict):
            order_data = order_json
        else:
            error_msg = "订单数据类型无效，必须是字符串或字典"
            logger.error(error_msg)
            return json.dumps({"error": error_msg}, ensure_ascii=False)
        
        # 检查是否有解析错误
        if "error" in order_data:
            logger.warning("订单包含错误信息: %s", order_data["error"])
            return json.dumps(order_data, ensure_ascii=False)
        
        # 验证订单结构
        validate_order_json(json.dumps(order_data, ensure_ascii=False))
        
        # 提交订单
        result = _run_async(create_order(order_data))
        
        logger.info("订单提交成功")
        return json.dumps({
            "success": True,
            "message": "订单提交成功",
            "sale_id": result.get("sale_id"),
            "order_data": order_data
        }, ensure_ascii=False)
        
    except Exception as e:
        error_msg = f"订单提交失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return json.dumps({
            "success": False,
            "error": error_msg
        }, ensure_ascii=False)


def tool_get_menu() -> str:
    """LangChain 工具：获取当前菜单信息
    
    Returns:
        JSON 格式的菜单信息字符串
    """
    logger.info("获取菜单信息")
    
    try:
        menu_data = _run_async(get_menu_items())
        menu_names = get_menu_item_names(menu_data)
        
        return json.dumps({
            "success": True,
            "menu_items": menu_names,
            "total_items": len(menu_names)
        }, ensure_ascii=False)
        
    except Exception as e:
        error_msg = f"获取菜单失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return json.dumps({
            "success": False,
            "error": error_msg
        }, ensure_ascii=False)


# 工具描述（供 LangChain 使用）
TOOL_DESCRIPTIONS = {
    "ParseOrder": "解析客户的自然语言订单消息为标准 JSON 格式。输入：客户订单消息（字符串）。输出：JSON 格式的订单数据。",
    "SubmitOrder": "将解析好的订单提交到 Loyverse POS 系统。输入：JSON 格式的订单数据。输出：提交结果。",
    "GetMenu": "获取当前可用的菜单项目列表。无需输入参数。输出：菜单项目列表。"
}
