import time
import asyncio
from typing import Dict, Any, Optional
from twilio.rest import Client
from twilio.base.exceptions import TwilioException
import httpx

from ..config import get_settings
from ..logger import get_logger, business_logger

settings = get_settings()
logger = get_logger(__name__)

class TwilioWhatsAppAdapter:
    """Twilio WhatsApp消息适配器"""
    
    def __init__(self):
        if settings.twilio_account_sid and settings.twilio_auth_token:
            self.client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            self.whatsapp_number = settings.twilio_whatsapp_number
        else:
            self.client = None
            logger.warning("Twilio credentials not configured")
    
    async def send_message(self, to_number: str, message: str, user_id: str) -> bool:
        """
        发送WhatsApp文本消息
        
        Args:
            to_number: 目标号码
            message: 消息内容
            user_id: 用户ID
            
        Returns:
            发送是否成功
        """
        if not self.client:
            logger.error("Twilio client not initialized")
            return False
        
        start_time = time.time()
        
        try:
            # 格式化号码
            formatted_to = self._format_whatsapp_number(to_number)
            formatted_from = self._format_whatsapp_number(self.whatsapp_number)
            
            logger.info(f"Sending WhatsApp message to {formatted_to}")
            
            # 使用异步执行Twilio API调用
            message_obj = await asyncio.to_thread(
                self.client.messages.create,
                body=message,
                from_=formatted_from,
                to=formatted_to
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 记录发送日志
            business_logger.log_outbound_message(
                user_id=user_id,
                provider="twilio",
                message_type="text",
                success=True,
                duration_ms=duration_ms
            )
            
            logger.info(f"Message sent successfully. SID: {message_obj.sid}")
            return True
            
        except TwilioException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            business_logger.log_outbound_message(
                user_id=user_id,
                provider="twilio",
                message_type="text",
                success=False,
                duration_ms=duration_ms
            )
            business_logger.log_error(
                user_id=user_id,
                stage="outbound",
                error_code="TWILIO_SEND_FAILED",
                error_msg=str(e),
                exception=e
            )
            logger.error(f"Twilio error sending message: {e}")
            return False
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            business_logger.log_error(
                user_id=user_id,
                stage="outbound",
                error_code="MESSAGE_SEND_ERROR",
                error_msg=str(e),
                exception=e
            )
            logger.error(f"Unexpected error sending message: {e}")
            return False
    
    async def send_template_message(self, to_number: str, template_sid: str, parameters: Dict[str, str], user_id: str) -> bool:
        """
        发送WhatsApp模板消息
        
        Args:
            to_number: 目标号码
            template_sid: 模板SID
            parameters: 模板参数
            user_id: 用户ID
            
        Returns:
            发送是否成功
        """
        if not self.client:
            logger.error("Twilio client not initialized")
            return False
        
        start_time = time.time()
        
        try:
            formatted_to = self._format_whatsapp_number(to_number)
            formatted_from = self._format_whatsapp_number(self.whatsapp_number)
            
            logger.info(f"Sending WhatsApp template message to {formatted_to}")
            
            message_obj = await asyncio.to_thread(
                self.client.messages.create,
                content_sid=template_sid,
                content_variables=parameters,
                from_=formatted_from,
                to=formatted_to
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            business_logger.log_outbound_message(
                user_id=user_id,
                provider="twilio",
                message_type="template",
                success=True,
                duration_ms=duration_ms
            )
            
            logger.info(f"Template message sent successfully. SID: {message_obj.sid}")
            return True
            
        except TwilioException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            business_logger.log_error(
                user_id=user_id,
                stage="outbound",
                error_code="TWILIO_TEMPLATE_FAILED",
                error_msg=str(e),
                exception=e
            )
            logger.error(f"Twilio error sending template: {e}")
            return False
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            business_logger.log_error(
                user_id=user_id,
                stage="outbound",
                error_code="TEMPLATE_SEND_ERROR",
                error_msg=str(e),
                exception=e
            )
            logger.error(f"Unexpected error sending template: {e}")
            return False
    
    async def download_media(self, media_url: str, user_id: str) -> Optional[bytes]:
        """
        下载媒体文件
        
        Args:
            media_url: 媒体文件URL
            user_id: 用户ID
            
        Returns:
            媒体文件字节数据，如果下载失败返回None
        """
        start_time = time.time()
        
        try:
            logger.info(f"Downloading media from {media_url}")
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    media_url,
                    timeout=30.0,
                    follow_redirects=True
                )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                logger.info(f"Media downloaded successfully ({len(response.content)} bytes)")
                return response.content
            else:
                business_logger.log_error(
                    user_id=user_id,
                    stage="inbound",
                    error_code="MEDIA_DOWNLOAD_FAILED",
                    error_msg=f"HTTP {response.status_code}"
                )
                logger.error(f"Failed to download media: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            business_logger.log_error(
                user_id=user_id,
                stage="inbound",
                error_code="MEDIA_DOWNLOAD_ERROR",
                error_msg=str(e),
                exception=e
            )
            logger.error(f"Error downloading media: {e}")
            return None
    
    def _format_whatsapp_number(self, number: str) -> str:
        """格式化WhatsApp号码"""
        if not number:
            return ""
        
        # 移除所有非数字字符
        clean_number = ''.join(filter(str.isdigit, number))
        
        # 如果是Twilio sandbox号码，直接返回
        if "whatsapp:+14155238886" in number:
            return number
        
        # 确保号码以whatsapp:+开头
        if not clean_number.startswith('+'):
            if clean_number.startswith('1'):
                clean_number = '+' + clean_number
            else:
                clean_number = '+1' + clean_number
        
        return f"whatsapp:{clean_number}"
    
    def parse_webhook_payload(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        解析Twilio webhook负载
        
        Args:
            payload: webhook负载
            
        Returns:
            解析后的消息数据
        """
        try:
            message_data = {
                "message_sid": payload.get("MessageSid"),
                "from_number": payload.get("From", "").replace("whatsapp:", ""),
                "to_number": payload.get("To", "").replace("whatsapp:", ""),
                "body": payload.get("Body", ""),
                "media_count": int(payload.get("NumMedia", 0)),
                "media_urls": [],
                "message_type": "text"
            }
            
            # 处理媒体附件
            if message_data["media_count"] > 0:
                for i in range(message_data["media_count"]):
                    media_url = payload.get(f"MediaUrl{i}")
                    media_type = payload.get(f"MediaContentType{i}")
                    
                    if media_url:
                        message_data["media_urls"].append({
                            "url": media_url,
                            "content_type": media_type
                        })
                
                # 确定消息类型
                if any("audio" in media.get("content_type", "") for media in message_data["media_urls"]):
                    message_data["message_type"] = "voice"
                elif any("image" in media.get("content_type", "") for media in message_data["media_urls"]):
                    message_data["message_type"] = "image"
                else:
                    message_data["message_type"] = "media"
            
            return message_data
            
        except Exception as e:
            logger.error(f"Error parsing Twilio webhook payload: {e}")
            return None
    
    async def send_order_confirmation(self, to_number: str, order_details: Dict[str, Any], user_id: str) -> bool:
        """
        发送订单确认消息
        
        Args:
            to_number: 目标号码
            order_details: 订单详情
            user_id: 用户ID
            
        Returns:
            发送是否成功
        """
        try:
            # 构建订单确认消息
            message = self._build_order_confirmation_message(order_details)
            
            return await self.send_message(to_number, message, user_id)
            
        except Exception as e:
            logger.error(f"Error sending order confirmation: {e}")
            return False
    
    def _build_order_confirmation_message(self, order_details: Dict[str, Any]) -> str:
        """构建订单确认消息"""
        try:
            receipt = order_details.get("receipt", {})
            total_info = order_details.get("total_info", {})
            
            message_parts = [
                f"✅ *Pedido Confirmado*",
                f"📋 Número: {receipt.get('receipt_number', 'N/A')}",
                "",
                "📝 *Detalles del pedido:*"
            ]
            
            # 添加订单项目
            for item in order_details.get("matched_items", []):
                item_line = f"• {item.get('quantity', 1)}x {item.get('item_name', 'Item')} - ${item.get('price', 0):.2f}"
                message_parts.append(item_line)
            
            message_parts.extend([
                "",
                f"💰 *Total: ${total_info.get('total_with_tax', 0):.2f}*",
                f"   (Incluye impuesto: ${total_info.get('tax_amount', 0):.2f})",
                "",
                f"⏰ Su pedido estará listo en {settings.preparation_time_basic}-{settings.preparation_time_complex} minutos.",
                "",
                f"¡Gracias por elegir {settings.restaurant_name}! 🍽️"
            ])
            
            return "\n".join(message_parts)
            
        except Exception as e:
            logger.error(f"Error building confirmation message: {e}")
            return "Pedido confirmado. Gracias por su orden."

# 全局Twilio适配器实例
twilio_adapter = TwilioWhatsAppAdapter()
