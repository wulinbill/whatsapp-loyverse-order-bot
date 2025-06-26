import time
import asyncio
from typing import Dict, Any, Optional
from enum import Enum

from ..config import get_settings
from ..logger import get_logger, business_logger
from ..llm.claude_client import claude_client
from ..speech.deepgram_client import deepgram_client
from ..utils.alias_matcher import alias_matcher
from ..utils.vector_search import vector_search_client
from ..pos.order_processor import order_processor
from .twilio_adapter import twilio_adapter
from .dialog360_adapter import dialog360_adapter

settings = get_settings()
logger = get_logger(__name__)

class ConversationState(Enum):
    """对话状态枚举"""
    GREETING = "greeting"
    ORDERING = "ordering"
    CLARIFYING = "clarifying"
    ASKING_NAME = "asking_name"
    CONFIRMING = "confirming"
    COMPLETED = "completed"

class WhatsAppRouter:
    """WhatsApp消息路由和订单处理核心类"""
    
    def __init__(self):
        self.provider = settings.channel_provider
        self.adapter = self._get_adapter()
        
        # 简单的会话状态管理（生产环境应使用Redis等）
        self.user_sessions = {}
    
    def _get_adapter(self):
        """根据配置选择适配器"""
        if self.provider == "dialog360":
            return dialog360_adapter
        else:
            return twilio_adapter
    
    async def handle_incoming_message(self, webhook_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理入站消息的主要入口
        
        Args:
            webhook_payload: WhatsApp webhook负载
            
        Returns:
            处理结果
        """
        try:
            # 解析消息数据
            message_data = self.adapter.parse_webhook_payload(webhook_payload)
            
            if not message_data:
                logger.warning("Failed to parse webhook payload")
                return {"status": "ignored", "reason": "invalid_payload"}
            
            user_id = message_data.get("from_number", "")
            
            # 记录入站消息
            business_logger.log_inbound_message(
                user_id=user_id,
                message_type=message_data.get("message_type", "unknown"),
                content=message_data.get("body", ""),
                metadata={
                    "message_id": message_data.get("message_id"),
                    "provider": self.provider
                }
            )
            
            # 处理消息
            response = await self._process_message(message_data)
            
            return response
            
        except Exception as e:
            business_logger.log_error(
                user_id=webhook_payload.get("from_number", "unknown"),
                stage="inbound",
                error_code="MESSAGE_PROCESSING_ERROR",
                error_msg=str(e),
                exception=e
            )
            logger.error(f"Error handling incoming message: {e}")
            return {"status": "error", "error": str(e)}
    
    async def _process_message(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理消息的主要逻辑"""
        user_id = message_data.get("from_number", "")
        message_type = message_data.get("message_type", "text")
        
        # 获取或创建用户会话
        session = self._get_user_session(user_id)
        
        try:
            # 处理语音消息
            if message_type == "voice":
                text_content = await self._process_voice_message(message_data, user_id)
                if not text_content:
                    await self._send_response(user_id, "Lo siento, no pude procesar su mensaje de voz. ¿Podría escribir su pedido?")
                    return {"status": "processed", "action": "voice_failed"}
                
                # 将语音转换的文字作为文本消息处理
                message_data["body"] = text_content
                message_data["message_type"] = "text"
            
            # 处理文本消息
            if message_data["message_type"] == "text":
                return await self._process_text_message(message_data, session)
            
            # 处理其他类型消息
            else:
                await self._send_response(user_id, "Por favor, envíe un mensaje de texto o audio con su pedido.")
                return {"status": "processed", "action": "unsupported_type"}
                
        except Exception as e:
            business_logger.log_error(
                user_id=user_id,
                stage="processing",
                error_code="MESSAGE_PROCESS_ERROR",
                error_msg=str(e),
                exception=e
            )
            
            # 发送错误消息给用户
            await self._send_response(user_id, "Disculpe, hubo un error procesando su mensaje. ¿Podría intentar de nuevo?")
            return {"status": "error", "error": str(e)}
    
    async def _process_voice_message(self, message_data: Dict[str, Any], user_id: str) -> Optional[str]:
        """处理语音消息"""
        try:
            media_urls = message_data.get("media_urls", [])
            
            if not media_urls:
                logger.warning("No media URLs in voice message")
                return None
            
            # 下载音频文件
            if self.provider == "dialog360":
                # 360Dialog使用media ID
                media_id = media_urls[0].get("id")
                audio_data = await self.adapter.download_media(media_id, user_id)
            else:
                # Twilio使用URL
                media_url = media_urls[0].get("url")
                audio_data = await self.adapter.download_media(media_url, user_id)
            
            if not audio_data:
                logger.error("Failed to download audio data")
                return None
            
            # 转录音频
            if self.provider == "dialog360":
                # 对于360Dialog，使用字节数据转录
                mime_type = media_urls[0].get("mime_type", "audio/ogg")
                transcript = await deepgram_client.transcribe_audio_bytes(audio_data, user_id, mime_type)
            else:
                # 对于Twilio，直接使用URL转录
                transcript = await deepgram_client.transcribe_audio_url(media_urls[0].get("url"), user_id)
            
            return transcript
            
        except Exception as e:
            business_logger.log_error(
                user_id=user_id,
                stage="speech",
                error_code="VOICE_PROCESSING_ERROR",
                error_msg=str(e),
                exception=e
            )
            logger.error(f"Error processing voice message: {e}")
            return None
    
    async def _process_text_message(self, message_data: Dict[str, Any], session: Dict[str, Any]) -> Dict[str, Any]:
        """处理文本消息"""
        user_id = message_data.get("from_number", "")
        text_content = message_data.get("body", "").strip()
        current_state = session.get("state", ConversationState.GREETING)
        
        # 根据会话状态处理消息
        if current_state == ConversationState.GREETING:
            return await self._handle_greeting_state(user_id, text_content, session)
        elif current_state == ConversationState.ORDERING:
            return await self._handle_ordering_state(user_id, text_content, session)
        elif current_state == ConversationState.CLARIFYING:
            return await self._handle_clarifying_state(user_id, text_content, session)
        elif current_state == ConversationState.ASKING_NAME:
            return await self._handle_name_state(user_id, text_content, session)
        elif current_state == ConversationState.CONFIRMING:
            return await self._handle_confirming_state(user_id, text_content, session)
        else:
            # 默认回到问候状态
            session["state"] = ConversationState.GREETING
            return await self._handle_greeting_state(user_id, text_content, session)
    
    async def _handle_greeting_state(self, user_id: str, text_content: str, session: Dict[str, Any]) -> Dict[str, Any]:
        """处理问候状态"""
        # 发送问候消息并进入订餐状态
        greeting_message = f"Hola, restaurante {settings.restaurant_name}. ¿Qué desea ordenar hoy?"
        
        # 如果用户直接说了菜品，跳过问候直接处理订单
        if any(word in text_content.lower() for word in ["quiero", "necesito", "dame", "pollo", "carne", "arroz"]):
            session["state"] = ConversationState.ORDERING
            return await self._handle_ordering_state(user_id, text_content, session)
        
        await self._send_response(user_id, greeting_message)
        session["state"] = ConversationState.ORDERING
        
        return {"status": "processed", "action": "greeting_sent"}
    
    async def _handle_ordering_state(self, user_id: str, text_content: str, session: Dict[str, Any]) -> Dict[str, Any]:
        """处理订餐状态"""
        try:
            # 1. 使用模糊匹配查找相关菜品
            fuzzy_matches = alias_matcher.find_matches(text_content, user_id, limit=10)
            
            # 2. 如果模糊匹配效果不好，使用向量搜索
            if not fuzzy_matches or fuzzy_matches[0].get("score", 0) < settings.fuzzy_match_threshold:
                vector_matches = await vector_search_client.search_similar_items(text_content, user_id, limit=5)
                
                # 合并结果
                all_matches = fuzzy_matches + vector_matches
                # 去重并排序
                seen_items = {}
                for match in all_matches:
                    item_id = match.get("item_id")
                    if item_id and (item_id not in seen_items or match.get("score", 0) > seen_items[item_id].get("score", 0)):
                        seen_items[item_id] = match
                
                final_matches = list(seen_items.values())
                final_matches.sort(key=lambda x: x.get("score", 0), reverse=True)
            else:
                final_matches = fuzzy_matches
            
            # 3. 使用Claude分析订单意图
            claude_result = await claude_client.extract_order(text_content, user_id, final_matches[:5])
            
            # 4. 根据Claude的分析结果采取行动
            if claude_result.get("need_clarify", False):
                session["state"] = ConversationState.CLARIFYING
                session["pending_query"] = text_content
                session["clarify_context"] = final_matches[:3]
                
                clarify_message = claude_result.get("clarify_message") or claude_result.get("response_message", "¿Podría aclarar su pedido?")
                await self._send_response(user_id, clarify_message)
                
                return {"status": "processed", "action": "clarification_needed"}
            
            elif claude_result.get("intent") == "order" and claude_result.get("order_lines"):
                # 处理订单
                return await self._process_order(user_id, claude_result, session)
            
            else:
                # 其他意图或没有识别到订单
                response_message = claude_result.get("response_message", "¿En qué puedo ayudarle hoy?")
                await self._send_response(user_id, response_message)
                
                return {"status": "processed", "action": "general_response"}
                
        except Exception as e:
            logger.error(f"Error in ordering state: {e}")
            await self._send_response(user_id, "Disculpe, hubo un error. ¿Podría repetir su pedido?")
            return {"status": "error", "error": str(e)}
    
    async def _handle_clarifying_state(self, user_id: str, text_content: str, session: Dict[str, Any]) -> Dict[str, Any]:
        """处理澄清状态"""
        # 重新分析用户的澄清回复
        context_matches = session.get("clarify_context", [])
        claude_result = await claude_client.extract_order(text_content, user_id, context_matches)
        
        if claude_result.get("intent") == "order" and claude_result.get("order_lines"):
            session["state"] = ConversationState.ORDERING
            return await self._process_order(user_id, claude_result, session)
        else:
            # 仍需澄清或用户放弃
            response_message = claude_result.get("response_message", "¿Algo más en lo que pueda ayudarle?")
            await self._send_response(user_id, response_message)
            session["state"] = ConversationState.ORDERING
            
            return {"status": "processed", "action": "clarification_resolved"}
    
    async def _handle_name_state(self, user_id: str, text_content: str, session: Dict[str, Any]) -> Dict[str, Any]:
        """处理询问姓名状态"""
        # 保存客户姓名
        customer_name = text_content.strip()
        session["customer_name"] = customer_name
        
        # 创建订单
        order_data = session.get("pending_order")
        if order_data:
            result = await order_processor.process_order(order_data, user_id, user_id)
            
            if result.get("success"):
                # 更新客户姓名
                if result.get("customer_id"):
                    await order_processor.update_customer_name(result["customer_id"], customer_name, user_id)
                
                # 发送确认消息
                confirmation_message = await claude_client.generate_order_confirmation(
                    result.get("matched_items", []), user_id, customer_name
                )
                
                await self._send_response(user_id, confirmation_message)
                
                # 也可以发送结构化的订单确认
                await self.adapter.send_order_confirmation(user_id, result, user_id)
                
                session["state"] = ConversationState.COMPLETED
                session["last_order"] = result
                
                return {"status": "processed", "action": "order_completed", "order": result}
            else:
                await self._send_response(user_id, "Hubo un error procesando su pedido. Por favor, inténtelo de nuevo.")
                session["state"] = ConversationState.ORDERING
                return {"status": "error", "error": result.get("error")}
        else:
            await self._send_response(user_id, "Hubo un error. Por favor, realice su pedido nuevamente.")
            session["state"] = ConversationState.ORDERING
            return {"status": "error", "error": "no_pending_order"}
    
    async def _handle_confirming_state(self, user_id: str, text_content: str, session: Dict[str, Any]) -> Dict[str, Any]:
        """处理确认状态"""
        text_lower = text_content.lower()
        
        if any(word in text_lower for word in ["sí", "si", "yes", "ok", "confirmar", "está bien"]):
            # 用户确认订单
            session["state"] = ConversationState.ASKING_NAME
            await self._send_response(user_id, "Para finalizar, ¿podría indicarme su nombre, por favor?")
            
            return {"status": "processed", "action": "asking_name"}
        
        elif any(word in text_lower for word in ["no", "cancelar", "cambiar"]):
            # 用户取消或要求修改
            session["state"] = ConversationState.ORDERING
            await self._send_response(user_id, "Entendido. ¿Qué le gustaría ordenar?")
            
            return {"status": "processed", "action": "order_cancelled"}
        
        else:
            # 不明确的回复，重新询问
            await self._send_response(user_id, "¿Confirma su pedido? Responda 'sí' para confirmar o 'no' para cancelar.")
            
            return {"status": "processed", "action": "confirmation_repeated"}
    
    async def _process_order(self, user_id: str, claude_result: Dict[str, Any], session: Dict[str, Any]) -> Dict[str, Any]:
        """处理订单"""
        try:
            # 检查是否是已知客户
            existing_customer = session.get("customer_name")
            
            if existing_customer:
                # 直接处理订单
                result = await order_processor.process_order(claude_result, user_id, user_id)
                
                if result.get("success"):
                    # 生成确认消息
                    confirmation_message = await claude_client.generate_order_confirmation(
                        result.get("matched_items", []), user_id, existing_customer
                    )
                    
                    await self._send_response(user_id, confirmation_message)
                    
                    # 发送结构化确认
                    await self.adapter.send_order_confirmation(user_id, result, user_id)
                    
                    session["state"] = ConversationState.COMPLETED
                    session["last_order"] = result
                    
                    return {"status": "processed", "action": "order_completed", "order": result}
                else:
                    await self._send_response(user_id, result.get("message", "Error al procesar el pedido."))
                    return {"status": "error", "error": result.get("error")}
            else:
                # 新客户，先确认订单然后询问姓名
                order_summary = self._build_order_summary(claude_result)
                
                confirm_message = f"Perfecto. Confirmo:\n{order_summary}\n¿Todo correcto?"
                
                await self._send_response(user_id, confirm_message)
                
                session["state"] = ConversationState.ASKING_NAME  # 直接跳到询问姓名
                session["pending_order"] = claude_result
                
                return {"status": "processed", "action": "order_confirmed"}
                
        except Exception as e:
            logger.error(f"Error processing order: {e}")
            await self._send_response(user_id, "Hubo un error procesando su pedido. Por favor, inténtelo de nuevo.")
            return {"status": "error", "error": str(e)}
    
    def _build_order_summary(self, claude_result: Dict[str, Any]) -> str:
        """构建订单摘要"""
        summary_lines = []
        
        for line in claude_result.get("order_lines", []):
            alias = line.get("alias", "")
            quantity = line.get("quantity", 1)
            modifiers = line.get("modifiers", [])
            
            line_text = f"- {quantity}x {alias}"
            if modifiers:
                line_text += f" ({', '.join(modifiers)})"
            
            summary_lines.append(line_text)
        
        return "\n".join(summary_lines) if summary_lines else "Su pedido"
    
    async def _send_response(self, user_id: str, message: str) -> bool:
        """发送响应消息"""
        return await self.adapter.send_message(user_id, message, user_id)
    
    def _get_user_session(self, user_id: str) -> Dict[str, Any]:
        """获取或创建用户会话"""
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = {
                "state": ConversationState.GREETING,
                "created_at": time.time(),
                "last_activity": time.time()
            }
        
        self.user_sessions[user_id]["last_activity"] = time.time()
        return self.user_sessions[user_id]
    
    def cleanup_expired_sessions(self, max_age_hours: int = 24):
        """清理过期的会话"""
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        expired_users = []
        for user_id, session in self.user_sessions.items():
            if current_time - session.get("last_activity", 0) > max_age_seconds:
                expired_users.append(user_id)
        
        for user_id in expired_users:
            del self.user_sessions[user_id]
        
        if expired_users:
            logger.info(f"Cleaned up {len(expired_users)} expired sessions")

# 全局WhatsApp路由器实例
whatsapp_router = WhatsAppRouter()
