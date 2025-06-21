"""修复后的 WhatsApp 消息处理模块"""
import json
from typing import Dict, Any
from fastapi import Request
from fastapi.responses import Response
from twilio.twiml.messaging_response import MessagingResponse

from config import settings, constants
from utils.logger import get_logger
from utils.session_store import get_session, reset_session, update_session, cleanup_expired_sessions
from utils.validators import (
    validate_user_message, validate_user_id, validate_customer_name,
    validate_twilio_form_data, ValidationError, sanitize_for_logging
)
from loyverse_api import create_customer, create_ticket
from gpt_tools import tool_parse_order

logger = get_logger(__name__)

# 全局计数器，用于定期清理
_request_counter = 0


def _is_finish_msg(text: str) -> bool:
    """检查是否为结束消息"""
    if not text:
        return False
    
    text_lower = text.lower().strip()
    return any(
        text_lower.startswith(keyword) or text_lower == keyword 
        for keyword in constants.TERMINATION_KEYWORDS
    )


def _items_to_text(items: list) -> str:
    """将订单项目转换为文本格式"""
    if not items:
        return "无项目"
    
    lines = []
    for item in items:
        name = item.get('name', '未知商品')
        quantity = item.get('quantity', 1)
        lines.append(f"- {name} x{quantity}")
    
    return "\n".join(lines)


def _calculate_prep_time(items: list) -> int:
    """计算准备时间"""
    if not items:
        return settings.default_prep_time_minutes
    
    # 计算主菜数量（排除配菜和额外项目）
    main_items = [
        item for item in items 
        if not any(keyword in item.get('name', '').lower() 
                  for keyword in ['acompañantes', 'aparte', 'extra', 'salsa', 'sin', 'poco'])
    ]
    
    if len(main_items) >= settings.large_order_threshold:
        return settings.large_order_prep_time_minutes
    else:
        return settings.default_prep_time_minutes


async def _process_business_logic(user_id: str, user_message: str) -> str:
    """核心业务逻辑处理 - 基于状态机的对话流程"""
    try:
        sess = get_session(user_id)
        stage = sess["stage"]
        
        logger.debug("用户 %s 当前阶段: %s", user_id, stage)
        
        # Stage 1: 初始问候
        if stage == constants.ORDER_STAGE_GREETING:
            update_session(user_id, {"stage": constants.ORDER_STAGE_CAPTURE})
            return constants.GREETING_MESSAGE
        
        # Stage 2: 收集菜品循环
        elif stage == constants.ORDER_STAGE_CAPTURE:
            if _is_finish_msg(user_message):
                if not sess.get("items"):
                    return constants.EMPTY_ORDER_MESSAGE
                
                update_session(user_id, {"stage": constants.ORDER_STAGE_NAME})
                return constants.NAME_REQUEST_MESSAGE
            
            # 解析订单
            try:
                order_json = tool_parse_order(user_message)
                order_data = json.loads(order_json)
            except Exception as e:
                logger.warning("订单解析失败 (用户: %s): %s", user_id, str(e))
                return constants.CLARIFICATION_MESSAGE
            
            # 检查解析结果
            items = order_data.get("items", []) if isinstance(order_data, dict) else []
            if not items:
                return constants.CLARIFICATION_MESSAGE
            
            # 添加到会话
            current_items = sess.get("items", [])
            current_items.extend(items)
            update_session(user_id, {"items": current_items})
            
            # 确认添加的第一个项目
            first_item = items[0]
            item_name = first_item.get('name', '商品')
            quantity = first_item.get('quantity', 1)
            
            return f"Perfecto, {item_name} x{quantity}. ¿Algo más?"
        
        # Stage 3: 获取客户姓名
        elif stage == constants.ORDER_STAGE_NAME:
            try:
                clean_name = validate_customer_name(user_message)
            except ValidationError as e:
                logger.warning("姓名验证失败 (用户: %s): %s", user_id, e.message)
                return "Por favor, indique un nombre válido."
            
            # 创建客户记录
            try:
                customer_id = await create_customer(name=clean_name, phone=user_id)
                update_session(user_id, {
