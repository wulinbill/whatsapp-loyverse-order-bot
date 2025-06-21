"""修复后的 LangChain 工具封装模块"""
import json
import logging
from typing import Any, Dict, List

from config import settings
from utils.logger import get_logger
from utils.validators import validate_json_order, ValidationError
from gpt_parser import (
    parse_order, get_menu_item_names, OrderParsingError, 
    parsing_stats, get_cached_menu_names
)

logger = get_logger(__name__)

# 菜单数据缓存 - 避免重复的异步调用
_menu_cache = {
    "data": None,
    "names": None,
    "timestamp": 0
}

MENU_CACHE_TTL = settings.menu_cache_ttl


def _get_current_timestamp() -> float:
    """获取当前时间戳"""
    import time
    return time.time()


async def _refresh_menu_cache() -> Dict[str, Any]:
    """刷新菜单缓存"""
    global _menu_cache
    
    try:
        # 动态导入避免循环依赖
        from loyverse_api import get_menu_items, get_name_to_id_mapping
        
        logger.debug("刷新菜单缓存")
        menu_data = await get_menu_items()
        
        if not menu_data:
            raise ValueError("无法获取菜单数据")
        
        # 提取菜单名称
        menu_names = get_cached_menu_names(menu_data)
        
        # 添加别名映射的名称
        try:
            alias_mapping = get_name_to_id_mapping()
            if alias_mapping:
                alias_names = list(alias_mapping.keys())
                # 美化别名（首字母大写）
                alias_pretty = [
                    " ".join(word.capitalize() for word in alias.split())
                    for alias in alias_names
                ]
                # 合并并去重
                all_names = list(set(menu_names + alias_names + alias_pretty))
                menu_names = all_names
                logger.debug("添加了 %d 个别名", len(alias_names))
        except Exception as e:
            logger.warning("无法获取别名映射: %s", str(e))
        
        # 更新缓存
        _menu_cache = {
            "data": menu_data,
            "names": menu_names,
            "timestamp": _get_current_timestamp()
        }
        
        logger.info("菜单缓存已刷新，包含 %d 个项目", len(menu_names))
        return menu_data
        
    except Exception as e:
        logger.error("刷新菜单缓存失败: %s", str(e))
        raise


def _get_menu_data() -> tuple[Dict[str, Any], List[str]]:
    """获取菜单数据，使用缓存机制
    
    Returns:
        tuple: (menu_data, menu_names)
    """
    current_time = _get_current_timestamp()
    
    # 检查缓存是否有效
    if (_menu_cache["data"] is not None and 
        _menu_cache["names"] is not None and
        current_time - _menu_cache["timestamp"] < MENU_CACHE_TTL):
        
        logger.debug("使用缓存的菜单数据")
        return _menu_cache["data"], _menu_cache["names"]
    
    # 缓存过期或不存在，需要异步刷新
    # 由于这是在同步函数中，我们返回错误信息
    logger.warning("菜单缓存过期，需要异步刷新")
    return None, []


def _extract_menu_names_fallback(menu_data: Dict[str, Any]) -> List[str]:
    """备用方案：从菜单数据中提取名称"""
    if not menu_data:
        return []
    
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
    """获取并返回当前菜单 JSON 字符串
    
    修复版本：移除了异步调用，使用缓存机制
    
    Args:
        dummy_input: 虚拟输入参数（LangChain 单输入工具要求）
        
    Returns:
        JSON 格式的菜单信息字符串
    """
    logger.info("获取菜单信息")
    
    try:
        menu_data, menu_names = _get_menu_data()
        
        if not menu_data or not menu_names:
            error_msg = "菜单缓存不可用，请稍后重试"
            logger.error(error_msg)
            return json.dumps({"success": False, "error": error_msg}, ensure_ascii=False)
        
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
    """把顾客消息解析为标准订单 JSON
    
    修复版本：
    - 移除了异步调用
    - 增强了错误处理
    - 添加了统计记录
    
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
    
    # 记录解析请求
    parsing_stats.record_request()
    
    logger.info("解析订单消息: %s", message[:100])
    
    try:
        # 获取菜单数据
        menu_data, menu_names = _get_menu_data()
        
        if not menu_data or not menu_names:
            error_msg = "菜单数据不可用，请稍后重试"
            logger.error(error_msg)
            parsing_stats.record_failure()
            return json.dumps({"error": error_msg}, ensure_ascii=False)
        
        logger.debug(f"使用 {len(menu_names)} 个菜单项目名称进行解析")
        
        # 调用 GPT 解析
        try:
            order_json = parse_order(message, menu_names)
            
            # 验证解析结果
            validate_json_order(order_json)
            
            parsing_stats.record_success()
            logger.info("订单解析成功")
            return order_json
            
        except OrderParsingError as e:
            parsing_stats.record_failure()
            if e.error_code == "INVALID_JSON_FORMAT" and e.original_error:
                parsing_stats.record_auto_fix()
            
            error_msg = f"订单解析失败: {e.message}"
            logger.warning(error_msg)
            return json.dumps({"error": error_msg}, ensure_ascii=False)
        
    except Exception as e:
        parsing_stats.record_failure()
        error_msg = f"订单解析过程中出现错误: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return json.dumps({"error": error_msg}, ensure_ascii=False)


# ---------- Tool: 提交订单 ---------- #
def tool_submit_order(order_json: str) -> str:
    """提交订单到 Loyverse POS 创建待结账票据
    
    修复版本：移除了不必要的异步包装
    
    Args:
        order_json: JSON 格式的订单字符串
        
    Returns:
        JSON 格式的提交结果字符串，包含 ticket_id 字段
    """
    logger.info("提交订单到 Loyverse POS")
    logger.debug("收到的订单数据长度: %d 字符", len(order_json) if order_json else 0)
    
    try:
        # 检查输入
        if not order_json or not isinstance(order_json, str):
            error_msg = "订单数据不能为空"
            logger.error(error_msg)
            return json.dumps({"success": False, "error": error_msg}, ensure_ascii=False)
        
        order_json = order_json.strip()
        if not order_json:
            error_msg = "订单数据不能为空"
            logger.error(error_msg)
            return json.dumps({"success": False, "error": error_msg}, ensure_ascii=False)
        
        # 验证和解析 JSON
        try:
            order_data = validate_json_order(order_json)
        except ValidationError as e:
            error_msg = f"订单验证失败: {e.message}"
            logger.error(error_msg)
            return json.dumps({"success": False, "error": error_msg}, ensure_ascii=False)
        except Exception as e:
            error_msg = f"订单 JSON 格式无效: {str(e)}"
            logger.error(error_msg)
            return json.dumps({"success": False, "error": error_msg}, ensure_ascii=False)
        
        # 检查是否包含有效项目
        items = order_data.get("items", [])
        if not items:
            error_msg = "未能识别任何有效商品，请检查菜单名称或重新下单"
            logger.warning(error_msg)
            return json.dumps({"success": False, "error": error_msg}, ensure_ascii=False)
        
        logger.info("准备提交包含 %d 个项目的订单", len(items))
        
        # 由于这是一个同步工具函数，我们不能直接调用异步函数
        # 需要返回一个指示，让调用方异步处理
        return json.dumps({
            "success": True,
            "action": "submit_to_pos",
            "order_data": order_data,
            "message": "订单已验证，准备提交到 POS 系统"
        }, ensure_ascii=False)
        
    except Exception as e:
        error_msg = f"订单处理失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return json.dumps({
            "success": False,
            "error": error_msg
        }, ensure_ascii=False)


# ---------- 异步工具函数（供其他模块使用） ---------- #

async def async_tool_get_menu() -> Dict[str, Any]:
    """异步版本的获取菜单工具"""
    try:
        await _refresh_menu_cache()
        menu_data, menu_names = _get_menu_data()
        
        return {
            "success": True,
            "total_items": len(menu_names),
            "menu_items": menu_names,
            "menu_data": menu_data
        }
    except Exception as e:
        logger.error("异步获取菜单失败: %s", str(e))
        return {
            "success": False,
            "error": str(e)
        }


async def async_tool_submit_order(order_data: Dict[str, Any]) -> Dict[str, Any]:
    """异步版本的提交订单工具"""
    try:
        # 动态导入避免循环依赖
        from loyverse_api import create_ticket
        
        logger.info("异步提交订单到 Loyverse POS")
        result = await create_ticket(order_data)
        
        return {
            "success": True,
            "message": "订单提交成功",
            "ticket_id": result.get("id") if result else None,
            "ticket_data": result,
            "order_data": order_data
        }
        
    except Exception as e:
        error_msg = f"异步订单提交失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "error": error_msg
        }


# ---------- 缓存管理函数 ---------- #

async def refresh_menu_cache() -> bool:
    """手动刷新菜单缓存"""
    try:
        await _refresh_menu_cache()
        return True
    except Exception as e:
        logger.error("手动刷新菜单缓存失败: %s", str(e))
        return False


def get_cache_status() -> Dict[str, Any]:
    """获取缓存状态信息"""
    current_time = _get_current_timestamp()
    
    return {
        "has_data": _menu_cache["data"] is not None,
        "has_names": _menu_cache["names"] is not None,
        "items_count": len(_menu_cache["names"]) if _menu_cache["names"] else 0,
        "cache_age_seconds": current_time - _menu_cache["timestamp"],
        "cache_ttl_seconds": MENU_CACHE_TTL,
        "is_expired": current_time - _menu_cache["timestamp"] > MENU_CACHE_TTL,
        "last_update": _menu_cache["timestamp"]
    }


def clear_tool_cache():
    """清除工具缓存"""
    global _menu_cache
    _menu_cache = {
        "data": None,
        "names": None,
        "timestamp": 0
    }
    logger.info("工具缓存已清除")


# ---------- 工具描述，供 LangChain 注册 ---------- #
TOOL_DESCRIPTIONS = {
    "GetMenu": (
        "获取当前菜单项目列表。"
        "输入：任意字符串（忽略）。"
        "输出：形如 {\"success\": True, \"total_items\": ..., \"menu_items\": [...]} 的 JSON。"
    ),
    "ParseOrder": (
        "解析客户的自然语言订单消息为标准 JSON 格式。"
        "输入：客户订单消息（字符串）。"
        "输出：JSON 格式的订单数据，包含 items 和 note 字段。"
    ),
    "SubmitOrder": (
        "验证订单数据并准备提交到 Loyverse POS 系统。"
        "输入：订单数据的 JSON 字符串。"
        "输出：验证结果和提交准备状态。"
    )
}


# ---------- 统计和监控 ---------- #

def get_tools_stats() -> Dict[str, Any]:
    """获取工具使用统计"""
    from gpt_parser import get_parsing_stats
    
    cache_status = get_cache_status()
    parsing_stats_data = get_parsing_stats()
    
    return {
        "cache_status": cache_status,
        "parsing_stats": parsing_stats_data,
        "settings": {
            "cache_ttl": MENU_CACHE_TTL,
            "openai_model": settings.openai_model,
            "openai_temperature": settings.openai_temperature,
            "max_tokens": settings.openai_max_tokens
        }
    }


def reset_tools_stats():
    """重置工具统计"""
    from gpt_parser import reset_parsing_stats
    reset_parsing_stats()
    clear_tool_cache()
    logger.info("工具统计已重置")
