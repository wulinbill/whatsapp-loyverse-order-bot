"""LangChain 工具封装模块 - 修复版"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Union

from loyverse_api import get_menu_items, create_order, get_name_to_id_mapping, create_ticket
from gpt_parser import parse_order, validate_order_json, get_menu_item_names
from utils.logger import get_logger

logger = get_logger(__name__)


# ---------- 辅助函数 ---------- #
def _run_async(coro):
    """在同步环境里执行协程，避免事件循环冲突"""
    try:
        return asyncio.run(coro)
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            # 在新线程中创建事件循环
            import concurrent.futures
            
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
                return future.result(timeout=60)
        else:
            raise


def _extract_menu_names_fallback(menu_data: Dict[str, Any]) -> List[str]:
    """备用方案：从菜单数据中提取名称"""
    names = []
    items = menu_data.get("items", [])
    
    for item in items:
        if isinstance(item, dict):
            name = (item.get('name') or 
                   item.get('item_name') or 
                   item.get('title') or 
                   item.get('display_name'))
            if name and isinstance(name, str):
                names.append(name.strip())
    
    return names


# ---------- Tool: 获取菜单 ---------- #
def tool_get_menu(dummy_input: str) -> str:
    """
    获取并返回当前菜单 JSON 字符串
    
    Args:
        dummy_input: 虚拟输入参数（LangChain 单输入工具要求）
        
    Returns:
        JSON 格式的菜单信息字符串
    """
    logger.info("获取菜单信息")
    
    try:
        menu_data = _run_async(get_menu_items())
        
        if not menu_data:
            error_msg = "无法获取菜单数据"
            logger.error(error_msg)
            return json.dumps({"success": False, "error": error_msg}, ensure_ascii=False)
        
        # 尝试使用原始函数获取菜单名称
        menu_names = None
        try:
            menu_names = get_menu_item_names(menu_data)
        except Exception as e:
            logger.warning(f"get_menu_item_names 函数执行失败: {e}")
        
        # 如果原始函数失败，使用备用方案
        if not menu_names:
            menu_names = _extract_menu_names_fallback(menu_data)
        
        # ---- NEW: append alias names from name→id index so GPT sees simplified variants ----
        try:
            alias_names = list(get_name_to_id_mapping().keys())
            # prettify alias names (capitalize words) to match user style
            alias_pretty = [" ".join([w.capitalize() for w in a.split()]) for a in alias_names]
            menu_names = list({*menu_names, *alias_names, *alias_pretty})
        except Exception as _e:
            logger.debug("无法加载别名列表: %s", _e)
        
        if not menu_names:
            error_msg = "无法从菜单数据中提取有效的项目名称"
            logger.error(error_msg)
            return json.dumps({"error": error_msg}, ensure_ascii=False)
        
        logger.info(f"成功获取 {len(menu_names)} 个菜单项目")
        return json.dumps({
            "success": True,
            "total_items": len(menu_names),
            "menu_items": menu_names
        }, ensure_ascii=False)
        
    except Exception as e:
        error_msg = f"获取菜单失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return json.dumps({"success": False, "error": error_msg}, ensure_ascii=False)


# ---------- Tool: 解析订单 ---------- #
def tool_parse_order(message: str) -> str:
    """
    把顾客消息解析为标准订单 JSON
    
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
        menu_data = _run_async(get_menu_items())
        
        if not menu_data:
            error_msg = "无法获取菜单数据"
            logger.error(error_msg)
            return json.dumps({"error": error_msg}, ensure_ascii=False)
        
        # 尝试使用原始函数获取菜单名称
        menu_names = None
        try:
            menu_names = get_menu_item_names(menu_data)
        except Exception as e:
            logger.warning(f"get_menu_item_names 函数执行失败: {e}")
        
        # 如果原始函数失败，使用备用方案
        if not menu_names:
            menu_names = _extract_menu_names_fallback(menu_data)
        
        # ---- NEW: append alias names from name→id index so GPT sees simplified variants ----
        try:
            alias_names = list(get_name_to_id_mapping().keys())
            # prettify alias names (capitalize words) to match user style
            alias_pretty = [" ".join([w.capitalize() for w in a.split()]) for a in alias_names]
            menu_names = list({*menu_names, *alias_names, *alias_pretty})
        except Exception as _e:
            logger.debug("无法加载别名列表: %s", _e)
        
        if not menu_names:
            error_msg = "无法从菜单数据中提取有效的项目名称"
            logger.error(error_msg)
            return json.dumps({"error": error_msg}, ensure_ascii=False)
        
        logger.info(f"成功获取 {len(menu_names)} 个菜单项目名称")
        
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


# ---------- Tool: 提交订单 ---------- #
def tool_submit_order(order_json: str) -> str:
    """
    提交订单到 Loyverse POS 创建待结账票据
    
    Args:
        order_json: JSON 格式的订单字符串（单一输入参数）
        
    Returns:
        JSON 格式的提交结果字符串，包含 ticket_id 字段
    """
    logger.info("提交订单到 Loyverse POS")
    logger.debug("收到的订单数据: %s", order_json)
    
    try:
        # 检查输入是否为空
        if not order_json or not isinstance(order_json, str):
            error_msg = "订单数据不能为空"
            logger.error(error_msg)
            return json.dumps({"success": False, "error": error_msg}, ensure_ascii=False)
        
        order_json = order_json.strip()
        if not order_json:
            error_msg = "订单数据不能为空"
            logger.error(error_msg)
            return json.dumps({"success": False, "error": error_msg}, ensure_ascii=False)
        
        # 解析 JSON 字符串
        try:
            order_data = json.loads(order_json)
        except json.JSONDecodeError as e:
            error_msg = f"订单 JSON 格式无效: {e}"
            logger.error(error_msg)
            logger.error("无效的 JSON 内容: %s", order_json[:200])
            return json.dumps({"success": False, "error": error_msg}, ensure_ascii=False)
        
        # 检查是否有解析错误
        if isinstance(order_data, dict) and "error" in order_data:
            logger.warning("订单包含错误信息: %s", order_data["error"])
            return json.dumps({"success": False, "error": order_data["error"]}, ensure_ascii=False)
        
        # 确保订单数据格式正确
        if not isinstance(order_data, dict):
            error_msg = f"订单数据必须是字典格式，当前类型: {type(order_data)}"
            logger.error(error_msg)
            return json.dumps({"success": False, "error": error_msg}, ensure_ascii=False)
        
        # 验证订单结构
        try:
            validate_order_json(order_json)
        except Exception as e:
            error_msg = f"订单验证失败: {e}"
            logger.error(error_msg)
            return json.dumps({"success": False, "error": error_msg}, ensure_ascii=False)
        
        # NEW: 若 items 为空则直接返回，不调用 POS
        if not order_data.get("items"):
            error_msg = "未能识别任何有效商品，请检查菜单名称或重新下单"
            logger.warning(error_msg)
            return json.dumps({"success": False, "error": error_msg}, ensure_ascii=False)
        
        # 提交订单
        result = _run_async(create_ticket(order_data))
        
        logger.info("订单提交成功")
        return json.dumps({
            "success": True,
            "message": "订单提交成功",
            "ticket_id": result.get("id") if result else None,
            "order_data": order_data
        }, ensure_ascii=False)
        
    except Exception as e:
        error_msg = f"订单提交失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return json.dumps({
            "success": False,
            "error": error_msg
        }, ensure_ascii=False)


# ---------- 工具描述，供 LangChain 注册 ---------- #
TOOL_DESCRIPTIONS = {
    "GetMenu": "获取当前菜单项目列表。输入：任意字符串（忽略）。输出：菜单项目列表的 JSON。",
    "ParseOrder": "解析客户的自然语言订单消息为标准 JSON 格式。输入：客户订单消息（字符串）。输出：JSON 格式的订单数据。",
    "SubmitOrder": "将解析好的订单提交到 Loyverse POS 系统创建待结账票据。输入：订单数据的 JSON 字符串。输出：提交结果，包含 ticket_id。"
}
