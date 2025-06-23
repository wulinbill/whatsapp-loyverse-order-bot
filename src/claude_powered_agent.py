#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude 4驱动的智能代理
让Claude 4直接处理菜单匹配和订单识别
"""

import os
import json
import pathlib
import logging
import re
from typing import List, Dict, Any, Optional

try:
    from claude_client import ClaudeClient
    from tools import place_loyverse_order, calculate_order_total, load_menu_data
except ImportError as e:
    import sys
    logger = logging.getLogger(__name__)
    logger.error(f"Import error: {e}")
    sys.path.insert(0, os.path.dirname(__file__))
    from claude_client import ClaudeClient
    from tools import place_loyverse_order, calculate_order_total, load_menu_data

logger = logging.getLogger(__name__)

def build_complete_menu_for_claude() -> str:
    """
    为Claude 4构建完整的菜单信息
    包含所有必要的匹配数据
    """
    try:
        menu_data = load_menu_data()
        menu_text = "\n## 📋 MENÚ COMPLETO - KONG FOOD RESTAURANT:\n\n"
        
        # 按类别组织菜单
        categories_order = [
            "Combinaciones", 
            "MINI Combinaciones", 
            "Pollo Frito", 
            "Arroz Frito", 
            "plato entrada",
            "Ofertas Familiares"
        ]
        
        for category_name in categories_order:
            category_items = []
            
            # 收集该类别的所有项目
            for cat_key, cat_data in menu_data.get("menu_categories", {}).items():
                if isinstance(cat_data, dict):
                    cat_display_name = cat_data.get("name", cat_key)
                    if cat_display_name == category_name:
                        items = cat_data.get("items", [])
                        for item in items:
                            if item.get("price", 0) > 0:  # 只包含有价格的项目
                                category_items.append(item)
            
            if category_items:
                # 添加类别标题
                emoji_map = {
                    "Combinaciones": "🍽️",
                    "MINI Combinaciones": "🥘", 
                    "Pollo Frito": "🍗",
                    "Arroz Frito": "🍚",
                    "plato entrada": "🥙",
                    "Ofertas Familiares": "👨‍👩‍👧‍👦"
                }
                emoji = emoji_map.get(category_name, "🍴")
                
                menu_text += f"### {emoji} {category_name.upper()}:\n"
                
                # 添加类别说明
                if category_name in ["Combinaciones", "MINI Combinaciones"]:
                    menu_text += "*Incluyen: Arroz frito + Papa frita (可换 tostones +$2.69)*\n\n"
                elif category_name == "Pollo Frito":
                    menu_text += "*Solo pollo frito con papas fritas*\n\n"
                
                # 按价格排序
                category_items.sort(key=lambda x: x.get("price", 0))
                
                # 添加项目
                for item in category_items:
                    name = item.get("item_name", "")
                    price = item.get("price", 0.0)
                    variant_id = item.get("variant_id", "")
                    
                    # 主要项目信息
                    menu_text += f"**{name}** - ${price:.2f} `[{variant_id}]`\n"
                    
                    # 添加别名和关键词
                    aliases = item.get("aliases", [])
                    keywords = item.get("keywords", [])
                    
                    extra_info = []
                    if aliases:
                        extra_info.append(f"别名: {', '.join(aliases[:3])}")
                    if keywords:
                        extra_info.append(f"关键词: {', '.join(keywords[:3])}")
                    
                    if extra_info:
                        menu_text += f"  _{' | '.join(extra_info)}_\n"
                    
                    menu_text += "\n"
                
                menu_text += "---\n\n"
        
        return menu_text
        
    except Exception as e:
        logger.error(f"Error building menu for Claude: {e}")
        return "\n## MENÚ: Error loading menu data\n\n"

def create_claude_optimized_prompt() -> str:
    """
    创建为Claude 4优化的系统提示
    """
    menu_section = build_complete_menu_for_claude()
    
    return f"""
Eres el asistente inteligente de Kong Food Restaurant, especializado en comida chino-puertorriqueña.

{menu_section}

## 🧠 INSTRUCCIONES PARA CLAUDE 4:

### FLUJO PRINCIPAL:
① **Saludo**: "Hola, restaurante KongFood. ¿Qué desea ordenar hoy?"

② **Captura Inteligente**: 
   - Usa tu comprensión natural para identificar platos del MENÚ ARRIBA
   - Reconoce variaciones: "pollo naranja", "combinacion de pollo naranja", "2 pollo naranja" = "Pollo Naranja"
   - Identifica cantidades: "dos", "2", "tres", etc.
   - Para ambigüedades reales, pregunta específicamente

③ **Confirmación**: "Confirmo su pedido: [lista] ¿Está todo correcto para procesar?"

④ **Procesamiento**: Solo cuando confirme, usa: ##JSON##{{\"sentences\":[\"cantidad NombreExacto\"]}}

### 🎯 EJEMPLOS DE IDENTIFICACIÓN INTELIGENTE:

**Entrada**: "2 pollo naranja"
**Reconocimiento**: Cliente quiere 2x "Pollo Naranja" ($11.89)
**Respuesta**: "Perfecto, 2 Pollo Naranja (incluye arroz frito + papa frita). ¿Algo más?"

**Entrada**: "combinacion de pollo teriyaki"  
**Reconocimiento**: Cliente quiere 1x "Pollo Teriyaki" ($11.99)
**Respuesta**: "Perfecto, Pollo Teriyaki (incluye arroz frito + papa frita). ¿Algo más?"

**Entrada**: "mini pollo agridulce"
**Reconocimiento**: Cliente quiere 1x "mini Pollo Agridulce" ($9.29) 
**Respuesta**: "Perfecto, mini Pollo Agridulce (incluye arroz + papa). ¿Algo más?"

**Entrada**: "3 presa pollo" (ambiguo)
**Reconocimiento**: Múltiples opciones válidas
**Respuesta**: "Para 3 presas de pollo tenemos:
1. **3 Presas de Pollo con Papas** ($7.29) - Solo pollo frito
2. **Combinaciones 2 presa pollo** ($10.29) - Con arroz + papa  
3. **mini Combinaciones 2 Presas de Pollo** ($9.29) - Versión mini
¿Cuál prefiere?"

### 🔧 REGLAS DE PROCESAMIENTO:

**Identificación Directa (90% de casos):**
- Si hay correspondencia clara con el menú → confirma directamente
- Usa tu comprensión contextual, no busques coincidencias exactas de texto
- Reconoce sinónimos naturales: "combinación de X" = "X"

**Manejo de Ambigüedad (10% de casos):**
- Solo pregunta cuando genuinamente hay múltiples interpretaciones válidas
- Presenta opciones claras y específicas
- Limita a 3-4 opciones máximo

**JSON Final:**
- Usa nombres exactos del menú arriba
- Formato: ##JSON##{{\"sentences\":[\"2 Pollo Naranja\", \"1 Tostones (8 pedazos)\"]}}
- El sistema procesará POS y reportará precio real

### ⚡ OPTIMIZACIONES CLAVE:

1. **Inteligencia Contextual**: Usa tu comprensión natural del lenguaje
2. **Eficiencia**: Minimiza preguntas innecesarias  
3. **Precisión**: Referencia exacta al menú proporcionado
4. **Fluidez**: Mantén conversación natural y profesional

Tu objetivo es aprovechar la capacidad de Claude 4 para entender intenciones naturales y hacer coincidencias inteligentes con el menú, eliminando la necesidad de algoritmos de búsqueda complejos.
"""

class ClaudePoweredMenuAgent:
    """
    Agente completamente impulsado por Claude 4
    Sin lógica de búsqueda de código - solo inteligencia de Claude
    """
    
    def __init__(self):
        self.claude_client = ClaudeClient()
        self.system_prompt = create_claude_optimized_prompt()
        self.conversation_state = {}
        
        logger.info("🧠 Claude-powered menu agent initialized")
        logger.info(f"📋 System prompt length: {len(self.system_prompt)} characters")

    def handle_message(self, from_id: str, text: str, history: List[Dict[str, str]]) -> str:
        """
        主要消息处理 - 完全由Claude 4驱动
        
        Args:
            from_id: 用户标识符
            text: 用户消息内容  
            history: 对话历史记录
            
        Returns:
            助手回复内容
        """
        try:
            logger.info(f"🧠 Claude processing message from {from_id}: '{text[:50]}{'...' if len(text) > 50 else ''}'")
            
            # 添加用户消息到历史
            history.append({"role": "user", "content": text})
            
            # 构建完整的对话上下文
            messages = [
                {"role": "system", "content": self.system_prompt}
            ] + history
            
            # Claude 4处理 - 增加token限制和降低温度提高准确性
            reply = self.claude_client.chat(
                messages, 
                max_tokens=2000, 
                temperature=0.1  # 降低温度提高一致性
            )
            
            # 添加回复到历史
            history.append({"role": "assistant", "content": reply})
            
            # 检查是否需要处理订单
            if "##JSON##" in reply:
                order_result = self.process_claude_order(reply, from_id, history)
                if order_result:
                    # 替换回复为订单处理结果
                    reply = order_result
                    # 更新历史中的最后一个助手消息
                    history[-1]["content"] = reply
            
            logger.info(f"✅ Claude response sent to {from_id}")
            return reply
            
        except Exception as e:
            logger.error(f"❌ Claude processing error for {from_id}: {e}", exc_info=True)
            return self.get_error_response()

    def process_claude_order(self, reply: str, from_id: str, history: List[Dict[str, str]]) -> Optional[str]:
        """
        处理Claude识别的订单
        
        Args:
            reply: 包含JSON的Claude回复
            from_id: 用户ID
            history: 对话历史
            
        Returns:
            处理结果消息
        """
        try:
            logger.info(f"🛒 Processing Claude-identified order for {from_id}")
            
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
            
            logger.info(f"📝 Claude identified sentences: {sentences}")
            
            # 转换为POS格式
            pos_items = self.convert_sentences_to_pos_format(sentences)
            
            if not pos_items:
                return "No pude procesar los items identificados por Claude. ¿Podría verificar su orden?"
            
            # 发送到POS系统
            receipt_number = place_loyverse_order(pos_items)
            
            # 计算实际总金额
            order_totals = calculate_order_total(pos_items)
            actual_total = order_totals["total"]
            
            # 获取客户名称（如果有）
            customer_name = self.extract_customer_name(history)
            
            # 生成最终确认
            confirmation = self.generate_final_order_confirmation(
                sentences, pos_items, actual_total, receipt_number, customer_name
            )
            
            logger.info(f"✅ Claude order processed successfully: Receipt #{receipt_number}, Total: ${actual_total:.2f}")
            return confirmation
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error in Claude response: {e}")
            return "Hubo un error procesando el formato del pedido. ¿Podría confirmarlo nuevamente?"
            
        except Exception as e:
            logger.error(f"Claude order processing failed: {e}", exc_info=True)
            return "Disculpa, hubo un problema procesando su orden. Nuestro equipo ha sido notificado. ¿Podría intentar de nuevo?"

    def convert_sentences_to_pos_format(self, sentences: List[str]) -> List[Dict[str, Any]]:
        """
        将Claude识别的句子转换为POS格式
        
        Args:
            sentences: Claude识别的订单句子
            
        Returns:
            POS格式的订单项目
        """
        try:
            menu_data = load_menu_data()
            pos_items = []
            
            for sentence in sentences:
                logger.debug(f"🔍 Converting sentence: '{sentence}'")
                
                # 解析数量和菜品名
                quantity, dish_name = self.parse_quantity_and_dish(sentence)
                
                # 在菜单中查找项目
                menu_item = self.find_exact_menu_match(dish_name, menu_data)
                
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
                    logger.warning(f"❌ No menu match for: '{sentence}'")
                    # 尝试模糊匹配作为后备
                    fuzzy_match = self.fuzzy_menu_search(dish_name, menu_data)
                    if fuzzy_match:
                        pos_item = {
                            "variant_id": fuzzy_match["variant_id"], 
                            "quantity": quantity,
                            "price": fuzzy_match["price"],
                            "item_name": fuzzy_match["item_name"]
                        }
                        pos_items.append(pos_item)
                        logger.info(f"🔍 Fuzzy matched: '{sentence}' → {fuzzy_match['item_name']}")
            
            return pos_items
            
        except Exception as e:
            logger.error(f"Error converting sentences to POS format: {e}")
            return []

    def parse_quantity_and_dish(self, sentence: str) -> tuple:
        """
        解析句子中的数量和菜品名称
        
        Args:
            sentence: 如 "2 Pollo Naranja"
            
        Returns:
            (数量, 菜品名称)
        """
        # 数字词汇映射
        number_words = {
            'uno': 1, 'una': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5,
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5
        }
        
        sentence = sentence.strip()
        
        # 匹配开头的数字
        digit_match = re.match(r'^(\d+)\s+(.+)', sentence)
        if digit_match:
            quantity = int(digit_match.group(1))
            dish_name = digit_match.group(2).strip()
            return quantity, dish_name
        
        # 匹配开头的文字数字
        for word, num in number_words.items():
            if sentence.lower().startswith(word.lower() + ' '):
                quantity = num
                dish_name = sentence[len(word):].strip()
                return quantity, dish_name
        
        # 默认数量为1
        return 1, sentence

    def find_exact_menu_match(self, dish_name: str, menu_data: Dict) -> Optional[Dict]:
        """
        在菜单中查找精确匹配
        
        Args:
            dish_name: 菜品名称
            menu_data: 菜单数据
            
        Returns:
            匹配的菜单项目
        """
        dish_lower = dish_name.lower().strip()
        
        # 收集所有菜单项目
        all_items = []
        for category in menu_data.get("menu_categories", {}).values():
            if isinstance(category, dict) and "items" in category:
                all_items.extend(category["items"])
        
        # 精确名称匹配
        for item in all_items:
            item_name = item.get("item_name", "").lower()
            if dish_lower == item_name:
                return item
        
        # 包含匹配（菜品名包含在项目名中或反之）
        for item in all_items:
            item_name = item.get("item_name", "").lower()
            if dish_lower in item_name or item_name in dish_lower:
                # 确保匹配度高
                if len(dish_lower) >= 4 and len(item_name) >= 4:
                    return item
        
        # 别名匹配
        for item in all_items:
            aliases = item.get("aliases", [])
            for alias in aliases:
                if dish_lower == alias.lower():
                    return item
        
        return None

    def fuzzy_menu_search(self, dish_name: str, menu_data: Dict) -> Optional[Dict]:
        """
        模糊搜索作为后备方案
        
        Args:
            dish_name: 菜品名称
            menu_data: 菜单数据
            
        Returns:
            最佳匹配项目
        """
        try:
            from fuzzywuzzy import fuzz
            
            dish_lower = dish_name.lower()
            best_match = None
            best_score = 0
            
            # 收集所有菜单项目
            all_items = []
            for category in menu_data.get("menu_categories", {}).values():
                if isinstance(category, dict) and "items" in category:
                    all_items.extend(category["items"])
            
            for item in all_items:
                item_name = item.get("item_name", "")
                score = fuzz.ratio(dish_lower, item_name.lower())
                
                if score > best_score and score >= 70:  # 最低70%相似度
                    best_score = score
                    best_match = item
            
            if best_match:
                logger.debug(f"🔍 Fuzzy match: '{dish_name}' → '{best_match['item_name']}' (score: {best_score})")
            
            return best_match
            
        except Exception as e:
            logger.error(f"Fuzzy search error: {e}")
            return None

    def extract_customer_name(self, history: List[Dict[str, str]]) -> Optional[str]:
        """从对话历史中提取客户姓名"""
        # 简单实现：查找询问姓名后的回答
        for i, msg in enumerate(history):
            if (msg.get("role") == "assistant" and 
                "nombre" in msg.get("content", "").lower()):
                # 查找下一个用户消息
                if i + 1 < len(history) and history[i + 1].get("role") == "user":
                    potential_name = history[i + 1].get("content", "").strip()
                    # 简单验证（不包含数字，长度合理）
                    if (potential_name and len(potential_name) < 50 and 
                        not any(char.isdigit() for char in potential_name)):
                        return potential_name
        return None

    def generate_final_order_confirmation(self, sentences: List[str], pos_items: List[Dict], 
                                        total: float, receipt_number: str, 
                                        customer_name: Optional[str] = None) -> str:
        """
        生成最终订单确认消息
        """
        try:
            # 开始确认消息
            if customer_name:
                confirmation = f"Gracias, {customer_name}. Confirmo:\n\n"
            else:
                confirmation = "Gracias. Confirmo:\n\n"
            
            # 添加订单项目
            for item in pos_items:
                quantity = item["quantity"]
                name = item["item_name"]
                confirmation += f"- {quantity} {name}\n"
            
            # 总金额（从POS获取的实际金额）
            confirmation += f"\nTotal **con impuesto** es ${total:.2f}\n"
            confirmation += f"Número de recibo: #{receipt_number}\n\n"
            
            # 准备时间估算
            total_main_items = sum(item["quantity"] for item in pos_items)
            prep_time = "15 minutos" if total_main_items >= 3 else "10 minutos"
            confirmation += f"Su orden estará lista en {prep_time}.\n\n"
            
            confirmation += "¡Muchas gracias!"
            
            return confirmation
            
        except Exception as e:
            logger.error(f"Error generating final confirmation: {e}")
            return f"¡Su orden ha sido procesada! Total: ${total:.2f}, Recibo: #{receipt_number}. ¡Gracias!"

    def get_error_response(self) -> str:
        """获取错误响应"""
        error_responses = [
            "Disculpa, experimenté un problema técnico temporal. ¿Podrías repetir tu mensaje?",
            "Lo siento, hubo una interrupción momentánea. ¿Puedes intentar de nuevo?",
            "Disculpa la inconveniencia, ¿podrías reformular tu pedido?"
        ]
        
        import random
        return random.choice(error_responses)

    def get_debug_info(self) -> Dict[str, Any]:
        """获取调试信息"""
        return {
            "system_prompt_length": len(self.system_prompt),
            "claude_model": self.claude_client.model if hasattr(self.claude_client, 'model') else "unknown",
            "active_conversations": len(self.conversation_state)
        }

# 全局实例
_claude_agent = None

def get_claude_agent() -> ClaudePoweredMenuAgent:
    """获取Claude代理的全局实例"""
    global _claude_agent
    if _claude_agent is None:
        _claude_agent = ClaudePoweredMenuAgent()
    return _claude_agent

def handle_message_claude_powered(from_id: str, text: str, history: List[Dict[str, str]]) -> str:
    """
    Claude驱动的消息处理入口函数
    用于替换原有的handle_message
    """
    agent = get_claude_agent()
    return agent.handle_message(from_id, text, history)