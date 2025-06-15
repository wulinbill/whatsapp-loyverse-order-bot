"""LangChain 工具封装模块 - 修复版本"""
import asyncio
import json
from typing import Any, Dict, Union, Optional, List
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


def _extract_menu_names_fallback(menu_data: Dict[str, Any]) -> List[str]:
    """备用方案：手动从菜单数据中提取名称
    
    Args:
        menu_data: 菜单数据字典
        
    Returns:
        菜单项目名称列表
    """
    names = []
    
    if not isinstance(menu_data, dict):
        logger.warning("菜单数据不是字典格式")
        return names
    
    items = menu_data.get('items', [])
    if not items:
        logger.warning("菜单数据中没有 'items' 字段或为空")
        return names
    
    logger.info(f"尝试从 {len(items)} 个菜单项目中提取名称")
    
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            logger.warning(f"菜单项目 {i} 不是字典格式")
            continue
        
        # 尝试不同的名称字段
        name = (item.get('name') or 
                item.get('item_name') or 
                item.get('title') or 
                item.get('display_name'))
        
        if name and isinstance(name, str):
            names.append(name.strip())
        else:
            logger.warning(f"菜单项目 {i} 没有有效的名称字段: {list(item.keys())}")
    
    logger.info(f"成功提取 {len(names)} 个菜单名称")
    return names


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
        logger.debug("开始获取菜单数据...")
        menu_data: Dict[str, Any] = _run_async(get_menu_items())
        logger.debug(f"获取到菜单数据，类型: {type(menu_data)}")
        
        if not menu_data:
            error_msg = "无法获取菜单数据"
            logger.error(error_msg)
            return json.dumps({"error": error_msg}, ensure_ascii=False)
        
        # 尝试使用原始的 get_menu_item_names 函数
        menu_names = None
        try:
            logger.debug("尝试使用 get_menu_item_names 函数...")
            menu_names = get_menu_item_names(menu_data)
            logger.debug(f"get_menu_item_names 返回: {type(menu_names)}, 长度: {len(menu_names) if menu_names else 'None'}")
        except Exception as e:
            logger.warning(f"get_menu_item_names 函数执行失败: {e}")
        
        # 如果原始函数失败或返回空结果，使用备用方案
        if not menu_names:
            logger.info("使用备用方案提取菜单名称...")
            menu_names = _extract_menu_names_fallback(menu_data)
        
        if not menu_names:
            error_msg = "无法从菜单数据中提取有效的项目名称"
            logger.error(error_msg)
            logger.error(f"菜单数据结构: {json.dumps(menu_data, ensure_ascii=False, indent=2)[:500]}...")
            return json.dumps({"error": error_msg}, ensure_ascii=False)
        
        logger.info(f"成功获取 {len(menu_names)} 个菜单项目名称")
        logger.debug(f"菜单项目名称前5个: {menu_names[:5]}")
        
        # 调用 GPT 解析
        logger.debug("开始调用 GPT 解析订单...")
        order_json = parse_order(message, menu_names)
        
        # 验证解析结果
        logger.debug("验证解析结果...")
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


def tool_get_menu(_input: str = "") -> str:
    """LangChain 工具：获取当前菜单信息
    
    Returns:
        JSON 格式的菜单信息字符串
    """
    logger.info("获取菜单信息")
    
    try:
        menu_data = _run_async(get_menu_items())
        
        # 尝试使用原始函数获取菜单名称
        menu_names = None
        try:
            menu_names = get_menu_item_names(menu_data)
        except Exception as e:
            logger.warning(f"get_menu_item_names 函数执行失败: {e}")
        
        # 如果原始函数失败，使用备用方案
        if not menu_names:
            menu_names = _extract_menu_names_fallback(menu_data)
        
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