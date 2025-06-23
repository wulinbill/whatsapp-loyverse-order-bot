#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude 4直接菜单匹配代理 - 修复JSON输出问题
确保Claude在确认后正确输出JSON格式
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
    """
    为Claude 4构建完整的菜单上下文
    """
    try:
        menu_data = load_menu_data()
        menu_context = "\n## 🍽️ KONG FOOD RESTAURANT 完整菜单数据:\n\n"
        
        # 按类别整理菜单
        categories_info = {
            "Combinaciones": {
                "emoji": "🍽️",
                "description": "主要套餐 - 包含: 炒饭 + 炸土豆丝 (可换tostones +$2.69)",
                "price_range": "$10.29-$12.99"
            },
            "MINI Combinaciones": {
                "emoji": "🥘", 
                "description": "小份套餐 - 包含: 米饭 + 土豆丝",
                "price_range": "$9.29"
            },
            "Pollo Frito": {
                "emoji": "🍗",
                "description": "单纯炸鸡配薯条 - 不包含米饭",
                "price_range": "$3.75-$36.89"
            },
            "Arroz Frito": {
                "emoji": "🍚",
                "description": "炒饭单点",
                "price_range": "$4.29-$29.39"
            },
            "plato entrada": {
                "emoji": "🥙",
                "description": "开胃菜和汤",
                "price_range": "$2.79-$9.30"
            },
            "Ofertas Familiares": {
                "emoji": "👨‍👩‍👧‍👦",
                "description": "家庭套餐",
                "price_range": "$23.99-$47.99"
            }
        }
        
        # 为每个类别生成详细信息
        for category_name, category_info in categories_info.items():
            emoji = category_info["emoji"]
            description = category_info["description"]
            price_range = category_info["price_range"]
            
            menu_context += f"### {emoji} {category_name.upper()} ({price_range})\n"
            menu_context += f"*{description}*\n\n"
            
            # 收集该类别的所有项目
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
                # 按价格排序
                category_items.sort(key=lambda x: x.get("price", 0))
                
                # 生成项目列表
                for item in category_items:
                    name = item.get("item_name", "")
                    price = item.get("price", 0.0)
                    variant_id = item.get("variant_id", "")
                    
                    # 基本信息
                    menu_context += f"**{name}** - ${price:.2f} `[ID:{variant_id}]`\n"
                    
                    # 添加别名信息
                    aliases = item.get("aliases", [])
                    keywords = item.get("keywords", [])
                    
                    extra_info = []
                    if aliases:
                        extra_info.append(f"别名: {', '.join(aliases[:3])}")
                    if keywords:
                        extra_info.append(f"关键词: {', '.join(keywords[:3])}")
                    
                    if extra_info:
                        menu_context += f"  _{' | '.join(extra_info)}_\n"
                    
                    menu_context += "\n"
                
                menu_context += "---\n\n"
        
        return menu_context
        
    except Exception as e:
        logger.error(f"Error building Claude menu context: {e}")
        return "\n## MENÚ: Error loading menu data\n\n"

def create_claude_direct_prompt() -> str:
    """
    创建Claude 4直接处理菜单的系统提示
    重点强化JSON输出要求
    """
    menu_section = build_claude_menu_context()
    
    # 避免字符串格式化错误
    json_example = '##JSON##' + '{"sentences":["1 Combinaciones 2 presa pollo"]}'
    
    prompt = f"""
你是Kong Food Restaurant的智能订餐助手，专精中式波多黎各融合料理。

{menu_section}

## 🧠 CLAUDE 4 直接菜单匹配指令:

### 📋 严格流程 - 必须完整执行:

#### ① 欢迎语
"¡Hola! Restaurante Kong Food. ¿Qué desea ordenar hoy?"

#### ② 智能菜品识别
当客户说菜品时，直接从上面菜单匹配。

**示例：**
- 客户: "Combinaciones 2 presa pollo" → 识别: "Combinaciones 2 presa pollo ($10.29)"
- 客户: "pollo naranja" → 识别: "Pollo Naranja ($11.89)"

**歧义处理** - 提供选项：
```
Tenemos estas opciones:
1. **Combinaciones 2 presa pollo** ($10.29) - 套餐含炒饭+薯条
2. **mini Combinaciones 2 Presas de Pollo** ($9.29) - 小份套餐
3. **2 Presas de Pollo con Papas** ($5.79) - 单纯炸鸡
¿Cuál prefiere?
```

#### ③ 确认每个菜品
"Perfecto, [菜品名] ($价格). ¿Algo más?"

#### ④ 最终确认
"Confirmo su pedido:
- [项目列表]
¿Está correcto para procesar?"

#### ⑤ **关键步骤 - JSON输出**
**当客户确认时 (说 "sí", "si", "yes", "correcto", "está bien", "procesar", "confirmar" 等)，必须立即输出JSON:**

{json_example}

**重要规则:**
- 使用菜单中的确切名称
- JSON必须在确认后立即输出
- 不要添加其他文字，直接输出JSON
- 格式必须严格正确

#### ⑥ 等待系统处理
JSON输出后，系统会自动处理订单并返回确认信息。

### 🎯 关键成功要素:

1. **确认触发词识别**:
   - "sí" / "si" / "yes" = 立即输出JSON
   - "correcto" / "está bien" = 立即输出JSON  
   - "procesar" / "confirmar" = 立即输出JSON

2. **JSON格式要求**:
   - 必须使用菜单中的确切名称
   - 包含数量和完整菜品名
   - 例子: "1 Combinaciones 2 presa pollo"

3. **流程完整性**:
   - 绝不跳过确认步骤
   - 确认后必须输出JSON
   - 不要重新开始对话

### ⚠️ 常见错误避免:

❌ **绝不做**:
- 确认后不输出JSON
- 重新开始对话而不处理订单
- 使用不正确的菜品名称
- 在JSON后添加额外文字

✅ **必须做**:
- 识别确认意图
- 立即输出正确JSON
- 使用确切菜品名称
- 等待系统处理

### 💡 示例完整流程:

```
用户: "Combinaciones 2 presa pollo"
你: "¡Perfecto! Combinaciones 2 presa pollo ($10.29). ¿Algo más?"

用户: "No"  
你: "Confirmo su pedido: - Combinaciones 2 presa pollo ($10.29) ¿Está correcto para procesar?"

用户: "Sí"
你: {json_example}
```

记住: 确认后必须输出JSON，这是触发POS订单处理的唯一方式！
"""
    
    return prompt

class ClaudeDirectMenuAgent:
    """
    Claude 4直接菜单处理代理
    修复JSON输出问题
    """
    
    def __init__(self):
        self.claude_client = ClaudeClient()
        self.system_prompt = create_claude_direct_prompt()
        
        logger.info("🧠 Claude 4 Direct Menu Agent initialized (JSON output fixed)")
        logger.info(f"📋 System prompt length: {len(self.system_prompt)} characters")

    def handle_message(self, from_id: str, text: str, history: List[Dict[str, str]]) -> str:
        """
        Claude 4直接处理消息和菜单匹配
        增强确认检测和JSON输出
        """
        try:
            logger.info(f"🧠 Claude 4 processing: '{text[:50]}{'...' if len(text) > 50 else ''}'")
            
            # 添加用户消息到历史
            history.append({"role": "user", "content": text})
            
            # 检查是否是确认意图
            is_confirmation = self.detect_confirmation_intent(text, history)
            
            if is_confirmation:
                logger.info("🎯 Detected confirmation intent - forcing JSON output")
                # 如果是确认，特别处理以确保JSON输出
                reply = self.handle_confirmation_with_json(history)
            else:
                # 正常处理
                reply = self.handle_normal_conversation(history)
            
            # 添加回复到历史
            history.append({"role": "assistant", "content": reply})
            
            # 检查Claude是否输出了JSON
            if "##JSON##" in reply:
                order_result = self.process_claude_direct_order(reply, from_id, history)
                if order_result:
                    # 替换回复为订单处理结果
                    reply = order_result
                    # 更新历史中的最后一个助手消息
                    history[-1]["content"] = reply
            
            logger.info(f"✅ Claude 4 response complete")
            return reply
            
        except Exception as e:
            logger.error(f"❌ Claude 4 processing error: {e}", exc_info=True)
            return self.get_error_response()

    def detect_confirmation_intent(self, text: str, history: List[Dict[str, str]]) -> bool:
        """
        检测确认意图
        
        Args:
            text: 用户消息
            history: 对话历史
            
        Returns:
            是否是确认意图
        """
        text_lower = text.lower().strip()
        
        # 确认关键词
        confirmation_words = [
            'sí', 'si', 'yes', 'ok', 'okay', 'correcto', 'correct',
            'está bien', 'esta bien', 'perfecto', 'perfect',
            'procesar', 'confirmar', 'confirm', 'process',
            '是', '对', '好的', '确认', '处理'
        ]
        
        # 检查是否包含确认词
        is_confirmation_word = any(word in text_lower for word in confirmation_words)
        
        # 检查上下文 - 是否刚刚询问了确认
        has_confirmation_context = False
        if len(history) >= 2:
            last_assistant_msg = ""
            for msg in reversed(history):
                if msg.get("role") == "assistant":
                    last_assistant_msg = msg.get("content", "").lower()
                    break
            
            confirmation_phrases = [
                "está correcto para procesar",
                "¿está correcto?", 
                "confirmo su pedido",
                "¿correcto?",
                "para procesar"
            ]
            
            has_confirmation_context = any(phrase in last_assistant_msg for phrase in confirmation_phrases)
        
        result = is_confirmation_word and has_confirmation_context
        
        if result:
            logger.info(f"🎯 Confirmation detected: '{text}' with context")
        
        return result

    def handle_confirmation_with_json(self, history: List[Dict[str, str]]) -> str:
        """
        处理确认并强制输出JSON
        
        Args:
            history: 对话历史
            
        Returns:
            包含JSON的回复
        """
        try:
            # 从历史中提取订单信息
            order_items = self.extract_order_from_history(history)
            
            if not order_items:
                logger.warning("No order items found in history for confirmation")
                return "Lo siento, no pude encontrar los detalles de su pedido. ¿Podría repetir su orden?"
            
            # 构建JSON
            sentences = []
            for item in order_items:
                quantity = item.get("quantity", 1)
                name = item.get("name", "")
                sentences.append(f"{quantity} {name}")
            
            json_data = {"sentences": sentences}
            json_output = "##JSON##" + json.dumps(json_data, ensure_ascii=False)
            
            logger.info(f"🎯 Generated JSON for confirmation: {json_output}")
            
            return json_output
            
        except Exception as e:
            logger.error(f"Error handling confirmation with JSON: {e}")
            return "Procesando su orden..."

    def extract_order_from_history(self, history: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        从对话历史中提取订单信息
        
        Args:
            history: 对话历史
            
        Returns:
            订单项目列表
        """
        order_items = []
        
        try:
            # 查找最近的订单确认消息
            for msg in reversed(history):
                if msg.get("role") == "assistant":
                    content = msg.get("content", "")
                    
                    # 查找确认订单的模式
                    if "confirmo su pedido" in content.lower():
                        # 提取项目列表
                        lines = content.split('\n')
                        for line in lines:
                            line = line.strip()
                            if line.startswith('-') or line.startswith('•'):
                                # 解析项目行，如: "- Combinaciones 2 presa pollo ($10.29)"
                                item_text = line[1:].strip()
                                
                                # 提取菜品名称（去掉价格部分）
                                if '(' in item_text and '$' in item_text:
                                    name_part = item_text.split('(')[0].strip()
                                    # 移除开头的格式字符
                                    name_part = name_part.replace('*', '').strip()
                                    
                                    order_items.append({
                                        "quantity": 1,  # 默认数量
                                        "name": name_part
                                    })
                        
                        if order_items:
                            logger.info(f"📋 Extracted order items from history: {order_items}")
                            break
            
            # 如果没有找到确认消息，尝试从对话中提取
            if not order_items:
                order_items = self.extract_items_from_conversation(history)
            
            return order_items
            
        except Exception as e:
            logger.error(f"Error extracting order from history: {e}")
            return []

    def extract_items_from_conversation(self, history: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        从整个对话中提取订单项目
        
        Args:
            history: 对话历史
            
        Returns:
            订单项目列表
        """
        order_items = []
        
        try:
            # 查找助手确认的菜品
            for msg in history:
                if msg.get("role") == "assistant":
                    content = msg.get("content", "")
                    
                    # 查找确认模式，如: "¡Perfecto! Combinaciones 2 presa pollo ($10.29)"
                    if "perfecto" in content.lower() and "$" in content:
                        # 使用正则表达式提取菜品名称
                        import re
                        
                        # 匹配模式: "Perfecto! [菜品名] ($价格)"
                        pattern = r'perfecto.*?([A-Za-z].+?)\s*\(\$[\d.]+\)'
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        
                        for match in matches:
                            item_name = match.strip().replace('*', '')
                            if item_name:
                                order_items.append({
                                    "quantity": 1,
                                    "name": item_name
                                })
            
            # 去重
            seen_items = set()
            unique_items = []
            for item in order_items:
                item_key = item["name"].lower()
                if item_key not in seen_items:
                    seen_items.add(item_key)
                    unique_items.append(item)
            
            logger.info(f"📋 Extracted items from conversation: {unique_items}")
            return unique_items
            
        except Exception as e:
            logger.error(f"Error extracting items from conversation: {e}")
            return []

    def handle_normal_conversation(self, history: List[Dict[str, str]]) -> str:
        """
        处理正常对话
        
        Args:
            history: 对话历史
            
        Returns:
            Claude回复
        """
        # 构建完整对话上下文
        messages = [
            {"role": "system", "content": self.system_prompt}
        ] + history
        
        # Claude 4处理
        reply = self.claude_client.chat(
            messages, 
            max_tokens=2500,
            temperature=0.1
        )
        
        return reply

    def process_claude_direct_order(self, reply: str, from_id: str, history: List[Dict[str, str]]) -> Optional[str]:
        """
        处理Claude直接识别的订单
        """
        try:
            logger.info(f"🛒 Processing Claude direct order for {from_id}")
            
            # 提取JSON数据
            json_match = re.search(r'##JSON##\s*(\{.*?\})', reply, re.DOTALL)
            if not json_match:
                logger.error("No valid JSON found in Claude response")
                return None
            
            json_str = json_match.group(1).strip()
            order_data = json.loads(json_str)
            sentences = order_data.get("sentences", [])
            
            if not sentences:
                logger.warning("Empty sentences in Claude order")
                return None
            
            logger.info(f"📝 Claude identified items: {sentences}")
            
            # 将Claude识别的项目转换为POS格式
            pos_items = self.convert_claude_items_to_pos(sentences)
            
            if not pos_items:
                return "抱歉，无法处理Claude识别的订单项目。请重新确认您的订单。"
            
            # 发送到POS系统
            receipt_number = place_loyverse_order(pos_items)
            
            # 计算实际总金额
            order_totals = calculate_order_total(pos_items)
            actual_total = order_totals["total"]
            
            # 获取客户名称
            customer_name = self.extract_customer_name(history)
            
            # 生成最终确认
            confirmation = self.generate_order_confirmation(
                sentences, pos_items, actual_total, receipt_number, customer_name
            )
            
            logger.info(f"✅ Claude direct order processed: Receipt #{receipt_number}, Total: ${actual_total:.2f}")
            return confirmation
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e}")
            return "处理订单格式时出错，请重新确认您的订单。"
            
        except Exception as e:
            logger.error(f"Claude direct order processing failed: {e}", exc_info=True)
            return "订单处理时发生错误，我们的团队已收到通知。请稍后重试。"

    def convert_claude_items_to_pos(self, sentences: List[str]) -> List[Dict[str, Any]]:
        """
        将Claude识别的项目转换为POS格式
        """
        try:
            menu_data = load_menu_data()
            pos_items = []
            
            # 构建菜单名称映射
            menu_map = self.build_menu_name_map(menu_data)
            
            for sentence in sentences:
                logger.debug(f"🔍 Converting Claude item: '{sentence}'")
                
                # 解析数量和菜品名
                quantity, dish_name = self.parse_claude_sentence(sentence)
                
                # 直接查找匹配
                menu_item = self.find_menu_item_direct(dish_name, menu_map)
                
                if menu_item:
                    pos_item = {
                        "variant_id": menu_item["variant_id"],
                        "quantity": quantity,
                        "price": menu_item["price"],
                        "item_name": menu_item["item_name"]
                    }
                    pos_items.append(pos_item)
                    logger.info(f"✅ Matched: '{sentence}' → {menu_item['item_name']} (${menu_item['price']:.2f})")
                else:
                    logger.warning(f"❌ No direct match for: '{sentence}'")
            
            return pos_items
            
        except Exception as e:
            logger.error(f"Error converting Claude items: {e}")
            return []

    def build_menu_name_map(self, menu_data: Dict) -> Dict[str, Dict]:
        """构建菜单名称映射"""
        menu_map = {}
        
        for category in menu_data.get("menu_categories", {}).values():
            if isinstance(category, dict) and "items" in category:
                for item in category["items"]:
                    item_name = item.get("item_name", "")
                    if item_name:
                        menu_map[item_name] = item
                        menu_map[item_name.lower()] = item
                        
                        # 添加别名映射
                        for alias in item.get("aliases", []):
                            menu_map[alias] = item
                            menu_map[alias.lower()] = item
        
        return menu_map

    def find_menu_item_direct(self, dish_name: str, menu_map: Dict) -> Optional[Dict]:
        """直接查找菜单项目"""
        # 精确匹配
        if dish_name in menu_map:
            return menu_map[dish_name]
        
        # 小写匹配
        if dish_name.lower() in menu_map:
            return menu_map[dish_name.lower()]
        
        # 部分匹配
        for menu_name, item in menu_map.items():
            if dish_name.lower() in menu_name.lower() or menu_name.lower() in dish_name.lower():
                return item
        
        return None

    def parse_claude_sentence(self, sentence: str) -> tuple:
        """解析数量和菜品名"""
        sentence = sentence.strip()
        
        # 匹配数字开头
        match = re.match(r'^(\d+)\s+(.+)', sentence)
        if match:
            quantity = int(match.group(1))
            dish_name = match.group(2).strip()
            return quantity, dish_name
        
        return 1, sentence

    def extract_customer_name(self, history: List[Dict[str, str]]) -> Optional[str]:
        """从历史中提取客户姓名"""
        for i, msg in enumerate(history):
            if (msg.get("role") == "assistant" and 
                "nombre" in msg.get("content", "").lower()):
                if i + 1 < len(history) and history[i + 1].get("role") == "user":
                    potential_name = history[i + 1].get("content", "").strip()
                    if (potential_name and len(potential_name) < 50 and 
                        not any(char.isdigit() for char in potential_name)):
                        return potential_name
        return None

    def generate_order_confirmation(self, sentences: List[str], pos_items: List[Dict], 
                                  total: float, receipt_number: str, 
                                  customer_name: Optional[str] = None) -> str:
        """生成订单确认"""
        try:
            if customer_name:
                confirmation = f"Gracias, {customer_name}. Su orden ha sido procesada:\n\n"
            else:
                confirmation = "Su orden ha sido procesada exitosamente:\n\n"
            
            # 添加订单项目
            for item in pos_items:
                quantity = item["quantity"]
                name = item["item_name"]
                confirmation += f"• {quantity}x {name}\n"
            
            # 总金额
            confirmation += f"\n**Total con impuesto: ${total:.2f}**\n"
            confirmation += f"Número de recibo: #{receipt_number}\n\n"
            
            # 准备时间
            total_main_items = sum(item["quantity"] for item in pos_items)
            prep_time = "15 minutos" if total_main_items >= 3 else "10 minutos"
            confirmation += f"Su orden estará lista en aproximadamente {prep_time}.\n\n"
            
            confirmation += "¡Muchas gracias por su preferencia!"
            
            return confirmation
            
        except Exception as e:
            logger.error(f"Error generating confirmation: {e}")
            return f"Su orden ha sido procesada. Total: ${total:.2f}, Recibo: #{receipt_number}. ¡Gracias!"

    def get_error_response(self) -> str:
        """获取错误响应"""
        error_responses = [
            "Disculpe, tuve un problema procesando su mensaje. ¿Podría repetirlo?",
            "Lo siento, hubo una interrupción momentánea. ¿Qué necesita?",
            "Disculpe la inconveniencia técnica. ¿En qué puedo ayudarle?"
        ]
        
        import random
        return random.choice(error_responses)

    def get_debug_info(self) -> Dict[str, Any]:
        """获取调试信息"""
        return {
            "type": "claude_direct_menu_agent_fixed",
            "system_prompt_length": len(self.system_prompt),
            "claude_model": getattr(self.claude_client, 'model', 'unknown'),
            "menu_integration": "direct_matching",
            "json_output_fixed": True,
            "confirmation_detection": True
        }

# 全局实例
_claude_direct_agent = None

def get_claude_direct_agent() -> ClaudeDirectMenuAgent:
    """获取Claude直接菜单代理的全局实例"""
    global _claude_direct_agent
    if _claude_direct_agent is None:
        _claude_direct_agent = ClaudeDirectMenuAgent()
    return _claude_direct_agent

def handle_message_claude_direct(from_id: str, text: str, history: List[Dict[str, str]]) -> str:
    """
    Claude直接菜单匹配的消息处理入口函数
    """
    agent = get_claude_direct_agent()
    return agent.handle_message(from_id, text, history)
