#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude 4直接菜单匹配代理
完全由Claude 4负责菜单识别、匹配和订单处理
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
    让Claude完全理解菜单结构和项目
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
                            if item.get("price", 0) > 0:  # 只包含有价格的项目
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
                    
                    # 添加别名信息（帮助Claude理解不同的说法）
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
    """
    menu_section = build_claude_menu_context()
    
    return f"""
你是Kong Food Restaurant的智能订餐助手，专精中式波多黎各融合料理。

{menu_section}

## 🧠 CLAUDE 4 直接菜单匹配指令:

### 核心原则: 
你拥有完整的菜单知识，无需依赖外部搜索算法。直接使用你的理解能力匹配菜品。

### 📋 完整流程:

#### ① 欢迎语
"¡Hola! Restaurante Kong Food. ¿Qué desea ordenar hoy?"

#### ② 智能菜品识别 (你的专长)
当客户说菜品时，使用你的理解能力直接匹配上面的菜单:

**示例智能匹配:**
- 客户说: "pollo naranja" → 你识别: "Pollo Naranja ($11.89)"
- 客户说: "2 combinacion teriyaki" → 你识别: "2x Pollo Teriyaki ($11.99)"
- 客户说: "mini pollo agridulce" → 你识别: "mini Pollo Agridulce ($9.29)"

**歧义处理:**
当有多个可能匹配时，列出选项让客户选择:

例如: 客户说"2 presa pollo"
```
Tenemos estas opciones para 2 presas de pollo:

1. **Combinaciones 2 presa pollo** ($10.29) - 套餐含炒饭+薯条
2. **mini Combinaciones 2 Presas de Pollo** ($9.29) - 小份套餐
3. **2 Presas de Pollo con Papas** ($5.79) - 单纯炸鸡配薯条

¿Cuál prefiere?
```

#### ③ 确认每个菜品
"Perfecto, [菜品名] ($价格). ¿Algo más?"

#### ④ 最终确认
"Confirmo su pedido:
- [项目1]
- [项目2]
¿Está correcto para procesar?"

#### ⑤ JSON输出 (只在确认后)
当客户确认后，输出JSON格式:
##JSON##{"sentences":["数量 完整菜品名", "数量 完整菜品名"]}

**重要**: 使用菜单中的确切名称，如:
- "1 Pollo Naranja" (不是 "1 pollo naranja")
- "2 mini Pollo Teriyaki" (不是 "2 mini teriyaki")

#### ⑥ 订单完成确认
等待系统处理后，提供最终确认和取餐时间。

### 🎯 Claude 4 优势发挥:

1. **自然语言理解**: 理解各种表达方式
   - "quiero pollo con naranja" = Pollo Naranja
   - "dos combinaciones de teriyaki" = 2x Pollo Teriyaki
   - "mini版本的甜酸鸡" = mini Pollo Agridulce

2. **上下文记忆**: 记住对话中的选择和修改

3. **智能推理**: 
   - 区分套餐 vs 单品
   - 理解尺寸差异 (正常 vs mini)
   - 识别数量表达

4. **多语言能力**: 理解中文、西班牙语、英语混合表达

### ⚠️ 关键规则:

✅ **始终使用**:
- 菜单中的确切名称进行JSON输出
- 客户确认后才输出JSON
- 清晰的选项列表处理歧义

❌ **绝不**:
- 猜测不明确的订单
- 跳过确认步骤
- 使用菜单外的名称

### 💡 智能提示:

当客户说模糊的内容时，主动提供热门选择:
"我们最受欢迎的组合菜有:
• Pollo Teriyaki ($11.99)
• Pollo Naranja ($11.89) 
• Pollo Agridulce ($11.89)
您想要哪一个?"

记住: 你是菜单专家，直接使用你的智能来匹配和确认订单，无需依赖外部搜索!
"""

class ClaudeDirectMenuAgent:
    """
    Claude 4直接菜单处理代理
    完全依赖Claude的智能进行菜单匹配
    """
    
    def __init__(self):
        self.claude_client = ClaudeClient()
        self.system_prompt = create_claude_direct_prompt()
        
        logger.info("🧠 Claude 4 Direct Menu Agent initialized")
        logger.info(f"📋 System prompt length: {len(self.system_prompt)} characters")

    def handle_message(self, from_id: str, text: str, history: List[Dict[str, str]]) -> str:
        """
        Claude 4直接处理消息和菜单匹配
        
        Args:
            from_id: 用户标识符
            text: 用户消息内容  
            history: 对话历史记录
            
        Returns:
            助手回复内容
        """
        try:
            logger.info(f"🧠 Claude 4 direct processing: '{text[:50]}{'...' if len(text) > 50 else ''}'")
            
            # 添加用户消息到历史
            history.append({"role": "user", "content": text})
            
            # 构建完整对话上下文
            messages = [
                {"role": "system", "content": self.system_prompt}
            ] + history
            
            # Claude 4处理 - 使用最适合菜单匹配的参数
            reply = self.claude_client.chat(
                messages, 
                max_tokens=2500,  # 足够的token处理复杂菜单
                temperature=0.1   # 低温度确保一致性
            )
            
            # 添加回复到历史
            history.append({"role": "assistant", "content": reply})
            
            # 检查Claude是否识别出订单需要处理
            if "##JSON##" in reply:
                order_result = self.process_claude_direct_order(reply, from_id, history)
                if order_result:
                    # 替换回复为订单处理结果
                    reply = order_result
                    # 更新历史中的最后一个助手消息
                    history[-1]["content"] = reply
            
            logger.info(f"✅ Claude 4 direct response complete")
            return reply
            
        except Exception as e:
            logger.error(f"❌ Claude 4 direct processing error: {e}", exc_info=True)
            return self.get_error_response()

    def process_claude_direct_order(self, reply: str, from_id: str, history: List[Dict[str, str]]) -> Optional[str]:
        """
        处理Claude直接识别的订单
        
        Args:
            reply: 包含JSON的Claude回复
            from_id: 用户ID
            history: 对话历史
            
        Returns:
            处理结果消息
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
            
            # 计算实际总金额（从POS返回）
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
        直接使用菜单数据匹配，不依赖搜索算法
        
        Args:
            sentences: Claude识别的订单句子
            
        Returns:
            POS格式的订单项目
        """
        try:
            menu_data = load_menu_data()
            pos_items = []
            
            # 构建菜单名称到项目的直接映射
            menu_map = self.build_menu_name_map(menu_data)
            
            for sentence in sentences:
                logger.debug(f"🔍 Converting Claude item: '{sentence}'")
                
                # 解析数量和菜品名
                quantity, dish_name = self.parse_claude_sentence(sentence)
                
                # 直接在菜单映射中查找
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
        """
        构建菜单名称到项目的直接映射
        
        Args:
            menu_data: 菜单数据
            
        Returns:
            名称映射字典
        """
        menu_map = {}
        
        for category in menu_data.get("menu_categories", {}).values():
            if isinstance(category, dict) and "items" in category:
                for item in category["items"]:
                    item_name = item.get("item_name", "")
                    if item_name:
                        # 原始名称
                        menu_map[item_name] = item
                        # 小写版本
                        menu_map[item_name.lower()] = item
                        
                        # 添加别名映射
                        for alias in item.get("aliases", []):
                            menu_map[alias] = item
                            menu_map[alias.lower()] = item
        
        return menu_map

    def find_menu_item_direct(self, dish_name: str, menu_map: Dict) -> Optional[Dict]:
        """
        直接在菜单映射中查找项目
        
        Args:
            dish_name: Claude识别的菜品名称
            menu_map: 菜单映射
            
        Returns:
            匹配的菜单项目
        """
        # 直接精确匹配
        if dish_name in menu_map:
            return menu_map[dish_name]
        
        # 小写匹配
        if dish_name.lower() in menu_map:
            return menu_map[dish_name.lower()]
        
        # 部分匹配（包含关系）
        for menu_name, item in menu_map.items():
            if dish_name.lower() in menu_name.lower() or menu_name.lower() in dish_name.lower():
                return item
        
        return None

    def parse_claude_sentence(self, sentence: str) -> tuple:
        """
        解析Claude生成的句子获取数量和菜品名
        
        Args:
            sentence: 如 "2 Pollo Naranja"
            
        Returns:
            (数量, 菜品名称)
        """
        sentence = sentence.strip()
        
        # 匹配数字开头
        match = re.match(r'^(\d+)\s+(.+)', sentence)
        if match:
            quantity = int(match.group(1))
            dish_name = match.group(2).strip()
            return quantity, dish_name
        
        # 默认数量为1
        return 1, sentence

    def extract_customer_name(self, history: List[Dict[str, str]]) -> Optional[str]:
        """从对话历史中提取客户姓名"""
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
        """
        生成最终订单确认消息
        """
        try:
            # 开始确认消息
            if customer_name:
                confirmation = f"Gracias, {customer_name}. Su orden ha sido procesada:\n\n"
            else:
                confirmation = "Su orden ha sido procesada exitosamente:\n\n"
            
            # 添加订单项目
            for item in pos_items:
                quantity = item["quantity"]
                name = item["item_name"]
                confirmation += f"• {quantity}x {name}\n"
            
            # 总金额（POS系统返回的实际金额，含税）
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
            "type": "claude_direct_menu_agent",
            "system_prompt_length": len(self.system_prompt),
            "claude_model": getattr(self.claude_client, 'model', 'unknown'),
            "menu_integration": "direct_matching"
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
