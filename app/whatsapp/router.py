import time
import asyncio
from typing import Dict, List, Any, Optional
from enum import Enum

from ..config import get_settings
from ..logger import get_logger, business_logger
from ..llm.claude_client import claude_client
from ..speech.deepgram_client import deepgram_client
from ..utils.alias_matcher import alias_matcher
from ..utils.vector_search import vector_search_client
from ..pos.order_processor import order_processor
from ..utils.memory_sessions import get_user_session, update_user_session
from .twilio_adapter import twilio_adapter
from .dialog360_adapter import dialog360_adapter

settings = get_settings()
logger = get_logger(__name__)

class ConversationState(Enum):
    """对话状态枚举"""
    GREETING = "greeting"
    ORDERING = "ordering"
    CLARIFYING = "clarifying"
    CONFIRMING_ORDER = "confirming_order"
    ASKING_NAME = "asking_name"
    COMPLETED = "completed"

class WhatsAppRouter:
    """WhatsApp消息路由和订单处理核心类 - 更真人化的对话流程"""
    
    def __init__(self):
        self.provider = settings.channel_provider
        self.adapter = self._get_adapter()
    
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
        
        # 获取用户会话
        session = get_user_session(user_id)
        
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
    
    async def _process_text_message(self, message_data: Dict[str, Any], session: Any) -> Dict[str, Any]:
        """处理文本消息"""
        user_id = message_data.get("from_number", "")
        text_content = message_data.get("body", "").strip()
        current_state = session.state
        
        logger.info(f"Processing text message for user {user_id} in state {current_state}: '{text_content}'")
        
        # 根据会话状态处理消息
        if current_state == ConversationState.GREETING:
            return await self._handle_greeting_state(user_id, text_content, session)
        elif current_state == ConversationState.ORDERING:
            return await self._handle_ordering_state(user_id, text_content, session)
        elif current_state == ConversationState.CLARIFYING:
            return await self._handle_clarifying_state(user_id, text_content, session)
        elif current_state == ConversationState.CONFIRMING_ORDER:
            return await self._handle_confirming_state(user_id, text_content, session)
        elif current_state == ConversationState.ASKING_NAME:
            return await self._handle_name_state(user_id, text_content, session)
        else:
            # 默认回到问候状态
            logger.warning(f"Unknown state {current_state} for user {user_id}, resetting to greeting")
            session.state = ConversationState.GREETING
            # session 是引用，不需要额外调用 update_user_session
            return await self._handle_greeting_state(user_id, text_content, session)
    
    async def _handle_greeting_state(self, user_id: str, text_content: str, session: Any) -> Dict[str, Any]:
        """处理问候状态 - 按照文档流程"""
        # 检查是否第一条消息就包含订单
        if self._contains_order_keywords(text_content):
            # 直接跳转到订单处理，不发送问候语
            session.state = ConversationState.ORDERING
            return await self._handle_ordering_state(user_id, text_content, session)
        
        # 发送问候消息（只有在没有订单关键词时）
        greeting_message = "¡Hola! Bienvenido a Kong Food 🍗. ¿Qué te gustaría ordenar hoy?"
        await self._send_response(user_id, greeting_message)
        session.state = ConversationState.ORDERING
        
        return {"status": "processed", "action": "greeting_sent"}
    
    def _contains_order_keywords(self, text: str) -> bool:
        """检查文本是否包含订单关键词"""
        order_keywords = [
            "quiero", "necesito", "dame", "pido", "ordenar", "pedido",
            "pollo", "carne", "arroz", "presas", "combinación", "combo",
            "pechuga", "muro", "cadera", "pepper", "churrasco", 
            "sopa", "china", "papa", "frita", "tostones", "ensalada"  # 添加更多菜品关键词
        ]
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in order_keywords)
    
    async def _handle_ordering_state(self, user_id: str, text_content: str, session: Any) -> Dict[str, Any]:
        """处理订餐状态 - 使用Claude解析并确认"""
        try:
            # 步骤2: 使用Claude extract_order函数（按照文档要求）
            claude_result = await claude_client.extract_order(text_content, user_id, [])
            
            if claude_result.get("need_clarify", True):
                # 步骤4: 需要澄清
                session.state = ConversationState.CLARIFYING
                session.pending_query = text_content
                
                clarify_message = self._get_clarification_message(claude_result, text_content)
                await self._send_response(user_id, clarify_message)
                
                return {"status": "processed", "action": "clarification_needed"}
            
            # 步骤3: 识别和确认订单
            order_lines = claude_result.get("order_lines", [])
            if order_lines:
                session.draft_lines = order_lines
                return await self._process_recognized_order(user_id, order_lines, session)
            else:
                await self._send_response(user_id, "Disculpa, ¿podrías aclararlo, por favor?")
                session.state = ConversationState.CLARIFYING
                return {"status": "processed", "action": "general_clarification"}
                
        except Exception as e:
            logger.error(f"Error in ordering state: {e}")
            await self._send_response(user_id, "Disculpe, hubo un error. ¿Podría repetir su pedido?")
            return {"status": "error", "error": str(e)}
    
    def _get_clarification_message(self, claude_result: Dict[str, Any], original_text: str) -> str:
        """生成澄清消息"""
        # 检查是否是特定类型的澄清
        text_lower = original_text.lower()
        
        if "pepper" in text_lower and "steak" in text_lower:
            return "¿Pepper Steak de carne de res, correcto?"
        elif "pollo" in text_lower and any(word in text_lower for word in ["presas", "piezas"]):
            return "¿Cuántas presas de pollo desea?"
        elif "combinación" in text_lower or "combo" in text_lower:
            return "¿Qué tipo de combinación prefiere?"
        else:
            return "Disculpa, ¿podrías aclararlo, por favor?"
    
    async def _process_recognized_order(self, user_id: str, order_lines: List[Dict[str, Any]], session: Any) -> Dict[str, Any]:
        """处理识别到的订单 - 按照文档的步骤3"""
        try:
            logger.info(f"Processing recognized order for user {user_id}: {len(order_lines)} items")
            
            # 清除之前的选择状态 - 重要：防止使用旧的选择项
            session.pending_choice = None
            if not hasattr(session, 'matched_items'):
                session.matched_items = []
            
            # 解析别名并匹配菜品
            matched_items = await self._match_and_resolve_items(order_lines, user_id)
            
            if not matched_items:
                await self._send_response(user_id, "No pude encontrar los productos solicitados. ¿Podría especificar mejor?")
                session.state = ConversationState.CLARIFYING
                return {"status": "processed", "action": "no_matches"}
            
            # 检查是否有歧义选项需要用户选择
            ambiguous_items = self._find_ambiguous_items(matched_items)
            if ambiguous_items:
                choice_message = self._build_choice_message(ambiguous_items[0])
                await self._send_response(user_id, choice_message)
                session.state = ConversationState.CLARIFYING
                session.pending_choice = ambiguous_items[0]
                return {"status": "processed", "action": "choice_needed"}
            
            # 确认单元并询问是否还要其他
            session.matched_items = matched_items
            confirmation_message = self._build_confirmation_message(matched_items)
            await self._send_response(user_id, confirmation_message)
            
            session.state = ConversationState.CONFIRMING_ORDER
            return {"status": "processed", "action": "order_confirmed"}
            
        except Exception as e:
            logger.error(f"Error processing recognized order: {e}")
            await self._send_response(user_id, "Hubo un error procesando su pedido. ¿Podría intentarlo de nuevo?")
            return {"status": "error", "error": str(e)}
    
    async def _match_and_resolve_items(self, order_lines: List[Dict[str, Any]], user_id: str) -> List[Dict[str, Any]]:
        """匹配和解析菜品项目 - 按照最新文档的步骤3A和3B，优化数量提取"""
        matched_items = []
        
        for line in order_lines:
            alias = line.get("alias", "")
            original_quantity = line.get("quantity", 1)
            
            if not alias:
                continue
            
            # 预处理：提取数量并清理文本
            extracted_quantity, cleaned_alias = self._extract_quantity_and_clean_text(alias)
            
            # 使用提取的数量，如果Claude已经识别了数量则优先使用Claude的结果
            final_quantity = original_quantity if original_quantity > 1 else extracted_quantity
            
            logger.info(f"Processing alias '{alias}' -> cleaned: '{cleaned_alias}', quantity: {final_quantity}")
            
            # 步骤3A-1: 首先使用RapidFuzz尝试匹配清理后的文本 (token_set_ratio ≥ 80)
            rapidfuzz_matches = alias_matcher.find_matches(cleaned_alias, user_id, limit=5)
            
            if rapidfuzz_matches:
                # RapidFuzz找到匹配，处理结果
                top_matches = [m for m in rapidfuzz_matches if m.get("score", 0) >= 80]
                
                if len(top_matches) > 1:
                    # 有多个高分匹配，需要用户选择
                    matched_item = {
                        "original_alias": alias,  # 保留原始输入
                        "cleaned_alias": cleaned_alias,  # 保存清理后的文本
                        "quantity": final_quantity,
                        "matches": top_matches,
                        "needs_choice": True
                    }
                else:
                    # 单一最佳匹配
                    best_match = rapidfuzz_matches[0]
                    matched_item = {
                        "item_id": best_match.get("item_id"),
                        "variant_id": best_match.get("variant_id"),
                        "item_name": best_match.get("item_name"),
                        "category_name": best_match.get("category_name"),
                        "price": best_match.get("price", 0),
                        "sku": best_match.get("sku"),
                        "quantity": final_quantity,
                        "original_alias": alias,
                        "cleaned_alias": cleaned_alias,
                        "needs_choice": False,
                        "match_method": "rapidfuzz"
                    }
                
                matched_items.append(matched_item)
                logger.info(f"RapidFuzz match found for '{cleaned_alias}': {matched_item.get('item_name', 'multiple options')}")
            else:
                # 步骤3A-2: RapidFuzz失败，调用Claude 4对menu_kb.json进行直接匹配
                logger.info(f"RapidFuzz failed for '{cleaned_alias}', trying Claude menu matching")
                claude_match = await self._claude_menu_matching(cleaned_alias, user_id)
                
                if claude_match:
                    matched_item = {
                        "item_id": claude_match.get("item_id"),
                        "variant_id": claude_match.get("variant_id"),
                        "item_name": claude_match.get("item_name"),
                        "category_name": claude_match.get("category_name"),
                        "price": claude_match.get("price", 0),
                        "sku": claude_match.get("sku"),
                        "quantity": final_quantity,
                        "original_alias": alias,
                        "cleaned_alias": cleaned_alias,
                        "needs_choice": False,
                        "match_method": "claude_menu_kb"
                    }
                    matched_items.append(matched_item)
                    logger.info(f"Claude menu matching found item for '{cleaned_alias}': {claude_match.get('item_name')}")
                else:
                    # Claude也无法匹配，记录但不添加到结果中
                    logger.warning(f"No match found for alias '{alias}' (cleaned: '{cleaned_alias}') using both RapidFuzz and Claude menu matching")
        
        return matched_items
    
    async def _claude_menu_matching(self, alias: str, user_id: str) -> Optional[Dict[str, Any]]:
        """使用Claude 4对menu_kb.json进行直接匹配 - 按照最新文档流程"""
        try:
            # 调用Claude客户端进行菜单匹配
            match_result = await claude_client.match_menu_item(alias, user_id)
            
            if match_result and match_result.get("found"):
                logger.info(f"Claude menu matching found item for '{alias}': {match_result.get('item_name')}")
                return match_result
            else:
                logger.info(f"Claude menu matching found no match for '{alias}'")
                return None
                
        except Exception as e:
            logger.error(f"Error in Claude menu matching for '{alias}': {e}")
            return None
    
    def _find_ambiguous_items(self, matched_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """查找需要用户选择的歧义项目"""
        return [item for item in matched_items if item.get("needs_choice", False)]
    
    def _build_choice_message(self, ambiguous_item: Dict[str, Any]) -> str:
        """构建选择消息 - 步骤3B"""
        matches = ambiguous_item.get("matches", [])
        original_alias = ambiguous_item.get("original_alias", "")
        cleaned_alias = ambiguous_item.get("cleaned_alias", original_alias)
        
        # 使用原始别名来显示给用户，保持上下文
        message_lines = [f"Para '{original_alias}', encontré estas opciones:"]
        
        for i, match in enumerate(matches[:3], 1):
            name = match.get("item_name", "")
            price = match.get("price", 0)
            message_lines.append(f"{i}. {name} --- ${price:.2f}")
        
        message_lines.append("¿Cuál prefieres?")
        return "\n".join(message_lines)
    
    def _build_confirmation_message(self, matched_items: List[Dict[str, Any]]) -> str:
        """构建确认消息 - 步骤3C"""
        if not matched_items:
            return "¿Algo más?"
        
        # 生成确认文本
        item_summaries = []
        for item in matched_items:
            if not item.get("needs_choice", False):
                quantity = item.get("quantity", 1)
                name = item.get("item_name", "")
                item_summaries.append(f"{quantity} {name}")
        
        if item_summaries:
            items_text = ", ".join(item_summaries)
            return f"Perfecto: {items_text}. ¿Algo más?"
        else:
            return "¿Algo más?"
    
    async def _handle_clarifying_state(self, user_id: str, text_content: str, session: Any) -> Dict[str, Any]:
        """处理澄清状态"""
        # 检查是否是对选择的回应
        if hasattr(session, 'pending_choice') and session.pending_choice:
            return await self._handle_choice_response(user_id, text_content, session)
        
        # 重新分析澄清后的回复
        claude_result = await claude_client.extract_order(text_content, user_id, [])
        
        if not claude_result.get("need_clarify", False) and claude_result.get("order_lines"):
            # 澄清成功，处理订单
            session.state = ConversationState.ORDERING
            order_lines = claude_result.get("order_lines", [])
            session.draft_lines = order_lines
            return await self._process_recognized_order(user_id, order_lines, session)
        else:
            # 仍需澄清
            clarify_message = self._get_clarification_message(claude_result, text_content)
            await self._send_response(user_id, clarify_message)
            return {"status": "processed", "action": "still_clarifying"}
    
    async def _handle_choice_response(self, user_id: str, text_content: str, session: Any) -> Dict[str, Any]:
        """处理用户对选择的回应"""
        # 检查是否有待处理的选择
        if not hasattr(session, 'pending_choice') or not session.pending_choice:
            logger.warning(f"No pending choice found for user {user_id}")
            await self._send_response(user_id, "Lo siento, no hay opciones pendientes. ¿En qué puedo ayudarte?")
            session.state = ConversationState.ORDERING
            return {"status": "processed", "action": "no_pending_choice"}
        
        pending_choice = session.pending_choice
        matches = pending_choice.get("matches", [])
        
        logger.info(f"Processing choice for user {user_id}: '{text_content}' from {len(matches)} options")
        logger.info(f"Pending choice alias: '{pending_choice.get('original_alias')}'")
        
        # 尝试解析用户的选择
        choice_num = self._parse_choice_number(text_content)
        
        if choice_num and 1 <= choice_num <= len(matches):
            # 用户选择了有效选项
            selected_match = matches[choice_num - 1]
            
            # 更新匹配项
            matched_items = session.matched_items if hasattr(session, 'matched_items') else []
            for item in matched_items:
                if item.get("original_alias") == pending_choice.get("original_alias"):
                    item.update({
                        "item_id": selected_match.get("item_id"),
                        "variant_id": selected_match.get("variant_id"),
                        "item_name": selected_match.get("item_name"),
                        "category_name": selected_match.get("category_name"),
                        "price": selected_match.get("price", 0),
                        "sku": selected_match.get("sku"),
                        "needs_choice": False
                    })
                    break
            
            session.matched_items = matched_items
            session.pending_choice = None
            
            # 检查是否还有其他需要选择的项目
            remaining_choices = self._find_ambiguous_items(matched_items)
            if remaining_choices:
                choice_message = self._build_choice_message(remaining_choices[0])
                await self._send_response(user_id, choice_message)
                session.pending_choice = remaining_choices[0]
                return {"status": "processed", "action": "next_choice_needed"}
            else:
                # 所有选择完成，确认订单
                logger.info(f"All choices completed for user {user_id}, moving to confirmation state")
                confirmation_message = self._build_confirmation_message(matched_items)
                await self._send_response(user_id, confirmation_message)
                session.state = ConversationState.CONFIRMING_ORDER
                logger.info(f"User {user_id} state changed to: {session.state}")
                return {"status": "processed", "action": "choices_completed"}
        else:
            # 无效选择
            await self._send_response(user_id, "Por favor, seleccione un número válido de las opciones mostradas.")
            return {"status": "processed", "action": "invalid_choice"}
    
    def _extract_quantity_and_clean_text(self, text: str) -> tuple[int, str]:
        """提取数量并清理文本，返回(数量, 清理后的文本)"""
        import re
        
        # 西班牙语数字词汇映射
        spanish_numbers = {
            "un": 1, "una": 1, "uno": 1,
            "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
            "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
            "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
            "veinte": 20, "veintiuno": 21, "treinta": 30
        }
        
        text_lower = text.lower().strip()
        quantity = 1  # 默认数量
        
        # 1. 首先查找阿拉伯数字
        digit_match = re.search(r'\b(\d+)\b', text_lower)
        if digit_match:
            quantity = int(digit_match.group(1))
            # 移除数字
            text_lower = re.sub(r'\b\d+\b', '', text_lower).strip()
        else:
            # 2. 查找西班牙语数字词汇
            for word, num in spanish_numbers.items():
                # 使用单词边界确保完整匹配
                pattern = r'\b' + re.escape(word) + r'\b'
                if re.search(pattern, text_lower):
                    quantity = num
                    # 移除找到的数字词汇
                    text_lower = re.sub(pattern, '', text_lower).strip()
                    break
        
        # 3. 清理多余的空格
        cleaned_text = ' '.join(text_lower.split())
        
        return quantity, cleaned_text
    
    def _parse_choice_number(self, text: str) -> Optional[int]:
        """解析用户选择的数字"""
        import re
        
        # 查找数字
        numbers = re.findall(r'\d+', text)
        if numbers:
            return int(numbers[0])
        
        # 查找文字数字
        word_to_num = {
            "uno": 1, "una": 1, "primero": 1, "primera": 1,
            "dos": 2, "segundo": 2, "segunda": 2,
            "tres": 3, "tercero": 3, "tercera": 3,
            "cuatro": 4, "cuarto": 4, "cuarta": 4,
            "cinco": 5, "quinto": 5, "quinta": 5
        }
        
        text_lower = text.lower()
        for word, num in word_to_num.items():
            if word in text_lower:
                return num
        
        return None
    
    async def _handle_confirming_state(self, user_id: str, text_content: str, session: Any) -> Dict[str, Any]:
        """处理确认状态 - 询问是否还要其他"""
        text_lower = text_content.lower().strip()
        
        logger.info(f"Handling confirming state for user {user_id}: '{text_content}' (state: {session.state})")
        
        # 检查是否要添加更多项目
        add_more_keywords = ["sí", "si", "yes", "también", "más", "quiero", "dame", "añade", "agrega"]
        no_more_keywords = ["no", "nada", "está bien", "es todo", "ya", "terminar", "finalizar", "listo"]
        
        # 明确的"不要更多"回复
        if any(keyword in text_lower for keyword in no_more_keywords):
            logger.info(f"User {user_id} indicated no more items, proceeding to name collection")
            # 用户不要更多，进入询问姓名阶段
            session.state = ConversationState.ASKING_NAME
            await self._send_response(user_id, "Para finalizar, ¿a nombre de quién registramos la orden?")
            return {"status": "processed", "action": "asking_name"}
        
        # 明确的"要更多"回复
        elif any(keyword in text_lower for keyword in add_more_keywords) and not any(keyword in text_lower for keyword in no_more_keywords):
            logger.info(f"User {user_id} wants to add more items")
            # 用户想要添加更多
            if self._contains_order_keywords(text_content):
                # 直接包含了新的订单项
                session.state = ConversationState.ORDERING
                return await self._handle_ordering_state(user_id, text_content, session)
            else:
                # 只是说要更多，但没说具体要什么
                await self._send_response(user_id, "¿Qué más te gustaría ordenar?")
                session.state = ConversationState.ORDERING
                return {"status": "processed", "action": "asking_for_more"}
        
        else:
            # 检查是否直接是新的订单项
            if self._contains_order_keywords(text_content):
                logger.info(f"User {user_id} provided new order items directly")
                session.state = ConversationState.ORDERING
                return await self._handle_ordering_state(user_id, text_content, session)
            else:
                # 不明确的回复，再次询问
                logger.info(f"Ambiguous response from user {user_id}, asking for clarification")
                await self._send_response(user_id, "¿Algo más que quieras ordenar? Responde 'sí' para agregar más o 'no' para finalizar.")
                return {"status": "processed", "action": "clarifying_if_more"}
    
    async def _handle_name_state(self, user_id: str, text_content: str, session: Any) -> Dict[str, Any]:
        """处理询问姓名状态 - 步骤5到8"""
        # 保存客户姓名
        customer_name = text_content.strip()
        session.customer_name = customer_name
        
        # 获取客户电话号码（就是WhatsApp号码）
        customer_phone = user_id  # WhatsApp号码
        
        # 步骤6: 创建订单并注册到POS
        matched_items = session.matched_items if hasattr(session, 'matched_items') else []
        if not matched_items:
            await self._send_response(user_id, "Hubo un error. Por favor, realice su pedido nuevamente.")
            session.state = ConversationState.ORDERING
            return {"status": "error", "error": "no_matched_items"}
        
        try:
            # 调用order_processor处理订单
            result = await order_processor.place_order(customer_name, customer_phone, matched_items, user_id)
            
            if result.get("success"):
                # 步骤7: 发送确认摘要
                order_summary = self._build_final_summary(result, customer_name)
                await self._send_response(user_id, order_summary)
                
                # 步骤8: 发送感谢消息
                await self._send_response(user_id, "¡Muchas gracias por tu pedido! 😊")
                
                session.state = ConversationState.COMPLETED
                session.last_order = result
                
                return {"status": "processed", "action": "order_completed", "order": result}
            else:
                await self._send_response(user_id, "Hubo un error procesando su pedido. Por favor, inténtelo de nuevo.")
                session.state = ConversationState.ORDERING
                return {"status": "error", "error": result.get("error")}
                
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            await self._send_response(user_id, "Hubo un error procesando su pedido. Por favor, inténtelo de nuevo.")
            session.state = ConversationState.ORDERING
            return {"status": "error", "error": str(e)}
    
    def _build_final_summary(self, order_result: Dict[str, Any], customer_name: str) -> str:
        """构建最终订单摘要 - 步骤7，确保使用正确的税率计算"""
        items = order_result.get("line_items", [])
        total_with_tax = order_result.get("total_with_tax", 0)
        prep_time = order_result.get("preparation_time", 10)
        
        # 从配置获取正确的税率
        tax_rate = settings.tax_rate  # 这应该是0.115 (11.5%)
        
        summary_lines = [f"Gracias, {customer_name}. Resumen:"]
        
        # 计算实际的含税总价来验证
        calculated_subtotal = 0
        for item in items:
            quantity = item.get("quantity", 1)
            name = item.get("item_name", "")
            price = item.get("price", 0)
            item_total = quantity * price
            calculated_subtotal += item_total
            
            line = f"• {quantity} {name}"
            if price > 0:
                line += f" (+${price:.2f} c/u)"
            else:
                line += " (sin costo)"
            summary_lines.append(line)
        
        # 使用order_result中的total_with_tax，但添加日志验证
        calculated_tax = calculated_subtotal * tax_rate
        calculated_total_with_tax = calculated_subtotal + calculated_tax
        
        # 日志记录用于调试
        logger.info(f"Tax calculation verification for user {customer_name}:")
        logger.info(f"  Subtotal: ${calculated_subtotal:.2f}")
        logger.info(f"  Tax rate: {tax_rate * 100:.1f}%")
        logger.info(f"  Calculated tax: ${calculated_tax:.2f}")
        logger.info(f"  Calculated total: ${calculated_total_with_tax:.2f}")
        logger.info(f"  POS reported total: ${total_with_tax:.2f}")
        
        # 使用POS系统返回的实际总价，因为它包含了所有业务逻辑
        final_total = total_with_tax
        
        summary_lines.append(f"**Total (con IVU) ${final_total:.2f}**.")
        summary_lines.append(f"Tu orden estará lista en **{prep_time} min**.")
        
        return "\n".join(summary_lines)
    
    async def _send_response(self, user_id: str, message: str) -> bool:
        """发送响应消息"""
        return await self.adapter.send_message(user_id, message, user_id)

# 全局WhatsApp路由器实例
whatsapp_router = WhatsAppRouter()
