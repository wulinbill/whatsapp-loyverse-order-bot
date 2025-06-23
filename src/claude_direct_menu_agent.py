#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude 4直接菜单匹配代理 - 完整修复版
修复菜单搜索和订单项目丢失问题
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

def build_complete_menu_context() -> str:
    """构建完整的菜单上下文 - 包含所有项目"""
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
            },
            "plato entrada": {
                "emoji": "🥙",
                "description": "开胃菜和汤类",
                "price_range": "$2.79-$9.30"
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
                # 显示所有项目 (特别是汤类)
                for item in category_items:
                    name = item.get("item_name", "")
                    price = item.get("price", 0.0)
                    menu_context += f"**{name}** - ${price:.2f}\n"
                
                menu_context += "\n---\n\n"
        
        return menu_context
        
    except Exception as e:
        logger.error(f"Error building menu context: {e}")
        return "\n## MENÚ: Error loading menu\n\n"

def create_enhanced_claude_prompt() -> str:
    """创建增强的Claude提示 - 包含完整菜单和订单管理"""
    menu_section = build_complete_menu_context()
    
    prompt = f"""
你是Kong Food Restaurant的智能订餐助手。

{menu_section}

## 🎯 核心任务: 准确识别菜品并管理订单

### 📋 处理流程:

#### ① 欢迎
"¡Hola! Restaurante Kong Food. ¿Qué desea ordenar hoy?"

#### ② 智能菜品识别
从上面菜单中匹配用户说的菜品，包括:
- **模糊匹配**: "sopa china" → "Sopa China Pequeñas" 或 "Sopa China Grandes"
- **部分匹配**: "sopa" → 显示所有汤类选项
- **数量识别**: "15 presas pollo" → "15 Presas de Pollo con Papas"

**示例处理:**
- "sopa china" → "Tenemos Sopa China Pequeñas ($5.69) y Sopa China Grandes ($9.10). ¿Cuál prefiere?"
- "15 presas pollo" → "¡Perfecto! 15 Presas de Pollo con Papas ($27.89). ¿Algo más?"

#### ③ 订单累积管理
**重要**: 管理当前订单状态，累积所有项目:
- 第一个项目: "Su pedido actual: - [项目1]"
- 添加项目: "Su pedido actualizado: - [项目1] - [项目2]"
- 始终显示完整订单列表

#### ④ 最终确认
当用户说完所有菜品后:
"Confirmo su pedido completo:
- [所有项目列表]
Total estimado: $[总计]
¿Está correcto para procesar?"

#### ⑤ 订单处理
当用户确认时，处理完整订单列表。

### 🔍 菜单搜索规则:

1. **精确匹配**: 直接找到项目
2. **模糊匹配**: 
   - "sopa" → 显示所有汤类
   - "pollo" → 显示所有鸡肉类
3. **数量处理**: 
   - "15 presas" → "15 Presas de Pollo con Papas"
   - "3 tostones" → "Tostones (8 pedazos)" (最接近的)

### 📝 订单状态管理:

**关键**: 始终跟踪和显示完整的订单状态:
- 用户添加项目时，累积到现有订单
- 确认时处理所有累积的项目
- 不要丢失任何已添加的项目

### ⚠️ 重要规则:

✅ **必须做**:
- 识别菜单中的所有项目（包括汤类）
- 累积管理订单状态
- 确认时处理完整订单
- 提供清晰的菜品选项

❌ **避免**:
- 说"没有"某个菜品而不先搜索
- 处理订单时丢失项目
- 重复处理相同订单
- 忽略已添加的项目

记住: 完整准确地管理整个订单过程！
"""
    
    return prompt

class ClaudeCompleteAgent:
    """Claude完整修复版代理"""
    
    def __init__(self):
        self.claude_client = ClaudeClient()
        self.system_prompt = create_enhanced_claude_prompt()
        self.processed_orders = set()  # 跟踪已处理的订单
        
        logger.info("🧠 Claude Complete Agent initialized")

    def handle_message(self, from_id: str, text: str, history: List[Dict[str, str]]) -> str:
        """处理消息 - 完整版本"""
        try:
            logger.info(f"🧠 Processing: '{text}' for {from_id}")
            
            # 添加用户消息到历史
            history.append({"role": "user", "content": text})
            
            # 检查是否是确认并且还没有处理过
            if self.is_confirmation_message(text, history):
                order_hash = self.get_order_hash(history)
                
                if order_hash not in self.processed_orders:
                    logger.info("🎯 CONFIRMATION DETECTED - Processing new order")
                    self.processed_orders.add(order_hash)
                    return self.handle_confirmation_and_order(history, from_id)
                else:
                    logger.info("⏭️ Order already processed, skipping")
                    return "Esta orden ya ha sido procesada. ¿Desea hacer un nuevo pedido?"
            
            # 否则正常处理对话
            return self.handle_normal_message(history)
            
        except Exception as e:
            logger.error(f"❌ Error processing message: {e}", exc_info=True)
            return "Disculpe, hubo un error técnico. ¿Podría repetir su mensaje?"

    def get_order_hash(self, history: List[Dict[str, str]]) -> str:
        """生成订单的唯一标识"""
        try:
            # 提取订单项目
            order_items = self.extract_order_items_from_history(history)
            
            # 创建订单签名
            order_signature = ""
            for item in order_items:
                order_signature += f"{item['quantity']}x{item['name']};"
            
            return hash(order_signature)
        except:
            return ""

    def is_confirmation_message(self, text: str, history: List[Dict[str, str]]) -> bool:
        """检测确认消息"""
        text_clean = text.lower().strip()
        
        # 确认词
        confirmation_words = [
            'si', 'sí', 'yes', 'ok', 'okay', 'correcto', 'correct', 
            'bien', 'perfecto', 'listo', 'vale', 'procesar', 'confirmar',
            '是', '对', '好', '确认'
        ]
        
        has_confirmation_word = any(word == text_clean or word in text_clean.split() for word in confirmation_words)
        
        # 检查上下文
        has_confirmation_context = False
        if len(history) >= 2:
            for msg in reversed(history[-4:]):
                if msg.get("role") == "assistant":
                    content = msg.get("content", "").lower()
                    if any(phrase in content for phrase in [
                        "está correcto", "correcto para procesar", "confirmo su pedido",
                        "¿está bien?", "para procesar", "¿correcto?"
                    ]):
                        has_confirmation_context = True
                        break
        
        result = has_confirmation_word and has_confirmation_context
        logger.info(f"🔍 Confirmation: word={has_confirmation_word}, context={has_confirmation_context}, result={result}")
        
        return result

    def handle_confirmation_and_order(self, history: List[Dict[str, str]], from_id: str) -> str:
        """处理确认并处理完整订单"""
        try:
            logger.info("🛒 Processing complete order")
            
            # 提取所有订单项目
            order_items = self.extract_complete_order_from_history(history)
            
            if not order_items:
                logger.warning("No order items found")
                return "No pude encontrar los detalles de su pedido. ¿Podría repetir su orden?"
            
            logger.info(f"📋 Complete order items: {order_items}")
            
            # 转换为POS格式
            pos_items = self.convert_items_to_pos_format(order_items)
            
            if not pos_items:
                logger.warning("Failed to convert items to POS format")
                return "No pude procesar los items del pedido. ¿Podría verificar su orden?"
            
            # 提交到POS系统
            receipt_number = place_loyverse_order(pos_items)
            
            # 计算总金额
            order_totals = calculate_order_total(pos_items)
            actual_total = order_totals["total"]
            
            # 生成确认消息
            confirmation = self.generate_final_confirmation(
                pos_items, actual_total, receipt_number
            )
            
            logger.info(f"✅ Complete order processed: Receipt #{receipt_number}, Total: ${actual_total:.2f}")
            
            # 添加助手回复到历史
            history.append({"role": "assistant", "content": confirmation})
            
            return confirmation
            
        except Exception as e:
            logger.error(f"❌ Error handling order: {e}", exc_info=True)
            return "Hubo un error procesando su orden. Por favor intente nuevamente."

    def extract_complete_order_from_history(self, history: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """从历史中提取完整订单 - 包括所有累积的项目"""
        order_items = []
        
        try:
            # 查找最近的完整订单确认
            for msg in reversed(history):
                if msg.get("role") == "assistant":
                    content = msg.get("content", "")
                    
                    if "confirmo su pedido" in content.lower():
                        # 提取项目列表
                        lines = content.split('\n')
                        for line in lines:
                            line = line.strip()
                            if line.startswith('-') or line.startswith('•'):
                                # 解析项目行
                                item_text = line[1:].strip()
                                
                                # 移除格式字符
                                item_text = item_text.replace('*', '').strip()
                                
                                # 提取名称和数量
                                if '(' in item_text and '$' in item_text:
                                    name_part = item_text.split('(')[0].strip()
                                    
                                    # 解析数量
                                    quantity = 1
                                    dish_name = name_part
                                    
                                    # 检查数量前缀
                                    words = name_part.split()
                                    if words and words[0].isdigit():
                                        quantity = int(words[0])
                                        dish_name = ' '.join(words[1:])
                                    elif 'x' in name_part:
                                        # 处理 "15x Pollo Frito" 格式
                                        parts = name_part.split('x', 1)
                                        if len(parts) == 2 and parts[0].strip().isdigit():
                                            quantity = int(parts[0].strip())
                                            dish_name = parts[1].strip()
                                    
                                    order_items.append({
                                        "quantity": quantity,
                                        "name": dish_name
                                    })
                        
                        if order_items:
                            break
            
            # 如果没找到确认消息，从对话流程中提取
            if not order_items:
                order_items = self.extract_from_conversation_mentions(history)
            
            logger.info(f"📋 Extracted complete order: {order_items}")
            return order_items
            
        except Exception as e:
            logger.error(f"Error extracting complete order: {e}")
            return []

    def extract_from_conversation_mentions(self, history: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """从对话中提取所有提到的菜品"""
        order_items = []
        
        try:
            # 查找所有助手确认的菜品
            for msg in history:
                if msg.get("role") == "assistant":
                    content = msg.get("content", "")
                    
                    # 查找确认菜品的模式
                    if "perfecto" in content.lower() and "$" in content:
                        # 提取菜品信息
                        import re
                        
                        # 匹配不同的模式
                        patterns = [
                            r'perfecto.*?(\d+)\s*presas.*?pollo.*?\(\$[\d.]+\)',  # "15 presas pollo"
                            r'perfecto.*?([A-Za-z][^($]*?)\s*\(\$[\d.]+\)',      # 一般菜品
                        ]
                        
                        for pattern in patterns:
                            matches = re.findall(pattern, content, re.IGNORECASE)
                            for match in matches:
                                if match.isdigit():
                                    # 数量匹配，这是presas
                                    quantity = int(match)
                                    dish_name = f"{quantity} Presas de Pollo con Papas"
                                    order_items.append({
                                        "quantity": 1,  # 作为一个整体订单
                                        "name": dish_name
                                    })
                                else:
                                    # 菜品名称匹配
                                    dish_name = match.strip().replace('*', '').replace('!', '')
                                    if dish_name:
                                        order_items.append({
                                            "quantity": 1,
                                            "name": dish_name
                                        })
            
            # 去重但保持顺序
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
        """转换为POS格式 - 改进的菜品匹配"""
        try:
            menu_data = load_menu_data()
            pos_items = []
            
            # 构建更完整的菜单映射
            menu_map = {}
            for category in menu_data.get("menu_categories", {}).values():
                if isinstance(category, dict) and "items" in category:
                    for item in category["items"]:
                        item_name = item.get("item_name", "")
                        if item_name:
                            # 精确名称
                            menu_map[item_name.lower()] = item
                            
                            # 关键词匹配
                            keywords = item_name.lower().split()
                            for keyword in keywords:
                                if len(keyword) >= 3:  # 避免太短的词
                                    if keyword not in menu_map:
                                        menu_map[keyword] = []
                                    if isinstance(menu_map[keyword], list):
                                        menu_map[keyword].append(item)
                                    else:
                                        menu_map[keyword] = [menu_map[keyword], item]
            
            for order_item in order_items:
                dish_name = order_item["name"]
                quantity = order_item["quantity"]
                
                logger.info(f"🔍 Looking for: '{dish_name}'")
                
                # 查找匹配的菜单项目
                menu_item = self.find_best_menu_match(dish_name, menu_map)
                
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

    def find_best_menu_match(self, dish_name: str, menu_map: Dict) -> Optional[Dict]:
        """找到最佳菜单匹配"""
        dish_lower = dish_name.lower()
        
        # 1. 精确匹配
        if dish_lower in menu_map and isinstance(menu_map[dish_lower], dict):
            return menu_map[dish_lower]
        
        # 2. 特殊处理：presas de pollo
        if "presas" in dish_lower and "pollo" in dish_lower:
            # 提取数量
            import re
            number_match = re.search(r'(\d+)', dish_lower)
            if number_match:
                number = int(number_match.group(1))
                
                # 查找对应的presas项目
                for item_name, item in menu_map.items():
                    if isinstance(item, dict) and "presas de pollo con papas" in item_name:
                        if str(number) in item_name:
                            return item
        
        # 3. 关键词匹配
        dish_words = dish_lower.split()
        best_match = None
        best_score = 0
        
        for word in dish_words:
            if word in menu_map:
                candidates = menu_map[word]
                if isinstance(candidates, dict):
                    candidates = [candidates]
                elif not isinstance(candidates, list):
                    continue
                
                for candidate in candidates:
                    if isinstance(candidate, dict):
                        # 计算匹配度
                        candidate_name = candidate.get("item_name", "").lower()
                        score = sum(1 for w in dish_words if w in candidate_name)
                        
                        if score > best_score:
                            best_score = score
                            best_match = candidate
        
        # 4. 部分匹配
        if not best_match:
            for item_name, item in menu_map.items():
                if isinstance(item, dict):
                    item_name_lower = item.get("item_name", "").lower()
                    if any(word in item_name_lower for word in dish_words):
                        best_match = item
                        break
        
        return best_match

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
                max_tokens=2500,
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
            "type": "claude_complete_agent",
            "menu_search": "enhanced_fuzzy_matching",
            "order_management": "cumulative_tracking",
            "duplicate_prevention": "order_hash_tracking",
            "processed_orders": len(self.processed_orders)
        }

# 全局实例
_claude_complete_agent = None

def get_claude_direct_agent() -> ClaudeCompleteAgent:
    """获取Claude完整代理的全局实例"""
    global _claude_complete_agent
    if _claude_complete_agent is None:
        _claude_complete_agent = ClaudeCompleteAgent()
    return _claude_complete_agent

def handle_message_claude_direct(from_id: str, text: str, history: List[Dict[str, str]]) -> str:
    """Claude完整代理的消息处理入口函数"""
    agent = get_claude_direct_agent()
    return agent.handle_message(from_id, text, history)
