import time
import asyncio
from typing import Dict, Any, Optional, List
import httpx
import json

from ..config import get_settings
from ..logger import get_logger, business_logger

settings = get_settings()
logger = get_logger(__name__)

class Dialog360WhatsAppAdapter:
    """360Dialog WhatsApp Business API适配器"""
    
    def __init__(self):
        self.api_token = settings.dialog360_token
        self.phone_number = settings.dialog360_phone_number
        self.base_url = "https://waba.360dialog.io/v1"
        
        if not self.api_token:
            logger.warning("360Dialog credentials not configured")
    
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
        if not self.api_token:
            logger.error("360Dialog API token not configured")
            return False
        
        start_time = time.time()
        
        try:
            # 格式化号码
            formatted_to = self._format_phone_number(to_number)
            
            # 构建消息负载
            payload = {
                "messaging_product": "whatsapp",
                "to": formatted_to,
                "type": "text",
                "text": {
                    "body": message
                }
            }
            
            logger.info(f"Sending WhatsApp message to {formatted_to} via 360Dialog")
            
            # 发送请求
            success = await self._send_api_request("/messages", payload, user_id)
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 记录发送日志
            business_logger.log_outbound_message(
                user_id=user_id,
                provider="dialog360",
                message_type="text",
                success=success,
                duration_ms=duration_ms
            )
            
            return success
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            business_logger.log_error(
                user_id=user_id,
                stage="outbound",
                error_code="DIALOG360_SEND_ERROR",
                error_msg=str(e),
                exception=e
            )
            logger.error(f"Error sending message via 360Dialog: {e}")
            return False
    
    async def send_template_message(self, to_number: str, template_name: str, language_code: str, 
                                  parameters: List[Dict[str, Any]], user_id: str) -> bool:
        """
        发送WhatsApp模板消息
        
        Args:
            to_number: 目标号码
            template_name: 模板名称
            language_code: 语言代码 (如: 'es', 'en')
            parameters: 模板参数
            user_id: 用户ID
            
        Returns:
            发送是否成功
        """
        if not self.api_token:
            logger.error("360Dialog API token not configured")
            return False
        
        start_time = time.time()
        
        try:
            formatted_to = self._format_phone_number(to_number)
            
            # 构建模板消息负载
            payload = {
                "messaging_product": "whatsapp",
                "to": formatted_to,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {
                        "code": language_code
                    },
                    "components": [
                        {
                            "type": "body",
                            "parameters": parameters
                        }
                    ]
                }
            }
            
            logger.info(f"Sending WhatsApp template '{template_name}' to {formatted_to}")
            
            success = await self._send_api_request("/messages", payload, user_id)
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            business_logger.log_outbound_message(
                user_id=user_id,
                provider="dialog360",
                message_type="template",
                success=success,
                duration_ms=duration_ms
            )
            
            return success
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            business_logger.log_error(
                user_id=user_id,
                stage="outbound",
                error_code="DIALOG360_TEMPLATE_ERROR",
                error_msg=str(e),
                exception=e
            )
            logger.error(f"Error sending template via 360Dialog: {e}")
            return False
    
    async def send_interactive_message(self, to_number: str, message_data: Dict[str, Any], user_id: str) -> bool:
        """
        发送交互式消息（按钮、列表等）
        
        Args:
            to_number: 目标号码
            message_data: 交互式消息数据
            user_id: 用户ID
            
        Returns:
            发送是否成功
        """
        if not self.api_token:
            logger.error("360Dialog API token not configured")
            return False
        
        start_time = time.time()
        
        try:
            formatted_to = self._format_phone_number(to_number)
            
            payload = {
                "messaging_product": "whatsapp",
                "to": formatted_to,
                "type": "interactive",
                "interactive": message_data
            }
            
            logger.info(f"Sending interactive message to {formatted_to}")
            
            success = await self._send_api_request("/messages", payload, user_id)
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            business_logger.log_outbound_message(
                user_id=user_id,
                provider="dialog360",
                message_type="interactive",
                success=success,
                duration_ms=duration_ms
            )
            
            return success
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            business_logger.log_error(
                user_id=user_id,
                stage="outbound",
                error_code="DIALOG360_INTERACTIVE_ERROR",
                error_msg=str(e),
                exception=e
            )
            logger.error(f"Error sending interactive message: {e}")
            return False
    
    async def download_media(self, media_id: str, user_id: str) -> Optional[bytes]:
        """
        下载媒体文件
        
        Args:
            media_id: 媒体文件ID
            user_id: 用户ID
            
        Returns:
            媒体文件字节数据
        """
        if not self.api_token:
            logger.error("360Dialog API token not configured")
            return None
        
        start_time = time.time()
        
        try:
            logger.info(f"Downloading media {media_id}")
            
            # 首先获取媒体URL
            headers = {"D360-API-KEY": self.api_token}
            
            async with httpx.AsyncClient() as client:
                # 获取媒体信息
                response = await client.get(
                    f"{self.base_url}/{media_id}",
                    headers=headers,
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to get media info: {response.status_code}")
                    return None
                
                media_info = response.json()
                media_url = media_info.get("url")
                
                if not media_url:
                    logger.error("No media URL in response")
                    return None
                
                # 下载媒体文件
                media_response = await client.get(
                    media_url,
                    headers=headers,
                    timeout=60.0
                )
                
                if media_response.status_code == 200:
                    duration_ms = int((time.time() - start_time) * 1000)
                    logger.info(f"Media downloaded successfully ({len(media_response.content)} bytes)")
                    return media_response.content
                else:
                    logger.error(f"Failed to download media: {media_response.status_code}")
                    return None
                
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            business_logger.log_error(
                user_id=user_id,
                stage="inbound",
                error_code="DIALOG360_MEDIA_ERROR",
                error_msg=str(e),
                exception=e
            )
            logger.error(f"Error downloading media: {e}")
            return None
    
    async def _send_api_request(self, endpoint: str, payload: Dict[str, Any], user_id: str) -> bool:
        """发送API请求"""
        try:
            headers = {
                "D360-API-KEY": self.api_token,
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}{endpoint}",
                    headers=headers,
                    json=payload,
                    timeout=30.0
                )
            
            if response.status_code in [200, 201]:
                logger.info(f"360Dialog API request successful: {response.status_code}")
                return True
            else:
                error_msg = f"360Dialog API error: {response.status_code} - {response.text}"
                business_logger.log_error(
                    user_id=user_id,
                    stage="outbound",
                    error_code="DIALOG360_API_ERROR",
                    error_msg=error_msg
                )
                logger.error(error_msg)
                return False
                
        except Exception as e:
            business_logger.log_error(
                user_id=user_id,
                stage="outbound",
                error_code="DIALOG360_REQUEST_ERROR",
                error_msg=str(e),
                exception=e
            )
            logger.error(f"360Dialog API request failed: {e}")
            return False
    
    def _format_phone_number(self, number: str) -> str:
        """格式化电话号码"""
        if not number:
            return ""
        
        # 移除所有非数字字符
        clean_number = ''.join(filter(str.isdigit, number))
        
        # 确保号码格式正确（不需要+号）
        if clean_number.startswith('1') and len(clean_number) == 11:
            return clean_number
        elif len(clean_number) == 10:
            return '1' + clean_number
        else:
            return clean_number
    
    def parse_webhook_payload(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        解析360Dialog webhook负载
        
        Args:
            payload: webhook负载
            
        Returns:
            解析后的消息数据
        """
        try:
            # 360Dialog webhook格式
            entry = payload.get("entry", [])
            if not entry:
                return None
            
            changes = entry[0].get("changes", [])
            if not changes:
                return None
            
            value = changes[0].get("value", {})
            messages = value.get("messages", [])
            
            if not messages:
                return None
            
            message = messages[0]
            
            message_data = {
                "message_id": message.get("id"),
                "from_number": message.get("from"),
                "timestamp": message.get("timestamp"),
                "message_type": message.get("type", "text"),
                "body": "",
                "media_urls": []
            }
            
            # 处理不同类型的消息
            if message_data["message_type"] == "text":
                message_data["body"] = message.get("text", {}).get("body", "")
            
            elif message_data["message_type"] == "audio":
                audio_data = message.get("audio", {})
                message_data["media_urls"].append({
                    "id": audio_data.get("id"),
                    "mime_type": audio_data.get("mime_type")
                })
                message_data["message_type"] = "voice"
            
            elif message_data["message_type"] == "image":
                image_data = message.get("image", {})
                message_data["media_urls"].append({
                    "id": image_data.get("id"),
                    "mime_type": image_data.get("mime_type"),
                    "caption": image_data.get("caption", "")
                })
                message_data["body"] = image_data.get("caption", "")
            
            elif message_data["message_type"] == "document":
                doc_data = message.get("document", {})
                message_data["media_urls"].append({
                    "id": doc_data.get("id"),
                    "mime_type": doc_data.get("mime_type"),
                    "filename": doc_data.get("filename", "")
                })
                message_data["message_type"] = "document"
            
            elif message_data["message_type"] == "interactive":
                interactive_data = message.get("interactive", {})
                if interactive_data.get("type") == "button_reply":
                    message_data["body"] = interactive_data.get("button_reply", {}).get("title", "")
                elif interactive_data.get("type") == "list_reply":
                    message_data["body"] = interactive_data.get("list_reply", {}).get("title", "")
            
            return message_data
            
        except Exception as e:
            logger.error(f"Error parsing 360Dialog webhook payload: {e}")
            return None
    
    async def send_order_confirmation(self, to_number: str, order_details: Dict[str, Any], user_id: str) -> bool:
        """发送订单确认消息"""
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

# 全局360Dialog适配器实例
dialog360_adapter = Dialog360WhatsAppAdapter()
