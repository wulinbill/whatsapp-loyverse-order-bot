#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced Menu Search Agent - 优化版本
减少Claude API成本，改进对话流程
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional, Tuple

from claude_client import ClaudeClient
from tools import search_menu, place_loyverse_order, calculate_order_total, format_menu_display

logger = logging.getLogger(__name__)

class MenuSearchAgent:
    """
    智能菜单搜索代理 - 先模糊搜索再精准匹配
    """
    
    def __init__(self):
        self.claude_client = ClaudeClient()
        logger.info("🔍 Menu Search Agent initialized")
    
    def fuzzy_search_menu(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        模糊搜索菜单，返回候选项供Claude选择
        
        Args:
            query: 用户查询
            limit: 返回结果数量
            
        Returns:
            菜单候选项列表
        """
        try:
            # 使用tools模块的搜索功能
            candidates = search_menu(query, limit=limit)
            
            if not candidates:
                # 尝试提取关键词再搜索
                keywords = self._extract_keywords(query)
                for keyword in keywords:
                    candidates = search_menu(keyword, limit=limit//2)
                    if candidates:
                        break
            
            logger.info(f"🔍 Fuzzy search for '{query}' found {len(candidates)} candidates")
            return candidates
            
        except Exception as e:
            logger.error(f"Error in fuzzy search: {e}")
            return []
    
    def _extract_keywords(self, query: str) -> List[str]:
        """提取查询关键词"""
        # 简单的关键词提取
        keywords = []
        query_lower = query.lower()
        
        # 常见菜品关键词
        food_keywords = [
            'pollo', 'chicken', '鸡',
            'carne', 'beef', '牛肉',
            'arroz', 'rice', '米饭',
            'sopa', 'soup', '汤',
            'combinacion', 'combo', '套餐',
            'tostones', 'papa', 'potato'
        ]
        
        for keyword in food_keywords:
            if keyword in query_lower:
                keywords.append(keyword)
        
        # 如果没有找到关键词，分割查询
        if not keywords:
            words = query.split()
            keywords = [w for w in words if len(w) > 2]
        
        return keywords[:3]  # 最多返回3个关键词

class EnhancedClaudeMenuAgent:
    """
    增强版Claude菜单代理 - 优化成本和对话流程
    """
    
    def __init__(self):
        self.claude_client = ClaudeClient()
        self.menu_searcher = MenuSearchAgent()
        self.processed_orders = set()
        
        # 加载简化的系统提示
        self.system_prompt = self._load_simplified_prompt()
        
        logger.info("💡 Enhanced Claude Menu Agent initialized")
    
    def _load_simplified_prompt(self) -> str:
        """加载简化的系统提示"""
        return """
Eres el asistente de Kong Food Restaurant. Sé CONCISO y DIRECTO.

## FLUJO SIMPLIFICADO:

1. **SALUDO BREVE**: "Hola, Kong Food. ¿Qué desea ordenar?"

2. **CAPTURA RÁPIDA**: 
   - Cliente dice plato → Confirma con precio: "Perfecto, [plato] ($X.XX). ¿Algo más?"
   - NO menciones ingredientes incluidos (arroz, papa) a menos que pregunten
   - NO ofrezcas cambios a menos que pidan

3. **CONFIRMACIÓN FINAL** (cuando digan "es todo", "solo eso", etc.):
   "Su pedido:
   - [items con precios]
   ¿Correcto para procesar?"

4. **PROCESAR** (cuando confirmen):
   - Usa ##JSON## para procesar
   - Reporta total CON IMPUESTO del sistema
   - Da número de recibo

## REGLAS CRÍTICAS:
- SÉ BREVE - No expliques lo obvio
- NO menciones arroz+papa en combinaciones
- NO preguntes sobre tostones a menos que pidan
- SIEMPRE muestra precio individual al confirmar cada plato
- SOLO reporta total DESPUÉS del POS (con impuesto incluido)

## CANDIDATOS DE MENÚ:
{menu_candidates}

Elige el mejor match basado en el contexto y precio mencionado por el cliente.
"""
    
    def handle_message(self, from_id: str, text: str, history: List[Dict[str, str]]) -> str:
        """
        Maneja mensajes con búsqueda optimizada
        """
        try:
            logger.info(f"💬 Processing message from {from_id}: '{text[:50]}...'")
            
            # Agregar mensaje del usuario
            history.append({"role": "user", "content": text})
            
            # Detectar confirmación
            if self._is_confirmation(text, history):
                order_hash = self._get_order_hash(history)
                if order_hash not in self.processed_orders:
                    self.processed_orders.add(order_hash)
                    return self._process_confirmed_order(history, from_id)
                else:
                    return "Esta orden ya fue procesada. ¿Desea hacer un nuevo pedido?"
            
            # Buscar candidatos de menú si el mensaje parece contener items
            menu_context = ""
            if self._might_contain_menu_items(text):
                candidates = self.menu_searcher.fuzzy_search_menu(text, limit=10)
                if candidates:
                    menu_context = self._format_menu_candidates(candidates)
            
            # Construir prompt con candidatos
            prompt_with_candidates = self.system_prompt.format(
                menu_candidates=menu_context if menu_context else "No se encontraron candidatos específicos."
            )
            
            # Construir mensajes para Claude
            messages = [
                {"role": "system", "content": prompt_with_candidates}
            ] + history
            
            # Obtener respuesta de Claude
            reply = self.claude_client.chat(
                messages,
                max_tokens=1000,  # Reducido para respuestas más cortas
                temperature=0.1
            )
            
            # Agregar respuesta al historial
            history.append({"role": "assistant", "content": reply})
            
            return reply
            
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            return "Disculpe, hubo un error. ¿Podría repetir su pedido?"
    
    def _might_contain_menu_items(self, text: str) -> bool:
        """Detecta si el texto podría contener items del menú"""
        text_lower = text.lower()
        
        # Palabras clave de comida
        food_indicators = [
            'pollo', 'chicken', 'carne', 'beef', 'arroz', 'rice',
            'sopa', 'soup', 'combo', 'combinacion', 'tostones',
            'papa', 'presa', 'teriyaki', 'naranja', 'agridulce'
        ]
        
        return any(indicator in text_lower for indicator in food_indicators)
    
    def _format_menu_candidates(self, candidates: List[Dict[str, Any]]) -> str:
        """Formatea candidatos del menú para Claude"""
        formatted = []
        
        for i, item in enumerate(candidates[:10], 1):  # Máximo 10 candidatos
            name = item.get("item_name", "")
            price = item.get("price", 0)
            category = item.get("category_name", "")
            
            formatted.append(f"{i}. {name} - ${price:.2f} ({category})")
        
        return "\n".join(formatted)
    
    def _is_confirmation(self, text: str, history: List[Dict[str, str]]) -> bool:
        """Detecta mensajes de confirmación con contexto más amplio y robusto"""
        import unicodedata, re

        # Normalizar texto del usuario
        def _norm(s: str) -> str:
            s = unicodedata.normalize('NFD', s)
            s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')  # remove accents
            s = re.sub(r'[^\w\s]', '', s)  # remove punctuation
            return s.lower().strip()

        text_clean = _norm(text)

        confirmation_words = {
            'si', 'sí', 'yes', 'ok', 'okay', 'correcto',
            'correct', 'bien', 'perfecto', 'listo', 'vale'
        }

        # Solo procede si el texto contiene una palabra de confirmación
        if not any(word == text_clean or word == _norm(part) for word in confirmation_words for part in text.split()):
            return False

        # Ampliar la ventana de búsqueda del mensaje del asistente con el resumen
        search_window = history[-10:] if len(history) >= 10 else history

        # Buscar el último mensaje del asistente que pida confirmación
        for msg in reversed(search_window):
            if msg.get("role") == "assistant":
                assistant_text = _norm(msg.get("content", ""))
                if "correcto para procesar" in assistant_text:
                    return True
                # También aceptar variantes comunes
                if "confirmar" in assistant_text and "pedido" in assistant_text:
                    return True
                break  # Encontrado mensaje assistant pero no es confirmación, salir

        return False
    
    def _get_order_hash(self, history: List[Dict[str, str]]) -> str:
        """Genera hash único para la orden"""
        order_items = self._extract_order_items(history)
        order_signature = ""
        for item in order_items:
            order_signature += f"{item.get('quantity')}x{item.get('name')};"
        return str(hash(order_signature))
    
    def _process_confirmed_order(self, history: List[Dict[str, str]], from_id: str) -> str:
        """Procesa orden confirmada con impuestos y KDS"""
        try:
            logger.info("💰 Processing confirmed order with tax")
            
            # Extraer items de la orden
            order_items = self._extract_order_items(history)
            
            if not order_items:
                return "No pude encontrar los detalles de su pedido. ¿Podría repetir su orden?"
            
            # Convertir a formato POS
            pos_items = []
            for item in order_items:
                # Buscar en el menú para obtener variant_id
                candidates = self.menu_searcher.fuzzy_search_menu(item['name'], limit=1)
                if candidates:
                    menu_item = candidates[0]
                    pos_items.append({
                        "variant_id": menu_item["variant_id"],
                        "quantity": item["quantity"],
                        "price": menu_item["price"],
                        "item_name": menu_item["item_name"]
                    })
            
            if not pos_items:
                return "No pude procesar los items del pedido. Por favor verifique su orden."
            
            # Calcular totales CON IMPUESTO
            totals = calculate_order_total(pos_items)
            
            # Procesar en Loyverse con configuración KDS
            receipt_number = self._place_order_with_kds(pos_items, from_id)
            
            # Generar confirmación con total real
            confirmation = self._generate_confirmation(
                pos_items,
                totals["total"],  # Total con impuesto
                receipt_number,
                totals["tax_amount"]
            )
            
            history.append({"role": "assistant", "content": confirmation})
            
            # 🧹 Después de confirmar la orden, limpiamos el historial para iniciar un nuevo flujo
            # Mantiene solo la última confirmación para referencia
            if len(history) > 1:
                history[:] = history[-1:]
            
            return confirmation
            
        except Exception as e:
            logger.error(f"Error processing order: {e}", exc_info=True)
            return "Hubo un error procesando su orden. Por favor intente nuevamente."
    
    def _place_order_with_kds(self, items: List[Dict[str, Any]], customer_id: str) -> str:
        """
        Procesa orden con soporte para KDS (Kitchen Display System)
        """
        try:
            from loyverse_api import place_order
            
            # Construir payload con información adicional para KDS
            payload = {
                "line_items": items,
                "source": "whatsapp",  # Identificar origen
                "customer_name": f"WhatsApp-{customer_id[-4:]}",  # Identificador del cliente
                "order_type": "takeout",  # Tipo de orden
                "notes": f"Pedido WhatsApp desde {customer_id}",
                # Agregar flag para KDS
                "send_to_kitchen": True,
                "kitchen_notes": "Orden de WhatsApp - Preparar para llevar"
            }
            
            # Procesar orden
            order_response = place_order(payload)
            
            receipt_number = order_response.get("receipt_number", "unknown")
            logger.info(f"✅ Order sent to KDS and POS: #{receipt_number}")
            
            return receipt_number
            
        except Exception as e:
            logger.error(f"Error placing order with KDS: {e}")
            # Intentar sin KDS como fallback
            return place_loyverse_order(items)
    
    def _extract_order_items(self, history: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Extrae items de la orden del historial"""
        order_items = []
        
        # Buscar en el último mensaje de confirmación del asistente
        for msg in reversed(history):
            if msg.get("role") == "assistant" and "su pedido:" in msg.get("content", "").lower():
                content = msg["content"]
                
                # Extraer items con formato "- X [nombre] ($Y.YY)"
                import re
                pattern = r'-\s*(\d+)?\s*([^($]+)\s*\(\$?([\d.]+)\)'
                matches = re.findall(pattern, content)
                
                for match in matches:
                    quantity = int(match[0]) if match[0] else 1
                    name = match[1].strip()
                    
                    order_items.append({
                        "quantity": quantity,
                        "name": name
                    })
                
                break
        
        return order_items
    
    def _generate_confirmation(self, items: List[Dict], total_with_tax: float, 
                              receipt_number: str, tax_amount: float) -> str:
        """Genera mensaje de confirmación conciso"""
        confirmation = "✅ Orden procesada:\n\n"
        
        # Items
        for item in items:
            confirmation += f"• {item['quantity']}x {item['item_name']}\n"
        
        # Total con impuesto
        confirmation += f"\n💰 **Total (incluye impuesto): ${total_with_tax:.2f}**\n"
        confirmation += f"🧾 Recibo: #{receipt_number}\n"
        
        # Tiempo de preparación
        total_items = sum(item['quantity'] for item in items)
        prep_time = "15 minutos" if total_items >= 3 else "10 minutos"
        confirmation += f"⏰ Listo en: {prep_time}\n\n"
        
        confirmation += "¡Gracias por su orden!"
        
        return confirmation
    
    def get_debug_info(self) -> Dict[str, Any]:
        """Información de debug"""
        return {
            "type": "enhanced_claude_menu_agent",
            "features": [
                "fuzzy_search_optimization",
                "reduced_api_cost",
                "simplified_conversation",
                "tax_calculation",
                "kds_support"
            ],
            "processed_orders": len(self.processed_orders)
        }

# Instancia global
_enhanced_agent = None

def get_enhanced_agent() -> EnhancedClaudeMenuAgent:
    """Obtiene instancia del agente mejorado"""
    global _enhanced_agent
    if _enhanced_agent is None:
        _enhanced_agent = EnhancedClaudeMenuAgent()
    return _enhanced_agent

def handle_message_enhanced(from_id: str, text: str, history: List[Dict[str, str]]) -> str:
    """Punto de entrada para el agente mejorado"""
    agent = get_enhanced_agent()
    return agent.handle_message(from_id, text, history)
