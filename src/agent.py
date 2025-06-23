#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
原始代理模块 - 用作Claude代理的后备方案
处理WhatsApp消息的基础逻辑
"""

import os
import logging
import json
import re
from typing import List, Dict, Any, Optional
from tools import search_menu, place_loyverse_order, calculate_order_total

logger = logging.getLogger(__name__)

def handle_message(from_id: str, text: str, history: List[Dict[str, str]]) -> str:
    """
    处理来自用户的消息 - 基础版本
    
    Args:
        from_id: 用户标识符
        text: 用户消息内容  
        history: 对话历史记录
        
    Returns:
        助手回复内容
    """
    try:
        logger.info(f"🔧 Original agent processing message from {from_id}: '{text[:50]}{'...' if len(text) > 50 else ''}'")
        
        # 添加用户消息到历史
        history.append({"role": "user", "content": text})
        
        # 基础响应逻辑
        response = process_basic_message(text, history)
        
        # 添加回复到历史
        history.append({"role": "assistant", "content": response})
        
        logger.info(f"✅ Original agent response sent to {from_id}")
        return response
        
    except Exception as e:
        logger.error(f"❌ Original agent processing error for {from_id}: {e}", exc_info=True)
        return get_error_response()

def process_basic_message(text: str, history: List[Dict[str, str]]) -> str:
    """
    基础消息处理逻辑
    
    Args:
        text: 用户消息
        history: 对话历史
        
    Returns:
        处理后的回复
    """
    text_lower = text.lower().strip()
    
    # 问候处理
    if is_greeting(text_lower):
        return "¡Hola! Bienvenido a Kong Food Restaurant. ¿Qué desea ordenar hoy?"
    
    # 菜单查询
    if any(word in text_lower for word in ['menu', 'carta', 'menú', '菜单']):
        return get_menu_summary()
    
    # 尝试识别订单
    if contains_food_keywords(text_lower):
        return process_potential_order(text, history)
    
    # 帮助信息
    if any(word in text_lower for word in ['help', 'ayuda', '帮助']):
        return get_help_message()
    
    # 默认回复
    return "¿En qué puedo ayudarle hoy? Puede pedirme comida o ver nuestro menú."

def is_greeting(text: str) -> bool:
    """检查是否是问候语"""
    greeting_words = [
        'hola', 'hello', 'hi', 'buenos', 'buenas', 'good', 
        '你好', '您好', 'alo', 'saludos'
    ]
    return any(word in text for word in greeting_words)

def contains_food_keywords(text: str) -> bool:
    """检查是否包含食物关键词"""
    food_keywords = [
        'pollo', 'chicken', 'carne', 'beef', 'arroz', 'rice',
        'combo', 'combinacion', 'sopa', 'soup', 'tostones',
        'quiero', 'want', 'order', 'pedir', '要', '点'
    ]
    return any(keyword in text for keyword in food_keywords)

def get_menu_summary() -> str:
    """获取菜单摘要"""
    try:
        from tools import get_popular_items, format_menu_display
        
        popular_items = get_popular_items(5)
        
        if popular_items:
            formatted_menu = format_menu_display(popular_items)
            return f"🍽️ **Nuestros platos populares:**\n\n{formatted_menu}\n\n¿Qué le gustaría ordenar?"
        else:
            return "🍽️ **Menú disponible:**\n\n• Combinaciones (套餐)\n• MINI Combinaciones (小套餐)\n• Pollo Frito (炸鸡)\n• Arroz Frito (炒饭)\n• Entradas (开胃菜)\n\n¿Qué le gustaría ordenar?"
            
    except Exception as e:
        logger.error(f"Error getting menu summary: {e}")
        return "Tenemos deliciosa comida chino-puertorriqueña. ¿Qué le gustaría ordenar?"

def process_potential_order(text: str, history: List[Dict[str, str]]) -> str:
    """处理潜在的订单"""
    try:
        # 简单的关键词搜索
        search_results = search_menu(text, limit=3)
        
        if search_results:
            if len(search_results) == 1:
                # 只有一个匹配项，直接确认
                item = search_results[0]
                return f"Perfecto, encontré: **{item['item_name']}** (${item['price']:.2f}). ¿Está correcto? ¿Algo más?"
            else:
                # 多个匹配项，让用户选择
                options = []
                for i, item in enumerate(search_results, 1):
                    options.append(f"{i}. **{item['item_name']}** - ${item['price']:.2f}")
                
                options_text = "\n".join(options)
                return f"Encontré estas opciones:\n\n{options_text}\n\n¿Cuál prefiere?"
        else:
            return "Lo siento, no pude encontrar ese plato. ¿Podría decirme qué le gustaría ordenar de otra manera?"
            
    except Exception as e:
        logger.error(f"Error processing potential order: {e}")
        return "¿Qué le gustaría ordenar? Puedo ayudarle a encontrar nuestros platos."

def get_help_message() -> str:
    """获取帮助信息"""
    return """🍜 **Kong Food Restaurant - Ayuda**

Puedo ayudarle con:
• 📋 Ver el menú: diga "menú"
• 🍽️ Hacer pedidos: diga qué plato quiere
• ❓ Información: pregunte sobre nuestros platos

Ejemplos:
• "Quiero pollo teriyaki"
• "2 combinaciones de pollo naranja"
• "¿Qué tienen de sopa?"

¿En qué puedo ayudarle?"""

def get_error_response() -> str:
    """获取错误响应"""
    error_responses = [
        "Disculpe, tuve un problema técnico. ¿Podría repetir su mensaje?",
        "Lo siento, hubo una interrupción. ¿Qué necesita?",
        "Disculpe la inconveniencia. ¿En qué puedo ayudarle?"
    ]
    
    import random
    return random.choice(error_responses)

def extract_items_from_text(text: str) -> List[str]:
    """
    从文本中提取可能的菜品项目
    
    Args:
        text: 用户输入文本
        
    Returns:
        可能的菜品名称列表
    """
    # 简单的分割逻辑
    items = []
    
    # 按逗号分割
    parts = text.split(',')
    for part in parts:
        part = part.strip()
        if part and len(part) > 2:
            items.append(part)
    
    # 如果没有逗号，尝试识别"y"连接词
    if not items:
        parts = re.split(r'\s+y\s+', text, flags=re.IGNORECASE)
        for part in parts:
            part = part.strip()
            if part and len(part) > 2:
                items.append(part)
    
    # 如果还是没有，整个文本作为一个项目
    if not items:
        items = [text.strip()]
    
    return items

def simple_order_parser(text: str) -> List[Dict[str, Any]]:
    """
    简单的订单解析器
    
    Args:
        text: 订单文本
        
    Returns:
        解析的订单项目列表
    """
    try:
        items = extract_items_from_text(text)
        order_items = []
        
        for item_text in items:
            # 提取数量
            quantity = 1
            dish_name = item_text
            
            # 查找数字
            number_match = re.match(r'^(\d+)\s+(.+)', item_text)
            if number_match:
                quantity = int(number_match.group(1))
                dish_name = number_match.group(2)
            
            # 搜索菜单
            search_results = search_menu(dish_name, limit=1)
            if search_results:
                menu_item = search_results[0]
                order_items.append({
                    "variant_id": menu_item["variant_id"],
                    "quantity": quantity,
                    "price": menu_item["price"],
                    "item_name": menu_item["item_name"]
                })
        
        return order_items
        
    except Exception as e:
        logger.error(f"Error parsing order: {e}")
        return []

def check_for_confirmation(text: str) -> bool:
    """检查是否是确认意图"""
    confirmation_words = [
        'sí', 'si', 'yes', 'ok', 'okay', 'correcto', 'correct',
        '是', '对', '好', 'confirmar', 'confirm'
    ]
    
    text_lower = text.lower().strip()
    return any(word in text_lower for word in confirmation_words)

def process_confirmation(history: List[Dict[str, str]]) -> str:
    """处理订单确认"""
    try:
        # 从历史中查找最近的订单信息
        # 这里是简化版本，实际应该有更复杂的状态管理
        
        return "¡Excelente! Su orden ha sido confirmada. ¿Podría proporcionarme su nombre para el pedido?"
        
    except Exception as e:
        logger.error(f"Error processing confirmation: {e}")
        return "Su orden ha sido confirmada. Procesando..."