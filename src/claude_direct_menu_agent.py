#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude 4直接菜单匹配代理 - 最终修复版
重新设计确认检测和JSON输出逻辑
"""

import os
import json
import pathlib
import logging
import re
from typing import List, Dict, Any, Optional

try:
    from claude_client import ClaudeClient
    from tools import load_menu_data, place_loyverse_order, calculate_order_total
except ImportError as e:
    import sys
    logger = logging.getLogger(__name__)
    logger.error(f"Import error: {e}")
    sys.path.insert(0, os.path.dirname(__file__))
    from claude_client import ClaudeClient
    from tools import load_menu_data, place_loyverse_order, calculate_order_total

logger = logging.getLogger(__name__)

def build_claude_menu_context() -> str:
    """为Claude 4构建完整的菜单上下文"""
    try:
        menu_data = load_menu_data()
        menu_context = "\n## 🍽️ KONG FOOD RESTAURANT 完整菜单:\n\n"
        
        # 按类别整理菜单
        categories_info = {
            "Combinaciones": {
                "emoji": "🍽️",
                "description": "主要套餐 - 包含: 炒饭 + 炸土豆丝",
                "price_range": "$10.29-$12.99"
            },
            "MINI Combinaciones": {
                "emoji": "🥘", 
                "description": "小份套餐 - 包含: 米饭 + 土豆丝",
                "price_range": "$9.29"
            },
            "Pollo Frito": {
                "emoji": "🍗",
                "description": "单纯炸鸡配薯条",
                "price_range": "$3.75-$36.89"
            }
        }
        
        # 为每个类别生成详细信息
        for category_name, category_info in categories_info.items():
            emoji = category_info["emoji"]
            description = category_info["description"]
            price_range = category_info["price_range"]
            
            menu_context += f"### {emoji} {category_name.upper()} ({price_range})\n"
            menu_context += f"*{description}*\n\n"
            
            # 收集该类别的项目
            category_items = []
            for cat_key, cat_data in menu_data.get("menu_categories", {}).items():
                if isinstance(cat_data, dict):
                    cat_display_name = cat_data.get("name", cat_key)
                    if cat_display_name == category_name:
                        items = cat_data.get("items", [])
                        for item in items:
                            if item.get("price", 0) > 0:
                                category_items.append(item)
            
            if category_items:
                # 显示主要项目
                for item in category_items[:5]:  # 只显示前5个避免过长
                    name = item.get("item_name", "")
                    price = item.get("price", 0.0)
                    menu_context += f"**{name}** - ${price:.2f}\n"
                
                menu_context += "\n---\n\n"
        
        return menu_context
        
    except Exception as e:
        logger.error(f"Error building menu context: {e}")
        return "\n## MENÚ: Error loading menu\n\n"

def create_improved_claude_prompt() -> str:
    """创建改进的Claude提示 - 强调JSON输出"""
    menu_section = build_claude_menu_context()
    
    prompt = f"""
你是Kong Food Restaurant的智能订餐助手。

{menu_section}

## 🎯 核心任务: 准确识别菜品并在确认后输出JSON

### 📋 严格流程:

#### ① 欢迎
"¡Hola! Restaurante Kong Food. ¿Qué desea ordenar hoy?"

#### ② 识别菜品
直接从上面菜单匹配用户说的菜品:
- "Combinaciones 2 presa pollo" → "¡Perfecto! Combinaciones 2 presa pollo ($10.29). ¿Algo más?"
- "pollo naranja" → "¡Perfecto! Pollo Naranja ($11.89). ¿Algo más?"

#### ③ 确认订单
当用户说完所有菜品后:
"Confirmo su pedido:
- [菜品列表]
¿Está correcto para procesar?"

#### ④ **关键步骤** - JSON输出
**当用户确认时 (说任何确认词如: si, sí, yes, ok, correcto, bien, listo, vale)，立即输出JSON:**

##JSON##
然后紧接着输出: 
{{"sentences":["1 Combinaciones 2 presa pollo"]}}

**重要**: 
- 使用菜单中的确切名称
- 包含数量 + 完整菜品名
- 必须在确认后立即输出
- 不要添加其他文字

#### ⑤ 系统自动处理
JSON输出后系统会自动处理订单并显示收据。

### ⚠️ 关键规则:

✅ **确认后必须做**:
1. 检测到确认词 (si, sí, yes, ok, correcto, bien, listo, vale)
2. 立即输出: ##JSON##
3. 立即输出: {{"sentences":["数量 菜品名"]}}
4. 等待系统处理

❌ **绝不做**:
- 确认后不输出JSON
- 重新开始对话
- 添加JSON后的额外文字

### 💡 完整示例:

用户: "Combinaciones 2 presa pollo"
你: "¡Perfecto! Combinaciones 2 presa pollo ($10.29). ¿Algo más?"

用户: "Es todo"
你: "Confirmo su pedido: - Combinaciones 2 presa pollo ($10.29) ¿Está correcto para procesar?"

用户: "Si"
你: ##JSON##
{{"sentences":["1 Combinaciones 2 presa pollo"]}}

记住: 确认后的JSON输出是触发订单处理的唯一方式！
"""
    
    return prompt

class ClaudeDirectMenuAgentFinal:
    """Claude 4直接菜单处理代理 - 最终修复版"""
    
    def __init__(self):
        self.claude_client = ClaudeClient()
        self.system_prompt = create_improved_claude_prompt()
        
        logger.info("🧠 Claude 4 Direct Menu Agent (Final Fix) initialized")

    def handle_message(self, from_id: str, text: str, history: List[Dict[str, str]]) -> str:
        """处理消息 - 重新设计的逻辑"""
        try:
            logger.info(f"🧠 Processing: '{text}' for {from_id}")
            
            # 添加用户消息到历史
            history.append({"role": "user", "content": text})
            
            # **关键修改**: 先检查是否是确认，如果是则强制处理JSON
            if self.is_confirmation_message(text, history):
                logger.info("🎯 CONFIRMATION DETECTED - Processing order")
                return self.handle_confirmation_and_order(history, from_id)
            
            # 否则正常处理对话
            return self.handle_normal_message(history)
            
        except Exception as e:
            logger.error(f"❌ Error processing message: {e}", exc_info=True)
            return "Disculpe, hubo un error técnico. ¿Podría repetir su mensaje?"

    def is_confirmation_message(self, text: str, history: List[Dict[str, str]]) -> bool:
        """检测是否是确认消息 - 简化逻辑"""
        text_clean = text.lower().strip()
        
        # 确认词列表
        confirmation_words = [
            'si', 'sí', 'yes', 'ok', 'okay', 'correcto', 'correct', 
            'bien', 'perfecto', 'listo', 'vale', 'procesar', 'confirmar',
            '是', '对', '好', '确认'
        ]
        
        # 检查是否包含确认词
        has_confirmation_word = any(word == text_clean or word in text_clean.split() for word in confirmation_words)
        
        # 检查上下文 - 最近是否有确认请求
        has_confirmation_context = False
        if len(history) >= 2:
            # 检查最后几条助手消息
            for msg in reversed(history[-4:]):  # 检查最近4条消息
                if msg.get("role") == "assistant":
                    content = msg.get("content", "").lower()
                    if any(phrase in content for phrase in [
                        "está correcto", "correcto para procesar", "confirmo su pedido",
                        "¿está bien?", "para procesar", "¿correcto?"
                    ]):
                        has_confirmation_context = True
                        break
        
        result = has_confirmation_word and has_confirmation_context
        
        logger.info(f"🔍 Confirmation check: text='{text}', word={has_confirmation_word}, context={has_confirmation_context}, result={result}")
        
        return result

    def handle_confirmation_and_order(self, history: List[Dict[str, str]], from_id: str) -> str:
        """处理确认并直接处理订单"""
        try:
            logger.info("🛒 Handling confirmation and processing order")
            
            # 从历史中提取订单信息
            order_items = self.extract_order_items_from_history(history)
            
            if not order_items:
                logger.warning("No order items found in history")
                return "Lo siento, no pude encontrar los detalles de su pedido. ¿Podría repetir su orden?"
            
            logger.info(f"📋 Extracted order items: {order_items}")
            
            # 转换为POS格式
            pos_items = self.convert_items_to_pos_format(order_items)
            
            if not pos_items:
                logger.warning("Failed to convert items to POS format")
                return "No pude procesar los items del pedido. ¿Podría verificar su orden?"
            
            # 直接提交到POS系统
            receipt_number = place_loyverse_order(pos_items)
            
            # 计算总金额
            order_totals = calculate_order_total(pos_items)
            actual_total = order_totals["total"]
            
            # 生成确认消息
            confirmation = self.generate_final_confirmation(
                pos_items, actual_total, receipt_number
            )
            
            logger.info(f"✅ Order processed successfully: Receipt #{receipt_number}, Total: ${actual_total:.2f}")
            
            # 添加助手回复到历史
            history.append({"role": "assistant", "content": confirmation})
            
            return confirmation
            
        except Exception as e:
            logger.error(f"❌ Error handling confirmation and order: {e}", exc_info=True)
            return "Hubo un error procesando su orden. Por favor intente nuevamente."

    def extract_order_items_from_history(self, history: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """从对话历史中提取订单项目"""
        order_items = []
        
        try:
            # 查找确认订单的消息
            for msg in reversed(history):
                if msg.get("role") == "assistant":
                    content = msg.get("content", "")
                    
                    if "confirmo su pedido" in content.lower():
                        # 提取项目列表
                        lines = content.split('\n')
                        for line in lines:
                            line = line.strip()
                            if line.startswith('-') or line.startswith('•'):
                                # 解析: "- *1 Combinaciones 2 presa pollo* ($10.29)"
                                item_text = line[1:].strip()
                                
                                # 移除格式字符
                                item_text = item_text.replace('*', '').strip()
                                
                                # 提取名称（去掉价格）
                                if '(' in item_text and '$' in item_text:
                                    name_part = item_text.split('(')[0].strip()
                                    
                                    # 解析数量
                                    quantity = 1
                                    dish_name = name_part
                                    
                                    # 检查是否有数量前缀
                                    if name_part and name_part[0].isdigit():
                                        parts = name_part.split(' ', 1)
                                        if len(parts) >= 2 and parts[0].isdigit():
                                            quantity = int(parts[0])
                                            dish_name = parts[1].strip()
                                    
                                    order_items.append({
                                        "quantity": quantity,
                                        "name": dish_name
                                    })
                        
                        if order_items:
                            break
            
            # 如果没找到确认消息，尝试从对话中提取
            if not order_items:
                order_items = self.extract_from_conversation_flow(history)
            
            logger.info(f"📋 Extracted order items: {order_items}")
            return order_items
            
        except Exception as e:
            logger.error(f"Error extracting order items: {e}")
            return []

    def extract_from_conversation_flow(self, history: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """从对话流程中提取订单"""
        order_items = []
        
        try:
            # 查找助手确认的菜品
            for msg in history:
                if msg.get("role") == "assistant":
                    content = msg.get("content", "")
                    
                    # 查找 "¡Perfecto! [菜品] ($价格)" 模式
                    if "perfecto" in content.lower() and "$" in content:
                        # 使用正则提取菜品名
                        import re
                        pattern = r'perfecto.*?([A-Za-z][^($]*?)\s*\(\$[\d.]+\)'
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        
                        for match in matches:
                            dish_name = match.strip().replace('*', '').replace('!', '')
                            if dish_name:
                                order_items.append({
                                    "quantity": 1,
                                    "name": dish_name
                                })
            
            # 去重
            unique_items = []
            seen = set()
            for item in order_items:
                key = item["name"].lower()
                if key not in seen:
                    seen.add(key)
                    unique_items.append(item)
            
            return unique_items
            
        except Exception as e:
            logger.error(f"Error extracting from conversation: {e}")
            return []

    def convert_items_to_pos_format(self, order_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """转换为POS格式"""
        try:
            menu_data = load_menu_data()
            pos_items = []
            
            # 构建菜单映射
            menu_map = {}
            for category in menu_data.get("menu_categories", {}).values():
                if isinstance(category, dict) and "items" in category:
                    for item in category["items"]:
                        item_name = item.get("item_name", "")
                        if item_name:
                            menu_map[item_name.lower()] = item
            
            for order_item in order_items:
                dish_name = order_item["name"]
                quantity = order_item["quantity"]
                
                # 查找匹配的菜单项目
                menu_item = None
                
                # 精确匹配
                if dish_name.lower() in menu_map:
                    menu_item = menu_map[dish_name.lower()]
                else:
                    # 部分匹配
                    for menu_name, item in menu_map.items():
                        if dish_name.lower() in menu_name or menu_name in dish_name.lower():
                            menu_item = item
                            break
                
                if menu_item:
                    pos_items.append({
                        "variant_id": menu_item["variant_id"],
                        "quantity": quantity,
                        "price": menu_item["price"],
                        "item_name": menu_item["item_name"]
                    })
                    logger.info(f"✅ Matched: '{dish_name}' → {menu_item['item_name']}")
                else:
                    logger.warning(f"❌ No match found for: '{dish_name}'")
            
            return pos_items
            
        except Exception as e:
            logger.error(f"Error converting to POS format: {e}")
            return []

    def generate_final_confirmation(self, pos_items: List[Dict], total: float, receipt_number: str) -> str:
        """生成最终确认消息"""
        try:
            confirmation = "✅ Su orden ha sido procesada exitosamente:\n\n"
            
            # 订单项目
            for item in pos_items:
                quantity = item["quantity"]
                name = item["item_name"]
                confirmation += f"• {quantity}x {name}\n"
            
            # 总金额和收据
            confirmation += f"\n💰 **Total con impuesto: ${total:.2f}**\n"
            confirmation += f"🧾 Número de recibo: #{receipt_number}\n\n"
            
            # 准备时间
            total_items = sum(item["quantity"] for item in pos_items)
            prep_time = "15 minutos" if total_items >= 3 else "10 minutos"
            confirmation += f"⏰ Su orden estará lista en {prep_time}.\n\n"
            
            confirmation += "¡Muchas gracias por su preferencia! 🍽️"
            
            return confirmation
            
        except Exception as e:
            logger.error(f"Error generating confirmation: {e}")
            return f"Su orden ha sido procesada. Total: ${total:.2f}, Recibo: #{receipt_number}."

    def handle_normal_message(self, history: List[Dict[str, str]]) -> str:
        """处理正常对话消息"""
        try:
            # 构建对话上下文
            messages = [
                {"role": "system", "content": self.system_prompt}
            ] + history
            
            # 调用Claude
            reply = self.claude_client.chat(
                messages, 
                max_tokens=2000,
                temperature=0.1
            )
            
            # 添加回复到历史
            history.append({"role": "assistant", "content": reply})
            
            return reply
            
        except Exception as e:
            logger.error(f"Error handling normal message: {e}")
            return "¿En qué puedo ayudarle con su pedido?"

    def get_debug_info(self) -> Dict[str, Any]:
        """获取调试信息"""
        return {
            "type": "claude_direct_menu_agent_final_fix",
            "confirmation_logic": "simplified_and_reliable",
            "order_processing": "direct_pos_integration",
            "json_output": "bypassed_for_reliability"
        }

# 全局实例
_claude_direct_agent = None

def get_claude_direct_agent() -> ClaudeDirectMenuAgentFinal:
    """获取Claude直接菜单代理的全局实例"""
    global _claude_direct_agent
    if _claude_direct_agent is None:
        _claude_direct_agent = ClaudeDirectMenuAgentFinal()
    return _claude_direct_agent

def handle_message_claude_direct(from_id: str, text: str, history: List[Dict[str, str]]) -> str:
    """Claude直接菜单匹配的消息处理入口函数"""
    agent = get_claude_direct_agent()
    return agent.handle_message(from_id, text, history)
