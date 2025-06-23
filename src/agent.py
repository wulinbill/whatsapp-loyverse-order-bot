#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对话代理模块
处理用户消息和订单逻辑，使用Claude AI进行智能对话
"""

import os
import json
import pathlib
import logging
from typing import List, Dict, Any, Optional

# 使用相对导入
try:
    from claude_client import ClaudeClient
    from order_processor import convert
    from tools import place_loyverse_order
except ImportError as e:
    # 如果相对导入失败，尝试绝对导入
    import sys
    logger = logging.getLogger(__name__)
    logger.error(f"Import error in agent.py: {e}")
    logger.error(f"Current directory: {os.getcwd()}")
    logger.error(f"Python path: {sys.path}")
    
    # 尝试从src目录导入
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from claude_client import ClaudeClient
        from order_processor import convert
        from tools import place_loyverse_order
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
        return prompt_path.read_text(encoding='utf-8')
    except Exception as e:
        logger.error(f"Failed to load system prompt: {e}")
        return get_default_system_prompt()

def get_default_system_prompt() -> str:
    """获取默认系统提示词"""
    return """Eres el asistente de pedidos por WhatsApp de Kong Food Restaurant.

Responsabilidades:
1. Ayudar a los clientes a hacer pedidos del menú
2. Confirmar cantidades y detalles de cada plato
3. Manejar modificaciones especiales
4. Resumir el pedido completo

Cuando el cliente confirme su orden, termina con:
##JSON##{"sentences":["cantidad item", "cantidad item"]}"""

SYSTEM_PROMPT = load_system_prompt()

def handle_message(from_id: str, text: str, history: List[Dict[str, str]]) -> str:
    """
    处理用户消息并生成回复
    
    Args:
        from_id: 用户标识符
        text: 用户消息内容
        history: 对话历史记录
        
    Returns:
        助手回复内容
    """
    try:
        logger.info(f"📨 Processing message from {from_id}: {text[:50]}{'...' if len(text) > 50 else ''}")
        
        # 添加用户消息到历史
        history.append({"role": "user", "content": text})
        
        # 构建完整的消息列表（包括系统提示）
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
        
        # 获取Claude回复
        client = get_claude_client()
        reply = client.chat(messages, max_tokens=1500, temperature=0.7)
        
        # 添加助手回复到历史
        history.append({"role": "assistant", "content": reply})
        
        # 处理订单信息
        if "##JSON##" in reply:
            order_result = process_order(reply, from_id)
            if order_result:
                reply = order_result
        
        logger.info(f"✅ Reply sent to {from_id}: {reply[:50]}{'...' if len(reply) > 50 else ''}")
        return reply
        
    except Exception as e:
        logger.error(f"❌ Error handling message from {from_id}: {e}", exc_info=True)
        return get_error_response(e)

def process_order(reply: str, from_id: str) -> Optional[str]:
    """
    处理订单信息
    
    Args:
        reply: 包含JSON订单信息的回复
        from_id: 用户标识符
        
    Returns:
        订单确认消息，如果处理失败返回None
    """
    try:
        logger.info(f"🛒 Processing order for {from_id}")
        
        # 提取JSON数据
        json_start = reply.find("##JSON##") + 8
        json_part = reply[json_start:].strip()
        
        # 解析订单数据
        order_data = json.loads(json_part)
        sentences = order_data.get("sentences", [])
        
        if not sentences:
            logger.warning("Empty order sentences")
            return None
        
        # 转换订单项目
        items = convert(sentences)
        
        if not items:
            logger.warning("No valid items found in order")
            return "Lo siento, no pude encontrar los platos que mencionaste en nuestro menú. ¿Podrías especificar de nuevo?"
        
        # 下单到POS系统
        receipt_number = place_loyverse_order(items)
        
        # 计算总价
        total_price = sum(item["price"] * item["quantity"] for item in items) / 100
        
        # 生成确认消息
        confirmation = generate_order_confirmation(items, total_price, receipt_number)
        
        logger.info(f"✅ Order processed successfully for {from_id}: Receipt #{receipt_number}")
        return confirmation
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        return "Hubo un error procesando tu pedido. ¿Podrías confirmarlo nuevamente?"
        
    except Exception as e:
        logger.error(f"Order processing failed: {e}", exc_info=True)
        return "Disculpa, hubo un problema procesando tu orden. Nuestro equipo ha sido notificado. ¿Podrías intentar de nuevo?"

def generate_order_confirmation(items: List[Dict], total_price: float, receipt_number: str) -> str:
    """
    生成订单确认消息
    
    Args:
        items: 订单项目列表
        total_price: 总价格
        receipt_number: 收据编号
        
    Returns:
        订单确认消息
    """
    try:
        confirmation = "🎉 ¡Perfecto! Tu orden ha sido procesada exitosamente.\n\n"
        confirmation += "📋 **Resumen de tu pedido:**\n"
        
        # 添加订单项目详情
        for item in items:
            item_name = item.get("name", "Artículo")  # 如果有名称信息
            quantity = item["quantity"]
            price = item["price"] / 100  # 转换为美元
            confirmation += f"• {quantity}x {item_name} - ${price:.2f}\n"
        
        confirmation += f"\n💰 **Total: ${total_price:.2f}**\n"
        confirmation += f"🧾 **Número de recibo: #{receipt_number}**\n\n"
        confirmation += "⏰ Tu orden será preparada en aproximadamente 15-20 minutos.\n"
        confirmation += "🍜 ¡Gracias por elegir Kong Food Restaurant!"
        
        return confirmation
        
    except Exception as e:
        logger.error(f"Error generating confirmation: {e}")
        return f"¡Tu orden ha sido procesada! Total: ${total_price:.2f}, Recibo: #{receipt_number}. ¡Gracias!"

def get_error_response(error: Exception) -> str:
    """
    根据错误类型返回适当的错误响应
    
    Args:
        error: 错误对象
        
    Returns:
        错误响应消息
    """
    # 可以根据不同类型的错误返回不同的消息
    error_messages = [
        "Lo siento, estoy experimentando problemas técnicos temporales.",
        "Disculpa la inconveniencia, ¿podrías intentar de nuevo?",
        "Hay un problema temporal con el sistema. Nuestro equipo está trabajando para solucionarlo."
    ]
    
    # 简单的随机选择错误消息
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
    return {
        "user_id": from_id,
        "message_count": len(history),
        "last_activity": "now",
        "has_active_order": "##JSON##" in str(history[-5:]) if history else False
    }
