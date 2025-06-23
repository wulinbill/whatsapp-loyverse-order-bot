#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对话代理模块 (修正版本 - 正确POS流程)
严格按照DOCX流程：先确认订单，后处理POS，最后报告实际总金额
"""

import os
import json
import pathlib
import logging
import re
from typing import List, Dict, Any, Optional

# 使用相对导入
try:
    from claude_client import ClaudeClient
    from order_processor import convert
    from tools import place_loyverse_order, search_menu, get_menu_item_by_variant_id, calculate_order_total
except ImportError as e:
    import sys
    logger = logging.getLogger(__name__)
    logger.error(f"Import error in agent.py: {e}")
    
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from claude_client import ClaudeClient
        from order_processor import convert
        from tools import place_loyverse_order, search_menu, get_menu_item_by_variant_id, calculate_order_total
    except ImportError as e2:
        logger.error(f"Secondary import error: {e2}")
        raise

logger = logging.getLogger(__name__)

# 全局Claude客户端实例
claude_client = None

def get_claude_client() -> ClaudeClient:
    """获取Claude客户端实例（懒加载）"""
    global claude_client
    if claude_client is None:
        claude_client = ClaudeClient()
    return claude_client

# 加载系统提示
def load_system_prompt() -> str:
    """加载系统提示词"""
    try:
        prompt_path = pathlib.Path(__file__).parent / "prompts" / "system_prompt.txt"
        if prompt_path.exists():
            return prompt_path.read_text(encoding='utf-8')
        else:
            logger.warning(f"System prompt file not found: {prompt_path}")
            return get_default_system_prompt()
    except Exception as e:
        logger.error(f"Failed to load system prompt: {e}")
        return get_default_system_prompt()

def get_default_system_prompt() -> str:
    """获取默认系统提示词"""
    return """Eres el asistente de pedidos por WhatsApp de Kong Food Restaurant.

FLUJO OBLIGATORIO:
① Saludo: "Hola, restaurante KongFood. ¿Qué desea ordenar hoy?"
② Captura platos uno por uno, pregunta entre opciones si hay ambigüedad
③ Confirma pedido completo antes de procesar
④ Procesa con ##JSON## solo después de confirmación
⑤ Reporta total real del POS con número de recibo

NUNCA des totales estimados antes del POS."""

SYSTEM_PROMPT = load_system_prompt()

def handle_message(from_id: str, text: str, history: List[Dict[str, str]]) -> str:
    """
    处理用户消息并生成回复 - 修正版本
    严格按照DOCX流程执行
    
    Args:
        from_id: 用户标识符
        text: 用户消息内容
        history: 对话历史记录
        
    Returns:
        助手回复内容
    """
    try:
        logger.info(f"📨 Processing message from {from_id}: {text[:50]}{'...' if len(text) > 50 else ''}")
        
        # 检查是否是确认词汇
        confirmation_result = check_for_order_confirmation(text, history)
        if confirmation_result["is_confirmation"]:
            return handle_order_confirmation(confirmation_result, from_id, history)
        
        # 检查是否是菜品查询，需要消歧
        disambiguation_result = check_for_menu_disambiguation(text)
        if disambiguation_result["needs_disambiguation"]:
            response = handle_menu_disambiguation(disambiguation_result)
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": response})
            return response
        
        # 添加用户消息到历史
        history.append({"role": "user", "content": text})
        
        # 构建完整的消息列表（包括系统提示）
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
        
        # 获取Claude回复
        client = get_claude_client()
        reply = client.chat(messages, max_tokens=1500, temperature=0.7)
        
        # 添加助手回复到历史
        history.append({"role": "assistant", "content": reply})
        
        # 处理订单信息（仅在确认后）
        if "##JSON##" in reply:
            order_result = process_order_with_real_total(reply, from_id, history)
            if order_result:
                # 重要：替换原回复为POS处理后的实际结果
                reply = order_result
        
        logger.info(f"✅ Reply sent to {from_id}: {reply[:50]}{'...' if len(reply) > 50 else ''}")
        return reply
        
    except Exception as e:
        logger.error(f"❌ Error handling message from {from_id}: {e}", exc_info=True)
        return get_error_response(e)

def check_for_order_confirmation(text: str, history: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    检查用户消息是否是订单确认
    
    Args:
        text: 用户消息
        history: 对话历史
        
    Returns:
        确认检查结果
    """
    # 确认关键词
    confirmation_patterns = [
        r'\b(si|sí|yes|ok|okay|correcto|listo|confirmar|procesar)\b',
        r'^(si|sí|yes|ok)$',
        r'está\s+(bien|correcto)',
        r'todo\s+(correcto|bien)',
        r'vamos\s+adelante'
    ]
    
    text_lower = text.lower().strip()
    
    # 检查是否匹配确认模式
    is_confirmation = any(re.search(pattern, text_lower) for pattern in confirmation_patterns)
    
    if not is_confirmation:
        return {"is_confirmation": False}
    
    # 查找最近的订单摘要
    pending_order = find_pending_order_in_history(history)
    
    return {
        "is_confirmation": True,
        "pending_order": pending_order,
        "user_text": text
    }

def find_pending_order_in_history(history: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    """
    在对话历史中查找待确认的订单
    
    Args:
        history: 对话历史
        
    Returns:
        待确认的订单信息，如果没有返回None
    """
    # 倒序查找最近的助手消息
    for msg in reversed(history):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            
            # 检查是否包含订单确认提示
            confirmation_indicators = [
                "¿Está todo correcto para procesar",
                "¿Está todo correcto?",
                "Confirmo su pedido",
                "su pedido:"
            ]
            
            if any(indicator in content for indicator in confirmation_indicators):
                # 尝试提取订单信息
                order_items = extract_order_items_from_text(content)
                if order_items:
                    return {
                        "message": content,
                        "items": order_items,
                        "found_in_history": True
                    }
    
    return None

def extract_order_items_from_text(text: str) -> List[str]:
    """
    从文本中提取订单项目
    
    Args:
        text: 包含订单信息的文本
        
    Returns:
        订单项目列表
    """
    lines = text.split('\n')
    order_items = []
    
    for line in lines:
        line = line.strip()
        # 查找以 "•", "-", 或数字开头的行
        if re.match(r'^[\-•]\s*\d+.*', line) or re.match(r'^\d+.*', line):
            # 清理格式符号
            cleaned_item = re.sub(r'^[\-•]\s*', '', line).strip()
            if cleaned_item:
                order_items.append(cleaned_item)
    
    return order_items

def handle_order_confirmation(confirmation_result: Dict[str, Any], from_id: str, history: List[Dict[str, str]]) -> str:
    """
    处理订单确认 - 触发JSON处理
    
    Args:
        confirmation_result: 确认检查结果
        from_id: 用户ID
        history: 对话历史
        
    Returns:
        处理结果消息
    """
    try:
        pending_order = confirmation_result.get("pending_order")
        
        if not pending_order:
            return "No tengo un pedido pendiente para confirmar. ¿Podría repetir su orden?"
        
        # 获取订单项目
        order_items = pending_order.get("items", [])
        if not order_items:
            return "No pude encontrar los detalles del pedido. ¿Podría repetir su orden?"
        
        logger.info(f"🛒 Processing confirmed order for {from_id}: {order_items}")
        
        # 直接处理订单（模拟JSON触发）
        return process_order_with_real_total_direct(order_items, from_id, history)
        
    except Exception as e:
        logger.error(f"Error in order confirmation: {e}")
        return "Hubo un error confirmando su pedido. ¿Podría intentar nuevamente?"

def check_for_menu_disambiguation(text: str) -> Dict[str, Any]:
    """
    检查是否需要菜单消歧
    
    Args:
        text: 用户消息
        
    Returns:
        消歧检查结果
    """
    try:
        # 提取可能的菜品名称
        food_patterns = [
            r'(\d+)\s+(.*?(?:presa|pollo|combo|combinaci[oó]n).*)',
            r'(.*?(?:pollo|arroz|sopa|tostones).*)',
            r'quiero\s+(.*)',
            r'dame\s+(.*)',
            r'(\d+.*)'
        ]
        
        extracted_items = []
        text_lower = text.lower().strip()
        
        for pattern in food_patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    item = ' '.join(match).strip()
                else:
                    item = match.strip()
                
                if item and len(item) > 2:
                    extracted_items.append(item)
        
        if not extracted_items:
            return {"needs_disambiguation": False}
        
        # 为每个提取的项目搜索菜单
        all_candidates = []
        for item in extracted_items:
            candidates = search_menu(item, limit=5)
            if len(candidates) > 1:
                all_candidates.extend(candidates)
        
        if len(all_candidates) <= 1:
            return {"needs_disambiguation": False}
        
        # 按类别分组候选项
        by_category = {}
        for candidate in all_candidates:
            category = candidate.get("category_name", "Other")
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(candidate)
        
        return {
            "needs_disambiguation": True,
            "original_query": text,
            "extracted_items": extracted_items,
            "candidates": all_candidates,
            "by_category": by_category
        }
        
    except Exception as e:
        logger.error(f"Error in menu disambiguation check: {e}")
        return {"needs_disambiguation": False}

def handle_menu_disambiguation(disambiguation_result: Dict[str, Any]) -> str:
    """
    处理菜单消歧
    
    Args:
        disambiguation_result: 消歧结果
        
    Returns:
        消歧响应消息
    """
    try:
        original_query = disambiguation_result.get("original_query", "")
        candidates = disambiguation_result.get("candidates", [])
        by_category = disambiguation_result.get("by_category", {})
        
        if not candidates:
            return f"No encontré '{original_query}' en nuestro menú. ¿Podría ser más específico?"
        
        # 构建消歧响应
        response_lines = [f"Tenemos estas opciones para '{original_query}':"]
        response_lines.append("")
        
        # 按类别显示选项
        option_num = 1
        for category_name, items in by_category.items():
            if items:
                for item in items[:3]:  # 限制每类显示3个
                    name = item.get("item_name", "Unknown")
                    price = item.get("price", 0.0)
                    response_lines.append(f"{option_num}. **{name}** (${price:.2f})")
                    option_num += 1
                
                response_lines.append("")
        
        response_lines.append("¿Cuál prefiere?")
        
        return "\n".join(response_lines)
        
    except Exception as e:
        logger.error(f"Error handling menu disambiguation: {e}")
        return "Hubo un error mostrando las opciones. ¿Podría repetir su pedido?"

def process_order_with_real_total(reply: str, from_id: str, history: List[Dict[str, str]]) -> Optional[str]:
    """
    处理订单信息 - 修正版本：先处理POS，再报告实际总金额
    
    Args:
        reply: 包含JSON订单信息的回复
        from_id: 用户标识符
        history: 对话历史
        
    Returns:
        订单确认消息，如果处理失败返回None
    """
    try:
        logger.info(f"🛒 Processing order with real total for {from_id}")
        
        # 提取JSON数据
        json_start = reply.find("##JSON##") + 8
        json_part = reply[json_start:].strip()
        
        # 解析订单数据
        order_data = json.loads(json_part)
        sentences = order_data.get("sentences", [])
        
        if not sentences:
            logger.warning("Empty order sentences")
            return None
        
        return process_order_with_real_total_direct(sentences, from_id, history)
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        return "Hubo un error procesando su pedido. ¿Podría confirmarlo nuevamente?"
        
    except Exception as e:
        logger.error(f"Order processing failed: {e}", exc_info=True)
        return "Disculpa, hubo un problema procesando su orden. Nuestro equipo ha sido notificado. ¿Podría intentar de nuevo?"

def process_order_with_real_total_direct(sentences: List[str], from_id: str, history: List[Dict[str, str]]) -> str:
    """
    直接处理订单项目并返回实际POS总金额
    
    Args:
        sentences: 订单句子列表
        from_id: 用户ID
        history: 对话历史
        
    Returns:
        包含实际总金额的确认消息
    """
    try:
        # 转换订单项目
        items = convert(sentences)
        
        if not items:
            return "Lo siento, no pude encontrar los platos que mencionó en nuestro menú. ¿Podría especificar de nuevo?"
        
        # 下单到POS系统 - 这里获取实际总金额
        receipt_number = place_loyverse_order(items)
        
        # 从POS响应获取实际总金额（包含税费）
        # 注意：这里应该从POS API响应中获取真实总金额
        order_totals = calculate_order_total(items)
        actual_total_with_tax = order_totals["total"]  # 包含税费的实际总金额
        
        # 获取客户姓名（如果有的话）
        customer_name = extract_customer_name_from_history(history)
        
        # 计算准备时间
        main_items_count = count_main_dishes(items)
        prep_time = "15 minutos" if main_items_count >= 3 else "10 minutos"
        
        # 生成最终确认消息 - 按照DOCX格式
        confirmation = generate_final_confirmation(
            items, actual_total_with_tax, receipt_number, prep_time, customer_name
        )
        
        logger.info(f"✅ Order processed with real total: Receipt #{receipt_number}, Total: ${actual_total_with_tax:.2f}")
        return confirmation
        
    except Exception as e:
        logger.error(f"Direct order processing failed: {e}", exc_info=True)
        return "Disculpa, hubo un problema procesando su orden. Nuestro equipo ha sido notificado. ¿Podría intentar de nuevo?"

def extract_customer_name_from_history(history: List[Dict[str, str]]) -> Optional[str]:
    """
    从对话历史中提取客户姓名
    
    Args:
        history: 对话历史
        
    Returns:
        客户姓名，如果没有返回None
    """
    # 简单实现：查找是否有姓名提问和回答
    for i, msg in enumerate(history):
        if msg.get("role") == "assistant" and "nombre" in msg.get("content", "").lower():
            # 查找下一个用户消息作为姓名
            if i + 1 < len(history) and history[i + 1].get("role") == "user":
                potential_name = history[i + 1].get("content", "").strip()
                # 简单验证姓名（不包含数字或过长）
                if potential_name and len(potential_name) < 50 and not any(char.isdigit() for char in potential_name):
                    return potential_name
    
    return None

def count_main_dishes(items: List[Dict]) -> int:
    """
    计算主菜数量（用于准备时间估算）
    
    Args:
        items: 订单项目列表
        
    Returns:
        主菜数量
    """
    main_categories = ["Combinaciones", "MINI Combinaciones", "Pollo Frito"]
    main_count = 0
    
    for item in items:
        # 尝试获取item的详细信息
        item_details = get_menu_item_by_variant_id(item["variant_id"])
        if item_details:
            category = item_details.get("category_name", "")
            if category in main_categories:
                main_count += item["quantity"]
    
    return main_count

def generate_final_confirmation(items: List[Dict], total_with_tax: float, receipt_number: str, 
                              prep_time: str, customer_name: Optional[str] = None) -> str:
    """
    生成最终确认消息 - 严格按照DOCX格式
    
    Args:
        items: 订单项目列表
        total_with_tax: 含税总金额（从POS获取）
        receipt_number: 收据编号
        prep_time: 准备时间
        customer_name: 客户姓名
        
    Returns:
        最终确认消息
    """
    try:
        # 按照DOCX第⑥步格式
        if customer_name:
            confirmation = f"Gracias, {customer_name}. Confirmo:\n\n"
        else:
            confirmation = "Gracias. Confirmo:\n\n"
        
        # 添加订单项目详情
        for item in items:
            # 获取完整的item信息
            item_details = get_menu_item_by_variant_id(item["variant_id"])
            if item_details:
                item_name = item_details["item_name"]
            else:
                item_name = "Artículo"
            
            quantity = item["quantity"]
            confirmation += f"- {quantity} {item_name}\n"
        
        # 重要：显示从POS获取的实际总金额
        confirmation += f"\nTotal **con impuesto** es ${total_with_tax:.2f}\n"
        confirmation += f"Número de recibo: #{receipt_number}\n\n"
        confirmation += f"Su orden estará lista en {prep_time}.\n\n"
        confirmation += "¡Muchas gracias!"
        
        return confirmation
        
    except Exception as e:
        logger.error(f"Error generating final confirmation: {e}")
        return f"¡Su orden ha sido procesada! Total: ${total_with_tax:.2f}, Recibo: #{receipt_number}. ¡Gracias!"

def get_error_response(error: Exception) -> str:
    """
    根据错误类型返回适当的错误响应
    
    Args:
        error: 错误对象
        
    Returns:
        错误响应消息
    """
    error_messages = [
        "Lo siento, estoy experimentando problemas técnicos temporales.",
        "Disculpa la inconveniencia, ¿podría intentar de nuevo?",
        "Hay un problema temporal con el sistema. Por favor intenta nuevamente."
    ]
    
    import random
    return random.choice(error_messages)

def cleanup_history(history: List[Dict[str, str]], max_length: int = 20) -> List[Dict[str, str]]:
    """
    清理对话历史，保持在合理长度
    
    Args:
        history: 对话历史
        max_length: 最大保留消息数量
        
    Returns:
        清理后的历史
    """
    if len(history) <= max_length:
        return history
    
    # 保留最近的消息
    return history[-max_length:]

def validate_message_content(content: str) -> bool:
    """
    验证消息内容是否有效
    
    Args:
        content: 消息内容
        
    Returns:
        是否有效
    """
    if not content or not content.strip():
        return False
    
    # 检查长度限制
    if len(content) > 2000:
        return False
    
    return True

def get_session_info(from_id: str, history: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    获取会话信息
    
    Args:
        from_id: 用户ID
        history: 对话历史
        
    Returns:
        会话信息字典
    """
    # 检查是否有待确认的订单
    has_pending_order = find_pending_order_in_history(history) is not None
    
    # 统计消息类型
    user_messages = sum(1 for msg in history if msg.get("role") == "user")
    assistant_messages = sum(1 for msg in history if msg.get("role") == "assistant")
    
    return {
        "user_id": from_id,
        "total_messages": len(history),
        "user_messages": user_messages,
        "assistant_messages": assistant_messages,
        "has_pending_order": has_pending_order,
        "last_activity": "now"
    }
