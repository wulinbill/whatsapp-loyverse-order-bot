"""LangChain 工具封装模块 - 修复版"""
import asyncio, json, logging
from typing import Any, Dict, List, Union

from loyverse_api import get_menu_items, create_order
from gpt_parser import parse_order, validate_order_json
from utils.logger import logger


# ---------- 辅助 ---------- #
def _run(coro):
    """在同步环境里执行协程，避免事件循环冲突"""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


# ---------- Tool: 获取菜单 ---------- #
async def _async_get_menu() -> Dict[str, Any]:
    return await get_menu_items()


def tool_get_menu(_input: str = "") -> str:  # ← 必须接收 1 个参数
    """
    获取并返回当前菜单 JSON 字符串
    LangChain 会始终传入一个位置参数（可能为空字符串）
    """
    try:
        menu = _run(_async_get_menu())
        items = menu.get("items", [])
        names = [i.get("name") for i in items if "name" in i]
        return json.dumps({"success": True,
                           "total": len(names),
                           "items": names}, ensure_ascii=False)
    except Exception as e:
        logger.exception("获取菜单失败: %s", e)
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


# ---------- Tool: 解析订单 ---------- #
def tool_parse_order(message: str) -> str:
    """把顾客消息解析为标准订单 JSON"""
    try:
        menu = _run(_async_get_menu())
        names = [i["name"] for i in menu.get("items", [])]
        order_json = parse_order(message, names)
        validate_order_json(order_json)
        return order_json
    except Exception as e:
        logger.exception("订单解析失败: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ---------- Tool: 提交订单 ---------- #
async def _async_submit(order: Dict[str, Any]):
    return await create_order(order)


def tool_submit_order(order: Union[str, Dict[str, Any]]) -> str:
    """提交订单到 Loyverse POS"""
    try:
        if isinstance(order, str):
            order = json.loads(order)
        validate_order_json(json.dumps(order, ensure_ascii=False))
        res = _run(_async_submit(order))
        return json.dumps({"success": True, "result": res}, ensure_ascii=False)
    except Exception as e:
        logger.exception("订单提交失败: %s", e)
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


# ---------- 描述，供 LangChain 注册 ---------- #
TOOL_DESCRIPTIONS = {
    "GetMenu": "获取当前菜单列表；无输入，返回 JSON",
    "ParseOrder": "解析顾客自然语言为订单 JSON；输入: 顾客消息",
    "SubmitOrder": "提交订单到 Loyverse；输入: 订单 JSON"
}
