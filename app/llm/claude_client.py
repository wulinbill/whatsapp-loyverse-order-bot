# TODO: implement Anthropics call
import asyncio
import time
from typing import Dict, List, Any, Optional
from anthropic import AsyncAnthropic
import json

from ..config import get_settings
from ..logger import get_logger, business_logger

settings = get_settings()
logger = get_logger(__name__)

class ClaudeClient:
    """Claude AI客户端，负责自然语言理解和订单提取"""
    
    def __init__(self):
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model
    
    async def extract_order(self, user_message: str, user_id: str, menu_context: List[Dict]) -> Dict[str, Any]:
        """
        从用户消息中提取订单信息
        
        Args:
            user_message: 用户消息内容
            user_id: 用户ID  
            menu_context: 菜单上下文信息
            
        Returns:
            订单提取结果
        """
        start_time = time.time()
        
        try:
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(user_message, menu_context)
            
            logger.info(f"Sending request to Claude for user {user_id}")
            
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                temperature=0.1,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": user_prompt
                }]
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 记录LLM请求日志
            business_logger.log_llm_request(
                user_id=user_id,
                prompt_tokens=response.usage.input_tokens if response.usage else 0,
                model=self.model,
                duration_ms=duration_ms
            )
            
            # 解析响应
            result = self._parse_response(response.content[0].text)
            logger.info(f"Claude response parsed for user {user_id}: {result}")
            
            return result
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            business_logger.log_error(
                user_id=user_id,
                stage="llm",
                error_code="CLAUDE_REQUEST_FAILED",
                error_msg=str(e),
                exception=e
            )
            raise
    
    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return """你是Kong Food Restaurant的订餐助手，专门处理西班牙语和中文订单。

核心任务：
1. 理解用户的订餐意图，提取具体的菜品和数量
2. 应用Kong Food的订餐规则
3. 返回标准化的JSON格式

订餐规则：
1. Combinaciones和MINI Combinaciones默认搭配：arroz+papa
2. 如果用户要换搭配（如"cambio tostones"、"con tostones"），需要单独添加cambio项目
3. Pollo Frito默认是任意cadera和muro，如果用户指定部位需要记录
4. 处理修饰词：extra(额外)、poco(少量)、no/sin(不要)、aparte(分开装)

输出格式（严格JSON）：
{
  "intent": "order|clarification|greeting|other",
  "order_lines": [
    {
      "alias": "菜品别名或关键词",
      "quantity": 数量,
      "modifiers": ["extra ajo", "poco sal", "no MSG"]
    }
  ],
  "need_clarify": false|true,
  "clarify_message": "需要澄清的问题",
  "response_message": "给用户的回复消息（西班牙语）"
}

注意：
- 如果菜品不明确，设置need_clarify=true
- response_message必须是友好的西班牙语
- 严格按照JSON格式返回，不要额外的解释文字"""

    def _build_user_prompt(self, user_message: str, menu_context: List[Dict]) -> str:
        """构建用户提示词"""
        menu_info = ""
        if menu_context:
            menu_info = "\n可选菜品：\n"
            for item in menu_context[:10]:  # 限制上下文长度
                menu_info += f"- {item.get('item_name', '')}: ${item.get('price', 0)}\n"
                if item.get('aliases'):
                    menu_info += f"  别名: {', '.join(item['aliases'])}\n"
        
        return f"""用户消息: "{user_message}"
{menu_info}

请根据Kong Food的订餐规则处理这个消息，返回标准JSON格式。"""

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """解析Claude响应"""
        try:
            # 清理响应文本，提取JSON部分
            cleaned_text = response_text.strip()
            
            # 如果有markdown代码块，提取其中的JSON
            if "```json" in cleaned_text:
                start = cleaned_text.find("```json") + 7
                end = cleaned_text.find("```", start)
                if end != -1:
                    cleaned_text = cleaned_text[start:end].strip()
            elif "```" in cleaned_text:
                start = cleaned_text.find("```") + 3
                end = cleaned_text.find("```", start)
                if end != -1:
                    cleaned_text = cleaned_text[start:end].strip()
            
            # 解析JSON
            result = json.loads(cleaned_text)
            
            # 验证必要字段
            required_fields = ["intent", "order_lines", "need_clarify", "response_message"]
            for field in required_fields:
                if field not in result:
                    result[field] = self._get_default_value(field)
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
            logger.error(f"Raw response: {response_text}")
            
            # 返回安全的默认响应
            return {
                "intent": "other",
                "order_lines": [],
                "need_clarify": True,
                "clarify_message": "No pude entender tu pedido",
                "response_message": "Disculpe, ¿podría repetir su pedido más claro, por favor?"
            }
    
    def _get_default_value(self, field: str) -> Any:
        """获取字段的默认值"""
        defaults = {
            "intent": "other",
            "order_lines": [],
            "need_clarify": True,
            "clarify_message": "",
            "response_message": "¿En qué puedo ayudarle hoy?"
        }
        return defaults.get(field, "")

    async def generate_order_confirmation(self, matched_items: List[Dict], user_id: str, customer_name: str = "") -> str:
        """生成订单确认消息"""
        start_time = time.time()
        
        try:
            system_prompt = """Eres un asistente de Kong Food Restaurant. Tu tarea es generar un mensaje de confirmación de pedido en español profesional y amigable.

Incluye:
1. Saludo personalizado (si hay nombre)
2. Lista de items con precios
3. Total con impuestos (11%)
4. Tiempo estimado de preparación
5. Mensaje de agradecimiento

Formato amigable en español."""

            items_text = "\n".join([
                f"- {item.get('item_name', 'Item')}: ${item.get('price', 0):.2f} x {item.get('quantity', 1)}"
                for item in matched_items
            ])
            
            subtotal = sum(item.get('price', 0) * item.get('quantity', 1) for item in matched_items)
            total_with_tax = subtotal * (1 + settings.tax_rate)
            
            prep_time = settings.preparation_time_complex if len(matched_items) >= 3 else settings.preparation_time_basic
            
            user_prompt = f"""Genera un mensaje de confirmación para:
Cliente: {customer_name or "Cliente"}
Items:
{items_text}
Subtotal: ${subtotal:.2f}
Total con impuesto (11%): ${total_with_tax:.2f}
Tiempo estimado: {prep_time} minutos

Genera un mensaje profesional y amigable en español."""

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=512,
                temperature=0.3,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            business_logger.log_llm_request(
                user_id=user_id,
                prompt_tokens=response.usage.input_tokens if response.usage else 0,
                model=self.model,
                duration_ms=duration_ms
            )
            
            return response.content[0].text.strip()
            
        except Exception as e:
            business_logger.log_error(
                user_id=user_id,
                stage="llm",
                error_code="CONFIRMATION_GENERATION_FAILED",
                error_msg=str(e),
                exception=e
            )
            
            # 返回基本确认消息
            total = sum(item.get('price', 0) * item.get('quantity', 1) for item in matched_items) * (1 + settings.tax_rate)
            return f"Gracias{' ' + customer_name if customer_name else ''}. Total: ${total:.2f}. Su pedido estará listo en {prep_time} minutos."

# 全局Claude客户端实例
claude_client = ClaudeClient()
