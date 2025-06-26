import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import json

from app.whatsapp.router import whatsapp_router
from app.config import get_settings

settings = get_settings()

class TestWhatsAppIntegration:
    """WhatsApp订餐机器人集成测试"""
    
    @pytest.fixture
    def mock_webhook_payload(self):
        """模拟WhatsApp webhook负载"""
        return {
            "MessageSid": "SM1234567890",
            "From": "whatsapp:+1234567890",
            "To": f"whatsapp:{settings.twilio_whatsapp_number}",
            "Body": "Quiero 2 Pollo Teriyaki y 1 Pepper Steak",
            "NumMedia": "0"
        }
    
    @pytest.fixture
    def mock_voice_webhook_payload(self):
        """模拟语音消息webhook负载"""
        return {
            "MessageSid": "SM1234567891",
            "From": "whatsapp:+1234567890",
            "To": f"whatsapp:{settings.twilio_whatsapp_number}",
            "Body": "",
            "NumMedia": "1",
            "MediaUrl0": "https://api.twilio.com/voice.ogg",
            "MediaContentType0": "audio/ogg"
        }
    
    @pytest.fixture
    def mock_order_response(self):
        """模拟订单处理响应"""
        return {
            "success": True,
            "receipt": {
                "receipt_number": "R001",
                "total_money": 25.50,
                "created_at": "2024-01-01T12:00:00Z"
            },
            "matched_items": [
                {
                    "item_name": "Pollo Teriyaki",
                    "quantity": 2,
                    "price": 11.99
                },
                {
                    "item_name": "Pepper Steak", 
                    "quantity": 1,
                    "price": 11.99
                }
            ],
            "total_info": {
                "subtotal": 35.97,
                "tax_amount": 3.96,
                "total_with_tax": 39.93
            },
            "customer_id": "CUST001"
        }
    
    @pytest.mark.asyncio
    async def test_complete_order_flow(self, mock_webhook_payload, mock_order_response):
        """测试完整的订单流程"""
        with patch('app.llm.claude_client.claude_client.extract_order') as mock_claude, \
             patch('app.pos.order_processor.order_processor.process_order') as mock_processor, \
             patch('app.whatsapp.twilio_adapter.twilio_adapter.send_message') as mock_send, \
             patch('app.llm.claude_client.claude_client.generate_order_confirmation') as mock_confirm:
            
            # 模拟Claude提取订单
            mock_claude.return_value = {
                "intent": "order",
                "order_lines": [
                    {"alias": "Pollo Teriyaki", "quantity": 2, "modifiers": []},
                    {"alias": "Pepper Steak", "quantity": 1, "modifiers": []}
                ],
                "need_clarify": False,
                "response_message": "Perfecto, procesando su pedido..."
            }
            
            # 模拟订单处理
            mock_processor.return_value = mock_order_response
            
            # 模拟确认消息生成
            mock_confirm.return_value = "Gracias, Juan. Su pedido R001 por $39.93 estará listo en 15 minutos."
            
            # 模拟消息发送
            mock_send.return_value = True
            
            # 清理会话状态
            user_id = "+1234567890"
            if user_id in whatsapp_router.user_sessions:
                del whatsapp_router.user_sessions[user_id]
            
            # 测试完整流程
            # 1. 问候消息
            result1 = await whatsapp_router.handle_incoming_message({
                **mock_webhook_payload,
                "Body": "Hola"
            })
            
            assert result1["status"] == "processed"
            assert mock_send.call_count >= 1
            
            # 2. 订餐消息
            result2 = await whatsapp_router.handle_incoming_message(mock_webhook_payload)
            
            assert result2["status"] == "processed"
            assert result2["action"] == "order_confirmed"
            
            # 3. 提供姓名
            result3 = await whatsapp_router.handle_incoming_message({
                **mock_webhook_payload,
                "Body": "Juan"
            })
            
            assert result3["status"] == "processed"
            assert result3["action"] == "order_completed"
            assert "order" in result3
            
            # 验证调用次数
            assert mock_claude.call_count >= 1
            assert mock_processor.call_count == 1
            assert mock_confirm.call_count == 1
    
    @pytest.mark.asyncio
    async def test_voice_message_processing(self, mock_voice_webhook_payload):
        """测试语音消息处理"""
        with patch('app.speech.deepgram_client.deepgram_client.transcribe_audio_url') as mock_transcribe, \
             patch('app.llm.claude_client.claude_client.extract_order') as mock_claude, \
             patch('app.whatsapp.twilio_adapter.twilio_adapter.send_message') as mock_send:
            
            # 模拟语音转录
            mock_transcribe.return_value = "Quiero dos pollo teriyaki"
            
            # 模拟Claude提取
            mock_claude.return_value = {
                "intent": "order",
                "order_lines": [{"alias": "pollo teriyaki", "quantity": 2}],
                "need_clarify": False,
                "response_message": "Entendido, 2 Pollo Teriyaki"
            }
            
            # 模拟消息发送
            mock_send.return_value = True
            
            result = await whatsapp_router.handle_incoming_message(mock_voice_webhook_payload)
            
            assert result["status"] == "processed"
            assert mock_transcribe.call_count == 1
            assert mock_claude.call_count == 1
    
    @pytest.mark.asyncio
    async def test_clarification_flow(self, mock_webhook_payload):
        """测试澄清流程"""
        with patch('app.llm.claude_client.claude_client.extract_order') as mock_claude, \
             patch('app.whatsapp.twilio_adapter.twilio_adapter.send_message') as mock_send:
            
            # 第一次调用 - 需要澄清
            mock_claude.return_value = {
                "intent": "order",
                "order_lines": [],
                "need_clarify": True,
                "clarify_message": "¿Te refieres a Pollo Teriyaki o Pollo Naranja?",
                "response_message": "¿Podrías aclarar tu pedido?"
            }
            
            mock_send.return_value = True
            
            # 清理会话
            user_id = "+1234567890"
            if user_id in whatsapp_router.user_sessions:
                del whatsapp_router.user_sessions[user_id]
            
            # 发送模糊的消息
            result1 = await whatsapp_router.handle_incoming_message({
                **mock_webhook_payload,
                "Body": "Quiero pollo"
            })
            
            assert result1["status"] == "processed"
            assert result1["action"] == "clarification_needed"
            
            # 第二次调用 - 澄清回复
            mock_claude.return_value = {
                "intent": "order",
                "order_lines": [{"alias": "Pollo Teriyaki", "quantity": 1}],
                "need_clarify": False,
                "response_message": "Perfecto, 1 Pollo Teriyaki"
            }
            
            result2 = await whatsapp_router.handle_incoming_message({
                **mock_webhook_payload,
                "Body": "Teriyaki"
            })
            
            assert result2["status"] == "processed"
            assert "order" in result2 or result2["action"] == "order_confirmed"
    
    @pytest.mark.asyncio
    async def test_order_calculation(self, mock_order_response):
        """测试订单金额计算"""
        total_info = mock_order_response["total_info"]
        
        # 验证税务计算
        expected_tax = round(total_info["subtotal"] * settings.tax_rate, 2)
        assert abs(total_info["tax_amount"] - expected_tax) < 0.01
        
        # 验证总价计算
        expected_total = total_info["subtotal"] + total_info["tax_amount"]
        assert abs(total_info["total_with_tax"] - expected_total) < 0.01
    
    @pytest.mark.asyncio
    async def test_error_handling(self, mock_webhook_payload):
        """测试错误处理"""
        with patch('app.llm.claude_client.claude_client.extract_order') as mock_claude, \
             patch('app.whatsapp.twilio_adapter.twilio_adapter.send_message') as mock_send:
            
            # 模拟Claude API错误
            mock_claude.side_effect = Exception("Claude API Error")
            mock_send.return_value = True
            
            result = await whatsapp_router.handle_incoming_message(mock_webhook_payload)
            
            # 应该处理错误并发送错误消息给用户
            assert result["status"] == "error"
            assert mock_send.called  # 应该向用户发送错误消息
    
    @pytest.mark.asyncio
    async def test_session_management(self, mock_webhook_payload):
        """测试会话管理"""
        user_id = "+1234567890"
        
        # 清理现有会话
        if user_id in whatsapp_router.user_sessions:
            del whatsapp_router.user_sessions[user_id]
        
        with patch('app.whatsapp.twilio_adapter.twilio_adapter.send_message') as mock_send:
            mock_send.return_value = True
            
            # 第一条消息应该创建会话
            await whatsapp_router.handle_incoming_message(mock_webhook_payload)
            
            assert user_id in whatsapp_router.user_sessions
            session = whatsapp_router.user_sessions[user_id]
            assert "state" in session
            assert "created_at" in session
            assert "last_activity" in session
    
    @pytest.mark.asyncio
    async def test_menu_matching(self):
        """测试菜单匹配功能"""
        from app.utils.alias_matcher import alias_matcher
        
        # 测试精确匹配
        matches = alias_matcher.find_matches("Pollo Teriyaki", "test_user", limit=5)
        assert len(matches) > 0
        assert matches[0]["score"] >= 80
        
        # 测试模糊匹配
        matches = alias_matcher.find_matches("pollo teryaki", "test_user", limit=5)  # 拼写错误
        assert len(matches) > 0
        
        # 测试别名匹配
        matches = alias_matcher.find_matches("Teriyaki Chicken", "test_user", limit=5)
        assert len(matches) > 0
    
    @pytest.mark.asyncio
    async def test_loyverse_integration(self):
        """测试Loyverse集成"""
        from app.pos.loyverse_auth import loyverse_auth
        from app.pos.loyverse_client import loyverse_client
        
        # 测试认证
        token_info = loyverse_auth.get_token_info()
        assert "has_access_token" in token_info
        
        # 如果配置了真实的凭据，测试连接
        if settings.loyverse_client_id and settings.loyverse_client_secret:
            connection_ok = await loyverse_client.test_connection()
            # 注意：这在没有真实凭据时可能会失败
            print(f"Loyverse connection test: {connection_ok}")

    def test_configuration_validation(self):
        """测试配置验证"""
        # 验证必要的配置存在
        assert settings.anthropic_api_key is not None
        assert settings.deepgram_api_key is not None
        assert settings.loyverse_client_id is not None
        assert settings.loyverse_client_secret is not None
        
        # 验证税率配置
        assert 0 <= settings.tax_rate <= 1
        
        # 验证准备时间配置
        assert settings.preparation_time_basic > 0
        assert settings.preparation_time_complex >= settings.preparation_time_basic

if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])
